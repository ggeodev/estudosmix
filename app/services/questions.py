from .. import db
from ..errors import ApiError
from ..util import jloads, now_iso
from . import taxonomy

LAST_CORRECT = "(SELECT a.is_correct FROM answers a WHERE a.question_id = q.id ORDER BY a.id DESC LIMIT 1)"
LAST_CONF = "(SELECT a.confidence FROM answers a WHERE a.question_id = q.id ORDER BY a.id DESC LIMIT 1)"
ATTEMPTS = "(SELECT COUNT(*) FROM answers a WHERE a.question_id = q.id)"

STATUSES = {"unseen", "answered", "correct", "wrong", "fragile", "flagged"}


def build_where(f):
    """Converte filtros (strings vindas da URL ou JSON) em cláusula WHERE."""
    where, params = [], []

    def val(key):
        v = f.get(key)
        return None if v in (None, "") else v

    if val("subject_id"):
        where.append("q.subject_id = ?")
        params.append(int(val("subject_id")))
    if val("exam_id"):
        where.append("q.subject_id IN (SELECT id FROM subjects WHERE exam_id = ?)")
        params.append(int(val("exam_id")))
    if val("topic_id"):
        ids = taxonomy.descendants(int(val("topic_id")))
        where.append(f"q.id IN (SELECT question_id FROM question_topics WHERE topic_id IN ({db.placeholders(len(ids))}))")
        params.extend(ids)
    for col in ("bank", "exam_name", "difficulty"):
        if val(col):
            where.append(f"q.{col} = ?")
            params.append(val(col))
    if val("year"):
        where.append("q.year = ?")
        params.append(int(val("year")))
    if val("import_id"):
        where.append("q.import_id = ?")
        params.append(int(val("import_id")))
    if val("q"):
        like = f"%{val('q')}%"
        where.append("(q.statement LIKE ? OR q.support_text LIKE ? OR q.external_id LIKE ?)")
        params.extend([like, like, like])
    status = val("status")
    if status:
        if status not in STATUSES:
            raise ApiError("Status de filtro inválido.")
        if status == "unseen":
            where.append(f"{ATTEMPTS} = 0")
        elif status == "answered":
            where.append(f"{ATTEMPTS} > 0")
        elif status == "correct":
            where.append(f"{LAST_CORRECT} = 1")
        elif status == "wrong":
            where.append(f"{LAST_CORRECT} = 0")
        elif status == "fragile":
            where.append(f"{LAST_CORRECT} = 1 AND {LAST_CONF} <> 'certeza'")
        elif status == "flagged":
            where.append("q.id IN (SELECT question_id FROM question_flags)")
    return (" WHERE " + " AND ".join(where)) if where else "", params


def _topics_for(question_ids):
    if not question_ids:
        return {}
    rows = db.query(
        f"""SELECT qt.question_id, t.id, t.name FROM question_topics qt
            JOIN topics t ON t.id = qt.topic_id
            WHERE qt.question_id IN ({db.placeholders(len(question_ids))}) ORDER BY t.name""",
        question_ids,
    )
    out = {}
    for r in rows:
        out.setdefault(r["question_id"], []).append({"id": r["id"], "name": r["name"]})
    return out


def _shape(row, topics, reveal=False):
    row = dict(row)
    row["alternatives"] = jloads(row.get("alternatives"), {})
    row["images"] = jloads(row.get("images"), [])
    row["extra"] = jloads(row.get("extra"), {})
    row["topics"] = topics
    row["flagged"] = bool(row.get("flagged"))
    row["last_correct"] = None if row.get("last_correct") is None else bool(row["last_correct"])
    if not reveal:
        row.pop("correct_answer", None)
        row.pop("explanation", None)
    return row


BASE_SELECT = f"""SELECT q.*, s.name AS subject_name,
       {ATTEMPTS} AS attempts, {LAST_CORRECT} AS last_correct, {LAST_CONF} AS last_confidence,
       (SELECT 1 FROM question_flags f WHERE f.question_id = q.id) AS flagged
       FROM questions q JOIN subjects s ON s.id = q.subject_id"""


