#!/usr/bin/env python3
"""Scan data/ subfolders and write split index files.

Output per subfolder (e.g. bdo):
  data/.tree/bdo/_dirs.json          — all directories with XML file counts
  data/.tree/bdo/bwb/A.json          — files directly in bwb/A/
  data/.tree/bdo/bwb/B.json          — files directly in bwb/B/
  ...

Run once (or after data changes):
    python index_data.py
"""
import json
import os
from pathlib import Path

DATA_DIR = Path("data")
INDEX_DIR = DATA_DIR / ".tree"


def _write_json(obj: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def build(root: Path, current: Path, index_base: Path) -> tuple[list[dict], int]:
    """Recursively build dir index and write per-dir file JSONs.

    Returns (dir_entries, xml_file_count_total).
    """
    try:
        entries = list(os.scandir(current))
    except PermissionError:
        return [], 0

    subdirs = sorted(
        (e for e in entries if e.is_dir(follow_symlinks=False)),
        key=lambda e: e.name.lower(),
    )
    files = sorted(
        (e for e in entries if e.is_file(follow_symlinks=False) and not e.name.startswith(".")),
        key=lambda e: e.name.lower(),
    )

    rel = current.relative_to(root)
    depth = len(rel.parts) - 1  # root itself → -1 (not written); its children → 0

    # Write file JSON for this directory (if it has direct files)
    xml_count_here = 0
    if files:
        file_items = []
        for entry in files:
            file_rel = Path(entry.path).relative_to(root)
            try:
                size_kb = round(entry.stat().st_size / 1024, 2)
            except OSError:
                size_kb = 0.0
            file_items.append({
                "path": "/".join(file_rel.parts),
                "name": entry.name,
                "is_dir": False,
                "depth": depth + 1,
                "size_kb": size_kb,
            })
            if entry.name.lower().endswith(".xml"):
                xml_count_here += 1

        if rel.parts:  # skip root itself
            out = index_base
            for part in rel.parts[:-1]:
                out = out / part
            _write_json(file_items, out / f"{rel.name}.json")

    # Recurse into subdirs
    dir_entries: list[dict] = []
    xml_count_total = xml_count_here
    for entry in subdirs:
        sub_path = Path(entry.path)
        sub_rel = sub_path.relative_to(root)
        sub_entries, sub_xml = build(root, sub_path, index_base)
        xml_count_total += sub_xml
        dir_entries.append({
            "path": "/".join(sub_rel.parts),
            "name": entry.name,
            "is_dir": True,
            "depth": len(sub_rel.parts) - 1,
            "file_count": sub_xml,
        })
        dir_entries.extend(sub_entries)

    return dir_entries, xml_count_total


def main() -> None:
    if not DATA_DIR.exists():
        print(f"Fehler: Verzeichnis '{DATA_DIR}' nicht gefunden.")
        return
    INDEX_DIR.mkdir(exist_ok=True)
    subfolders = sorted(
        d for d in DATA_DIR.iterdir()
        if d.is_dir() and d.name != ".tree"
    )
    if not subfolders:
        print("Keine Unterordner in data/ gefunden.")
        return
    for subfolder in subfolders:
        print(f"Indexiere {subfolder.name} ...", end=" ", flush=True)
        index_base = INDEX_DIR / subfolder.name
        index_base.mkdir(exist_ok=True)
        dir_entries, xml_total = build(subfolder, subfolder, index_base)
        _write_json(dir_entries, index_base / "_dirs.json")
        print(f"{xml_total:,} XML-Dateien, {len(dir_entries)} Ordner")
    print("Fertig.")


if __name__ == "__main__":
    main()
