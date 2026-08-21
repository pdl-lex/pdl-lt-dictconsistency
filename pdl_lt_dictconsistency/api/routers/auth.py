"""API-Endpunkte für Login, Logout und den aktuell angemeldeten Nutzer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ...auth import db as auth_db
from ...auth.deps import get_current_user
from ...auth.passwords import verify_password
from ...auth.sessions import COOKIE_NAME, SESSION_LIFETIME, create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    wbdb_principal_id: str | None
    is_admin: bool


def _user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=user["id"],
        username=user["username"],
        wbdb_principal_id=user["wbdb_principal_id"],
        is_admin=bool(user["is_admin"]),
    )


@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, request: Request, response: Response) -> UserResponse:
    with auth_db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (req.username,)).fetchone()
    if row is None or not row["active"] or not verify_password(row["password_hash"], req.password):
        raise HTTPException(401, "Benutzername oder Passwort falsch.")

    token = create_session(row["id"])
    response.set_cookie(
        COOKIE_NAME, token,
        httponly=True, samesite="lax", secure=request.url.scheme == "https",
        max_age=int(SESSION_LIFETIME.total_seconds()), path="/",
    )
    return _user_response(dict(row))


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        revoke_session(token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)
