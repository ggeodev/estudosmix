from flask import Blueprint, jsonify

from ..services import taxonomy as svc
from . import json_body, opt_int

bp = Blueprint("taxonomy", __name__)
_UNSET = ...


@bp.get("/taxonomy")
def get_tree():
    return jsonify(svc.tree())


@bp.post("/exams")
def create_exam():
    return jsonify({"id": svc.create_exam(json_body().get("name"))}), 201


@bp.patch("/exams/<int:exam_id>")
def update_exam(exam_id):
    svc.update_exam(exam_id, json_body().get("name"))
    return jsonify({"ok": True})


@bp.delete("/exams/<int:exam_id>")
def delete_exam(exam_id):
    svc.delete_exam(exam_id)
    return jsonify({"ok": True})


@bp.post("/subjects")
def create_subject():
    b = json_body()
    return jsonify({"id": svc.create_subject(b.get("name"), opt_int(b.get("exam_id")))}), 201


@bp.patch("/subjects/<int:subject_id>")
def update_subject(subject_id):
    b = json_body()
    svc.update_subject(subject_id, b.get("name"), opt_int(b["exam_id"]) if "exam_id" in b else _UNSET)
    return jsonify({"ok": True})


@bp.delete("/subjects/<int:subject_id>")
def delete_subject(subject_id):
    svc.delete_subject(subject_id)
    return jsonify({"ok": True})


@bp.post("/topics")
def create_topic():
    b = json_body()
    return jsonify({"id": svc.create_topic(b.get("name"), opt_int(b.get("subject_id")), opt_int(b.get("parent_id")))}), 201


@bp.patch("/topics/<int:topic_id>")
def update_topic(topic_id):
    b = json_body()
    svc.update_topic(topic_id, b.get("name"), opt_int(b["parent_id"]) if "parent_id" in b else _UNSET)
    return jsonify({"ok": True})


@bp.delete("/topics/<int:topic_id>")
def delete_topic(topic_id):
    svc.delete_topic(topic_id)
    return jsonify({"ok": True})
