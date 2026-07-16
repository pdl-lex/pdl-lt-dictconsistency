"""API-Endpunkt für die XML-Validierung (Wohlgeformtheit + TEI-Lex 0)."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.validator import TYPES, run_validation
from .._helpers import resolve_files
from ..schemas import FileSelection

router = APIRouter(prefix="/checks", tags=["checks"])


class ValidatorRequest(FileSelection):
    validation_type: str = Field(..., description=f"Einer von: {', '.join(TYPES)}")


class ValidatorResponse(BaseModel):
    wellformed: list[dict]
    schema_errors: list[dict]
    files_checked: int
    files_with_wellformed_errors: int
    files_with_schema_errors: int
    duration_ms: int


@router.post("/validator", response_model=ValidatorResponse)
def validate(req: ValidatorRequest) -> ValidatorResponse:
    if req.validation_type not in TYPES:
        raise HTTPException(422, f"Unbekannter Validierungstyp: {req.validation_type!r}")
    base, files = resolve_files(req)

    started = time.perf_counter()
    wellformed: list[dict] = []
    schema_errors: list[dict] = []
    files_checked = 0
    files_with_wf = 0
    files_with_sc = 0
    try:
        for progress in run_validation(files, base, validation_type=req.validation_type):
            wellformed.extend(progress.wellformed)
            schema_errors.extend(progress.schema)
            files_checked = progress.files_checked
            files_with_wf = progress.files_with_wellformed_errors
            files_with_sc = progress.files_with_schema_errors
    except FileNotFoundError as e:
        raise HTTPException(500, str(e)) from e

    return ValidatorResponse(
        wellformed=wellformed,
        schema_errors=schema_errors,
        files_checked=files_checked,
        files_with_wellformed_errors=files_with_wf,
        files_with_schema_errors=files_with_sc,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
