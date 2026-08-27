"""API-Endpunkte für den Admin-Bereich: lokale Nutzerverwaltung.

Verwaltet ausschließlich lokale Accounts (auth.db) und ihre Zuordnung zu einer
bereits in wbdb existierenden principal_id. Legt keine Principals an und
schreibt keine Grants — das bleibt vollständig Sache von wbdb (siehe Plan
Phase 4 / setup/Readme Access WBDB.md §2, „keine zweite Rechteverwaltung").
"""
from __future__ import annotations

import sqlite3

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...auth import db as auth_db
from ...auth.deps import require_admin
from ...auth.passwords import hash_password
from ...wbdb import index_store
from ...wbdb.connection import als, verbindung

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class UserOut(BaseModel):
    id: int
    username: str
    wbdb_principal_id: str | None
    is_admin: bool
    active: bool
    created_at: str


def _user_out(row: sqlite3.Row) -> UserOut:
    return UserOut(
        id=row["id"], username=row["username"], wbdb_principal_id=row["wbdb_principal_id"],
        is_admin=bool(row["is_admin"]), active=bool(row["active"]), created_at=row["created_at"],
    )


@router.get("/users", response_model=list[UserOut])
def list_users() -> list[UserOut]:
    with auth_db.connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    return [_user_out(r) for r in rows]


class CreateUserRequest(BaseModel):
    username: str
    password: str
    wbdb_principal_id: str | None = None
    is_admin: bool = False


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(req: CreateUserRequest) -> UserOut:
    username = req.username.strip()
    if not username or not req.password:
        raise HTTPException(422, "Benutzername und Passwort sind Pflicht.")
    principal = req.wbdb_principal_id.strip() if req.wbdb_principal_id else None
    with auth_db.connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, wbdb_principal_id, is_admin) "
                "VALUES (?, ?, ?, ?)",
                (username, hash_password(req.password), principal, int(req.is_admin)),
            )
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f"Benutzername {username!r} ist bereits vergeben.") from e
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _user_out(row)


class UpdateUserRequest(BaseModel):
    wbdb_principal_id: str | None = None
    is_admin: bool | None = None
    active: bool | None = None


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, req: UpdateUserRequest, admin: dict = Depends(require_admin)) -> UserOut:
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Keine Änderungen übermittelt.")
    if user_id == admin["id"] and (fields.get("active") is False or fields.get("is_admin") is False):
        raise HTTPException(400, "Der eigene Account kann nicht deaktiviert oder degradiert werden.")
    if "wbdb_principal_id" in fields:
        v = fields["wbdb_principal_id"]
        fields["wbdb_principal_id"] = v.strip() if v and v.strip() else None
    if "is_admin" in fields:
        fields["is_admin"] = int(fields["is_admin"])
    if "active" in fields:
        fields["active"] = int(fields["active"])

    with auth_db.connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, "Nutzer nicht gefunden.")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*fields.values(), user_id))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_out(row)


class PasswordResetRequest(BaseModel):
    password: str


@router.post("/users/{user_id}/password")
def reset_password(user_id: int, req: PasswordResetRequest) -> dict:
    if not req.password:
        raise HTTPException(422, "Passwort darf nicht leer sein.")
    with auth_db.connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(req.password), user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Nutzer nicht gefunden.")
    return {"status": "ok"}


class PrincipalOut(BaseModel):
    principal_id: str
    kind: str
    label: str
    active: bool


@router.get("/principals", response_model=list[PrincipalOut])
def list_principals() -> list[PrincipalOut]:
    """Principals aus wbdb, rein lesend über die wbdb_reader-Freigabe auf
    auth.principal (siehe pdl-lt-wbdb sql/zugriff.sql) — kein als(), das ist
    ein Katalog-Read wie source.resource, keine principal-gefilterte Abfrage.
    Grants bleiben unsichtbar, die liest ausschließlich wbdb_admin_ui.

    Liefert 503 statt einer leeren Liste, wenn wbdb nicht konfiguriert oder
    nicht erreichbar ist, damit das Frontend das von „wbdb hat wirklich null
    Principals" unterscheiden und auf Freitext zurückfallen kann."""
    try:
        with verbindung() as conn:
            rows = conn.execute(
                "SELECT principal_id, kind, label, active FROM auth.principal ORDER BY label"
            ).fetchall()
    except (KeyError, psycopg.Error) as e:
        raise HTTPException(503, f"wbdb nicht erreichbar: {e}") from e
    return [
        PrincipalOut(principal_id=r[0], kind=r[1], label=r[2], active=r[3]) for r in rows
    ]


class TestPrincipalRequest(BaseModel):
    principal_id: str


@router.post("/test-principal")
def test_principal(req: TestPrincipalRequest) -> dict:
    """Zeigt, was eine principal_id aktuell in wbdb sehen darf — rein lesend,
    unter der ohnehin vorhandenen Leserolle wbdb_dictconsistency
    (`SELECT * FROM auth.current_scope`, siehe WBDB-Doku §2). Hilft, Tippfehler
    bei der Zuordnung eines Nutzers sofort zu bemerken, ohne dass die App
    jemals selbst Principals oder Grants anlegt."""
    principal = req.principal_id.strip()
    if not principal:
        raise HTTPException(422, "principal_id darf nicht leer sein.")
    with verbindung() as conn, als(conn, principal) as c:
        cur = c.execute("SELECT * FROM auth.current_scope")
        columns = [col.name for col in cur.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    return {"principal_id": principal, "scope": rows}


class WbdbIndexStatus(BaseModel):
    build_id: int | None
    started_at: str | None
    finished_at: str | None
    status: str | None
    row_count: int | None
    error: str | None
    triggered_by: str | None


@router.get("/wbdb-index/status", response_model=WbdbIndexStatus)
def wbdb_index_status() -> WbdbIndexStatus:
    """Letzter Reindex-Lauf des Artikel-Index-Caches (Baum-Browser, siehe
    routers/db_index.py) — Zeitstempel, Zeilenzahl, Status/Fehler."""
    status = index_store.get_status()
    if status is None:
        return WbdbIndexStatus(
            build_id=None, started_at=None, finished_at=None,
            status=None, row_count=None, error=None, triggered_by=None,
        )
    return WbdbIndexStatus(**status)


@router.post("/wbdb-index/rebuild", response_model=WbdbIndexStatus)
def rebuild_wbdb_index(admin: dict = Depends(require_admin)) -> WbdbIndexStatus:
    """Artikel-Index-Cache neu aufbauen — liest source.article komplett unter
    dem dedizierten Index-Principal (WBDB_INDEX_PRINCIPAL, siehe
    wbdb/connection.py::index_principal()), synchron (kein Fortschritts-Polling
    — reine Textspalten ohne XML-Bytes, deutlich leichter als
    materialize_db_resource, das bereits synchron läuft)."""
    try:
        status = index_store.rebuild_index(triggered_by=admin["username"])
    except index_store.RebuildInProgress as e:
        raise HTTPException(409, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    return WbdbIndexStatus(**status)
