"""Camada de acesso a dados.

Todo SQL do projeto passa por este módulo (query/one/execute). Para migrar para
PostgreSQL basta trocar a conexão e o dialeto aqui e nos arquivos de migração
(AUTOINCREMENT -> IDENTITY, placeholders '?' -> '%s'). As regras de negócio
ficam em app/services e não dependem do banco.
"""
import sqlite3
from pathlib import Path

from flask import current_app, g

from .util import now_iso

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        if exc is None:
            conn.commit()
        else:
            conn.rollback()
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql, params=()):
    return [dict(r) for r in get_db().execute(sql, params).fetchall()]


def one(sql, params=()):
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def scalar(sql, params=(), default=0):
    row = get_db().execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else default


def execute(sql, params=()):
    return get_db().execute(sql, params).lastrowid


def placeholders(n):
    return ",".join("?" * n)


def run_migrations(path):
    conn = connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in applied:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)", (f.name, now_iso()))
        conn.commit()
    conn.close()


def backup_to(dest_path):
    """Cópia consistente do banco (SQLite backup API)."""
    dest = sqlite3.connect(dest_path)
    try:
        get_db().backup(dest)
    finally:
        dest.close()
