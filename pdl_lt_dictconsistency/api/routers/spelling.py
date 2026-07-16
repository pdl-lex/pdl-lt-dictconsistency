"""API-Endpunkte für die Rechtschreibprüfung (alte Schreibungen)."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.spelling import (
    BUILTIN_SPELLINGS,
    DEFAULT_EXCLUDED_TAGS,
    collect_text_bearing_tags,
    run_spelling,
)
from .._helpers import resolve_files
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks/spelling", tags=["checks"])


class SpellingPair(BaseModel):
    alt: str
    neu: str


class SpellingRequest(FileSelection):
    included_tags: list[str] = Field(..., description="Zu durchsuchende Tags")
    custom_spellings: list[SpellingPair] = Field(default_factory=list)
    custom_list_mode: str = Field("extend", description="'extend' (Builtin + Custom) oder 'replace'")


class SpellingTagsResponse(BaseModel):
    tags: list[str]
    default_excluded: list[str]


class WordlistInfoResponse(BaseModel):
    builtin_count: int
    spellings: list[SpellingPair]


@router.post("/search", response_model=GenericCheckResponse)
def search(req: SpellingRequest) -> GenericCheckResponse:
    if not req.included_tags:
        raise HTTPException(422, "Mindestens ein Tag erforderlich.")
    base, files = resolve_files(req)
    custom = [(p.alt, p.neu) for p in req.custom_spellings]

    started = time.perf_counter()
    results: list[dict] = []
    files_checked = 0
    try:
        for progress in run_spelling(
            files, base,
            included_tags=req.included_tags,
            custom_spellings=custom,
            custom_list_mode=req.custom_list_mode,
        ):
            results.extend(progress.results)
            files_checked = progress.files_checked
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    return GenericCheckResponse(
        results=results, files_checked=files_checked, result_count=len(results),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("/tags", response_model=SpellingTagsResponse)
def list_text_tags(req: FileSelection) -> SpellingTagsResponse:
    """Text-tragende Tags + Vorschlag für standardmäßig ausgeschlossene Tags."""
    base, files = resolve_files(req)
    tags = collect_text_bearing_tags(files, base)
    return SpellingTagsResponse(
        tags=tags,
        default_excluded=[t for t in tags if t in DEFAULT_EXCLUDED_TAGS],
    )


@router.get("/wordlist", response_model=WordlistInfoResponse)
def wordlist() -> WordlistInfoResponse:
    """Integrierte Wortliste (alte → neue Schreibung)."""
    return WordlistInfoResponse(
        builtin_count=len(BUILTIN_SPELLINGS),
        spellings=[SpellingPair(alt=a, neu=n) for a, n in BUILTIN_SPELLINGS],
    )
