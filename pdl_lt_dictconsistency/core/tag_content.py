"""Inhalts-/Leere-Tags-Suche — reine Kernlogik (Reflex-unabhängig)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE
from .source import XmlFileRef, get_quelle


@dataclass
class TagContentProgress:
    """Fortschritt der Inhaltssuche; tag_found für die 'Tag nicht gefunden'-Meldung."""

    files_checked: int
    results: list[dict] = field(default_factory=list)
    tag_found: bool = False


def get_attr_value(elem: etree._Element, attr_name: str) -> str | None:
    """Attributwert über lokalen Namen lesen, Namespaces berücksichtigend."""
    val = elem.get(attr_name)
    if val is None:
        for k, v in elem.attrib.items():
            try:
                local = etree.QName(k).localname if k.startswith("{") else k
            except Exception:
                local = k
            if local == attr_name:
                return v
    return val


def get_element_text(elem: etree._Element, include_whitespace: bool) -> str:
    """Direkten Textinhalt des Elements (ohne Kind-Element-Text) extrahieren."""
    text = elem.text or ""
    if not include_whitespace:
        text = text.strip()
        text = " ".join(text.split())
    return text


def format_text_with_visible_whitespace(text: str) -> str:
    """Whitespace durch sichtbare Symbole ersetzen."""
    return text.replace(" ", "·").replace("\n", "↵\n").replace("\r", "↵")


def _iter_docs(refs: list[XmlFileRef], base: Path):
    """Über (ref, doc) iterieren; Parse-Fehler überspringen."""
    for ref in refs:
        try:
            with open(ref.resolve(base), "rb") as f:
                yield ref, etree.parse(f)
        except Exception as e:  # noqa: BLE001
            print(f"Error loading {ref.filename}: {e}")
            continue


def _as_refs(files: Iterable[XmlFileRef | dict]) -> list[XmlFileRef]:
    return [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]


def collect_tags(files: Iterable[XmlFileRef | dict], base_path: str | Path) -> list[str]:
    """Alle eindeutigen Tag-Namen aus allen Dateien sammeln."""
    base = Path(base_path).expanduser()
    tags: set[str] = set()
    for _ref, doc in _iter_docs(_as_refs(files), base):
        for elem in doc.iter():
            if isinstance(elem.tag, str):
                try:
                    tags.add(etree.QName(elem).localname)
                except Exception:
                    continue
    return sorted(tags)


def collect_attrs(
    files: Iterable[XmlFileRef | dict], base_path: str | Path, tags_filter: list[str]
) -> list[str]:
    """Eindeutige Attributnamen der gewählten Tags sammeln."""
    base = Path(base_path).expanduser()
    attrs: set[str] = set()
    for _ref, doc in _iter_docs(_as_refs(files), base):
        for tag_name in tags_filter:
            for elem in doc.xpath(f"//*[local-name()='{tag_name}']"):
                for k in elem.attrib:
                    try:
                        local = etree.QName(k).localname if k.startswith("{") else k
                    except Exception:
                        local = k
                    attrs.add(local)
    return sorted(attrs)


def collect_attr_values(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    attrs_to_check: list[str],
    tags_filter: list[str] | None,
) -> list[str]:
    """Eindeutige Werte der gewählten Attribute (in gewählten Tags) sammeln."""
    base = Path(base_path).expanduser()
    values: set[str] = set()
    for _ref, doc in _iter_docs(_as_refs(files), base):
        if tags_filter:
            elements: list = []
            for tag_name in tags_filter:
                elements.extend(doc.xpath(f"//*[local-name()='{tag_name}']"))
        else:
            elements = [e for e in doc.iter() if isinstance(e.tag, str)]
        for elem in elements:
            for attr_name in attrs_to_check:
                val = get_attr_value(elem, attr_name)
                if val is not None:
                    values.add(val)
    return sorted(values)


def run_tag_content_search(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    tags_to_search: list[str],
    search_text: str = "",
    include_whitespace: bool = True,
    attrs_to_filter: list[str] | None = None,
    attr_value: str = "",
    is_single_tag_mode: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[TagContentProgress]:
    """Tag-Inhalte nach Text und/oder Attributen durchsuchen."""
    attrs_to_filter = attrs_to_filter or []
    has_attr_filter = bool(attrs_to_filter)
    attr_value = attr_value.strip()

    base = Path(base_path).expanduser()
    refs = _as_refs(files)
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_results: list[dict] = []
        tag_found = False

        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f)
                quelle = get_quelle(doc.getroot(), ref.filename)

                for tag_name in tags_to_search:
                    elements = doc.xpath(f"//*[local-name()='{tag_name}']")
                    if is_single_tag_mode and len(elements) > 0:
                        tag_found = True

                    for elem in elements:
                        elem_text = get_element_text(elem, include_whitespace)
                        if include_whitespace and not has_attr_filter and elem_text:
                            if elem_text.startswith("\n") and not elem_text.strip():
                                continue

                        if search_text:
                            if not include_whitespace:
                                term = " ".join(search_text.split())
                                content_match = bool(term) and term in elem_text
                            else:
                                content_match = search_text in elem_text
                        elif has_attr_filter:
                            content_match = True
                        else:
                            content_match = bool(elem_text)

                        attr_match = True
                        matched_attr = ""
                        matched_attr_val = ""
                        if has_attr_filter:
                            attr_match = False
                            for attr_name in attrs_to_filter:
                                val = get_attr_value(elem, attr_name)
                                if val is not None:
                                    if attr_value:
                                        if attr_value in val:
                                            attr_match = True
                                            matched_attr = attr_name
                                            matched_attr_val = val
                                            break
                                    else:
                                        attr_match = True
                                        matched_attr = attr_name
                                        matched_attr_val = val
                                        break

                        if content_match and attr_match:
                            display_text = elem_text
                            if len(display_text) > 200:
                                display_text = display_text[:200] + "..."
                            display_text = format_text_with_visible_whitespace(display_text)
                            chunk_results.append({
                                "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                                "line": elem.sourceline or 0,
                                "tag": tag_name,
                                "attribute": matched_attr,
                                "attr_value": matched_attr_val,
                                "text": display_text,
                            })
            except Exception as e:  # noqa: BLE001
                print(f"Error searching {ref.filename}: {e}")
                continue

        yield TagContentProgress(
            files_checked=files_checked, results=chunk_results, tag_found=tag_found
        )
