"""Validação, prévia e importação de questões em JSON."""
import hashlib
import re

from .. import db
from ..errors import ApiError
from ..util import jdumps, now_iso
from . import taxonomy

KNOWN_FIELDS = {
    "id", "subject", "topics", "bank", "year", "organization", "exam_name", "statement",
    "support_text", "alternatives", "correct_answer", "explanation", "difficulty", "images",
}
LETTERS = "ABCDEFGHIJ"


def _text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def content_hash(statement, support_text, alternatives):
    norm = lambda s: re.sub(r"\s+", " ", (s or "")).strip().lower()
    base = norm(statement) + "|" + norm(support_text) + "|" + "|".join(norm(alternatives[k]) for k in sorted(alternatives))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _normalize_alternatives(raw, errors):
    if isinstance(raw, list):
        raw = {LETTERS[i]: v for i, v in enumerate(raw) if i < len(LETTERS)}
    if not isinstance(raw, dict):
        errors.append("'alternatives' deve ser um objeto {\"A\": \"...\", \"B\": \"...\"}.")
        return None
    out = {}
    for k, v in raw.items():
        key = str(k).strip().upper()
        text = _text(v)
        if not re.fullmatch(r"[A-J]", key):
            errors.append(f"Letra de alternativa inválida: '{k}'.")
        elif text is None:
            errors.append(f"A alternativa {key} está vazia.")
        else:
            out[key] = text
    if len(out) < 2:
        errors.append("São necessárias ao menos 2 alternativas.")
        return None
    return out


def _normalize_images(raw, warnings):
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        warnings.append("'images' deveria ser uma lista; o valor original foi preservado em 'extra'.")
        return None
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"src": item, "caption": None})
        elif isinstance(item, dict) and (item.get("src") or item.get("url") or item.get("data")):
            out.append({"src": item.get("src") or item.get("url") or item.get("data"), "caption": item.get("caption")})
        else:
            warnings.append("Uma imagem sem 'src' foi ignorada.")
    return out


def validate_question(raw, defaults):
    """Retorna (registro_normalizado | None, erros, avisos)."""
    errors, warnings = [], []
    if not isinstance(raw, dict):
        return None, ["A questão deve ser um objeto JSON."], []

    statement = _text(raw.get("statement"))
    if not statement:
        errors.append("Campo obrigatório ausente: 'statement' (enunciado).")

    alternatives = _normalize_alternatives(raw.get("alternatives"), errors) if "alternatives" in raw else None
    if "alternatives" not in raw:
        errors.append("Campo obrigatório ausente: 'alternatives'.")

    correct = _text(raw.get("correct_answer"))
    correct = correct.upper() if correct else None
    if not correct:
        errors.append("Campo obrigatório ausente: 'correct_answer' (gabarito).")
    elif alternatives and correct not in alternatives:
        errors.append(f"O gabarito '{correct}' não existe entre as alternativas ({', '.join(sorted(alternatives))}).")

    subject = _text(raw.get("subject")) or defaults.get("subject")
    if not subject:
        errors.append("Disciplina ausente: informe 'subject' na questão ou em 'metadata'.")

    extra = {k: v for k, v in raw.items() if k not in KNOWN_FIELDS}

    topics = raw.get("topics")
    if topics is None:
        topics = []
    elif isinstance(topics, str):
        topics = [topics]
    if not isinstance(topics, list):
        warnings.append("'topics' deveria ser uma lista; valor preservado em 'extra'.")
        extra["topics"] = topics
        topics = []
    topics = [t for t in (_text(t) for t in topics) if t]

    year = None
    if raw.get("year") not in (None, ""):
        try:
            year = int(str(raw["year"]).strip())
        except ValueError:
            warnings.append(f"Ano inválido ('{raw['year']}'); valor preservado em 'extra'.")
            extra["year"] = raw["year"]

    images = _normalize_images(raw.get("images"), warnings)
    if images is None:
        extra["images"] = raw.get("images")
        images = []

    ext_id = _text(raw.get("id"))
    if not ext_id:
        warnings.append("Sem 'id' original: a detecção de duplicadas usará o texto da questão.")
    if not _text(raw.get("explanation")):
        warnings.append("Sem explicação.")
    if extra:
        warnings.append("Campos extras preservados: " + ", ".join(sorted(extra)))

    if errors:
        return None, errors, warnings

    record = {
        "external_id": ext_id,
        "subject": subject,
        "topics": topics,
        "bank": _text(raw.get("bank")) or defaults.get("bank"),
        "year": year,
        "organization": _text(raw.get("organization")),
        "exam_name": _text(raw.get("exam_name")) or defaults.get("exam"),
        "statement": statement,
        "support_text": _text(raw.get("support_text")),
        "alternatives": alternatives,
        "correct_answer": correct,
        "explanation": _text(raw.get("explanation")),
        "difficulty": _text(raw.get("difficulty")),
        "images": images,
        "extra": extra,
    }
    record["content_hash"] = content_hash(statement, record["support_text"], alternatives)
    return record, errors, warnings


