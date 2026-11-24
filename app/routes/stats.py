from flask import Blueprint, jsonify, request

from ..services import stats as svc

bp = Blueprint("stats", __name__)


def _tz():
    try:
        return -int(request.args.get("tz", 0))  # JS getTimezoneOffset(): minutos ATRÁS do UTC
    except ValueError:
        return 0


@bp.get("/dashboard")
def dashboard():
    return jsonify(svc.dashboard(_tz()))


@bp.get("/stats")
def stats():
    days = request.args.get("days")
    return jsonify(svc.stats(int(days) if days else None, _tz()))
