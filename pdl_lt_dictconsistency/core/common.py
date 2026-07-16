"""Gemeinsame Bausteine der Prüf-Kernlogik."""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CHUNK_SIZE = 500


@dataclass
class Progress:
    """Ein Fortschrittsschritt: Gesamtzahl geprüfter Dateien + neue Treffer."""

    files_checked: int
    results: list[dict] = field(default_factory=list)


class InvalidExpressionError(ValueError):
    """Ungültiger Such-/Pfadausdruck (z. B. fehlerhaftes XPath-Muster)."""
