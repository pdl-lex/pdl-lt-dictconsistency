"""API-Endpunkt für Bedeutungsstatistiken (Anzahl/Länge)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import Field

from ...core.senses_stats import run_senses_stats
from .._helpers import resolve_files, timed_response
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks", tags=["checks"])


class SensesStatsRequest(FileSelection):
    tag_name: str = Field(..., description="Tag, der eine Bedeutung repräsentiert, z. B. 'sense'")


@router.post("/senses-stats", response_model=GenericCheckResponse)
def check_senses_stats(req: SensesStatsRequest) -> GenericCheckResponse:
    if not req.tag_name.strip():
        raise HTTPException(422, "Tag-Name erforderlich.")
    base, files = resolve_files(req)
    return timed_response(run_senses_stats(files, base, tag_name=req.tag_name))
