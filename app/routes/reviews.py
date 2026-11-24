from flask import Blueprint, jsonify, request

from ..services import reviews

bp = Blueprint("reviews", __name__)


@bp.get("/reviews")
def overview():
    return jsonify(reviews.overview())


@bp.post("/reviews/session")
def session():
    b = request.get_json(silent=True) or {}
    return jsonify({"id": reviews.create_session(b.get("limit", 15))}), 201
