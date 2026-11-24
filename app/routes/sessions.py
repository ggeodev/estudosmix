from flask import Blueprint, jsonify, request

from ..services import sessions as svc
from . import json_body

bp = Blueprint("sessions", __name__)


@bp.get("/meta")
def meta():
    return jsonify({"kinds": svc.KINDS, "error_types": svc.ERROR_TYPES})


@bp.post("/sessions")
def create():
    return jsonify({"id": svc.create(json_body())}), 201


@bp.get("/sessions")
def list_sessions():
    return jsonify(svc.list_sessions(
        int(request.args.get("limit", 20)), int(request.args.get("offset", 0)),
        request.args.get("in_progress") == "1"))


@bp.get("/sessions/<int:session_id>")
def get(session_id):
    return jsonify(svc.get(session_id))


@bp.delete("/sessions/<int:session_id>")
def delete(session_id):
    svc.delete(session_id)
    return jsonify({"ok": True})


@bp.post("/sessions/<int:session_id>/answers")
def answer(session_id):
    return jsonify(svc.answer(session_id, json_body()))


@bp.post("/sessions/<int:session_id>/finish")
def finish(session_id):
    return jsonify(svc.finish(session_id))


@bp.get("/sessions/<int:session_id>/results")
def results(session_id):
    return jsonify(svc.results(session_id))


@bp.patch("/answers/<int:answer_id>")
def set_error(answer_id):
    b = json_body()
    svc.set_error(answer_id, b.get("error_type"), b.get("error_note"))
    return jsonify({"ok": True})
