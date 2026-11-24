import os
import tempfile
from datetime import datetime

from flask import Blueprint, after_this_request, current_app, jsonify, send_file

from .. import db
from ..errors import ApiError
from ..util import jdumps, jloads
from . import json_body

bp = Blueprint("system", __name__)
ALLOWED_SETTINGS = {"theme": {"dark", "light"}, "show_timer": {True, False}}


@bp.get("/settings")
def get_settings():
    rows = db.query("SELECT key, value FROM settings")
    out = {"theme": "dark", "show_timer": True}
    out.update({r["key"]: jloads(r["value"]) for r in rows})
    return jsonify(out)


@bp.put("/settings")
def put_settings():
    for key, value in json_body().items():
        if key not in ALLOWED_SETTINGS or value not in ALLOWED_SETTINGS[key]:
            raise ApiError(f"Configuração inválida: {key}.")
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, jdumps(value)),
        )
    return get_settings()


@bp.get("/system/info")
def info():
    path = current_app.config["DATABASE_PATH"]
    return jsonify({
        "database_path": path,
        "database_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "questions": db.scalar("SELECT COUNT(*) FROM questions"),
        "answers": db.scalar("SELECT COUNT(*) FROM answers"),
        "sessions": db.scalar("SELECT COUNT(*) FROM sessions"),
    })


@bp.get("/backup")
def backup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db.backup_to(tmp.name)

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        return response

    name = f"estudos-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    return send_file(tmp.name, as_attachment=True, download_name=name, mimetype="application/octet-stream")
