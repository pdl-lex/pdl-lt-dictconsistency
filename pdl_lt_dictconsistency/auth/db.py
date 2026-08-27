"""Lokale SQLite-Datenbank für Accounts/Sessions.

wbdb hat kein Passwort-Konzept — Anmeldedaten müssen ohnehin lokal liegen.
Zwei Tabellen, kein ORM. Pfad über LT_LOCAL_DB_PATH (Default ./local.db),
analog zur bestehenden LT_DATA_ROOTS-Konvention.
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOCAL_DB_PATH_ENV = "LT_LOCAL_DB_PATH"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    wbdb_principal_id TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def local_db_path() -> Path:
    return Path(os.environ.get(LOCAL_DB_PATH_ENV, "./local.db")).expanduser().resolve()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(local_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL statt des Rollback-Journals: der wbdb-Reindex (wbdb/index_store.py)
    # schreibt hier jetzt auch in großen Batches, und WAL lässt Sessions/Logins
    # währenddessen weiterlesen statt zu blockieren.
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Schema anlegen, falls noch nicht vorhanden. Idempotent, beim App-Start aufgerufen."""
    with connect() as conn:
        conn.executescript(_SCHEMA)
