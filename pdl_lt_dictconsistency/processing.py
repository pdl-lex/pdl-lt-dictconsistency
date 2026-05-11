"""Chunked file processing utilities to avoid OOM on large datasets.

Results are written to per-session JSONL temp files during processing
so the Reflex state stays small. Load them once at the end.
"""
import json
import tempfile
from pathlib import Path

CHUNK_SIZE = 500


def _path(token: str, tag: str) -> Path:
    return Path(tempfile.gettempdir()) / f"dc_{token}_{tag}.jsonl"


def clear(token: str, tag: str) -> None:
    _path(token, tag).unlink(missing_ok=True)


def append(token: str, tag: str, items: list[dict]) -> None:
    if not items:
        return
    p = _path(token, tag)
    with open(p, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def get_quelle(root, filename: str) -> str:
    """Return source label for a parsed XML document.

    BWB files get "BWB Bd. X, H. Y"; all others get the filename.
    Checks root element and its direct children (BWB stores wb/band/heft on
    the <artikel> child, not on the <bdo> root).
    root may be None (e.g. when the file failed to parse).
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


def load(token: str, tag: str) -> list[dict]:
    p = _path(token, tag)
    if not p.exists():
        return []
    rows: list[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    p.unlink(missing_ok=True)
    return rows
