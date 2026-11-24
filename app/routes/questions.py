from flask import Blueprint, jsonify, request

from ..errors import ApiError
from ..services import questions as svc
from . import json_body, opt_int

bp = Blueprint("questions", __name__)


def _filters():
    return {k: v for k, v in request.args.items() if k not in ("page", "per_page")}


@bp.get("/questions")
def list_questions():
    try:
        return jsonify(svc.list_questions(_filters(), request.args.get("page", 1), request.args.get("per_page", 25)))
    except ValueError:
        raise ApiError("Parâmetro de filtro inválido.")


@bp.get("/questions/count")
def count():
    try:
        return jsonify({"total": svc.count(_filters())})
    except ValueError:
        raise ApiError("Parâmetro de filtro inválido.")


@bp.get("/questions/facets")
def facets():
    return jsonify(svc.facets())


@bp.get("/questions/<int:question_id>")
def get_question(question_id):
    return jsonify(svc.get_question(question_id))


@bp.patch("/questions/<int:question_id>")
def update_question(question_id):
    b = json_body()
    skipped = 0
    if b.get("subject_id") is not None:
        svc.move_subject(question_id, opt_int(b["subject_id"]))
    if b.get("add_topic_ids") or b.get("remove_topic_ids"):
        skipped = svc.set_topics(question_id, b.get("add_topic_ids") or [], b.get("remove_topic_ids") or [])
    return jsonify({"ok": True, "skipped_other_subject": skipped})


@bp.post("/questions/bulk-topics")
def bulk_topics():
    b = json_body()
    ids = b.get("question_ids") or []
    if not ids:
        raise ApiError("Selecione ao menos uma questão.")
    return jsonify(svc.bulk_topics(ids, b.get("add_topic_ids") or [], b.get("remove_topic_ids") or []))


@bp.post("/questions/<int:question_id>/flag")
def flag(question_id):
    return jsonify({"flagged": svc.toggle_flag(question_id)})