def list_questions(filters, page=1, per_page=25):
    where, params = build_where(filters)
    total = db.scalar(f"SELECT COUNT(*) FROM questions q{where}", params)
    per_page = max(1, min(int(per_page), 100))
    page = max(1, int(page))
    rows = db.query(f"{BASE_SELECT}{where} ORDER BY q.id LIMIT ? OFFSET ?", params + [per_page, (page - 1) * per_page])
    topics = _topics_for([r["id"] for r in rows])
    return {
        "items": [_shape(r, topics.get(r["id"], [])) for r in rows],
        "total": total, "page": page, "per_page": per_page,
    }


def matching_ids(filters):
    where, params = build_where(filters)
    return [r["id"] for r in db.query(f"SELECT q.id, q.subject_id FROM questions q{where} ORDER BY q.id", params)]


def count(filters):
    where, params = build_where(filters)
    return db.scalar(f"SELECT COUNT(*) FROM questions q{where}", params)


def get_question(question_id):
    row = db.one(f"{BASE_SELECT} WHERE q.id = ?", (question_id,))
    if not row:
        raise ApiError("Questão não encontrada.", 404)
    q = _shape(row, _topics_for([question_id]).get(question_id, []), reveal=True)
    q["history"] = db.query(
        """SELECT a.id, a.chosen, a.is_correct, a.confidence, a.time_s, a.error_type, a.answered_at, a.session_id
           FROM answers a WHERE a.question_id = ? ORDER BY a.id DESC""",
        (question_id,),
    )
    return q


def facets():
    def distinct(col):
        return [r[col] for r in db.query(f"SELECT DISTINCT {col} FROM questions WHERE {col} IS NOT NULL ORDER BY {col}")]
    return {c: distinct(c) for c in ("bank", "year", "exam_name", "difficulty")}


def toggle_flag(question_id):
    if not db.one("SELECT id FROM questions WHERE id = ?", (question_id,)):
        raise ApiError("Questão não encontrada.", 404)
    if db.one("SELECT 1 AS x FROM question_flags WHERE question_id = ?", (question_id,)):
        db.execute("DELETE FROM question_flags WHERE question_id = ?", (question_id,))
        return False
    db.execute("INSERT INTO question_flags (question_id, created_at) VALUES (?, ?)", (question_id, now_iso()))
    return True


def set_topics(question_id, add=(), remove=()):
    q = db.one("SELECT id, subject_id FROM questions WHERE id = ?", (question_id,))
    if not q:
        raise ApiError("Questão não encontrada.", 404)
    skipped = 0
    for tid in add:
        t = db.one("SELECT id, subject_id FROM topics WHERE id = ?", (tid,))
        if not t:
            raise ApiError("Assunto não encontrado.", 404)
        if t["subject_id"] != q["subject_id"]:
            skipped += 1
            continue
        db.execute("INSERT INTO question_topics (question_id, topic_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (question_id, tid))
    for tid in remove:
        db.execute("DELETE FROM question_topics WHERE question_id = ? AND topic_id = ?", (question_id, tid))
    return skipped


def bulk_topics(question_ids, add=(), remove=()):
    skipped = 0
    for qid in question_ids:
        skipped += set_topics(qid, add, remove)
    return {"updated": len(question_ids), "skipped_other_subject": skipped}


def move_subject(question_id, subject_id):
    if not db.one("SELECT id FROM subjects WHERE id = ?", (subject_id,)):
        raise ApiError("Disciplina não encontrada.", 404)
    db.execute("UPDATE questions SET subject_id = ? WHERE id = ?", (subject_id, question_id))
    # assuntos de outra disciplina deixam de valer
    db.execute(
        """DELETE FROM question_topics WHERE question_id = ? AND topic_id IN
           (SELECT id FROM topics WHERE subject_id <> ?)""",
        (question_id, subject_id),
    )