def parse_payload(payload):
    if isinstance(payload, list):
        payload = {"metadata": {}, "questions": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise ApiError("Arquivo inválido: esperado um objeto JSON com a lista \"questions\".")
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    defaults = {"subject": _text(meta.get("subject")), "bank": _text(meta.get("bank")), "exam": _text(meta.get("exam"))}
    return meta, defaults, payload["questions"]


def analyze(payload):
    meta, defaults, questions = parse_payload(payload)
    existing_ids = {r["external_id"] for r in db.query("SELECT external_id FROM questions WHERE external_id IS NOT NULL")}
    existing_hashes = {r["content_hash"] for r in db.query("SELECT content_hash FROM questions")}
    seen_ids, seen_hashes = set(), set()
    items, valid_records = [], []
    for i, raw in enumerate(questions):
        rec, errors, warnings = validate_question(raw, defaults)
        status, reason = "valid", None
        if rec is None:
            status = "invalid"
        else:
            if rec["external_id"] and rec["external_id"] in existing_ids:
                status, reason = "duplicate", f"ID {rec['external_id']} já existe no banco."
            elif rec["content_hash"] in existing_hashes:
                status, reason = "duplicate", "Questão idêntica já existe no banco."
            elif rec["external_id"] and rec["external_id"] in seen_ids:
                status, reason = "duplicate", f"ID {rec['external_id']} repetido neste arquivo."
            elif rec["content_hash"] in seen_hashes:
                status, reason = "duplicate", "Questão repetida neste arquivo."
            if status == "valid":
                valid_records.append(rec)
            if rec["external_id"]:
                seen_ids.add(rec["external_id"])
            seen_hashes.add(rec["content_hash"])
        stmt = ""
        if isinstance(raw, dict):
            stmt = (_text(raw.get("statement")) or "")
        items.append({
            "index": i + 1,
            "id": (rec or {}).get("external_id") or (_text(raw.get("id")) if isinstance(raw, dict) else None),
            "subject": (rec or {}).get("subject") or (_text(raw.get("subject")) if isinstance(raw, dict) else None) or defaults.get("subject"),
            "preview": stmt[:160],
            "status": status,
            "reason": reason,
            "errors": errors,
            "warnings": warnings,
        })
    counts = {s: sum(1 for it in items if it["status"] == s) for s in ("valid", "invalid", "duplicate")}
    counts["total"] = len(items)
    subjects = sorted({r["subject"] for r in valid_records})
    topics = sorted({t for r in valid_records for t in r["topics"]})
    return {
        "metadata": meta,
        "counts": counts,
        "subjects": subjects,
        "topics": topics,
        "items": items,
    }, valid_records


def preview(payload):
    report, _ = analyze(payload)
    return report


def commit(payload, exam_id=None, filename=None):
    if exam_id is not None and not db.one("SELECT id FROM exams WHERE id = ?", (exam_id,)):
        raise ApiError("Concurso não encontrado.", 404)
    report, records = analyze(payload)
    if not records:
        raise ApiError("Não há questões válidas para importar.")
    counts = report["counts"]
    import_id = db.execute(
        "INSERT INTO imports (filename, source, total, imported, duplicates, invalid, created_at) VALUES (?,?,?,?,?,?,?)",
        (filename, (report["metadata"] or {}).get("source"), counts["total"], len(records),
         counts["duplicate"], counts["invalid"], now_iso()),
    )
    subject_cache, topic_cache = {}, {}
    for rec in records:
        sid = subject_cache.get(rec["subject"].lower())
        if sid is None:
            sid = taxonomy.get_or_create_subject(rec["subject"], exam_id)
            subject_cache[rec["subject"].lower()] = sid
        qid = db.execute(
            """INSERT INTO questions (external_id, content_hash, subject_id, import_id, bank, year, organization,
                 exam_name, statement, support_text, alternatives, correct_answer, explanation, difficulty,
                 images, extra, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec["external_id"], rec["content_hash"], sid, import_id, rec["bank"], rec["year"], rec["organization"],
             rec["exam_name"], rec["statement"], rec["support_text"], jdumps(rec["alternatives"]),
             rec["correct_answer"], rec["explanation"], rec["difficulty"], jdumps(rec["images"]),
             jdumps(rec["extra"]), now_iso()),
        )
        for path in rec["topics"]:
            key = (sid, path.lower())
            tid = topic_cache.get(key)
            if tid is None:
                tid = taxonomy.get_or_create_topic_path(sid, path)
                topic_cache[key] = tid
            if tid:
                db.execute("INSERT INTO question_topics (question_id, topic_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (qid, tid))
    return {
        "import_id": import_id,
        "imported": len(records),
        "duplicates": counts["duplicate"],
        "invalid": counts["invalid"],
    }


def list_imports():
    return db.query(
        """SELECT i.*, (SELECT COUNT(*) FROM questions q WHERE q.import_id = i.id) AS current_questions
           FROM imports i ORDER BY i.id DESC"""
    )


def delete_import(import_id):
    if not db.one("SELECT id FROM imports WHERE id = ?", (import_id,)):
        raise ApiError("Importação não encontrada.", 404)
    removed = db.scalar("SELECT COUNT(*) FROM questions WHERE import_id = ?", (import_id,))
    db.execute("DELETE FROM questions WHERE import_id = ?", (import_id,))
    db.execute("DELETE FROM imports WHERE id = ?", (import_id,))
    return {"removed_questions": removed}
