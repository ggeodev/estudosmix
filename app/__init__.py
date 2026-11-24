from pathlib import Path

from flask import Flask, abort, send_from_directory

from . import db
from .config import Config

ROOT = Path(__file__).resolve().parent.parent
FILES = {  # arquivos de ajuda para download na tela de importação
    "exemplo.json": ROOT / "samples",
    "FORMATO_IMPORTACAO.md": ROOT / "docs",
    "PROMPT_CONVERSAO_PDF.md": ROOT / "docs",
}


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    db.init_app(app)
    db.run_migrations(app.config["DATABASE_PATH"])
    with app.app_context():
        from .services import pdf_import
        pdf_import.reset_stuck()  # PDFs que ficaram "processando" quando o app foi fechado
        if app.config.get("PDF_WORKER") and db.one("SELECT 1 AS x FROM pdf_jobs WHERE status = 'queued'"):
            pdf_import.ensure_worker(app)

    from .routes import register_routes
    register_routes(app)

    static_dir = ROOT / "static"

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html", max_age=0)

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(static_dir, name, max_age=0)

    @app.get("/files/<name>")
    def files(name):
        if name not in FILES:
            abort(404)
        return send_from_directory(FILES[name], name, as_attachment=True)

    return app
