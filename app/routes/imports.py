from flask import Blueprint, current_app, jsonify, request

from ..errors import ApiError
from ..services import importer, pdf_import
from . import json_body, opt_int

bp = Blueprint("imports", __name__)


@bp.post("/imports/preview")
def preview():
    return jsonify(importer.preview(json_body().get("data")))


@bp.post("/imports/commit")
def commit():
    b = json_body()
    res = importer.commit(b.get("data"), opt_int(b.get("exam_id")), b.get("filename"))
    pdf_import.mark_imported(b.get("pdf_job_ids"))
    return jsonify(res), 201


@bp.get("/imports")
def list_imports():
    return jsonify(importer.list_imports())


@bp.delete("/imports/<int:import_id>")
def delete_import(import_id):
    return jsonify(importer.delete_import(import_id))


# ---- conversão de PDF com IA ----
@bp.post("/pdf-jobs")
def upload_pdf():
    files = request.files.getlist("files")
    if not files:
        raise ApiError("Nenhum arquivo enviado.")
    ids = [pdf_import.enqueue(current_app._get_current_object(), f.filename or "arquivo.pdf", f.read(), request.form.get("subject"))
           for f in files]
    return jsonify({"ids": ids}), 201


@bp.get("/pdf-jobs")
def list_jobs():
    return jsonify(pdf_import.list_jobs())


@bp.post("/pdf-jobs/combine")
def combine():
    return jsonify(pdf_import.combine(json_body().get("job_ids") or []))


@bp.post("/pdf-jobs/<int:job_id>/retry")
def retry(job_id):
    pdf_import.retry(current_app._get_current_object(), job_id)
    return jsonify({"ok": True})


@bp.delete("/pdf-jobs/<int:job_id>")
def delete_job(job_id):
    pdf_import.delete(current_app._get_current_object(), job_id)
    return jsonify({"ok": True})
