import os

from flask import Blueprint, jsonify

from .. import ai as ai_layer
from ..config import save_env
from ..errors import ApiError
from . import json_body

bp = Blueprint("ai", __name__)


@bp.get("/ai/status")
def status():
    return jsonify({**ai_layer.status(), "usage": ai_layer.usage()})


@bp.put("/ai/config")
def config():
    b = json_body()
    updates = {}
    key = (b.get("api_key") or "").strip()
    if key:
        if len(key) < 20 or any(c.isspace() for c in key):
            raise ApiError("Essa chave não parece válida (sem espaços, ao menos 20 caracteres).")
        updates["GEMINI_API_KEY"] = key
    for field, env in (("model", "GEMINI_MODEL"), ("extraction_model", "GEMINI_EXTRACTION_MODEL")):
        v = (b.get(field) or "").strip()
        if v:
            if not v.replace("-", "").replace(".", "").replace("_", "").isalnum():
                raise ApiError("Nome de modelo inválido.")
            updates[env] = v
    if not updates:
        raise ApiError("Nada para salvar.")
    save_env(updates)
    return jsonify(ai_layer.status())  # a chave nunca é devolvida


@bp.post("/ai/test")
def test():
    out = ai_layer.run_text("test", None, "Responda apenas com a palavra: ok")
    return jsonify({"ok": True, "reply": out.strip()[:80], **ai_layer.status()})
