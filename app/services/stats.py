from datetime import datetime, timedelta, timezone

from .. import db
from ..util import now_iso
from . import questions as qsvc
from . import sessions as ssvc
from . import reviews as rvsvc
from . import study as stsvc


def _cutoff(days):
    if not days:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pct(c, n):
    return round(100 * c / n) if n else None


def _daily(days, tz_offset_min):
    """Respostas por dia (no fuso do usuário). tz_offset_min: minutos a ADICIONAR ao UTC (Brasil = -180)."""
    since = datetime.now(timezone.utc) - timedelta(days=days + 1)
    rows = db.query("SELECT answered_at, is_correct, time_s FROM answers WHERE answered_at >= ?",
                    (since.strftime("%Y-%m-%dT%H:%M:%SZ"),))
    delta = timedelta(minutes=tz_offset_min)
    buckets = {}
    for r in rows:
        d = (datetime.strptime(r["answered_at"], "%Y-%m-%dT%H:%M:%SZ") + delta).date().isoformat()
        b = buckets.setdefault(d, {"n": 0, "correct": 0, "time_s": 0})
        b["n"] += 1
        b["correct"] += r["is_correct"]
        b["time_s"] += r["time_s"]
    today = (datetime.now(timezone.utc) + delta).date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        b = buckets.get(d, {"n": 0, "correct": 0, "time_s": 0})
        out.append({"date": d, **b})
    return out


def _suggestion():
    if db.scalar("SELECT COUNT(*) FROM questions") == 0:
        return {"kind": "import", "title": "Importe suas primeiras questões",
                "reason": "Ainda não há questões no banco."}
    due = rvsvc.due_count()
    if due:
        return {"kind": "review", "title": f"Revisar {min(due, 15)} questão(ões)",
                "reason": f"{due} revisão(ões) pendente(s) pelo seu histórico de erros e dúvidas."}
    gaps = stsvc.open_gaps()
    if gaps:
        return {"kind": "gaps", "title": "Estudar suas lacunas",
                "reason": f"{len(gaps)} questão(ões) errada(s) ou acertada(s) sem certeza ainda sem estudo consolidado."}
    weak = db.query(
        """SELECT t.id, t.name, COUNT(*) AS n, SUM(a.is_correct) AS c
           FROM answers a JOIN question_topics qt ON qt.question_id = a.question_id
           JOIN topics t ON t.id = qt.topic_id GROUP BY t.id, t.name HAVING COUNT(*) >= 3
           ORDER BY 1.0 * SUM(a.is_correct) / COUNT(*) ASC, COUNT(*) DESC LIMIT 1"""
    )
    if weak and weak[0]["c"] < weak[0]["n"]:
        w = weak[0]
        filt = {"topic_id": w["id"], "status": "wrong"}
        if qsvc.count(filt) == 0:
            filt = {"topic_id": w["id"]}
        return {"kind": "session", "session_kind": "bateria", "title": f"Reforçar: {w['name']}",
                "reason": f"Seu menor aproveitamento por assunto: {_pct(w['c'], w['n'])}% em {w['n']} respostas.",
                "filters": filt, "limit": 10}
    fragile = qsvc.count({"status": "fragile"})
    if fragile:
        return {"kind": "session", "session_kind": "bateria", "title": "Consolidar acertos frágeis",
                "reason": f"{fragile} questão(ões) acertada(s) com dúvida ou chute na última tentativa.",
                "filters": {"status": "fragile"}, "limit": 10}
    row = db.one(
        """SELECT s.id, s.name, COUNT(*) AS n FROM questions q JOIN subjects s ON s.id = q.subject_id
           WHERE NOT EXISTS (SELECT 1 FROM answers a WHERE a.question_id = q.id)
           GROUP BY s.id, s.name ORDER BY n DESC LIMIT 1"""
    )
    if row:
        return {"kind": "session", "session_kind": "diagnostico", "title": f"Sondagem de {row['name']}",
                "reason": f"{row['n']} questão(ões) inédita(s) nesta disciplina.",
                "filters": {"subject_id": row["id"], "status": "unseen"}, "limit": 10}
    return {"kind": "session", "session_kind": "bateria", "title": "Refazer questões erradas",
            "reason": "Você já viu todas as questões; revise as que errou.",
            "filters": {"status": "wrong"}, "limit": 10}


