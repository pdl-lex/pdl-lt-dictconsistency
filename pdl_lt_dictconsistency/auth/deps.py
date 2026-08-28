"""FastAPI-Dependencies für Login-Pflicht und Admin-Rechte."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .sessions import COOKIE_NAME, resolve_session


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user = resolve_session(token) if token else None
    if user is None:
        raise HTTPException(401, "Nicht angemeldet.")
    return user


def get_current_user_optional(request: Request) -> dict | None:
    """Wie `get_current_user`, aber ohne 401 — für Endpunkte, die auch ohne
    Login nutzbar sind (anonymer Zugriff auf öffentliche Daten)."""
    token = request.cookies.get(COOKIE_NAME)
    return resolve_session(token) if token else None


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(403, "Nur für Administratoren.")
    return user
