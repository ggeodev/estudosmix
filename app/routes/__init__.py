from flask import Blueprint, jsonify, request

from ..errors import ApiError


def json_body():
    data = request.get_json(silent=True)
    if data is None:
        raise ApiError("Corpo da requisição inválido (JSON esperado).")
    return data


def opt_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError("Identificador inválido.")


def register_routes(app):
    from . import ai, imports, questions, reviews, sessions, stats, study, system, taxonomy, tutor
    for mod in (taxonomy, questions, imports, sessions, stats, system, ai, study, reviews, tutor):
        app.register_blueprint(mod.bp, url_prefix="/api")

    @app.errorhandler(ApiError)
    def handle_api_error(e):
        payload = {"error": e.message}
        if e.details:
            payload["details"] = e.details
        return jsonify(payload), e.status

    from ..ai.base import AIError

    @app.errorhandler(AIError)
    def handle_ai_error(e):
        return jsonify({"error": e.message, "kind": e.kind}), e.status

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Rota não encontrada."}), 404
        return e

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Erro inesperado")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Erro interno do servidor. Veja o terminal para detalhes."}), 500
        raise e
