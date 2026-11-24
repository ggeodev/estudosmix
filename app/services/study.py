"""Etapas 2–4 do estudo reverso: lacunas, material direcionado, verificação e registro de aprendizagem."""
import random

from .. import ai, db
from ..ai import prompts
from ..errors import ApiError
from ..util import jdumps, jloads, now_iso
from . import importer, reviews
from . import questions as qsvc
from . import sessions as ssvc
from . import taxonomy

KIND_ORDER = {"lacuna": 0, "chute": 1, "fragil": 2}
OUTCOME_LABEL = {"correct_confident": "acertou com certeza", "correct_fragile": "acertou com dúvida/chute", "wrong": "errou de novo"}
AI_BANK = "Gerada por IA"


def revealable(question_id):
    """O gabarito só pode ser usado (material/tutor) se a questão não estiver em diagnóstico ainda aberto."""
    return not db.one(
        """SELECT 1 AS x FROM session_questions sq JOIN sessions s ON s.id = sq.session_id
           WHERE sq.question_id = ? AND s.reveal = 'end' AND s.finished_at IS NULL""", (question_id,))


def _classify(a):
    if not a["is_correct"]:
        return "lacuna"
    return "chute" if a["confidence"] == "chute" else "fragil"


def _concepts(ids):
    if not ids:
        return {}
    rows = db.query(f"SELECT question_id, concept FROM question_concepts WHERE question_id IN ({db.placeholders(len(ids))})", ids)
    return {r["question_id"]: r["concept"] for r in rows}


def _item(r, topics, concepts, studied):
    kind = _classify(r)
    return {
        "question_id": r["id"], "external_id": r.get("external_id"), "subject_name": r["subject_name"], "subject_id": r["subject_id"],
        "statement": r["statement"][:200], "topics": topics.get(r["id"], []), "concept": concepts.get(r["id"]),
        "kind": kind, "confident_wrong": kind == "lacuna" and r["confidence"] == "certeza",
        "confidence": r["confidence"], "chosen": r["chosen"], "error_type": r["error_type"],
        "studied": studied.get(r["id"]),
    }


_BASE = """SELECT q.id, q.external_id, q.statement, q.subject_id, s.name AS subject_name, a.chosen, a.is_correct, a.confidence,
              a.error_type, a.answered_at
           FROM questions q JOIN subjects s ON s.id = q.subject_id"""


def open_gaps(session_id=None):
    """Questões cuja resposta mais recente (ou a da sessão) foi erro ou acerto sem certeza e que ainda não foram consolidadas."""
    if session_id:
        rows = db.query(f"{_BASE} JOIN answers a ON a.question_id = q.id AND a.session_id = ?", (session_id,))
    else:
        rows = db.query(f"{_BASE} JOIN answers a ON a.id = (SELECT MAX(a2.id) FROM answers a2 WHERE a2.question_id = q.id)")
    rows = [r for r in rows if (not r["is_correct"] or r["confidence"] != "certeza") and revealable(r["id"])]
    ids = [r["id"] for r in rows]
    studied = {}
    resolved = set()
    for rec in db.query("SELECT question_id, outcome, created_at FROM study_records ORDER BY id"):
        studied[rec["question_id"]] = {"outcome": rec["outcome"], "label": OUTCOME_LABEL.get(rec["outcome"]), "at": rec["created_at"]}
    out = []
    for r in rows:
        st = studied.get(r["id"])
        if st and st["outcome"] == "correct_confident" and st["at"] >= r["answered_at"]:
            continue  # lacuna já verificada com acerto confiante depois desta resposta
        out.append(r)
    topics = qsvc._topics_for([r["id"] for r in out])
    concepts = _concepts([r["id"] for r in out])
    items = [_item(r, topics, concepts, studied) for r in out]
    items.sort(key=lambda i: (not i["confident_wrong"], KIND_ORDER[i["kind"]], i["question_id"]))
    return items


def session_analysis(session_id):
    s = db.one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not s:
        raise ApiError("Sessão não encontrada.", 404)
    if not s["finished_at"]:
        raise ApiError("A sessão ainda não foi finalizada.", 409)
    rows = db.query(f"{_BASE} JOIN answers a ON a.question_id = q.id AND a.session_id = ?", (session_id,))
    topics = qsvc._topics_for([r["id"] for r in rows])
    concepts = _concepts([r["id"] for r in rows])
    buckets = {"demonstrated": [], "gaps": [], "fragile": [], "guessed": []}
    for r in rows:
        it = _item(r, topics, concepts, {})
        it["label"] = it["concept"] or (", ".join(t["name"] for t in it["topics"]) or it["statement"][:80])
        if r["is_correct"] and r["confidence"] == "certeza":
            buckets["demonstrated"].append(it)
        elif not r["is_correct"]:
            buckets["gaps"].append(it)
        elif r["confidence"] == "chute":
            buckets["guessed"].append(it)
        else:
            buckets["fragile"].append(it)
    buckets["total_answered"] = len(rows)
    buckets["unnamed"] = sum(1 for k in ("gaps", "fragile", "guessed") for i in buckets[k] if not i["concept"])
    buckets["small_sample"] = len(rows) < 10
    return buckets


