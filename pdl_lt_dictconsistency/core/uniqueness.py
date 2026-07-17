"""Einmaligkeitsprüfung — reine Kernlogik (Reflex-unabhängig).

`run_uniqueness` ist ein Generator, der chunkweise Fortschritt und neue
Treffer liefert. So konsumieren ihn beide Welten identisch:

  * API:    results = [r for p in run_uniqueness(...) for r in p.results]
  * Reflex: pro Progress-Schritt files_checked setzen und yield für die UI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, Progress, ensure_tag_name
from .source import XmlFileRef, get_quelle, make_parser

MODES = ("Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut")


def get_attribute_value(elem: etree._Element, attr_name: str) -> str | None:
    """Attributwert lesen, inkl. Namespace-Attributen wie xml:id."""
    for attr_key, attr_value in elem.attrib.items():
        if attr_key == attr_name:
            return attr_value
        if "}" in attr_key and ":" in attr_name:
            local_name = attr_key.split("}", 1)[1]
            prefix, local_input = attr_name.split(":", 1)
            if local_name == local_input:
                namespace_uri = attr_key.split("}", 1)[0] + "}"
                if prefix == "xml" and "XML/1998/namespace" in namespace_uri:
                    return attr_value
    return None


def _check_file(
    doc: etree._ElementTree,
    *,
    mode: str,
    tag_name: str,
    attribute_name: str,
    quelle: str,
    subdir: str,
    filename: str,
) -> list[dict]:
    """Eine einzelne Datei prüfen und Treffer als Dict-Liste zurückgeben."""
    out: list[dict] = []

    if mode == "Tag":
        elements = doc.xpath(f"//*[local-name()='{tag_name}']")
        if len(elements) > 1:
            first_line = elements[0].sourceline or 0
            out.append({
                "quelle": quelle, "subdir": subdir, "filename": filename, "line": first_line,
                "error_type": f"Tag '{tag_name}' kommt {len(elements)}x vor",
                "details": f"Erwartet: 1x, Gefunden: {len(elements)}x",
            })

    elif mode == "Tag-Inhalt":
        elements = doc.xpath(f"//*[local-name()='{tag_name}']")
        content_map: dict[str, list[int]] = {}
        for elem in elements:
            content = (elem.text or "").strip()
            if content:
                content_map.setdefault(content, []).append(elem.sourceline or 0)
        for content, lines in content_map.items():
            if len(lines) > 1:
                preview_text = content if len(content) <= 50 else content[:50] + "..."
                out.append({
                    "quelle": quelle, "subdir": subdir, "filename": filename, "line": lines[0],
                    "error_type": f"Inhalt '{preview_text}' in Tag '{tag_name}' kommt {len(lines)}x vor",
                    "details": f"Zeilen: {', '.join(map(str, lines))}",
                })

    elif mode == "Tag & Attribut":
        elements = doc.xpath(f"//*[local-name()='{tag_name}']")
        attr_map: dict[str, list[int]] = {}
        for elem in elements:
            attr_value = get_attribute_value(elem, attribute_name)
            if attr_value:
                attr_map.setdefault(attr_value, []).append(elem.sourceline or 0)
        for attr_value, lines in attr_map.items():
            if len(lines) > 1:
                out.append({
                    "quelle": quelle, "subdir": subdir, "filename": filename, "line": lines[0],
                    "error_type": f"Attribut '{attribute_name}' mit Wert '{attr_value}' in Tag '{tag_name}' kommt {len(lines)}x vor",
                    "details": f"Zeilen: {', '.join(map(str, lines))}",
                })

    elif mode == "Attribut":
        attr_map_full: dict[str, list[tuple[str, int]]] = {}
        for elem in doc.xpath("//*"):
            attr_value = get_attribute_value(elem, attribute_name)
            if attr_value:
                tag = etree.QName(elem).localname
                attr_map_full.setdefault(attr_value, []).append((tag, elem.sourceline or 0))
        for attr_value, occurrences in attr_map_full.items():
            if len(occurrences) > 1:
                tag_list = ", ".join(f"{tag}:{line}" for tag, line in occurrences)
                out.append({
                    "quelle": quelle, "subdir": subdir, "filename": filename, "line": occurrences[0][1],
                    "error_type": f"Attribut '{attribute_name}' mit Wert '{attr_value}' kommt {len(occurrences)}x vor",
                    "details": f"In: {tag_list}",
                })

    return out


def run_uniqueness(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    mode: str,
    tag_name: str = "",
    attribute_name: str = "",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Einmaligkeitsprüfung über mehrere Dateien.

    Liefert chunkweise `Progress`-Schritte. Eingaben werden als gültig
    angenommen (Validierung gehört in die aufrufende Schicht). Parse-Fehler
    einzelner Dateien werden übersprungen.
    """
    if mode not in MODES:
        raise ValueError(f"Unbekannter Modus: {mode!r}")

    base = Path(base_path).expanduser()
    parser = make_parser()
    # tag_name landet in XPath-Ausdrücken, attribute_name nicht (Python-Vergleich).
    tag_name = ensure_tag_name(tag_name) if tag_name.strip() else ""
    attribute_name = attribute_name.strip()

    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_results: list[dict] = []

        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f, parser)
                quelle = get_quelle(doc.getroot(), ref.filename)
                chunk_results.extend(_check_file(
                    doc, mode=mode, tag_name=tag_name, attribute_name=attribute_name,
                    quelle=quelle, subdir=ref.subdir, filename=ref.filename,
                ))
            except Exception as e:  # noqa: BLE001 — einzelne Datei darf den Lauf nicht abbrechen
                print(f"Error in {ref.filename}: {e}")
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
