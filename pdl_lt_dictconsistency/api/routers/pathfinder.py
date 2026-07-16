"""API-Endpunkt für die Tag-/Pfadsuche."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import Field

from ...core.pathfinder import run_pathfinder
from .._helpers import resolve_files, timed_response
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks", tags=["checks"])


class PathfinderRequest(FileSelection):
    user_input: str = Field(..., description="Tag oder Pfad, z. B. 'sense' oder 'sense/*/bibl'")


@router.post("/pathfinder", response_model=GenericCheckResponse)
def search_path(req: PathfinderRequest) -> GenericCheckResponse:
    if not req.user_input.strip():
        raise HTTPException(422, "Suchbegriff erforderlich.")
    base, files = resolve_files(req)
    return timed_response(run_pathfinder(files, base, user_input=req.user_input))
