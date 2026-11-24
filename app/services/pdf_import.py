"""Conversão de PDFs de questões em JSON com IA, em segundo plano.

Cada PDF vira um 'job'. O PDF é dividido em trechos de poucas páginas (com 1 página de sobreposição) para caber na
resposta da IA; questões repetidas na sobreposição são removidas e questões cortadas são descartadas pela IA ou
marcadas como inválidas na prévia. O resultado NUNCA entra no banco direto: vai para a mesma prévia de importação.
"""
import io
import os
import threading
import time
from pathlib import Path

from .. import ai, db
from ..ai import prompts
from ..errors import ApiError
from ..util import jdumps, jloads, now_iso
from . import importer

CHUNK_PAGES = 6
OVERLAP = 1
MAX_PDF_BYTES = 40 * 1024 * 1024
_lock = threading.Lock()
_worker = {"thread": None}


def upload_dir(app):
    d = Path(app.config["DATABASE_PATH"]).parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def enqueue(app, filename, data, subject_hint=None):
    if not data.startswith(b"%PDF"):
        raise ApiError(f"'{filename}' não parece ser um PDF válido.")
    if len(data) > MAX_PDF_BYTES:
        raise ApiError(f"'{filename}' é grande demais (máx. 40 MB).")
    jid = db.execute(
        "INSERT INTO pdf_jobs (filename, status, subject_hint, created_at) VALUES (?, 'queued', ?, ?)",
        (filename, (subject_hint or "").strip() or None, now_iso()))
    (upload_dir(app) / f"{jid}.pdf").write_bytes(data)
    db.get_db().commit()
    if app.config.get("PDF_WORKER"):
        ensure_worker(app)
    return jid


