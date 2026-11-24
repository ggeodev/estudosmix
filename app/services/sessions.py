import random
from datetime import datetime

from .. import db
from ..errors import ApiError
from ..util import jdumps, jloads, now_iso
from . import questions as qsvc
from . import reviews

CONFIDENCES = ("certeza", "duvida", "chute")
ERROR_TYPES = {
    "desconhecimento": "Desconhecimento do conteúdo",
    "incompleto": "Conhecimento incompleto",
    "interpretacao": "Interpretação incorreta do enunciado",
    "confusao": "Confusão entre conceitos",
    "procedimento": "Erro de procedimento ou cálculo",
    "desatencao": "Desatenção ou distração",
    "outro": "Outro motivo",
}
# tipo de sessão -> quando revelar o gabarito por padrão
KINDS = {
    "bateria": {"label": "Bateria personalizada", "reveal": "each"},
    "diagnostico": {"label": "Diagnóstico de assunto", "reveal": "end"},
    "simulado": {"label": "Simulado", "reveal": "end"},
    "misto": {"label": "Assuntos mistos", "reveal": "each"},
    "avulsa": {"label": "Questão avulsa", "reveal": "each"},
    "revisao": {"label": "Revisão", "reveal": "each"},
    "verificacao": {"label": "Verificação de aprendizagem", "reveal": "each"},
}


def _interleave(ids):
    """Intercala disciplinas (round-robin) para sessões mistas."""
    by_subject = {}
    for qid, sid in ids:
        by_subject.setdefault(sid, []).append(qid)
    for lst in by_subject.values():
        random.shuffle(lst)
    groups = list(by_subject.values())
    random.shuffle(groups)
    out = []
    while any(groups):
        for g in groups:
            if g:
                out.append(g.pop())
    return out


def create(body):
    kind = body.get("kind") or "bateria"
    if kind not in KINDS:
        raise ApiError("Tipo de sessão inválido.")
    reveal = body.get("reveal") or KINDS[kind]["reveal"]
    if reveal not in ("each", "end"):
        raise ApiError("Modo de gabarito inválido.")
    filters = body.get("filters") or {}

    if body.get("question_ids"):
        ids = [int(i) for i in body["question_ids"]]
        found = {r["id"] for r in db.query(
            f"SELECT id FROM questions WHERE id IN ({db.placeholders(len(ids))})", ids)}
        ids = [i for i in ids if i in found]
    else:
        where, params = qsvc.build_where(filters)
        rows = db.query(f"SELECT q.id, q.subject_id FROM questions q{where} ORDER BY q.id", params)
        pairs = [(r["id"], r["subject_id"]) for r in rows]
        if kind == "misto":
            ids = _interleave(pairs)
        else:
            ids = [p[0] for p in pairs]
            if body.get("order", "random") == "random":
                random.shuffle(ids)
    limit = body.get("limit")
    if limit:
        ids = ids[: max(1, int(limit))]
    if not ids:
        raise ApiError("Nenhuma questão encontrada com esses filtros.")

    timer_min = body.get("timer_minutes")
    timer_s = int(float(timer_min) * 60) if timer_min else None
    title = (body.get("title") or "").strip() or f"{KINDS[kind]['label']} · {datetime.now().strftime('%d/%m %H:%M')}"
    sid = db.execute(
        "INSERT INTO sessions (kind, title, reveal, timer_limit_s, config, started_at) VALUES (?,?,?,?,?,?)",
        (kind, title, reveal, timer_s, jdumps({"filters": filters, "limit": limit}), now_iso()),
    )
    for pos, qid in enumerate(ids):
        db.execute("INSERT INTO session_questions (session_id, question_id, position) VALUES (?,?,?)", (sid, qid, pos))
    return sid


def _session_row(session_id):
    s = db.one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not s:
        raise ApiError("Sessão não encontrada.", 404)
    return s


