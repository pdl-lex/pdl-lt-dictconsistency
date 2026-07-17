"""API-Endpunkt für die Einmaligkeitsprüfung.

Dünner Wrapper um core.uniqueness.run_uniqueness — derselbe Generator, den
auch die Reflex-Oberfläche konsumiert.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import Field

from ...core.common import InvalidExpressionError
from ...core.uniqueness import MODES, run_uniqueness
from .._helpers import resolve_files
from ..schemas import CheckResponse, FileSelection

router = APIRouter(prefix="/checks", tags=["checks"])


class UniquenessRequest(FileSelection):
    mode: str = Field(..., description=f"Prüfmodus, einer von: {', '.join(MODES)}")
    tag_name: str = ""
    attribute_name: str = ""

    def validate_inputs(self) -> None:
        """Spiegelt die Eingabevalidierung der Reflex-Oberfläche."""
        if self.mode not in MODES:
            raise HTTPException(422, f"Unbekannter Modus: {self.mode!r}")
        needs_tag = self.mode in ("Tag", "Tag-Inhalt", "Tag & Attribut")
        needs_attr = self.mode in ("Tag & Attribut", "Attribut")
        if needs_tag and not self.tag_name.strip():
            raise HTTPException(422, "Tag-Name erforderlich.")
        if needs_attr and not self.attribute_name.strip():
            raise HTTPException(422, "Attribut-Name erforderlich.")


@router.post("/uniqueness", response_model=CheckResponse)
def check_uniqueness(req: UniquenessRequest) -> CheckResponse:
    req.validate_inputs()
    base, files = resolve_files(req)

    started = time.perf_counter()
    results: list[dict] = []
    files_checked = 0
    try:
        for progress in run_uniqueness(
            files, base,
            mode=req.mode, tag_name=req.tag_name, attribute_name=req.attribute_name,
        ):
            files_checked = progress.files_checked
            results.extend(progress.results)
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e
    duration_ms = int((time.perf_counter() - started) * 1000)

    return CheckResponse(
        results=results,
        files_checked=files_checked,
        result_count=len(results),
        duration_ms=duration_ms,
    )
