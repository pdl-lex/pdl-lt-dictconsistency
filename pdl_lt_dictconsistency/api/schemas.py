"""Gemeinsame Pydantic-Schemata für die Prüf-API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ResultRow(BaseModel):
    """Eine Treffer-/Fehlerzeile, wie von der core-Logik geliefert."""

    quelle: str = ""
    subdir: str
    filename: str
    line: int
    error_type: str
    details: str


class CheckResponse(BaseModel):
    """Standardantwort einer Prüfung: Treffer + Kennzahlen."""

    results: list[ResultRow]
    files_checked: int
    result_count: int
    duration_ms: int = Field(..., description="Laufzeit der Prüfung in Millisekunden")


class GenericCheckResponse(BaseModel):
    """Antwort für Prüfungen mit prüfungsspezifischer Treffer-Struktur.

    `results` enthält frei strukturierte Zeilen-Dicts (je Prüfung andere Felder).
    """

    results: list[dict]
    files_checked: int
    result_count: int
    duration_ms: int = Field(..., description="Laufzeit der Prüfung in Millisekunden")


class FileSelection(BaseModel):
    """Auswahl der zu prüfenden Dateien.

    Entweder ein serverseitiges Verzeichnis (rekursiver *.xml-Scan) oder eine
    explizite Dateiliste relativ zu `directory`.
    """

    directory: str = Field(..., description="Basisverzeichnis auf dem Server")
    files: list[dict] | None = Field(
        None,
        description="Optionale explizite Liste {subdir, filename}; sonst wird das Verzeichnis gescannt",
    )