def get(session_id):
    s = _session_row(session_id)
    finished = s["finished_at"] is not None
    rows = db.query(
        f"""{qsvc.BASE_SELECT} JOIN session_questions sq ON sq.question_id = q.id
            WHERE sq.session_id = ? ORDER BY sq.position""",
        (session_id,),
    )
    topics = qsvc._topics_for([r["id"] for r in rows])
    answers = {a["question_id"]: a for a in db.query("SELECT * FROM answers WHERE session_id = ?", (session_id,))}
    out = []
    for r in rows:
        q = qsvc._shape(r, topics.get(r["id"], []))
        for k in ("last_correct", "last_confidence", "attempts", "extra", "content_hash", "import_id"):
            q.pop(k, None)
        a = answers.get(r["id"])
        if a:
            show = s["reveal"] == "each" or finished
            q["answer"] = {
                "id": a["id"], "chosen": a["chosen"], "confidence": a["confidence"], "time_s": a["time_s"],
                "is_correct": bool(a["is_correct"]) if show else None,
                "error_type": a["error_type"] if show else None,
                "error_note": a["error_note"] if show else None,
            }
            if show:
                q["answer"]["correct_answer"] = r["correct_answer"]
                q["answer"]["explanation"] = r["explanation"]
        out.append(q)
    s["config"] = jloads(s["config"], {})
    s["questions"] = out
    s["finished"] = finished
    return s


