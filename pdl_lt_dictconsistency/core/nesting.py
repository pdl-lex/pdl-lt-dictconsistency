"""Verschachtelungsanalyse — reine Kernlogik (Reflex-unabhängig)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, InvalidExpressionError, Progress, ensure_tag_name
from .source import XmlFileRef, get_quelle, make_parser

MODES = ("Direkte Verschachtelung", "Beliebige Verschachtelung", "Pfad / Wildcard")


def pattern_to_xpath(pattern: str) -> str:
    """Einfaches Pfadmuster mit optionalen Wildcards in XPath übersetzen.

    sense/cit/sense -> //*[local-name()='sense']/*[local-name()='cit']/*[local-name()='sense']
    sense/*/sense   -> //*[local-name()='sense']/*/*[local-name()='sense']
    """
    parts = [p.strip() for p in pattern.strip().split("/") if p.strip()]
    xpath_parts = []
    for part in parts:
        xpath_parts.append("*" if part == "*" else f"*[local-name()='{ensure_tag_name(part)}']")
    return "//" + "/".join(xpath_parts) if xpath_parts else "//*"


def get_depth_and_path(elem: etree._Element, tag_name: str, direct_only: bool) -> tuple[int, str]:
    """(depth, display_path) für ein Treffer-Element zurückgeben.

    direct_only=True:  nur direkt aufeinanderfolgende gleichnamige Vorfahren zählen.
    direct_only=False: alle gleichnamigen Vorfahren zählen, egal was dazwischen liegt.
    """
    ancestors: list[str] = []
    for anc in elem.iterancestors():
        if isinstance(anc.tag, str):
            ancestors.append(etree.QName(anc).localname)
    ancestors.reverse()  # root-first

    if direct_only:
        depth = 1
        for anc in reversed(ancestors):
            if anc == tag_name:
                depth += 1
            else:
                break
        chain = " > ".join([tag_name] * depth)
        return depth, chain
    else:
        same_tag_count = sum(1 for a in ancestors if a == tag_name)
        depth = same_tag_count + 1
        first_match = next((i for i, a in enumerate(ancestors) if a == tag_name), None)
        if first_match is not None:
            path = " > ".join(ancestors[first_match:] + [tag_name])
        else:
            path = tag_name
        return depth, path


def run_nesting(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    search_mode: str,
    tag_input: str = "",
    path_input: str = "",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Verschachtelungsanalyse über mehrere Dateien.

    Bei ungültigem Pfadmuster wird beim Durchlaufen `InvalidExpressionError`
    ausgelöst (das XPath schlägt für alle Dateien gleich fehl).
    """
    if search_mode not in MODES:
        raise ValueError(f"Unbekannter Modus: {search_mode!r}")

    is_path_mode = search_mode == "Pfad / Wildcard"
    is_direct = search_mode == "Direkte Verschachtelung"

    if is_path_mode:
        xpath = pattern_to_xpath(path_input)
        tag_name = ""
    else:
        tag_name = ensure_tag_name(tag_input)
        xpath = f"//*[local-name()='{tag_name}']"

    base = Path(base_path).expanduser()
    parser = make_parser()
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

                try:
                    elements = doc.xpath(xpath)
                except etree.XPathEvalError as e:
                    raise InvalidExpressionError(f"Ungültiger Ausdruck: {e}") from e

                for elem in elements:
                    if not isinstance(elem, etree._Element):
                        continue
                    if is_path_mode:
                        elem_tag = etree.QName(elem).localname if isinstance(elem.tag, str) else "?"
                        chunk_results.append({
                            "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                            "line": elem.sourceline or 0, "depth": "",
                            "details": f"<{elem_tag}>",
                        })
                    else:
                        depth, path = get_depth_and_path(elem, tag_name, is_direct)
                        if depth > 1:
                            chunk_results.append({
                                "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                                "line": elem.sourceline or 0, "depth": depth, "details": path,
                            })
            except InvalidExpressionError:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"Error in {ref.filename}: {e}")
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
