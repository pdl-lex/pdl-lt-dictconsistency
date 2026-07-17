"""Bedeutungsstatistiken (Anzahl/Länge) — reine Kernlogik (Reflex-unabhängig)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, Progress, ensure_tag_name
from .source import XmlFileRef, get_quelle, make_parser


def run_senses_stats(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    tag_name: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[Progress]:
    """Pro Datei Anzahl und Textlänge (min/max/Ø) des Tags auswerten."""
    tag_name = ensure_tag_name(tag_name)
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
                elements = doc.xpath(xpath)
                count = len(elements)
                if count == 0:
                    chunk_results.append({
                        "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                        "count": 0, "min_length": "-", "max_length": "-", "avg_length": "-",
                    })
                else:
                    lengths = [
                        len("".join(elem.itertext()))
                        for elem in elements if isinstance(elem, etree._Element)
                    ]
                    avg = round(sum(lengths) / len(lengths), 1) if lengths else 0
                    chunk_results.append({
                        "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                        "count": count,
                        "min_length": min(lengths) if lengths else "-",
                        "max_length": max(lengths) if lengths else "-",
                        "avg_length": avg,
                    })
            except Exception as e:  # noqa: BLE001
                print(f"Error in {ref.filename}: {e}")
                continue

        yield Progress(files_checked=files_checked, results=chunk_results)
