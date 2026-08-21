"""API-Endpunkt für die Verschachtelungsanalyse."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from ...auth.deps import get_current_user
from ...core.common import InvalidExpressionError
from ...core.nesting import MODES, run_nesting
from .._helpers import resolve_files, timed_response
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks", tags=["checks"], dependencies=[Depends(get_current_user)])


class NestingRequest(FileSelection):
    search_mode: str = Field(..., description=f"Einer von: {', '.join(MODES)}")
    tag_input: str = ""
    path_input: str = ""

    def validate_inputs(self) -> None:
        if self.search_mode not in MODES:
            raise HTTPException(422, f"Unbekannter Modus: {self.search_mode!r}")
        if self.search_mode == "Pfad / Wildcard":
            if not self.path_input.strip():
                raise HTTPException(422, "Pfad-Muster erforderlich.")
        elif not self.tag_input.strip():
            raise HTTPException(422, "Tag-Name erforderlich.")


@router.post("/nesting", response_model=GenericCheckResponse)
def check_nesting(req: NestingRequest) -> GenericCheckResponse:
    req.validate_inputs()
    base, files = resolve_files(req)
    try:
        return timed_response(run_nesting(
            files, base,
            search_mode=req.search_mode, tag_input=req.tag_input, path_input=req.path_input,
        ))
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e
