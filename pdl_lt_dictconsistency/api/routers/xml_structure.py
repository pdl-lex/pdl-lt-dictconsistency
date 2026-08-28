"""API-Endpunkt für die XML-Strukturanalyse."""
from __future__ import annotations

from fastapi import APIRouter

from ...core.xml_structure import run_structure
from .._helpers import resolve_files, timed_response
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks", tags=["checks"])


@router.post("/structure", response_model=GenericCheckResponse)
def check_structure(req: FileSelection) -> GenericCheckResponse:
    """Zusammengeführten Tag-/Attribut-/Text-Baum aller ausgewählten Dateien liefern.

    `req.files` kann auf eine einzelne Datei eingeschränkt werden, um den Baum
    im Frontend auf deren Inhalte zu filtern (gleicher Aufbau, andere Werte).
    """
    base, files = resolve_files(req)
    return timed_response(run_structure(files, base))