def _chunks(data):
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(data))
    n = len(reader.pages)
    if n <= CHUNK_PAGES:
        return [data], n
    out, start = [], 0
    while start < n:
        end = min(start + CHUNK_PAGES, n)
        w = PdfWriter()
        for i in range(start, end):
            w.add_page(reader.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        out.append(buf.getvalue())
        if end >= n:
            break
        start = end - OVERLAP
    return out, n


def _update(job_id, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE pdf_jobs SET {sets} WHERE id = ?", list(fields.values()) + [job_id])
    db.get_db().commit()


def process_job(app, job_id):
    """Processa um job (precisa de app context)."""
    job = db.one("SELECT * FROM pdf_jobs WHERE id = ?", (job_id,))
    path = upload_dir(app) / f"{job_id}.pdf"
    if not job or not path.exists():
        _update(job_id, status="error", error="Arquivo do PDF não encontrado.", finished_at=now_iso())
        return
    _update(job_id, status="processing", error=None)
    try:
        chunks, pages = _chunks(path.read_bytes())
    except Exception as e:
        _update(job_id, status="error", error=f"Não foi possível ler o PDF: {e}", finished_at=now_iso())
        return
    _update(job_id, chunks_total=len(chunks), chunks_done=0)
    questions, omitted, warnings, seen = [], [], [], set()
    ok_chunks = 0
    prompt = prompts.extraction_prompt(job["subject_hint"], job["filename"])
    for i, chunk in enumerate(chunks, 1):
        try:
            data = ai.parse_json(ai.run_pdf("pdf_extract", prompts.EXTRACT_SYSTEM, prompt, chunk))
            qs = data.get("questions") if isinstance(data, dict) else data
            if not isinstance(qs, list):
                raise ai.AIError("formato inesperado", "bad_output")
            for q in qs:
                if not isinstance(q, dict):
                    continue
                key = (str(q.get("id")) if q.get("id") else None) or importer_key(q)
                if key in seen:
                    continue
                seen.add(key)
                q["source_pdf"] = job["filename"]
                questions.append(q)
            if isinstance(data, dict):
                omitted += [str(o) for o in (data.get("omitted") or [])]
            ok_chunks += 1
        except ai.AIError as e:
            warnings.append(f"Trecho {i}/{len(chunks)} falhou: {e.message}")
            if e.kind in ("auth", "not_configured"):
                break  # não adianta continuar
        _update(job_id, chunks_done=i)
        time.sleep(0 if app.config.get("TESTING") else 1)
    if ok_chunks == 0:
        _update(job_id, status="error", error=warnings[-1] if warnings else "Falha ao processar o PDF.",
                warnings=jdumps(warnings), finished_at=now_iso())
        return
    meta = {"source": "PDF (IA)", "filename": job["filename"]}
    if job["subject_hint"]:
        meta["subject"] = job["subject_hint"]
    _update(job_id, status="done", n_questions=len(questions), n_omitted=len(omitted), warnings=jdumps(warnings),
            result=jdumps({"metadata": meta, "questions": questions, "omitted": omitted}), finished_at=now_iso())
    try:
        path.unlink()
    except OSError:
        pass


def importer_key(q):
    return "h:" + str(hash((str(q.get("statement")), jdumps(q.get("alternatives")))))


def process_all(app):
    """Processa todos os jobs 'queued' em sequência (usado pela thread e pelos testes)."""
    while True:
        with app.app_context():
            row = db.one("SELECT id FROM pdf_jobs WHERE status = 'queued' ORDER BY id LIMIT 1")
            if not row:
                return
            process_job(app, row["id"])


def ensure_worker(app):
    with _lock:
        t = _worker["thread"]
        if t and t.is_alive():
            return
        t = threading.Thread(target=process_all, args=(app,), daemon=True, name="pdf-worker")
        _worker["thread"] = t
        t.start()


def reset_stuck():
    db.execute("UPDATE pdf_jobs SET status = 'queued' WHERE status = 'processing'")


def list_jobs():
    rows = db.query("""SELECT id, filename, status, error, subject_hint, chunks_total, chunks_done, n_questions, n_omitted,
                       warnings, imported_at, created_at, finished_at FROM pdf_jobs ORDER BY id DESC LIMIT 200""")
    for r in rows:
        r["warnings"] = jloads(r["warnings"], [])
    return rows


def combine(job_ids):
    if not job_ids:
        raise ApiError("Selecione ao menos um PDF concluído.")
    qs, omitted = [], []
    for jid in job_ids:
        job = db.one("SELECT filename, status, result FROM pdf_jobs WHERE id = ?", (jid,))
        if not job or job["status"] != "done":
            raise ApiError("Só é possível revisar PDFs concluídos.", 409)
        res = jloads(job["result"], {})
        qs += res.get("questions", [])
        omitted += [f"{job['filename']}: {o}" for o in res.get("omitted", [])]
    return {"metadata": {"source": "PDF (IA)", "omitted": omitted}, "questions": qs}


def mark_imported(job_ids):
    for jid in job_ids or []:
        db.execute("UPDATE pdf_jobs SET imported_at = ? WHERE id = ? AND status = 'done'", (now_iso(), jid))


def retry(app, job_id):
    job = db.one("SELECT status FROM pdf_jobs WHERE id = ?", (job_id,))
    if not job:
        raise ApiError("Tarefa não encontrada.", 404)
    if job["status"] != "error":
        raise ApiError("Só é possível tentar de novo tarefas com erro.", 409)
    if not (upload_dir(app) / f"{job_id}.pdf").exists():
        raise ApiError("O arquivo original não está mais disponível; envie o PDF novamente.", 409)
    db.execute("UPDATE pdf_jobs SET status = 'queued', error = NULL WHERE id = ?", (job_id,))
    db.get_db().commit()
    if app.config.get("PDF_WORKER"):
        ensure_worker(app)


def delete(app, job_id):
    if not db.one("SELECT id FROM pdf_jobs WHERE id = ?", (job_id,)):
        raise ApiError("Tarefa não encontrada.", 404)
    db.execute("DELETE FROM pdf_jobs WHERE id = ?", (job_id,))
    try:
        (upload_dir(app) / f"{job_id}.pdf").unlink()
    except OSError:
        pass
