from flask import Blueprint, jsonify, request

from ..services import study
from . import json_body

bp = Blueprint("study", __name__)


@bp.get("/gaps")
def gaps():
    sid = request.args.get("session_id")
    return jsonify({"items": study.open_gaps(int(sid) if sid else None)})


@bp.post("/gaps/name-concepts")
def name_concepts():
    b = json_body()
    ids = b.get("question_ids")
    if not ids:
        ids = [g["question_id"] for g in study.open_gaps(b.get("session_id"))]
    return jsonify(study.name_concepts([int(i) for i in ids]))


@bp.get("/sessions/<int:session_id>/analysis")
def analysis(session_id):
    return jsonify(study.session_analysis(session_id))


@bp.get("/study/records")
def records():
    return jsonify(study.list_records())


@bp.get("/study/<int:question_id>")
def state(question_id):
    return jsonify(study.study_state(question_id))


@bp.post("/study/<int:question_id>/material")
def material(question_id):
    b = request.get_json(silent=True) or {}
    return jsonify(study.get_material(question_id, b.get("level", "normal"), bool(b.get("force"))))


@bp.post("/study/<int:question_id>/verification")
def verification(question_id):
    b = request.get_json(silent=True) or {}
    return jsonify(study.start_verification(question_id, b.get("mode", "auto"))), 201


@bp.post("/study/<int:question_id>/record")
def record(question_id):
    return jsonify(study.record_outcome(question_id, json_body().get("session_id")))
