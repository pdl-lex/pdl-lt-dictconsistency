"""API-Endpunkte für die Verweisprüfung.

Läuft als Hintergrund-Job mit zweiphasigem Fortschritt (erst Scan der
Fundstellen, dann Zielprüfung — Artikel-Referenzen live gegen wbdb,
http(s)-Links per echtem Request, siehe `core/references.py`), analog zum
Muster von `/data/db-load` (`api/routers/db_index.py`), hier über den
generischen Job-Store `api/_jobs.py` statt `wbdb/load_jobs.py` — kein
wbdb-Bezug im Job-Mechanismus selbst.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...auth.deps import get_current_user_optional
from ...core.common import InvalidExpressionError, ensure_tag_name
from ...core.references import ReferenceSource, run_reference_check
from ...wbdb.connection import default_principal
from .. import _jobs as jobs
from .._helpers import resolve_files
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks/references", tags=["checks"])


class ReferenceSourceModel(BaseModel):
    tag: str
    attribute: str


class ReferencesRequest(FileSelection):
    sources: list[ReferenceSourceModel] = Field(default_factory=list)
    check_http_links: bool = False
    include_fehlt_marked: bool = True


class ReferencesJobHandle(BaseModel):
    job_id: str
    total: int


class ReferencesJobStatus(BaseModel):
    status: str
    phase: str
    done: int
    total: int
    error: str | None = None
    result: GenericCheckResponse | None = None


def _run(
    job: jobs.Job, files, base, sources, check_http_links, include_fehlt_marked, principal,
) -> None:
    try:
        result = run_reference_check(
            files, base,
            sources=sources, check_http_links=check_http_links,
            include_fehlt_marked=include_fehlt_marked, principal=principal,
            on_progress=lambda phase, done, total: jobs.update_progress(
                job, phase=phase, done=done, total=total,
            ),
        )
        jobs.finish_ok(job, result)
    except Exception as e:  # noqa: BLE001 — Fehlerursache dem Nutzer zeigen, nicht verschlucken
        jobs.finish_error(job, e)


@router.post("/run", response_model=ReferencesJobHandle, status_code=202)
def start(req: ReferencesRequest, user: dict | None = Depends(get_current_user_optional)) -> ReferencesJobHandle:
    if not req.sources and not req.check_http_links:
        raise HTTPException(422, "Mindestens eine Verweisquelle angeben oder Link-Prüfung aktivieren.")
    try:
        sources = [
            ReferenceSource(
                tag=ensure_tag_name(s.tag) if s.tag.strip() else "",
                attribute=ensure_tag_name(s.attribute),
            )
            for s in req.sources
        ]
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e

    base, files = resolve_files(req)
    principal = user.get("wbdb_principal_id") if user else default_principal()

    job = jobs.create_job(len(files), owner_user_id=user["id"] if user else None, phase="scanning")
    threading.Thread(
        target=_run,
        args=(job, files, base, sources, req.check_http_links, req.include_fehlt_marked, principal),
        daemon=True,
    ).start()
    return ReferencesJobHandle(job_id=job.id, total=job.total)


@router.get("/run/{job_id}", response_model=ReferencesJobStatus)
def status(job_id: str, user: dict | None = Depends(get_current_user_optional)) -> ReferencesJobStatus:
    job = jobs.get_job(job_id)
    if job is None or job.owner_user_id != (user["id"] if user else None):
        raise HTTPException(404, "Job nicht gefunden.")
    return ReferencesJobStatus(
        status=job.status, phase=job.phase, done=job.done, total=job.total, error=job.error,
        result=GenericCheckResponse(**job.result) if job.result else None,
    )
