"""Server-seitige Cookie-Sessions (kein JWT).

Das Klartext-Token verlässt den Server-Prozess nie außer im Set-Cookie-Header;
gespeichert wird nur sein SHA-256-Hash, damit ein Lesezugriff auf local.db
allein keine Sessions kapern kann.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from . import db

COOKIE_NAME = "lt_session"
SESSION_LIFETIME = timedelta(days=14)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, expires_at.isoformat()),
        )
    return token


def resolve_session(token: str) -> dict | None:
    """Nutzer zu einem Session-Token, sofern Session gültig und Account aktiv ist."""
    token_hash = _hash_token(token)
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.wbdb_principal_id, u.is_admin, u.active
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > datetime('now')
            """,
            (token_hash,),
        ).fetchone()
        if row is None or not row["active"]:
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_at = datetime('now') WHERE token_hash = ?",
            (token_hash,),
        )
        return dict(row)


def revoke_session(token: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
