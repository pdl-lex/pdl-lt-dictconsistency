"""API-Endpunkte für Daten-Ingest: Upload, Verzeichnis-Scan, Datenquellen."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from ...auth.deps import get_current_user
from ...core import data
from ...wbdb.connection import verbindung
from ...wbdb.resources import list_resources
from .._helpers import resolve_directory

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_user)])


class ScanRequest(BaseModel):
    directory: str


class DbResourceRequest(BaseModel):
    resource_ids: list[str]


class WbdbResource(BaseModel):
    resource_id: str
    article_count: int


class DatasetResponse(BaseModel):
    """Aufgelöstes Datenverzeichnis + Dateiliste; `directory` ist die Eingabe der Prüfungen."""

    directory: str
    file_count: int
    files: list[dict]
    session_id: str | None = None
    errors: list[str] = []


class Datasource(BaseModel):
    name: str
    path: str
    key: str
    exists: bool


@router.get("/datasources", response_model=list[Datasource])
def datasources() -> list[Datasource]:
    """Vorkonfigurierte Datenquellen aus datasources.json."""
    return [Datasource(**d) for d in data.load_datasources()]


@router.post("/scan", response_model=DatasetResponse)
def scan_directory(req: ScanRequest) -> DatasetResponse:
    """Serverseitiges Verzeichnis (Server-Pfad oder Datenquelle) scannen.

    Mit gesetztem LT_DATA_ROOTS sind nur Pfade unterhalb der erlaubten
    Wurzeln (und Upload-Sessions) zulässig — sonst 403."""
    base = resolve_directory(req.directory)
    files = data.scan(base)
    return DatasetResponse(directory=str(base), file_count=len(files), files=files)


@router.post("/upload", response_model=DatasetResponse)
async def upload(files: list[UploadFile], session_id: str | None = None) -> DatasetResponse:
    """XML-/ZIP-Dateien hochladen. Ohne session_id wird eine neue Session angelegt;
    mit session_id wird an eine bestehende angehängt."""
    if not files:
        raise HTTPException(422, "Keine Dateien übermittelt.")
    if session_id:
        try:
            dest = data.session_path(session_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
    else:
        session_id, dest = data.new_session()

    errors: list[str] = []
    for f in files:
        content = await f.read()
        errors.extend(data.save_upload(dest, f.filename or "", content))

    scanned = data.scan(dest)
    return DatasetResponse(
        directory=str(dest), file_count=len(scanned), files=scanned,
        session_id=session_id, errors=errors,
    )


def _require_principal(user: dict) -> str:
    """Principal des angemeldeten Nutzers, ohne stillen Fallback.

    Ein Nutzer ohne wbdb_principal_id-Zuordnung bekommt keinen DB-Zugriff —
    kein impliziter Rückgriff auf WBDB_PRINCIPAL/anon (siehe Plan Phase 3)."""
    principal = user["wbdb_principal_id"]
    if not principal:
        raise HTTPException(403, "Kein Datenbank-Zugriff: Ihrem Konto ist kein wbdb-Principal zugeordnet.")
    return principal


@router.get("/db-resources", response_model=list[WbdbResource])
def db_resources(user: dict = Depends(get_current_user)) -> list[WbdbResource]:
    """Wörterbücher aus wbdb, die der Principal des angemeldeten Nutzers sehen darf."""
    principal = _require_principal(user)
    with verbindung() as conn:
        return [WbdbResource(**r) for r in list_resources(conn, principal)]


@router.post("/db-resource", response_model=DatasetResponse)
def db_resource(req: DbResourceRequest, user: dict = Depends(get_current_user)) -> DatasetResponse:
    """Ausgewählte wbdb-Wörterbücher in eine neue Upload-Session materialisieren."""
    if not req.resource_ids:
        raise HTTPException(422, "Keine Wörterbücher ausgewählt.")
    principal = _require_principal(user)
    result = data.materialize_db_resource(req.resource_ids, principal=principal)
    return DatasetResponse(**result)


@router.delete("/upload/{session_id}")
def delete_session(session_id: str) -> dict:
    """Eine Upload-Session löschen."""
    try:
        data.clear_session(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"status": "deleted"}