def name_concepts(question_ids):
    """Uma única chamada de IA nomeia o conhecimento específico de várias questões."""
    have = _concepts(question_ids)
    todo = [i for i in question_ids if i not in have][:30]
    if not todo:
        return {"named": 0}
    items = []
    for qid in todo:
        if not revealable(qid):
            continue
        q = qsvc.get_question(qid)
        last = q["history"][0] if q["history"] else {"chosen": "?"}
        items.append({"q": q, "chosen": last["chosen"]})
    if not items:
        return {"named": 0}
    data = ai.run_json("concepts", prompts.CONTENT_SYSTEM, prompts.concepts_prompt(items))
    valid = {it["q"]["id"] for it in items}
    n = 0
    model = ai.status()["model"]
    for it in (data.get("items") if isinstance(data, dict) else None) or []:
        try:
            qid = int(it["question_id"])
        except (KeyError, TypeError, ValueError):
            continue
        concept = str(it.get("concept") or "").strip()[:160]
        if qid in valid and concept:
            db.execute("""INSERT INTO question_concepts (question_id, concept, model, created_at) VALUES (?,?,?,?)
                          ON CONFLICT (question_id) DO UPDATE SET concept = excluded.concept""", (qid, concept, model, now_iso()))
            n += 1
    return {"named": n}


def study_state(question_id):
    if not revealable(question_id):
        raise ApiError("Finalize a sessão de diagnóstico antes de estudar esta questão.", 409)
    q = qsvc.get_question(question_id)
    last = q["history"][0] if q["history"] else None
    mats = {m["level"]: jloads(m["content"]) for m in db.query("SELECT level, content FROM study_materials WHERE question_id = ?", (question_id,))}
    records = db.query("SELECT outcome, created_at FROM study_records WHERE question_id = ? ORDER BY id DESC", (question_id,))
    return {"question": q, "last_answer": last, "concept": _concepts([question_id]).get(question_id),
            "materials": mats, "records": records, "ai": ai.status()}


def get_material(question_id, level="normal", force=False):
    if level not in ("normal", "simples"):
        raise ApiError("Nível inválido.")
    if not revealable(question_id):
        raise ApiError("Finalize a sessão de diagnóstico antes de estudar esta questão.", 409)
    row = db.one("SELECT content FROM study_materials WHERE question_id = ? AND level = ?", (question_id, level))
    if row and not force:
        return {"material": jloads(row["content"]), "level": level, "cached": True}
    q = qsvc.get_question(question_id)
    last = q["history"][0] if q["history"] else None
    data = ai.run_json("material", prompts.CONTENT_SYSTEM, prompts.material_prompt(q, last, level))
    if not isinstance(data, dict) or not data.get("explanation"):
        raise ai.AIError("A IA não devolveu uma explicação utilizável. Tente novamente.", "bad_output")
    material = {k: data.get(k) for k in ("concept", "explanation", "rule", "example", "why_correct", "why_wrong", "prerequisites", "references")}
    db.execute("""INSERT INTO study_materials (question_id, level, content, model, created_at) VALUES (?,?,?,?,?)
                  ON CONFLICT (question_id, level) DO UPDATE SET content = excluded.content, model = excluded.model, created_at = excluded.created_at""",
               (question_id, level, jdumps(material), ai.status()["model"], now_iso()))
    if material.get("concept"):
        db.execute("""INSERT INTO question_concepts (question_id, concept, model, created_at) VALUES (?,?,?,?)
                      ON CONFLICT (question_id) DO NOTHING""", (question_id, str(material["concept"])[:160], ai.status()["model"], now_iso()))
    return {"material": material, "level": level, "cached": False}


def _existing_candidate(origin):
    topic_ids = [t["id"] for t in origin["topics"]]
    cond = "q.subject_id = ? AND q.id <> ? AND NOT EXISTS (SELECT 1 FROM answers a WHERE a.question_id = q.id)"
    params = [origin["subject_id"], origin["id"]]
    if topic_ids:
        cond += f" AND q.id IN (SELECT question_id FROM question_topics WHERE topic_id IN ({db.placeholders(len(topic_ids))}))"
        params += topic_ids
    rows = db.query(f"SELECT q.id, q.bank FROM questions q WHERE {cond}", params)
    if not rows:
        return None
    originals = [r for r in rows if r["bank"] != AI_BANK]
    return random.choice(originals or rows)["id"]


