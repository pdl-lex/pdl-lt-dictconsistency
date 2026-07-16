"""Tag-/Pfadsuche — reine Kernlogik (Reflex-unabhängig)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, Progress
from .source import XmlFileRef, get_quelle


def parse_user_input(user_input: str) -> dict:
    """Benutzereingabe in Suchparameter zerlegen (simple/path/wildcard)."""
    if "/" not in user_input:
        return {"type": "simple", "elements": [user_input.lower().strip()]}
    elif "*" not in user_input:
        return {"type": "path", "elements": user_input.lower().strip().split("/")}
    else:
        return {"type": "wildcard", "elements": user_input.lower().strip().split("/")}


def build_xpath(search_params: dict) -> str | None:
    """XPath aus zerlegten Suchparametern bauen."""
    if search_params["type"] == "simple":
        tag = search_params["elements"][0]
        return f"//*[local-name()='{tag}']"
    elif search_params["type"] == "path":
        parts = [f"*[local-name()='{elem}']" for elem in search_params["elements"]]
        return "//" + "/".join(parts)
    elif search_params["type"] == "wildcard":
        parts = [
            "*" if elem == "*" else f"*[local-name()='{elem}']"
            for elem in search_params["elements"]
        ]
        return "//" + "//".join(parts)
    return None


def run_pathfinder(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    user_input: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Alle Dateien nach dem Tag-/Pfadmuster durchsuchen."""
    xpath = build_xpath(parse_user_input(user_input))
    base = Path(base_path).expanduser()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_results: list[dict] = []

        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f)
                quelle = get_quelle(doc.getroot(), ref.filename)
                for elem in doc.xpath(xpath):
                    path_parts: list[str] = []
                    current = elem
                    while current is not None:
                        path_parts.insert(0, etree.QName(current).localname)
                        current = current.getparent()
                    text_content = (elem.text or "").strip()
                    if len(text_content) > 100:
                        text_content = text_content[:100] + "..."
                    chunk_results.append({
                        "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                        "line": elem.sourceline or 0,
                        "full_path": "/".join(path_parts),
                        "text_content": text_content,
                    })
            except Exception as e:  # noqa: BLE001
                print(e)
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
