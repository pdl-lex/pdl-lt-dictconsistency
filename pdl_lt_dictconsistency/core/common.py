"""Gemeinsame Bausteine der Prüf-Kernlogik."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_CHUNK_SIZE = 500


@dataclass
class Progress:
    """Ein Fortschrittsschritt: Gesamtzahl geprüfter Dateien + neue Treffer."""

    files_checked: int
    results: list[dict] = field(default_factory=list)


class InvalidExpressionError(ValueError):
    """Ungültiger Such-/Pfadausdruck (z. B. fehlerhaftes XPath-Muster)."""


# XML-Name (NCName, vereinfacht): kein Zahl-/Satzzeichen-Anfang, dann
# Wortzeichen/./-. Verhindert, dass Nutzereingaben XPath-Ausdrücke aufbrechen.
_TAG_NAME_RE = re.compile(r"^[^\W\d][\w.\-]*$", re.UNICODE)


def ensure_tag_name(name: str) -> str:
    """Tag-/Attributnamen für die XPath-Interpolation validieren.

    Gibt den getrimmten Namen zurück; wirft InvalidExpressionError bei
    Zeichen, die in XML-Namen nicht vorkommen (Quotes, Klammern, Leerraum …).
    """
    trimmed = name.strip()
    if not _TAG_NAME_RE.match(trimmed):
        raise InvalidExpressionError(f"Ungültiger Tag-Name: {name!r}")
    return trimmed
