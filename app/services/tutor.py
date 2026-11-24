from .. import ai, db
from ..ai import prompts
from ..errors import ApiError
from ..util import now_iso
from . import questions as qsvc
from . import study

MAX_HISTORY = 12


def _check_thread(thread):
    if thread != "free" and not (thread.startswith("q:") and thread[2:].isdigit()):
        raise ApiError("Conversa inválida.")


def history(thread):
    _check_thread(thread)
    return db.query("SELECT id, role, content, created_at FROM tutor_messages WHERE thread = ? ORDER BY id", (thread,))


def clear(thread):
    _check_thread(thread)
    db.execute("DELETE FROM tutor_messages WHERE thread = ?", (thread,))


def threads():
    return db.query(
        """SELECT thread, COUNT(*) AS n, MAX(created_at) AS last_at FROM tutor_messages GROUP BY thread ORDER BY MAX(id) DESC LIMIT 20""")


def chat(thread, message):
    _check_thread(thread)
    message = (message or "").strip()
    if not message:
        raise ApiError("Escreva uma mensagem.")
    if len(message) > 4000:
        raise ApiError("Mensagem longa demais (máx. 4000 caracteres).")
    system = prompts.TUTOR_SYSTEM
    if thread.startswith("q:"):
        qid = int(thread[2:])
        if not study.revealable(qid):
            raise ApiError("Finalize a sessão de diagnóstico antes de conversar sobre esta questão.", 409)
        q = qsvc.get_question(qid)
        system += "\n\n" + prompts.tutor_context(q, q["history"][0] if q["history"] else None)
    past = db.query("SELECT role, content FROM tutor_messages WHERE thread = ? ORDER BY id DESC LIMIT ?", (thread, MAX_HISTORY))
    msgs = list(reversed(past)) + [{"role": "user", "content": message}]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    reply = ai.run_text("tutor", system, msgs).strip()
    model = ai.status()["model"]
    db.execute("INSERT INTO tutor_messages (thread, role, content, created_at) VALUES (?,?,?,?)", (thread, "user", message, now_iso()))
    db.execute("INSERT INTO tutor_messages (thread, role, content, model, created_at) VALUES (?,?,?,?,?)", (thread, "model", reply, model, now_iso()))
    return {"reply": reply, "model": model}
