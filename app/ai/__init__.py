"""Camada de IA: o resto do app só usa run_text / run_json / run_pdf e nunca conhece o provedor concreto."""
import json
import os
import re

from .. import db
from ..util import now_iso
from .base import AIError, Provider


def get_provider():
    name = os.environ.get("AI_PROVIDER", "gemini").lower()
    if name == "fake":
        from .fake import FakeProvider
        return FakeProvider()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise AIError("A IA não está configurada. Informe sua chave de API em Configurações → IA.", "not_configured", 400)
    from .gemini import GeminiProvider
    return GeminiProvider(key, os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                          os.environ.get("GEMINI_EXTRACTION_MODEL", "gemini-3.5-flash"))


def status():
    name = os.environ.get("AI_PROVIDER", "gemini").lower()
    configured = name == "fake" or bool(os.environ.get("GEMINI_API_KEY", "").strip())
    return {
        "provider": name, "configured": configured,
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite") if name != "fake" else "fake-model",
        "extraction_model": os.environ.get("GEMINI_EXTRACTION_MODEL", "gemini-3.5-flash") if name != "fake" else "fake-extraction",
    }


def _log(feature, model, ok, error, in_chars, out_chars):
    try:
        db.execute(
            "INSERT INTO ai_calls (feature, model, ok, error, input_chars, output_chars, created_at) VALUES (?,?,?,?,?,?,?)",
            (feature, model, int(ok), (error or "")[:300] or None, in_chars, out_chars, now_iso()))
        db.get_db().commit()
    except Exception:  # log nunca pode quebrar a funcionalidade
        pass


def _contents(prompt_or_messages):
    if isinstance(prompt_or_messages, str):
        return [{"role": "user", "parts": [{"text": prompt_or_messages}]}]
    return [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in prompt_or_messages]


def run_text(feature, system, prompt_or_messages, json_mode=False):
    p = get_provider()
    contents = _contents(prompt_or_messages)
    size = sum(len(c["parts"][0]["text"]) for c in contents) + len(system or "")
    try:
        out = p.generate(feature, system, contents, json_mode=json_mode)
    except AIError as e:
        _log(feature, p.model, False, e.message, size, 0)
        raise
    _log(feature, p.model, True, None, size, len(out))
    return out


def run_pdf(feature, system, prompt, pdf_bytes):
    p = get_provider()
    try:
        out = p.generate_pdf(feature, system, prompt, pdf_bytes)
    except AIError as e:
        _log(feature, p.extraction_model, False, e.message, len(pdf_bytes) // 4, 0)
        raise
    _log(feature, p.extraction_model, True, None, len(pdf_bytes) // 4, len(out))
    return out


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    m = re.search(r"[\[{]", t)
    if m:
        end = max(t.rfind("}"), t.rfind("]"))
        try:
            return json.loads(t[m.start(): end + 1])
        except ValueError:
            pass
    raise AIError("A IA devolveu um formato inesperado (JSON inválido). Tente novamente.", "bad_output")


def run_json(feature, system, prompt):
    return parse_json(run_text(feature, system, prompt, json_mode=True))


def usage():
    row = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(ok),0) AS ok FROM ai_calls")
    recent = db.query("SELECT feature, COUNT(*) AS n FROM ai_calls GROUP BY feature ORDER BY n DESC")
    last_err = db.one("SELECT error, created_at FROM ai_calls WHERE ok = 0 ORDER BY id DESC LIMIT 1")
    return {"calls": row["n"], "failed": row["n"] - row["ok"], "by_feature": recent, "last_error": last_err}
