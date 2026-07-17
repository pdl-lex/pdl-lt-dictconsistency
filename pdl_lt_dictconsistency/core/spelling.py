"""Alte deutsche Rechtschreibung (vor Reform 1996/2006) — reine Kernlogik.

Durchsucht Textinhalte ausgewählter XML-Tags nach bekannten Altschreibungen.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, Progress
from .source import XmlFileRef, get_quelle, make_parser

CONTEXT_WINDOW = 40  # Zeichen links/rechts vom Treffer

DEFAULT_EXCLUDED_TAGS: frozenset[str] = frozenset({
    "autor", "bdo", "beleg-angabe", "beleg-kontext", "beleg-position",
    "beleg-quelle", "beleg-region", "beleg-text", "hoch", "komposita-position",
    "kompositum", "titel", "werk",
})

_SPELLINGS_CSV = Path(__file__).parent.parent.parent / "tools" / "spellings" / "spellings.csv"
_WHITELIST_CSV = Path(__file__).parent.parent.parent / "tools" / "spellings" / "whitelist.csv"


def _load_builtin_spellings() -> list[tuple[str, str]]:
    if not _SPELLINGS_CSV.exists():
        return []
    pairs: list[tuple[str, str]] = []
    with open(_SPELLINGS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            alt = (row.get("alt") or "").strip()
            neu = (row.get("neu") or "").strip()
            if alt and neu:
                pairs.append((alt, neu))
    return pairs


def _load_builtin_whitelist() -> frozenset[str]:
    if not _WHITELIST_CSV.exists():
        return frozenset()
    words: set[str] = set()
    with open(_WHITELIST_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            w = (row.get("wort") or "").strip()
            if w:
                words.add(w)
    return frozenset(words)


BUILTIN_SPELLINGS: list[tuple[str, str]] = _load_builtin_spellings()
BUILTIN_WHITELIST: frozenset[str] = _load_builtin_whitelist()


def compile_patterns(spellings: list[tuple[str, str]]) -> tuple[re.Pattern[str], dict[str, str]]:
    """Alle Schreibungspaare zu einer kombinierten Alternations-Regex verdichten.

    Eine kombinierte Regex ist deutlich schneller als N Einzelsuchen. Längere
    Alternativen zuerst, damit nicht vorzeitig ein kürzeres Präfix matcht.
    Case-sensitiv: dt. Substantive sind großgeschrieben, daher matcht das
    Verbmuster 'floß' nicht das Substantiv 'Floß'.
    """
    sorted_pairs = sorted(spellings, key=lambda x: len(x[0]), reverse=True)
    lookup: dict[str, str] = {old: new for old, new in sorted_pairs}
    alternatives = "|".join(re.escape(old) for old in lookup)
    pattern = re.compile(r"\b(?:" + alternatives + r")\b", re.UNICODE)
    return pattern, lookup


def exact_line(word: str, from_line: int, lines: list[str]) -> int:
    """Erste 1-basierte Zeile >= from_line, die word enthält."""
    for i in range(max(0, from_line - 1), len(lines)):
        if word in lines[i]:
            return i + 1
    return from_line


def find_in_text(text: str, pattern: re.Pattern[str], lookup: dict[str, str]) -> list[dict]:
    """Alle Altschreibungs-Treffer in text zurückgeben."""
    if not text or not text.strip():
        return []
    results = []
    text_single_line = text.replace("\n", " ").replace("\r", " ")
    for m in pattern.finditer(text_single_line):
        found = m.group(0)
        s, e = m.start(), m.end()
        ctx_s = max(0, s - CONTEXT_WINDOW)
        ctx_e = min(len(text_single_line), e + CONTEXT_WINDOW)
        prefix = "…" if ctx_s > 0 else ""
        suffix = "…" if ctx_e < len(text_single_line) else ""
        context = prefix + text_single_line[ctx_s:ctx_e].strip() + suffix
        results.append({"gefunden": found, "vorschlag": lookup[found], "kontext": context})
    return results


# Vorab kompilierte Builtin-Patterns (vermeidet Neukompilierung bei jedem Lauf).
_BUILTIN_PATTERN, _BUILTIN_LOOKUP = (
    compile_patterns(BUILTIN_SPELLINGS) if BUILTIN_SPELLINGS else (re.compile(r"(?!x)x"), {})
)


def collect_text_bearing_tags(files: Iterable[XmlFileRef | dict], base_path: str | Path) -> list[str]:
    """Alle Tags mit nicht-leerem Textinhalt sammeln (sortiert)."""
    base = Path(base_path).expanduser()
    parser = make_parser()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    tags: set[str] = set()
    for ref in refs:
        try:
            with open(ref.resolve(base), "rb") as f:
                doc = etree.parse(f, parser)
        except Exception as e:  # noqa: BLE001
            print(f"Error loading tags from {ref.filename}: {e}")
            continue
        for elem in doc.iter():
            if not isinstance(elem.tag, str):
                continue
            try:
                tag_name = etree.QName(elem).localname
            except Exception:
                continue
            if tag_name in tags:
                continue
            has_text = bool(elem.text and elem.text.strip()) or any(
                child.tail and child.tail.strip() for child in elem
            )
            if has_text:
                tags.add(tag_name)
    return sorted(tags)


def build_active_spellings(
    custom_spellings: list[tuple[str, str]],
    mode: str = "extend",
) -> tuple[re.Pattern[str], dict[str, str]]:
    """Aktive Wortliste aus Builtin + Custom bauen und kompilieren.

    mode: "extend" (Builtin + Custom) oder "replace" (nur Custom).
    Renutzt das vorkompilierte Builtin-Pattern, wenn keine Custom-Einträge da sind.
    """
    if mode == "replace":
        active = list(custom_spellings)
    else:
        active = list(BUILTIN_SPELLINGS) + list(custom_spellings)
    if not active:
        raise ValueError("Keine Wörterliste aktiv.")
    if mode == "extend" and not custom_spellings:
        return _BUILTIN_PATTERN, _BUILTIN_LOOKUP
    return compile_patterns(active)


def run_spelling(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    included_tags: list[str],
    custom_spellings: list[tuple[str, str]] | None = None,
    custom_list_mode: str = "extend",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Ausgewählte Tags auf alte Rechtschreibung durchsuchen."""
    pattern, lookup = build_active_spellings(custom_spellings or [], custom_list_mode)

    base = Path(base_path).expanduser()
    parser = make_parser()
    tags_to_search = set(included_tags)
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_results: list[dict] = []

        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as fh:
                    raw = fh.read()
                doc = etree.parse(io.BytesIO(raw), parser)
                file_lines = raw.decode("utf-8", errors="replace").splitlines()
                quelle = get_quelle(doc.getroot(), ref.filename)

                for elem in doc.iter():
                    raw_tag = elem.tag
                    if not isinstance(raw_tag, str):
                        continue
                    tag_name = raw_tag.split("}", 1)[1] if "}" in raw_tag else raw_tag
                    if tag_name not in tags_to_search:
                        continue

                    segments: list[tuple[str | None, int]] = []
                    if elem.text:
                        segments.append((elem.text, elem.sourceline or 0))
                    for child in elem:
                        if child.tail:
                            segments.append((child.tail, child.sourceline or elem.sourceline or 0))

                    for text, hint_line in segments:
                        for hit in find_in_text(text, pattern, lookup):
                            chunk_results.append({
                                "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                                "line": exact_line(hit["gefunden"], hint_line, file_lines),
                                "tag": tag_name,
                                "gefunden": hit["gefunden"],
                                "vorschlag": hit["vorschlag"],
                                "kontext": hit["kontext"],
                            })
            except Exception as e:  # noqa: BLE001
                print(f"Error searching {ref.filename}: {e}")
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
