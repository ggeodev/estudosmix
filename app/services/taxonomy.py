from .. import db
from ..errors import ApiError
from ..util import now_iso


def _name(value):
    name = (value or "").strip()
    if not name:
        raise ApiError("O nome é obrigatório.")
    if len(name) > 200:
        raise ApiError("O nome é longo demais (máximo 200 caracteres).")
    return name


def tree():
    exams = db.query("SELECT id, name FROM exams ORDER BY name COLLATE NOCASE")
    subjects = db.query(
        """SELECT s.id, s.name, s.exam_id,
                  (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS question_count
           FROM subjects s ORDER BY s.name COLLATE NOCASE"""
    )
    topics = db.query(
        """SELECT t.id, t.name, t.subject_id, t.parent_id,
                  (SELECT COUNT(*) FROM question_topics qt WHERE qt.topic_id = t.id) AS question_count
           FROM topics t ORDER BY t.name COLLATE NOCASE"""
    )
    return {"exams": exams, "subjects": subjects, "topics": topics}


# ---- concursos ----
def create_exam(name):
    return db.execute("INSERT INTO exams (name, created_at) VALUES (?, ?)", (_name(name), now_iso()))


def update_exam(exam_id, name):
    _require("exams", exam_id)
    db.execute("UPDATE exams SET name = ? WHERE id = ?", (_name(name), exam_id))


def delete_exam(exam_id):
    _require("exams", exam_id)
    db.execute("DELETE FROM exams WHERE id = ?", (exam_id,))  # disciplinas ficam sem concurso


# ---- disciplinas ----
def create_subject(name, exam_id=None):
    if exam_id is not None:
        _require("exams", exam_id)
    return db.execute(
        "INSERT INTO subjects (exam_id, name, created_at) VALUES (?, ?, ?)", (exam_id, _name(name), now_iso())
    )


def update_subject(subject_id, name=None, exam_id=..., ):
    _require("subjects", subject_id)
    if name is not None:
        db.execute("UPDATE subjects SET name = ? WHERE id = ?", (_name(name), subject_id))
    if exam_id is not ...:
        if exam_id is not None:
            _require("exams", exam_id)
        db.execute("UPDATE subjects SET exam_id = ? WHERE id = ?", (exam_id, subject_id))


def delete_subject(subject_id):
    _require("subjects", subject_id)
    n = db.scalar("SELECT COUNT(*) FROM questions WHERE subject_id = ?", (subject_id,))
    if n:
        raise ApiError(
            f"Esta disciplina possui {n} questão(ões). Mova ou exclua as questões antes de removê-la.", 409
        )
    db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))


# ---- assuntos ----
def create_topic(name, subject_id, parent_id=None):
    _require("subjects", subject_id)
    if parent_id is not None:
        parent = _require("topics", parent_id)
        if parent["subject_id"] != subject_id:
            raise ApiError("O assunto pai pertence a outra disciplina.")
    return db.execute(
        "INSERT INTO topics (subject_id, parent_id, name, created_at) VALUES (?, ?, ?, ?)",
        (subject_id, parent_id, _name(name), now_iso()),
    )


def update_topic(topic_id, name=None, parent_id=...):
    topic = _require("topics", topic_id)
    if name is not None:
        db.execute("UPDATE topics SET name = ? WHERE id = ?", (_name(name), topic_id))
    if parent_id is not ...:
        if parent_id is not None:
            parent = _require("topics", parent_id)
            if parent["subject_id"] != topic["subject_id"]:
                raise ApiError("O assunto pai pertence a outra disciplina.")
            if parent_id in descendants(topic_id):
                raise ApiError("Um assunto não pode ficar dentro de si mesmo.")
        db.execute("UPDATE topics SET parent_id = ? WHERE id = ?", (parent_id, topic_id))


def delete_topic(topic_id):
    _require("topics", topic_id)
    db.execute("DELETE FROM topics WHERE id = ?", (topic_id,))  # subassuntos e vínculos saem junto


def descendants(topic_id):
    """IDs do assunto e de todos os seus subassuntos."""
    children = {}
    for r in db.query("SELECT id, parent_id FROM topics"):
        children.setdefault(r["parent_id"], []).append(r["id"])
    out, stack = [], [topic_id]
    while stack:
        t = stack.pop()
        out.append(t)
        stack.extend(children.get(t, []))
    return out


def get_or_create_subject(name, exam_id=None):
    if exam_id is None:
        row = db.one("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND exam_id IS NULL", (name,))
        if not row:
            row = db.one("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?)", (name,))
    else:
        row = db.one("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND exam_id = ?", (name, exam_id))
    return row["id"] if row else create_subject(name, exam_id)


def get_or_create_topic_path(subject_id, path):
    """Aceita 'Sintaxe > Concordância verbal' e cria a hierarquia."""
    parent = None
    for part in [p.strip() for p in path.split(">") if p.strip()]:
        if parent is None:
            row = db.one(
                "SELECT id FROM topics WHERE subject_id = ? AND parent_id IS NULL AND LOWER(name) = LOWER(?)",
                (subject_id, part),
            )
        else:
            row = db.one(
                "SELECT id FROM topics WHERE subject_id = ? AND parent_id = ? AND LOWER(name) = LOWER(?)",
                (subject_id, parent, part),
            )
        parent = row["id"] if row else create_topic(part, subject_id, parent)
    return parent


def _require(table, row_id):
    row = db.one(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    if not row:
        raise ApiError("Registro não encontrado.", 404)
    return row
