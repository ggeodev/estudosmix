"""Revisão espaçada — regras simples e transparentes (hipóteses iniciais, não verdades científicas).

Para cada questão, o agendamento é recalculado a partir de TODO o histórico de respostas dela (idempotente):
  errou                          -> volta em WRONG_DAYS
  acertou com chute              -> volta em GUESS_DAYS
  acertou com dúvida             -> volta em DOUBT_DAYS
  acertou com certeza            -> intervalo cresce a cada acerto seguido: LADDER[acertos_seguidos - 1]
  desempenho inconsistente       -> (acertos e erros nas últimas 3 respostas) intervalo máximo de 3 dias
"""
from datetime import datetime, timedelta, timezone

from .. import db
from ..util import now_iso

WRONG_DAYS = 1
GUESS_DAYS = 2
DOUBT_DAYS = 3
LADDER = [3, 7, 16, 35]
INCONSISTENT_MAX_DAYS = 3
RULES = {"wrong_days": WRONG_DAYS, "guess_days": GUESS_DAYS, "doubt_days": DOUBT_DAYS, "ladder": LADDER,
         "inconsistent_max_days": INCONSISTENT_MAX_DAYS}
REASON_LABEL = {"errou": "errou", "chute": "acertou chutando", "duvida": "acertou com dúvida",
                "consolidando": "consolidando", "inconsistente": "desempenho inconsistente"}
PRIORITY = {"errou": 0, "inconsistente": 1, "chute": 2, "duvida": 3, "consolidando": 4}


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def recompute(question_id):
    rows = db.query("SELECT is_correct, confidence, answered_at FROM answers WHERE question_id = ? ORDER BY id", (question_id,))
    if not rows:
        db.execute("DELETE FROM reviews WHERE question_id = ?", (question_id,))
        return
    streak, interval, reason = 0, WRONG_DAYS, "errou"
    for a in rows:
        if not a["is_correct"]:
            streak, interval, reason = 0, WRONG_DAYS, "errou"
        elif a["confidence"] == "chute":
            streak, interval, reason = 0, GUESS_DAYS, "chute"
        elif a["confidence"] == "duvida":
            interval, reason = DOUBT_DAYS, "duvida"
        else:
            streak += 1
            interval, reason = LADDER[min(streak - 1, len(LADDER) - 1)], "consolidando"
    recent = rows[-3:]
    if len(recent) >= 2 and any(r["is_correct"] for r in recent) and any(not r["is_correct"] for r in recent):
        if interval > INCONSISTENT_MAX_DAYS:
            interval = INCONSISTENT_MAX_DAYS
        if reason == "consolidando":
            reason = "inconsistente"
    due = (_parse(rows[-1]["answered_at"]) + timedelta(days=interval)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """INSERT INTO reviews (question_id, due_at, interval_days, streak, reason, updated_at) VALUES (?,?,?,?,?,?)
           ON CONFLICT (question_id) DO UPDATE SET due_at = excluded.due_at, interval_days = excluded.interval_days,
           streak = excluded.streak, reason = excluded.reason, updated_at = excluded.updated_at""",
        (question_id, due, interval, streak, reason, now_iso()))


def recompute_many(ids):
    for i in set(ids):
        recompute(i)


def due_items(limit=None):
    sql = """SELECT r.question_id, r.due_at, r.interval_days, r.streak, r.reason, q.statement, q.subject_id, s.name AS subject_name
             FROM reviews r JOIN questions q ON q.id = r.question_id JOIN subjects s ON s.id = q.subject_id
             WHERE r.due_at <= ?"""
    rows = db.query(sql, (now_iso(),))
    rows.sort(key=lambda r: (PRIORITY.get(r["reason"], 9), r["due_at"]))
    for r in rows:
        r["reason_label"] = REASON_LABEL.get(r["reason"], r["reason"])
        r["statement"] = r["statement"][:160]
    return rows[:limit] if limit else rows


def overview():
    due = due_items()
    upcoming = db.query(
        """SELECT substr(due_at, 1, 10) AS date, COUNT(*) AS n FROM reviews WHERE due_at > ?
           GROUP BY substr(due_at, 1, 10) ORDER BY date LIMIT 14""", (now_iso(),))
    by_subject = {}
    for r in due:
        by_subject[r["subject_name"]] = by_subject.get(r["subject_name"], 0) + 1
    return {
        "due_count": len(due), "due": due[:100],
        "by_subject": [{"name": k, "n": v} for k, v in sorted(by_subject.items(), key=lambda kv: -kv[1])],
        "upcoming": upcoming, "tracked": db.scalar("SELECT COUNT(*) FROM reviews"),
        "rules": RULES, "reason_labels": REASON_LABEL,
    }


def due_count():
    return db.scalar("SELECT COUNT(*) FROM reviews WHERE due_at <= ?", (now_iso(),))


def create_session(limit=15):
    from . import sessions  # import tardio (evita ciclo)
    from ..errors import ApiError
    items = due_items(limit=max(1, int(limit)))
    if not items:
        raise ApiError("Não há revisões pendentes agora.")
    # prioridade decide QUAIS entram; a ordem é intercalada por disciplina (mistura assuntos)
    ids = sessions._interleave([(r["question_id"], r["subject_id"]) for r in items])
    return sessions.create({"kind": "revisao", "question_ids": ids, "title": f"Revisão · {len(ids)} questões"})