def _generate_question(origin):
    prev = [r["statement"] for r in db.query(
        "SELECT q.statement FROM study_records sr JOIN questions q ON q.id = sr.verification_question_id WHERE sr.question_id = ?", (origin["id"],))]
    data = ai.run_json("verification", prompts.CONTENT_SYSTEM, prompts.verification_prompt(origin, prev))
    if not isinstance(data, dict):
        raise ai.AIError("A IA devolveu uma questão em formato inesperado.", "bad_output")
    rec, errors, _ = importer.validate_question(data, {"subject": origin["subject_name"], "bank": AI_BANK})
    if rec is None:
        raise ai.AIError("A questão gerada pela IA é inválida (" + "; ".join(errors[:2]) + "). Tente novamente.", "bad_output")
    if db.one("SELECT 1 AS x FROM questions WHERE content_hash = ?", (rec["content_hash"],)):
        raise ai.AIError("A IA repetiu uma questão que já existe. Tente novamente.", "bad_output")
    qid = db.execute(
        """INSERT INTO questions (external_id, content_hash, subject_id, import_id, bank, year, organization, exam_name, statement,
             support_text, alternatives, correct_answer, explanation, difficulty, images, extra, created_at)
           VALUES (NULL,?,?,NULL,?,NULL,NULL,NULL,?,?,?,?,?,NULL,'[]',?,?)""",
        (rec["content_hash"], origin["subject_id"], AI_BANK, rec["statement"], rec["support_text"], jdumps(rec["alternatives"]),
         rec["correct_answer"], rec["explanation"], jdumps({"ai_generated": True, "derived_from": origin["id"]}), now_iso()))
    for t in origin["topics"]:
        db.execute("INSERT INTO question_topics (question_id, topic_id) VALUES (?,?) ON CONFLICT DO NOTHING", (qid, t["id"]))
    return qid


def start_verification(question_id, mode="auto"):
    if not revealable(question_id):
        raise ApiError("Finalize a sessão de diagnóstico antes de estudar esta questão.", 409)
    if mode not in ("auto", "existing", "ai"):
        raise ApiError("Modo inválido.")
    origin = qsvc.get_question(question_id)
    vq, source = None, None
    if mode in ("auto", "existing"):
        vq = _existing_candidate(origin)
        source = "existing"
        if vq is None and mode == "existing":
            raise ApiError("Não há questões inéditas deste assunto no banco. Gere uma com IA.", 404)
    if vq is None:
        vq, source = _generate_question(origin), "ai"
    sid = ssvc.create({"kind": "verificacao", "question_ids": [vq], "title": f"Verificação · questão {origin['external_id'] or origin['id']}",
                       "filters": {"study_question_id": question_id}})
    return {"session_id": sid, "question_id": vq, "source": source}


def record_outcome(question_id, session_id):
    s = db.one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    a = db.one("SELECT * FROM answers WHERE session_id = ?", (session_id,))
    if not s or s["kind"] != "verificacao" or not a:
        raise ApiError("Sessão de verificação inválida ou sem resposta.", 400)
    if db.one("SELECT 1 AS x FROM study_records WHERE session_id = ?", (session_id,)):
        raise ApiError("Este resultado já foi registrado.", 409)
    if not a["is_correct"]:
        outcome = "wrong"
    else:
        outcome = "correct_confident" if a["confidence"] == "certeza" else "correct_fragile"
    ssvc.finish(session_id)
    db.execute("INSERT INTO study_records (question_id, verification_question_id, session_id, outcome, created_at) VALUES (?,?,?,?,?)",
               (question_id, a["question_id"], session_id, outcome, now_iso()))
    rv = db.one("SELECT due_at, interval_days, reason FROM reviews WHERE question_id = ?", (question_id,))
    vr = db.one("SELECT due_at, interval_days, reason FROM reviews WHERE question_id = ?", (a["question_id"],))
    nxt = [g for g in open_gaps() if g["question_id"] != question_id]
    return {"outcome": outcome, "outcome_label": OUTCOME_LABEL[outcome], "review_original": rv, "review_verification": vr,
            "next_gap_id": nxt[0]["question_id"] if nxt else None, "open_gaps": len(nxt)}


def list_records(limit=15):
    rows = db.query(
        """SELECT sr.id, sr.question_id, sr.outcome, sr.created_at, q.statement, s.name AS subject_name
           FROM study_records sr JOIN questions q ON q.id = sr.question_id JOIN subjects s ON s.id = q.subject_id
           ORDER BY sr.id DESC LIMIT ?""", (limit,))
    concepts = _concepts([r["question_id"] for r in rows])
    for r in rows:
        r["statement"] = r["statement"][:120]
        r["concept"] = concepts.get(r["question_id"])
        r["outcome_label"] = OUTCOME_LABEL.get(r["outcome"])
    return rows
