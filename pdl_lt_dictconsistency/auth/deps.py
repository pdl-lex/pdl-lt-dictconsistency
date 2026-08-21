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


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(403, "Nur für Administratoren.")
    return user
