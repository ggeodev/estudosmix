from flask import Blueprint, jsonify, request

from ..services import tutor
from . import json_body

bp = Blueprint("tutor", __name__)


@bp.get("/tutor/threads")
def threads():
    return jsonify(tutor.threads())


@bp.get("/tutor/history")
def history():
    return jsonify(tutor.history(request.args.get("thread", "free")))


@bp.delete("/tutor/history")
def clear():
    tutor.clear(request.args.get("thread", "free"))
    return jsonify({"ok": True})


@bp.post("/tutor/chat")
def chat():
    b = json_body()
    return jsonify(tutor.chat(b.get("thread", "free"), b.get("message")))
