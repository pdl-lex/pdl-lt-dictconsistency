"""Prüfung der Bedeutungsnummerierung — reine Kernlogik (Reflex-unabhängig).

Jede Bedeutung ist ein verschachteltes Element (z. B. `<bedeutung-position>`),
dessen Nummer-Attribut den *kumulativen* Nummerierungsstring trägt (z. B.
`nr="12aαi"` = Ebene1 `12` + Ebene2 `a` + Ebene3 `α` + Ebene4 `i`, wie in den
BWB-/DIBS-Datenbeständen beobachtet). Anders als eine reine Zahlenlisten-
Validierung nutzen wir hier den echten Baum: die Tiefe eines Elements ergibt
sich direkt aus der XML-Verschachtelung (`nesting.get_depth_and_path`), und
die Elternnummer wird vom nächsten gleichnamigen Vorfahren gelesen statt aus
einer kombinierten Regex zurückgerechnet. Das vermeidet Mehrdeutigkeiten bei
mehreren gleichformatigen Ebenen hintereinander (z. B. arabisch→arabisch) und
macht eine separate "Einrückungsfehler"-Prüfung überflüssig, da es kein
zweites, unabhängig gegebenes Tiefensignal gibt, das abweichen könnte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, InvalidExpressionError, Progress, ensure_tag_name
from .nesting import get_depth_and_path
from .source import XmlFileRef, get_quelle, make_parser

MAX_LEVELS = 5


# ---------------------------------------------------------------------------
# Römische Zahlen (klein, keine externe Abhängigkeit nötig)

_ROMAN_PAIRS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)
_ROMAN_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def int_to_roman(n: int) -> str:
    if n <= 0:
        raise ValueError("n muss >= 1 sein")
    parts = []
    for value, symbol in _ROMAN_PAIRS:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def roman_to_int(s: str) -> int:
    s = s.upper()
    if not s or not _ROMAN_RE.fullmatch(s):
        raise ValueError(f"Ungültige römische Zahl: {s!r}")
    total = 0
    prev = 0
    for ch in reversed(s):
        value = _ROMAN_VALUES[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total


# ---------------------------------------------------------------------------
# Format-Typen je Ebene

# Korrektes 24-Buchstaben-Alphabet ohne Schlusssigma (ς) — in einer früheren
# Implementierung war ς fälschlich als eigene Position zwischen ρ und σ
# aufgeführt, was alle Positionen ab σ um eins verschob.
GREEK_LOWER = "αβγδεζηθικλμνξοπρστυφχψω"


@dataclass(frozen=True)
class FormatSpec:
    key: str
    label: str
    parse: Callable[[str], int | None]
    render: Callable[[int], str]


def _parse_arabic(s: str) -> int | None:
    return int(s) if re.fullmatch(r"[1-9][0-9]*", s) else None


def _parse_lower_letter(s: str) -> int | None:
    return ord(s) - ord("a") + 1 if re.fullmatch(r"[a-z]", s) else None


def _render_lower_letter(n: int) -> str:
    return chr(ord("a") + n - 1) if 1 <= n <= 26 else f"<{n}>"


def _parse_upper_letter(s: str) -> int | None:
    return ord(s) - ord("A") + 1 if re.fullmatch(r"[A-Z]", s) else None


def _render_upper_letter(n: int) -> str:
    return chr(ord("A") + n - 1) if 1 <= n <= 26 else f"<{n}>"


def _parse_greek(s: str) -> int | None:
    return GREEK_LOWER.index(s) + 1 if len(s) == 1 and s in GREEK_LOWER else None


def _render_greek(n: int) -> str:
    return GREEK_LOWER[n - 1] if 1 <= n <= len(GREEK_LOWER) else f"<{n}>"


def _parse_roman_lower(s: str) -> int | None:
    if not re.fullmatch(r"[ivxlcdm]+", s):
        return None
    try:
        return roman_to_int(s)
    except ValueError:
        return None


def _render_roman_lower(n: int) -> str:
    try:
        return int_to_roman(n).lower()
    except ValueError:
        return f"<{n}>"


def _parse_roman_upper(s: str) -> int | None:
    if not re.fullmatch(r"[IVXLCDM]+", s):
        return None
    try:
        return roman_to_int(s)
    except ValueError:
        return None


def _render_roman_upper(n: int) -> str:
    try:
        return int_to_roman(n)
    except ValueError:
        return f"<{n}>"


FORMATS: dict[str, FormatSpec] = {
    "arabisch": FormatSpec("arabisch", "Arabisch (1, 2, 3, …)", _parse_arabic, str),
    "kleinbuchstabe": FormatSpec("kleinbuchstabe", "Kleinbuchstabe (a, b, c, …)", _parse_lower_letter, _render_lower_letter),
    "grossbuchstabe": FormatSpec("grossbuchstabe", "Großbuchstabe (A, B, C, …)", _parse_upper_letter, _render_upper_letter),
    "griechisch": FormatSpec("griechisch", "Griechisch, klein (α, β, γ, …)", _parse_greek, _render_greek),
    "roemisch_gross": FormatSpec("roemisch_gross", "Römisch, groß (I, II, III, …)", _parse_roman_upper, _render_roman_upper),
    "roemisch_klein": FormatSpec("roemisch_klein", "Römisch, klein (i, ii, iii, …)", _parse_roman_lower, _render_roman_lower),
}


EMPTY_RULES: dict[str, str] = {
    "pflicht": "Nummer ist immer erforderlich",
    "einzelbedeutung": "Nummer darf fehlen, wenn keine Geschwister-Bedeutung vorhanden ist",
    "immer": "Nummer darf immer fehlen",
}


@dataclass(frozen=True)
class NumberingLevel:
    format: str
    empty_rule: str = "pflicht"


# ---------------------------------------------------------------------------
# Baum-Helfer

def _same_tag_parent(elem: etree._Element, tag_name: str) -> etree._Element | None:
    parent = elem.getparent()
    if parent is not None and isinstance(parent.tag, str) and etree.QName(parent).localname == tag_name:
        return parent
    return None


def _has_sibling(elem: etree._Element, tag_name: str) -> bool:
    """Ob es (in beliebiger Richtung) ein Geschwister mit demselben Tag gibt."""
    for sib in elem.itersiblings(preceding=True):
        if isinstance(sib.tag, str) and etree.QName(sib).localname == tag_name:
            return True
    for sib in elem.itersiblings(preceding=False):
        if isinstance(sib.tag, str) and etree.QName(sib).localname == tag_name:
            return True
    return False


def _previous_numbered_sibling(
    elem: etree._Element, tag_name: str, attribute_name: str
) -> tuple[etree._Element, str] | tuple[None, None]:
    """Nächstes vorangehendes Geschwister mit demselben Tag UND einer Nummer.

    Unnummerierte Geschwister dazwischen werden übersprungen (sie zählen
    nicht als Bezugspunkt für die Sequenzprüfung)."""
    for sib in elem.itersiblings(preceding=True):
        if isinstance(sib.tag, str) and etree.QName(sib).localname == tag_name:
            value = (sib.get(attribute_name) or "").strip()
            if value:
                return sib, value
    return None, None


def _check_element(
    elem: etree._Element,
    *,
    tag_name: str,
    attribute_name: str,
    levels: list[NumberingLevel],
    max_depth: int,
) -> dict | None:
    """Ein einzelnes Bedeutungs-Element prüfen. Liefert eine Fehlerzeile oder None."""
    depth, _ = get_depth_and_path(elem, tag_name, direct_only=True)

    if depth > max_depth:
        return {
            "line": elem.sourceline or 0, "tiefe": depth,
            "error_type": "Tiefe überschritten",
            "gefunden": f"Tiefe {depth}", "erwartet": f"maximal {max_depth} Ebene(n)",
        }

    level = levels[depth - 1]
    raw = (elem.get(attribute_name) or "").strip()

    if not raw:
        if level.empty_rule == "immer":
            return None
        if level.empty_rule == "einzelbedeutung" and not _has_sibling(elem, tag_name):
            return None
        return {
            "line": elem.sourceline or 0, "tiefe": depth,
            "error_type": "Nummer fehlt",
            "gefunden": "(fehlt)", "erwartet": f"eine Nummer (Ebene {depth}: {FORMATS[level.format].label})",
        }

    parent = _same_tag_parent(elem, tag_name)
    parent_raw = (parent.get(attribute_name) or "").strip() if parent is not None else ""

    if parent_raw:
        if not raw.startswith(parent_raw):
            return {
                "line": elem.sourceline or 0, "tiefe": depth,
                "error_type": "Elternfehler",
                "gefunden": raw, "erwartet": f"Präfix '{parent_raw}'",
            }
        suffix = raw[len(parent_raw):]
    else:
        suffix = raw

    fmt = FORMATS[level.format]
    value = fmt.parse(suffix)
    if value is None:
        return {
            "line": elem.sourceline or 0, "tiefe": depth,
            "error_type": "Formatfehler",
            "gefunden": raw, "erwartet": f"Ebene {depth}: {fmt.label}",
        }

    prev_sib, prev_raw = _previous_numbered_sibling(elem, tag_name, attribute_name)
    expected_value: int | None
    if prev_sib is None:
        expected_value = 1
    else:
        prev_suffix = prev_raw[len(parent_raw):] if parent_raw else prev_raw
        prev_value = fmt.parse(prev_suffix)
        expected_value = prev_value + 1 if prev_value is not None else None

    if expected_value is not None and value != expected_value:
        return {
            "line": elem.sourceline or 0, "tiefe": depth,
            "error_type": "Sequenzfehler",
            "gefunden": raw, "erwartet": parent_raw + fmt.render(expected_value),
        }

    return None


def run_numbering(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    tag_name: str,
    attribute_name: str,
    levels: list[NumberingLevel],
    max_depth: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Nummerierungsprüfung über mehrere Dateien (pro Datei eine Sequenz)."""
    if not (1 <= len(levels) <= MAX_LEVELS):
        raise ValueError(f"levels muss 1 bis {MAX_LEVELS} Einträge haben (bekam {len(levels)})")
    if not (1 <= max_depth <= len(levels)):
        raise ValueError(f"max_depth muss zwischen 1 und {len(levels)} liegen (bekam {max_depth})")
    for level in levels:
        if level.format not in FORMATS:
            raise InvalidExpressionError(f"Unbekanntes Format: {level.format!r}")
        if level.empty_rule not in EMPTY_RULES:
            raise InvalidExpressionError(f"Unbekannte Leer-Regel: {level.empty_rule!r}")

    tag_name = ensure_tag_name(tag_name)
    attribute_name = attribute_name.strip()
    base = Path(base_path).expanduser()
    parser = make_parser()
    xpath = f"//*[local-name()='{tag_name}']"
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

                # Ist ein Vorfahre bereits fehlerhaft, wird sein Nummernstring
                # als Präfix für Nachkommen unzuverlässig — Folgefehler im
                # gesamten Teilbaum werden daher unterdrückt (nur der eine
                # Fehler an der Wurzel des Problems wird gemeldet).
                unreliable: set[int] = set()

                for elem in doc.xpath(xpath):
                    if not isinstance(elem, etree._Element):
                        continue
                    parent = _same_tag_parent(elem, tag_name)
                    if parent is not None and id(parent) in unreliable:
                        unreliable.add(id(elem))
                        continue
                    error = _check_element(
                        elem, tag_name=tag_name, attribute_name=attribute_name,
                        levels=levels, max_depth=max_depth,
                    )
                    if error is not None:
                        unreliable.add(id(elem))
                        chunk_results.append({
                            "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                            **error,
                        })
            except Exception as e:  # noqa: BLE001
                print(f"Error in {ref.filename}: {e}")
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
