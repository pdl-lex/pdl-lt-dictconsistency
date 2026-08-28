"""API-Endpunkte für Daten-Ingest: Upload, Verzeichnis-Scan, Datenquellen.

wbdb-Artikel (Baum-Browser, Reindex, Laden nach Auswahl) leben in
routers/db_index.py und routers/admin.py — hier nur der dateisystembasierte Weg
(Server-Pfad, Upload)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from ...core import data
from .._helpers import resolve_directory

router = APIRouter(prefix="/data", tags=["data"])


class ScanRequest(BaseModel):
    directory: str


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


class FileContentResponse(BaseModel):
    content: str


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


@router.delete("/upload/{session_id}")
def delete_session(session_id: str) -> dict:
    """Eine Upload-Session löschen."""
    try:
        data.clear_session(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"status": "deleted"}


@router.get("/file-content", response_model=FileContentResponse)
def file_content(directory: str, subdir: str, filename: str) -> FileContentResponse:
    """Rohinhalt einer geprüften Datei für die Fundstellen-Vorschau (Ergebnistabelle
    „Datei öffnen"). `directory` unterliegt derselben LT_DATA_ROOTS-Prüfung wie
    /data/scan und die Prüf-Endpunkte."""
    base = resolve_directory(directory)
    try:
        content = data.read_file_content(base, subdir, filename)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, f"Datei nicht gefunden: {e}") from e
    return FileContentResponse(content=content)
