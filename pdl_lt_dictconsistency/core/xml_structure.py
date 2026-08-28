"""XML-Strukturanalyse — reine Kernlogik (Reflex-unabhängig).

Baut aus allen ausgewählten Dateien einen zusammengeführten Tag-/Attribut-/
Text-Baum: pro eindeutigem Pfad (Folge lokaler Tag-Namen ab der Wurzel) ein
Knoten mit den in den Daten vorkommenden Attributen (samt Beispielwerten)
und Beispiel-Textinhalten. Das Ergebnis wird als flache, tiefenerster Liste
von Zeilen (Tag-/Attribut-/Text-Zeilen) geliefert; Auf-/Zuklappen, Suche und
Datei-Filterung übernimmt das Frontend auf dieser Liste.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, Progress
from .source import XmlFileRef, make_parser

MAX_TEXT_LEN = 120


def run_structure(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Baut den zusammengeführten Strukturbaum über alle Dateien auf.

    Zwischenschritte melden nur den Fortschritt (leere `results`); die
    fertig abgeflachte Zeilenliste kommt in der letzten Progress-Meldung —
    kompatibel mit `_helpers.collect()`/`timed_response()`.
    """
    base = Path(base_path).expanduser()
    parser = make_parser()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    analysis: dict[str, dict] = {}
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f, parser)
                _traverse(doc.getroot(), analysis, ())
            except Exception as e:  # noqa: BLE001
                print(f"xml_structure: Fehler in {ref.filename}: {e}")
                continue
        yield Progress(files_checked=files_checked, results=[])

    yield Progress(files_checked=files_checked, results=flatten_to_rows(analysis))


def _traverse(elem, analysis: dict, parent_path: tuple) -> None:
    """Element rekursiv besuchen und in `analysis` einmischen."""
    if not isinstance(elem.tag, str):
        return  # Kommentare, Processing Instructions etc. überspringen

    try:
        tag = etree.QName(elem).localname
    except Exception:
        tag = str(elem.tag)

    current_path = parent_path + (tag,)
    path_key = "|".join(current_path)

    node = analysis.get(path_key)
    if node is None:
        node = {
            "tag": tag,
            "depth": len(parent_path),
            "children_order": [],
            "attrs": {},
            "text_examples": [],
            "has_text": False,
        }
        analysis[path_key] = node

    if parent_path:
        parent_node = analysis.get("|".join(parent_path))
        if parent_node is not None and tag not in parent_node["children_order"]:
            parent_node["children_order"].append(tag)

    text = (elem.text or "").strip()
    if text:
        node["has_text"] = True
        truncated = text[:MAX_TEXT_LEN]
        if truncated not in node["text_examples"]:
            node["text_examples"].append(truncated)

    for attr_qname, attr_val in elem.attrib.items():
        try:
            attr_local = etree.QName(attr_qname).localname
        except Exception:
            attr_local = str(attr_qname)

        values = node["attrs"].setdefault(attr_local, [])
        if attr_val not in values:
            values.append(attr_val)

    for child in elem:
        _traverse(child, analysis, current_path)


def flatten_to_rows(analysis: dict) -> list[dict]:
    """Analysis-Dict in eine flache, tiefenerste Zeilenliste umwandeln.

    Reihenfolge je Tag-Knoten: Tag-Zeile, Attribut-Zeilen (alphabetisch),
    #text-Zeile (falls vorhanden), Kind-Tag-Zeilen (in Erst-Auftrittsreihenfolge).
    """
    rows: list[dict] = []
    root_keys = sorted(k for k, v in analysis.items() if v["depth"] == 0)
    for root_key in root_keys:
        _flatten_recursive(root_key, analysis, rows)
    return rows


def _flatten_recursive(path_key: str, analysis: dict, rows: list[dict]) -> None:
    node = analysis[path_key]
    depth = node["depth"]
    tag_row_id = path_key.replace("|", "/")

    has_children = bool(node["children_order"]) or node["has_text"] or bool(node["attrs"])

    rows.append({
        "id": tag_row_id,
        "depth": depth,
        "kind": "tag",
        "label": node["tag"],
        "has_children": has_children,
    })

    for attr_name in sorted(node["attrs"].keys()):
        values = node["attrs"][attr_name]
        rows.append({
            "id": f"{tag_row_id}/@{attr_name}",
            "depth": depth + 1,
            "kind": "attr",
            "label": f"@{attr_name}",
            "has_children": False,
            "attr_values": values,
        })

    if node["has_text"]:
        rows.append({
            "id": f"{tag_row_id}/#text",
            "depth": depth + 1,
            "kind": "text_content",
            "label": "#text",
            "has_children": False,
            "text_examples": node["text_examples"],
        })

    for child_tag in node["children_order"]:
        child_key = f"{path_key}|{child_tag}"
        if child_key in analysis:
            _flatten_recursive(child_key, analysis, rows)
