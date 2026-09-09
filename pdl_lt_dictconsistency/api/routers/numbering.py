"""API-Endpunkt für die Bedeutungsnummerierungs-Prüfung."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.common import InvalidExpressionError
from ...core.numbering import EMPTY_RULES, FORMATS, MAX_LEVELS, NumberingLevel, run_numbering
from .._helpers import resolve_files, timed_response
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks", tags=["checks"])


class NumberingLevelRequest(BaseModel):
    format: str = Field(..., description=f"Einer von: {', '.join(FORMATS)}")
    empty_rule: str = Field("pflicht", description=f"Einer von: {', '.join(EMPTY_RULES)}")


class NumberingRequest(FileSelection):
    tag_name: str = Field(..., description="Tag, der eine Bedeutung repräsentiert, z. B. 'bedeutung-position'")
    attribute_name: str = Field(..., description="Attribut mit der Nummer, z. B. 'nr'")
    levels: list[NumberingLevelRequest] = Field(..., description=f"1 bis {MAX_LEVELS} Ebenen-Konfigurationen")
    max_depth: int = Field(..., description="Maximale erlaubte Verschachtelungstiefe (1..len(levels))")
    leading_level: NumberingLevelRequest | None = Field(
        None,
        description=(
            "Optionale vorgeschaltete Sonder-Ebene (z. B. Wortart-Gruppierung "
            "'I'/'II' vor den eigentlichen Bedeutungen). Wird pro Wurzel-"
            "Geschwistergruppe automatisch anhand des Nummernformats erkannt."
        ),
    )

    def validate_inputs(self) -> None:
        if not self.tag_name.strip():
            raise HTTPException(422, "Tag-Name erforderlich.")
        if not self.attribute_name.strip():
            raise HTTPException(422, "Attribut-Name erforderlich.")
        if not (1 <= len(self.levels) <= MAX_LEVELS):
            raise HTTPException(422, f"levels muss 1 bis {MAX_LEVELS} Einträge haben.")
        for level in self.levels:
            if level.format not in FORMATS:
                raise HTTPException(422, f"Unbekanntes Format: {level.format!r}")
            if level.empty_rule not in EMPTY_RULES:
                raise HTTPException(422, f"Unbekannte Leer-Regel: {level.empty_rule!r}")
        if not (1 <= self.max_depth <= len(self.levels)):
            raise HTTPException(422, f"max_depth muss zwischen 1 und {len(self.levels)} liegen.")
        if self.leading_level is not None:
            if self.leading_level.format not in FORMATS:
                raise HTTPException(422, f"Unbekanntes Format: {self.leading_level.format!r}")
            if self.leading_level.empty_rule not in EMPTY_RULES:
                raise HTTPException(422, f"Unbekannte Leer-Regel: {self.leading_level.empty_rule!r}")


@router.post("/numbering", response_model=GenericCheckResponse)
def check_numbering(req: NumberingRequest) -> GenericCheckResponse:
    req.validate_inputs()
    base, files = resolve_files(req)
    levels = [NumberingLevel(format=level.format, empty_rule=level.empty_rule) for level in req.levels]
    leading_level = (
        NumberingLevel(format=req.leading_level.format, empty_rule=req.leading_level.empty_rule)
        if req.leading_level is not None else None
    )
    try:
        return timed_response(run_numbering(
            files, base,
            tag_name=req.tag_name, attribute_name=req.attribute_name,
            levels=levels, max_depth=req.max_depth, leading_level=leading_level,
        ))
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e
