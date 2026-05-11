"""Shared config for data source paths and index location.

datasources.json lives at the project root (git-ignored).
Format:
  [
    {"path": "../relative/or/C:/absolute", "name": "Display Name"},
    ...
  ]

'path' may also be a list of candidates — the first existing path is used.
This lets you share one datasources.json across machines with different layouts:
  {"path": ["/home/user/data/bwb", "C:/Users/other/data/bwb"], "name": "BWB"}

Relative paths are resolved relative to the project root.
~ is expanded to the user home directory.
"""
import json
import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
DATASOURCES_FILE = _PROJECT_ROOT / "datasources.json"
INDEX_DIR = _PROJECT_ROOT / "index"


def _make_key(name: str) -> str:
    """Create a filesystem-safe folder name from a display name."""
    key = re.sub(r"[^\w]", "_", name.lower())
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "source"


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (_PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


def load_datasources() -> list[dict]:
    """Return list of {name, path, key} entries from datasources.json.

    path is always an absolute, resolved string (first existing candidate wins).
    key is a filesystem-safe identifier derived from name.
    """
    if not DATASOURCES_FILE.exists():
        return []
    with open(DATASOURCES_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    result: list[dict] = []
    seen_keys: dict[str, int] = {}
    for entry in raw:
        name = str(entry.get("name", "")).strip()
        raw_path = entry.get("path", "")
        if not name or not raw_path:
            continue
        candidates = raw_path if isinstance(raw_path, list) else [raw_path]
        # Use first existing path; fall back to first candidate if none exist
        resolved = _resolve(str(candidates[0]))
        for candidate in candidates:
            p = _resolve(str(candidate))
            if p.exists():
                resolved = p
                break
        key = _make_key(name)
        if key in seen_keys:
            seen_keys[key] += 1
            key = f"{key}_{seen_keys[key]}"
        else:
            seen_keys[key] = 0
        result.append({"name": name, "path": str(resolved), "key": key})
    return result
