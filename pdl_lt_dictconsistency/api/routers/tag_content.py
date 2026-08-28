"""API-Endpunkte für die Inhalts-/Leere-Tags-Suche."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.common import InvalidExpressionError
from ...core.tag_content import (
    collect_attr_values,
    collect_attrs,
    collect_tags,
    run_tag_content_search,
)
from .._helpers import resolve_files
from ..schemas import FileSelection, GenericCheckResponse

router = APIRouter(prefix="/checks/tag-content", tags=["checks"])


class TagContentRequest(FileSelection):
    tags_to_search: list[str] = Field(..., description="Zu durchsuchende Tags")
    search_text: str = ""
    include_whitespace: bool = True
    attrs_to_filter: list[str] = Field(default_factory=list)
    attr_value: str = ""
    is_single_tag_mode: bool = False


class TagsResponse(BaseModel):
    tags: list[str]


class AttrsRequest(FileSelection):
    tags_filter: list[str] = Field(default_factory=list)


class AttrsResponse(BaseModel):
    attrs: list[str]


class AttrValuesRequest(FileSelection):
    attrs_to_check: list[str]
    tags_filter: list[str] | None = None


class AttrValuesResponse(BaseModel):
    values: list[str]


@router.post("/search", response_model=GenericCheckResponse)
def search(req: TagContentRequest) -> GenericCheckResponse:
    if not req.tags_to_search:
        raise HTTPException(422, "Mindestens ein Tag erforderlich.")
    base, files = resolve_files(req)
    started = time.perf_counter()
    results: list[dict] = []
    files_checked = 0
    try:
        for progress in run_tag_content_search(
            files, base,
            tags_to_search=req.tags_to_search,
            search_text=req.search_text,
            include_whitespace=req.include_whitespace,
            attrs_to_filter=req.attrs_to_filter,
            attr_value=req.attr_value,
            is_single_tag_mode=req.is_single_tag_mode,
        ):
            results.extend(progress.results)
            files_checked = progress.files_checked
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e
    return GenericCheckResponse(
        results=results, files_checked=files_checked, result_count=len(results),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("/tags", response_model=TagsResponse)
def list_tags(req: FileSelection) -> TagsResponse:
    base, files = resolve_files(req)
    return TagsResponse(tags=collect_tags(files, base))


@router.post("/attrs", response_model=AttrsResponse)
def list_attrs(req: AttrsRequest) -> AttrsResponse:
    base, files = resolve_files(req)
    try:
        return AttrsResponse(attrs=collect_attrs(files, base, req.tags_filter))
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/attr-values", response_model=AttrValuesResponse)
def list_attr_values(req: AttrValuesRequest) -> AttrValuesResponse:
    base, files = resolve_files(req)
    try:
        return AttrValuesResponse(
            values=collect_attr_values(files, base, req.attrs_to_check, req.tags_filter)
        )
    except InvalidExpressionError as e:
        raise HTTPException(422, str(e)) from e