def dashboard(tz_offset_min=0):
    t = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(is_correct),0) AS c, COALESCE(SUM(time_s),0) AS t FROM answers")
    total_q = db.scalar("SELECT COUNT(*) FROM questions")
    seen = db.scalar("SELECT COUNT(DISTINCT question_id) FROM answers")
    progress = db.query(
        """SELECT s.id, s.name,
             (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS total,
             (SELECT COUNT(DISTINCT a.question_id) FROM answers a JOIN questions q ON q.id = a.question_id WHERE q.subject_id = s.id) AS seen,
             (SELECT COUNT(*) FROM answers a JOIN questions q ON q.id = a.question_id WHERE q.subject_id = s.id) AS n,
             (SELECT COALESCE(SUM(a.is_correct),0) FROM answers a JOIN questions q ON q.id = a.question_id WHERE q.subject_id = s.id) AS c
           FROM subjects s ORDER BY s.name COLLATE NOCASE"""
    )
    progress = [dict(p, accuracy=_pct(p["c"], p["n"])) for p in progress if p["total"] > 0]
    weak = db.query(
        """SELECT t.id, t.name, COUNT(*) AS n, SUM(a.is_correct) AS c
           FROM answers a JOIN question_topics qt ON qt.question_id = a.question_id
           JOIN topics t ON t.id = qt.topic_id GROUP BY t.id, t.name HAVING COUNT(*) >= 3
           ORDER BY 1.0 * SUM(a.is_correct) / COUNT(*) ASC, COUNT(*) DESC LIMIT 5"""
    )
    return {
        "totals": {
            "answered": t["n"], "correct": t["c"], "wrong": t["n"] - t["c"], "accuracy": _pct(t["c"], t["n"]),
            "study_seconds": t["t"], "questions_total": total_q, "questions_seen": seen,
            "sessions_finished": db.scalar("SELECT COUNT(*) FROM sessions WHERE finished_at IS NOT NULL"),
            "fragile": qsvc.count({"status": "fragile"}), "wrong_last": qsvc.count({"status": "wrong"}),
            "reviews_due": rvsvc.due_count(), "open_gaps": len(stsvc.open_gaps()),
        },
        "suggestion": _suggestion(),
        "in_progress": ssvc.list_sessions(5, 0, True),
        "recent_sessions": [s for s in ssvc.list_sessions(8) if s["finished_at"]][:5],
        "weak_topics": [dict(w, accuracy=_pct(w["c"], w["n"])) for w in weak],
        "subject_progress": progress,
        "activity": _daily(14, tz_offset_min),
    }


def _group(sql, params):
    rows = db.query(sql, params)
    return [dict(r, accuracy=_pct(r["c"], r["n"])) for r in rows]


def stats(days=None, tz_offset_min=0):
    cutoff = _cutoff(days)
    w = " WHERE a.answered_at >= ?" if cutoff else ""
    p = [cutoff] if cutoff else []
    and_ = " AND" if cutoff else " WHERE"

    overall = db.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(a.is_correct),0) AS c, COALESCE(SUM(a.time_s),0) AS t FROM answers a{w}", p)
    by_subject = _group(
        f"""SELECT s.id, s.name, COUNT(*) AS n, SUM(a.is_correct) AS c, SUM(a.time_s) AS t
            FROM answers a JOIN questions q ON q.id = a.question_id JOIN subjects s ON s.id = q.subject_id{w}
            GROUP BY s.id, s.name ORDER BY s.name COLLATE NOCASE""", p)
    by_topic = _group(
        f"""SELECT t.id, t.name, s.name AS subject, COUNT(*) AS n, SUM(a.is_correct) AS c
            FROM answers a JOIN question_topics qt ON qt.question_id = a.question_id
            JOIN topics t ON t.id = qt.topic_id JOIN subjects s ON s.id = t.subject_id{w}
            GROUP BY t.id, t.name, s.name ORDER BY 1.0 * SUM(a.is_correct) / COUNT(*) ASC, COUNT(*) DESC""", p)
    by_bank = _group(
        f"""SELECT COALESCE(q.bank, '(sem banca)') AS name, COUNT(*) AS n, SUM(a.is_correct) AS c
            FROM answers a JOIN questions q ON q.id = a.question_id{w} GROUP BY name ORDER BY n DESC""", p)
    by_exam = _group(
        f"""SELECT COALESCE(q.exam_name, '(sem prova)') AS name, COUNT(*) AS n, SUM(a.is_correct) AS c
            FROM answers a JOIN questions q ON q.id = a.question_id{w} GROUP BY name ORDER BY n DESC""", p)
    by_conf = _group(
        f"SELECT a.confidence AS name, COUNT(*) AS n, SUM(a.is_correct) AS c FROM answers a{w} GROUP BY a.confidence", p)
    order = {"certeza": 0, "duvida": 1, "chute": 2}
    by_conf.sort(key=lambda r: order.get(r["name"], 9))
    by_error = db.query(
        f"""SELECT a.error_type AS name, COUNT(*) AS n FROM answers a{w}{and_} a.error_type IS NOT NULL
            GROUP BY a.error_type ORDER BY n DESC""", p)
    novelty = _group(
        f"""SELECT CASE WHEN EXISTS (SELECT 1 FROM answers a2 WHERE a2.question_id = a.question_id
                AND a2.id < a.id AND a2.session_id <> a.session_id) THEN 'repeated' ELSE 'new' END AS name,
              COUNT(*) AS n, SUM(a.is_correct) AS c FROM answers a{w} GROUP BY name""", p)
    unmarked_wrong = db.scalar(
        f"SELECT COUNT(*) FROM answers a{w}{and_} a.is_correct = 0 AND a.error_type IS NULL", p)
    return {
        "days": days,
        "overall": {"answered": overall["n"], "correct": overall["c"], "accuracy": _pct(overall["c"], overall["n"]),
                    "study_seconds": overall["t"]},
        "by_subject": by_subject, "by_topic": by_topic, "by_bank": by_bank, "by_exam": by_exam,
        "by_confidence": by_conf, "by_error_type": by_error, "novelty": novelty,
        "daily": _daily(min(days or 30, 90) if days else 30, tz_offset_min),
        "facts": {
            "confident_wrong": next((r["n"] - r["c"] for r in by_conf if r["name"] == "certeza"), 0),
            "guess_correct": next((r["c"] for r in by_conf if r["name"] == "chute"), 0),
            "errors_without_cause": unmarked_wrong,
        },
        "error_labels": ssvc.ERROR_TYPES,
    }
