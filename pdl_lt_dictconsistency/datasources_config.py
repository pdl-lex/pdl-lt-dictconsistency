"""Shared config for data source paths and index location.

datasources.json lives at the project root (git-ignored).
Format:
  [
    {"path": "../relative/or/C:/absolute", "name": "Display Name"},
    ...
  ]

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


def load_datasources() -> list[dict]:
    """Return list of {name, path, key} entries from datasources.json.

    path is always an absolute, resolved string.
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
        path_str = str(entry.get("path", "")).strip()
        if not name or not path_str:
            continue
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (_PROJECT_ROOT / p).resolve()
        else:
            p = p.resolve()
        key = _make_key(name)
        # Deduplicate keys
        if key in seen_keys:
            seen_keys[key] += 1
            key = f"{key}_{seen_keys[key]}"
        else:
            seen_keys[key] = 0
        result.append({"name": name, "path": str(p), "key": key})
    return result
