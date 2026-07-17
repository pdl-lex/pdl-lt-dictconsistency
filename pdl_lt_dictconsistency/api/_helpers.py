"""Gemeinsame Helfer für die API-Router."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, Iterator

from fastapi import HTTPException

from ..core.data import ensure_allowed_directory
from ..core.source import scan_xml_files
from .schemas import FileSelection, GenericCheckResponse


def resolve_directory(directory: str) -> Path:
    """Verzeichnis auflösen, gegen LT_DATA_ROOTS prüfen (403) und auf
    Existenz prüfen (404). Einziger Eintrittspunkt für `directory`-Eingaben."""
    try:
        base = ensure_allowed_directory(directory)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    if not base.is_dir():
        raise HTTPException(404, f"Verzeichnis nicht gefunden: {base}")
    return base


def resolve_files(req: FileSelection) -> tuple[Path, list]:
    """Basisverzeichnis prüfen und Dateiliste bestimmen (explizit oder Scan)."""
    base = resolve_directory(req.directory)
    files = req.files if req.files is not None else scan_xml_files(base)
    return base, files


def collect(progress_gen: Iterator) -> tuple[list[dict], int]:
    """Einen Progress-Generator vollständig einsammeln."""
    results: list[dict] = []
    files_checked = 0
    for progress in progress_gen:
        results.extend(progress.results)
        files_checked = progress.files_checked
    return results, files_checked


def timed_response(progress_gen: Iterator) -> GenericCheckResponse:
    """Progress-Generator ausführen, Laufzeit messen, Antwort bauen."""
    started = time.perf_counter()
    results, files_checked = collect(progress_gen)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return GenericCheckResponse(
        results=results,
        files_checked=files_checked,
        result_count=len(results),
        duration_ms=duration_ms,
    )