def answer(session_id, body):
    s = _session_row(session_id)
    if s["finished_at"]:
        raise ApiError("Esta sessão já foi finalizada.", 409)
    qid = body.get("question_id")
    sq = db.one("SELECT 1 AS x FROM session_questions WHERE session_id = ? AND question_id = ?", (session_id, qid))
    if not sq:
        raise ApiError("A questão não pertence a esta sessão.", 404)
    q = db.one("SELECT alternatives, correct_answer, explanation FROM questions WHERE id = ?", (qid,))
    chosen = str(body.get("chosen") or "").upper()
    if chosen not in jloads(q["alternatives"], {}):
        raise ApiError("Alternativa inválida.")
    confidence = body.get("confidence")
    if confidence not in CONFIDENCES:
        raise ApiError("Informe a confiança: certeza, duvida ou chute.")
    try:
        time_s = max(0, min(int(body.get("time_s") or 0), 86400))
    except (TypeError, ValueError):
        raise ApiError("Tempo inválido.")
    correct = chosen == q["correct_answer"]
    existing = db.one("SELECT id FROM answers WHERE session_id = ? AND question_id = ?", (session_id, qid))
    if existing:
        if s["reveal"] == "each":
            raise ApiError("Esta questão já foi respondida.", 409)
        db.execute(
            "UPDATE answers SET chosen=?, is_correct=?, confidence=?, time_s=?, answered_at=? WHERE id=?",
            (chosen, int(correct), confidence, time_s, now_iso(), existing["id"]),
        )
        answer_id = existing["id"]
    else:
        answer_id = db.execute(
            """INSERT INTO answers (session_id, question_id, chosen, is_correct, confidence, time_s, answered_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, qid, chosen, int(correct), confidence, time_s, now_iso()),
        )
    reviews.recompute(qid)
    res = {"answer_id": answer_id, "saved": True}
    if s["reveal"] == "each":
        res.update({"is_correct": correct, "correct_answer": q["correct_answer"], "explanation": q["explanation"]})
    return res


def set_error(answer_id, error_type, note):
    a = db.one(
        "SELECT a.id, s.reveal, s.finished_at FROM answers a JOIN sessions s ON s.id = a.session_id WHERE a.id = ?",
        (answer_id,),
    )
    if not a:
        raise ApiError("Resposta não encontrada.", 404)
    if a["reveal"] == "end" and not a["finished_at"]:
        raise ApiError("Só é possível registrar a causa do erro depois de finalizar a sessão.", 409)
    if error_type and error_type not in ERROR_TYPES:
        raise ApiError("Tipo de erro inválido.")
    note = (note or "").strip()[:1000] or None
    db.execute("UPDATE answers SET error_type = ?, error_note = ? WHERE id = ?", (error_type or None, note, answer_id))


def finish(session_id):
    s = _session_row(session_id)
    if not s["finished_at"]:
        duration = db.scalar("SELECT SUM(time_s) FROM answers WHERE session_id = ?", (session_id,))
        db.execute("UPDATE sessions SET finished_at = ?, duration_s = ? WHERE id = ?", (now_iso(), duration, session_id))
    return results(session_id)


def results(session_id):
    s = _session_row(session_id)
    if not s["finished_at"]:
        raise ApiError("A sessão ainda não foi finalizada.", 409)
    rows = db.query(
        f"""{qsvc.BASE_SELECT} JOIN session_questions sq ON sq.question_id = q.id
            WHERE sq.session_id = ? ORDER BY sq.position""",
        (session_id,),
    )
    topics = qsvc._topics_for([r["id"] for r in rows])
    answers = {a["question_id"]: a for a in db.query("SELECT * FROM answers WHERE session_id = ?", (session_id,))}
    items, by_topic = [], {}
    matrix = {c: {"correct": 0, "wrong": 0} for c in CONFIDENCES}
    correct = wrong = 0
    for pos, r in enumerate(rows, 1):
        a = answers.get(r["id"])
        item = {
            "position": pos, "question_id": r["id"], "external_id": r["external_id"], "subject_name": r["subject_name"],
            "statement": r["statement"], "support_text": r["support_text"], "alternatives": jloads(r["alternatives"], {}),
            "correct_answer": r["correct_answer"], "explanation": r["explanation"],
            "topics": topics.get(r["id"], []), "answer": None,
        }
        if a:
            ok = bool(a["is_correct"])
            correct += ok
            wrong += not ok
            matrix[a["confidence"]]["correct" if ok else "wrong"] += 1
            item["answer"] = {
                "id": a["id"], "chosen": a["chosen"], "is_correct": ok, "confidence": a["confidence"],
                "time_s": a["time_s"], "error_type": a["error_type"], "error_note": a["error_note"],
            }
            for t in item["topics"] or [{"id": None, "name": "(sem assunto)"}]:
                b = by_topic.setdefault(t["name"], {"name": t["name"], "n": 0, "correct": 0})
                b["n"] += 1
                b["correct"] += ok
        items.append(item)
    answered = correct + wrong
    summary = {
        "total": len(rows), "answered": answered, "correct": correct, "wrong": wrong,
        "unanswered": len(rows) - answered,
        "accuracy": round(100 * correct / answered) if answered else None,
        "duration_s": s["duration_s"],
        "fragile_correct": sum(1 for i in items if i["answer"] and i["answer"]["is_correct"] and i["answer"]["confidence"] != "certeza"),
        "confident_wrong": matrix["certeza"]["wrong"],
    }
    s["config"] = jloads(s["config"], {})
    return {
        "session": s, "summary": summary, "confidence_matrix": matrix,
        "by_topic": sorted(by_topic.values(), key=lambda b: (b["correct"] / b["n"], -b["n"])),
        "items": items,
    }


def list_sessions(limit=20, offset=0, in_progress=False):
    cond = "WHERE s.finished_at IS NULL" if in_progress else ""
    return db.query(
        f"""SELECT s.id, s.kind, s.title, s.reveal, s.started_at, s.finished_at, s.duration_s,
              (SELECT COUNT(*) FROM session_questions sq WHERE sq.session_id = s.id) AS total,
              (SELECT COUNT(*) FROM answers a WHERE a.session_id = s.id) AS answered,
              (SELECT COALESCE(SUM(a.is_correct), 0) FROM answers a WHERE a.session_id = s.id) AS correct,
              (SELECT COALESCE(SUM(a.time_s), 0) FROM answers a WHERE a.session_id = s.id) AS time_s
            FROM sessions s {cond} ORDER BY s.id DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )


def delete(session_id):
    _session_row(session_id)
    qids = [r["question_id"] for r in db.query("SELECT question_id FROM answers WHERE session_id = ?", (session_id,))]
    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    reviews.recompute_many(qids)
