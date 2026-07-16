"""Gemeinsame, Reflex-unabhängige Helfer für die Prüf-Kernlogik."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class XmlFileRef:
    """Verweis auf eine zu prüfende XML-Datei relativ zu einem Basisverzeichnis."""

    subdir: str
    filename: str

    def resolve(self, base_path: Path) -> Path:
        if self.subdir == ".":
            return base_path / self.filename
        return base_path / self.subdir / self.filename

    @classmethod
    def from_dict(cls, data: dict) -> "XmlFileRef":
        return cls(subdir=data["subdir"], filename=data["filename"])


def get_quelle(root, filename: str) -> str:
    """Quellenangabe für ein geparstes XML-Dokument.

    BWB-Dateien liefern "BWB Bd. X, H. Y"; alle anderen den Dateinamen.
    Prüft das Wurzelelement und seine direkten Kinder (BWB legt wb/band/heft
    auf dem <artikel>-Kind ab, nicht auf der <bdo>-Wurzel).
    root darf None sein (z. B. wenn die Datei nicht geparst werden konnte).
    """
    if root is None:
        return filename
    for elem in [root, *list(root)[:3]]:
        wb = elem.get("wb", "")
        if wb.lower() == "bwb":
            band = elem.get("band", "?")
            heft = elem.get("heft", "?")
            return f"BWB Bd. {band}, H. {heft}"
    return ""


def scan_xml_files(base_path: str | Path) -> list[XmlFileRef]:
    """Alle *.xml-Dateien unter base_path rekursiv als XmlFileRef auflisten.

    Spiegelt die Verzeichnis-Scan-Logik der Reflex-Oberfläche (subdir =
    relativer Elternpfad bzw. "." für Dateien direkt im Basisverzeichnis).
    """
    base = Path(base_path).expanduser()
    refs: list[XmlFileRef] = []
    for file_path in base.rglob("*.xml"):
        rel_parent = file_path.relative_to(base).parent
        subdir = str(rel_parent) if rel_parent != Path(".") else "."
        refs.append(XmlFileRef(subdir=subdir, filename=file_path.name))
    return refs


def make_parser() -> etree.XMLParser:
    """Sicherer XML-Parser (keine DTD, kein Netzwerk, keine Entity-Auflösung)."""
    return etree.XMLParser(
        dtd_validation=False,
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
    )
