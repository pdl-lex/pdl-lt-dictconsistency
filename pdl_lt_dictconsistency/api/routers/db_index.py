"""wbdb-Artikel-Baum: Browsing gegen den lokalen Index-Cache, Laden per Auswahl.

Browsing (Baum, Buchstabe aufklappen, Suche) läuft ausschließlich gegen
wbdb/index_store.py's lokale SQLite-Kopie, gefiltert bei jeder Anfrage über den
live geprüften Scope des Principals — kein Postgres-Zugriff auf source.article
auf diesem Weg. Das eigentliche Laden ("Laden"-Button, /db-load) bleibt live
und RLS-geprüft (core/data.py::materialize_db_selection): der Cache entscheidet
nur, was angeboten wird, nie, was tatsächlich lesbar ist.

Größere Auswahlen dauern gemessen mehrere zehn Sekunden (34.496 Artikel ≈
80s) — /db-load startet daher nur einen Hintergrund-Job (wbdb/load_jobs.py)
und liefert sofort eine job_id zurück; das Frontend pollt /db-load/{job_id}
für den Fortschritt.

Der Reindex-Trigger selbst liegt in routers/admin.py (admin-only).
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...auth.deps import get_current_user_optional
from ...core import data
from ...wbdb import index_store, load_jobs
from ...wbdb.connection import default_principal
from .data import DatasetResponse

router = APIRouter(prefix="/data", tags=["data"])


def _resolve_principal(user: dict | None) -> str:
    """wbdb-Principal für Baum-Browsing/Laden.

    Nicht angemeldet: der öffentliche 'anon'-Principal (`default_principal()`,
    per WBDB_PRINCIPAL überschreibbar) — wbdb selbst kennt 'anon' für die vier
    veröffentlichten Wörterbücher, dafür ist kein Login nötig.
    Angemeldet: der zugeordnete Principal, ohne stillen Fallback — ein Nutzer
    ohne wbdb_principal_id-Zuordnung bekommt keinen DB-Zugriff (siehe Plan
    Phase 3)."""
    if user is None:
        return default_principal()
    principal = user["wbdb_principal_id"]
    if not principal:
        raise HTTPException(403, "Kein Datenbank-Zugriff: Ihrem Konto ist kein wbdb-Principal zugeordnet.")
    return principal


class LetterSummary(BaseModel):
    letter: str
    article_count: int


class ResourceSummary(BaseModel):
    resource_id: str
    article_count: int
    letters: list[LetterSummary]


class ArticleSummary(BaseModel):
    source_path: str
    article_id: str
    lemma: str | None
    pos: str | None


class SearchHit(BaseModel):
    resource_id: str
    letter: str
    source_path: str
    article_id: str
    lemma: str | None


def _not_built() -> HTTPException:
    return HTTPException(409, "Noch kein Artikelindex aufgebaut — ein Admin muss ihn zuerst anlegen.")


@router.get("/db-index/tree", response_model=list[ResourceSummary])
def db_index_tree(user: dict | None = Depends(get_current_user_optional)) -> list[ResourceSummary]:
    """Ressourcen + Buchstaben mit Zählung — erste zwei Baumebenen in einem Call."""
    principal = _resolve_principal(user)
    try:
        return [ResourceSummary(**r) for r in index_store.get_tree(principal)]
    except index_store.IndexNotBuilt:
        raise _not_built() from None


@router.get("/db-index/letter", response_model=list[ArticleSummary])
def db_index_letter(
    resource_id: str, letter: str, user: dict | None = Depends(get_current_user_optional)
) -> list[ArticleSummary]:
    """Artikel einer Ressource+Buchstabe — dritte Baumebene, lazy beim Aufklappen."""
    principal = _resolve_principal(user)
    try:
        return [ArticleSummary(**r) for r in index_store.get_letter_articles(principal, resource_id, letter)]
    except index_store.IndexNotBuilt:
        raise _not_built() from None


@router.get("/db-index/search", response_model=list[SearchHit])
def db_index_search(q: str, user: dict | None = Depends(get_current_user_optional)) -> list[SearchHit]:
    """Substring-Suche über Lemma/Artikel-ID im gescopten Index-Cache."""
    principal = _resolve_principal(user)
    try:
        return [SearchHit(**r) for r in index_store.search(principal, q)]
    except index_store.IndexNotBuilt:
        raise _not_built() from None


@router.get("/db-index/search-files", response_model=list[SearchHit])
def db_index_search_files(
    q: str, resource_ids: list[str] = Query(default=[]), user: dict | None = Depends(get_current_user_optional)
) -> list[SearchHit]:
    """Substring-Suche über den Dateinamen (Artikelsuche), optional auf einzelne
    Ressourcen (Wörterbücher) eingeschränkt."""
    principal = _resolve_principal(user)
    try:
        return [SearchHit(**r) for r in index_store.search_files(principal, q, resource_ids)]
    except index_store.IndexNotBuilt:
        raise _not_built() from None


class ArticleContentResponse(BaseModel):
    content: str


@router.get("/db-index/article", response_model=ArticleContentResponse)
def db_index_article(
    resource_id: str, source_path: str, user: dict | None = Depends(get_current_user_optional)
) -> ArticleContentResponse:
    """Rohinhalt eines einzelnen Artikels — live gegen wbdb, RLS-geprüft (nicht
    aus dem Index-Cache, der liefert nur Metadaten)."""
    principal = _resolve_principal(user)
    try:
        content = data.load_article_content(resource_id, source_path, principal=principal)
    except FileNotFoundError:
        raise HTTPException(404, "Artikel nicht gefunden oder außerhalb Ihres Zugriffs.") from None
    return ArticleContentResponse(content=content)


class DbLoadRequest(BaseModel):
    resource_ids: list[str] = []
    resource_letters: list[tuple[str, str]] = []
    articles: list[tuple[str, str]] = []


class LoadJobHandle(BaseModel):
    job_id: str
    total: int


@router.post("/db-load", response_model=LoadJobHandle, status_code=202)
def db_load(req: DbLoadRequest, user: dict | None = Depends(get_current_user_optional)) -> LoadJobHandle:
    """Baum-Auswahl (ganze Ressourcen, Buchstaben, einzelne Artikel) laden.

    Startet nur einen Hintergrund-Job und liefert sofort eine job_id — der
    eigentliche Materialisierungs-Aufruf kann bei großen Auswahlen mehrere
    zehn Sekunden dauern (siehe Moduldoc oben). Fortschritt über
    GET /db-load/{job_id}.
    """
    if not (req.resource_ids or req.resource_letters or req.articles):
        raise HTTPException(422, "Keine Artikel ausgewählt.")
    principal = _resolve_principal(user)
    try:
        pairs = index_store.resolve_selection(
            principal, req.resource_ids, req.resource_letters, req.articles
        )
    except index_store.IndexNotBuilt:
        raise _not_built() from None
    if not pairs:
        raise HTTPException(422, "Keine Artikel für die gewählte Auswahl gefunden.")

    job = load_jobs.create_job(len(pairs), owner_user_id=user["id"] if user else None)
    threading.Thread(
        target=load_jobs.run,
        args=(job, lambda on_progress: data.materialize_db_selection(pairs, principal=principal, on_progress=on_progress)),
        daemon=True,
    ).start()
    return LoadJobHandle(job_id=job.id, total=job.total)


class LoadJobStatus(BaseModel):
    status: str
    done: int
    total: int
    error: str | None = None
    result: DatasetResponse | None = None


@router.get("/db-load/{job_id}", response_model=LoadJobStatus)
def db_load_status(job_id: str, user: dict | None = Depends(get_current_user_optional)) -> LoadJobStatus:
    job = load_jobs.get_job(job_id)
    if job is None or job.owner_user_id != (user["id"] if user else None):
        raise HTTPException(404, "Job nicht gefunden.")
    return LoadJobStatus(
        status=job.status, done=job.done, total=job.total, error=job.error,
        result=DatasetResponse(**job.result) if job.result else None,
    )
