"""Daten-Ingest — Upload (XML/ZIP), Verzeichnis-Scan, Datenquellen, wbdb-Ressourcen.

Reflex-frei. Erzeugt aus Uploads, vorhandenen Verzeichnissen oder wbdb-Bestand
ein serverseitiges Verzeichnis, auf das die Prüfungen via `directory` zeigen.
Sicherheitslogik (Zip-Slip, Größenlimits, XML-Magic-Bytes) aus der früheren
Reflex-App übernommen.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

MAX_ZIP_EXTRACT_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILE_SIZE = 50 * 1024 * 1024           # 50 MB pro Datei

# Verwaltetes Upload-Wurzelverzeichnis (Sessions als Unterordner).
UPLOADS_ROOT = Path(tempfile.gettempdir()) / "lt_uploads"

# Datenquellen-Konfiguration und Projektwurzel.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATASOURCES_FILE = _PROJECT_ROOT / "datasources.json"

# Erlaubte Daten-Wurzelverzeichnisse (os.pathsep-getrennt, z. B.
# LT_DATA_ROOTS=/mnt/data/wb/data). Nicht gesetzt = keine Beschränkung
# (lokale Entwicklung); auf dem Server im Docker-Image gesetzt.
DATA_ROOTS_ENV = "LT_DATA_ROOTS"


def allowed_data_roots() -> list[Path] | None:
    """Erlaubte Wurzeln aus LT_DATA_ROOTS; None = unbeschränkt."""
    raw = os.environ.get(DATA_ROOTS_ENV, "").strip()
    if not raw:
        return None
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def ensure_allowed_directory(directory: str | Path) -> Path:
    """Verzeichnis auflösen und gegen LT_DATA_ROOTS prüfen.

    Upload-Sessions (UPLOADS_ROOT) sind immer erlaubt. resolve() normalisiert
    ../-Tricks und Symlinks. Wirft PermissionError bei Verstoß.
    """
    base = Path(directory).expanduser().resolve()
    roots = allowed_data_roots()
    if roots is None:
        return base
    for root in (*roots, UPLOADS_ROOT.resolve()):
        if base.is_relative_to(root):
            return base
    raise PermissionError(
        f"Zugriff außerhalb der erlaubten Datenverzeichnisse: {base}"
    )


def is_allowed_directory(directory: str | Path) -> bool:
    try:
        ensure_allowed_directory(directory)
        return True
    except PermissionError:
        return False


# ── Upload-Sessions ─────────────────────────────────────────────────────────

def new_session() -> tuple[str, Path]:
    """Neue Upload-Session anlegen und (id, Pfad) zurückgeben."""
    session_id = uuid.uuid4().hex
    path = UPLOADS_ROOT / session_id
    path.mkdir(parents=True, exist_ok=True)
    return session_id, path


def session_path(session_id: str) -> Path:
    """Pfad einer bestehenden Session; wirft bei ungültiger/fremder id."""
    # Nur Hex-ids zulassen (kein Path-Escape).
    if not re.fullmatch(r"[0-9a-f]{32}", session_id or ""):
        raise ValueError("Ungültige Session-ID.")
    path = (UPLOADS_ROOT / session_id).resolve()
    if not path.is_relative_to(UPLOADS_ROOT.resolve()) or not path.is_dir():
        raise ValueError("Session nicht gefunden.")
    return path


def is_valid_xml(file_path: Path) -> bool:
    """Prüft per Magic-Bytes, ob die Datei mit XML-Inhalt beginnt."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(100).lstrip()
            return header.startswith(b"<?xml") or header.startswith(b"<")
    except Exception as e:  # noqa: BLE001
        print(f"Error in: {file_path}: {e}")
        return False


def extract_zip(zip_path: Path, extract_to: Path) -> int:
    """XML-Dateien aus ZIP extrahieren — mit Zip-Slip- und Zip-Bomb-Schutz.

    Das Größenlimit wird über die tatsächlich entpackten Bytes durchgesetzt
    (die im ZIP-Header deklarierte Größe kann lügen).
    """
    xml_count = 0
    total_size = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                if ".." in member or member.startswith("/") or member.startswith("\\"):
                    print(f"SECURITY: dangerous path skipped: {member}")
                    continue
                if not member.lower().endswith(".xml"):
                    continue
                target = extract_to / Path(member)
                if not target.resolve().is_relative_to(extract_to.resolve()):
                    print(f"SECURITY: path escape attempt: {member}")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with zip_ref.open(member) as src, open(target, "wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            total_size += len(chunk)
                            if total_size > MAX_ZIP_EXTRACT_SIZE:
                                raise ValueError(
                                    f"ZIP zu groß (>{MAX_ZIP_EXTRACT_SIZE // 1024 // 1024} MB)"
                                )
                            dst.write(chunk)
                except ValueError:
                    target.unlink(missing_ok=True)
                    raise
                if is_valid_xml(target):
                    xml_count += 1
                else:
                    print(f"SECURITY: fake XML removed: {member}")
                    target.unlink()
    except zipfile.BadZipFile as e:
        raise ValueError("Ungültige oder beschädigte ZIP-Datei") from e
    return xml_count


def save_upload(dest: Path, filename: str, content: bytes) -> list[str]:
    """Eine hochgeladene Datei (XML oder ZIP) sicher in dest ablegen.

    Gibt eine Liste von Fehlermeldungen zurück (leer = ok).
    """
    errors: list[str] = []
    safe_name = Path(filename).name
    if not safe_name:
        return ["Ungültiger Dateiname übersprungen."]
    if len(content) > MAX_FILE_SIZE:
        return [f"Datei {safe_name} zu groß (max {MAX_FILE_SIZE // 1024 // 1024} MB)."]

    file_path = dest / safe_name
    with open(file_path, "wb") as f:
        f.write(content)

    lower = safe_name.lower()
    if lower.endswith(".zip"):
        try:
            extract_zip(file_path, dest)
        except ValueError as e:
            errors.append(str(e))
        finally:
            file_path.unlink(missing_ok=True)
    elif lower.endswith(".xml"):
        if not is_valid_xml(file_path):
            file_path.unlink(missing_ok=True)
            errors.append(f"{safe_name} ist keine gültige XML-Datei.")
    else:
        file_path.unlink(missing_ok=True)
        errors.append(f"{safe_name}: nur XML- oder ZIP-Dateien erlaubt.")
    return errors


# ── Verzeichnis-Scan ────────────────────────────────────────────────────────

def scan(directory: str | Path) -> list[dict]:
    """Rekursiv alle gültigen *.xml-Dateien als {subdir, filename, size_kb}."""
    base = Path(directory).expanduser()
    out: list[dict] = []
    for file_path in base.rglob("*.xml"):
        try:
            if not is_valid_xml(file_path):
                continue
            rel_parent = file_path.relative_to(base).parent
            subdir = str(rel_parent) if rel_parent != Path(".") else "."
            out.append({
                "subdir": subdir,
                "filename": file_path.name,
                "size_kb": round(file_path.stat().st_size / 1024, 2),
            })
        except Exception as e:  # noqa: BLE001
            print(e)
            continue
    return out


def clear_session(session_id: str) -> None:
    """Eine Upload-Session löschen."""
    path = session_path(session_id)
    shutil.rmtree(path, ignore_errors=True)


def read_file_content(base: Path, subdir: str, filename: str) -> str:
    """Rohinhalt einer geprüften Datei lesen (für die Fundstellen-Vorschau).

    `subdir`/`filename` kommen aus einer Ergebniszeile, sind also grundsätzlich
    vertrauenswürdig — die Auflösung wird trotzdem gegen `base` abgesichert
    (gleiches Muster wie `extract_zip`/`materialize_db_selection`), falls sie
    z. B. über die API direkt manipuliert werden.
    """
    from .source import XmlFileRef

    base_resolved = base.resolve()
    target = XmlFileRef(subdir=subdir or ".", filename=filename).resolve(base).resolve()
    if not target.is_relative_to(base_resolved):
        raise PermissionError(f"Pfad außerhalb des Basisverzeichnisses: {filename}")
    if not target.is_file():
        raise FileNotFoundError(filename)
    return target.read_text(encoding="utf-8", errors="replace")


# ── wbdb-Artikel ────────────────────────────────────────────────────────────

# \x01: ein Steuerzeichen, das in resource_id/source_path nicht vorkommen kann
# — macht "resource_id || \x01 || source_path" zu einer eindeutigen Kodierung
# des Paars (kein Cross-Match zwischen z. B. resource_id="ab"+source_path="c"
# und resource_id="a"+source_path="bc" möglich). Muss mit dem `chr(1)` in der
# Query unten übereinstimmen.
_PAIR_SEP = "\x01"

# Bewusst EIN Array aus vorkombinierten Schlüsseln statt eines Joins über zwei
# parallele unnest()-Arrays (`= ANY` auf zwei Spalten). Gemessen an echten
# Daten (5000 Artikel, eine Ressource): der Zwei-Spalten-Join wählte einen
# Merge-Join über die (fast konstante, also kaum selektive) resource_id als
# Merge-Key und filterte source_path erst danach — das entartet bei geringer
# Kardinalität zu einem Cross-Product (172 Mio. Zeilenvergleiche, >2 Minuten).
# Der kombinierte Schlüssel macht daraus einen einzelnen Scan mit `= ANY(...)`
# auf einem Array (Postgres nutzt dafür einen Hash/Binärsuche-Check pro Zeile,
# keinen Join) — dieselben 5000 Artikel in ~2s statt >120s.
_MATERIALIZE_BY_PATH_QUERY = """
    SELECT a.article_id, a.resource_id, a.source_path, o.content
    FROM source.article a
    JOIN source.document o USING (content_sha256)
    WHERE (a.resource_id || chr(1) || a.source_path) = ANY(%(keys)s::text[])
"""


def _stream_articles_to_session(
    query: str, params: dict | tuple, *, principal: str, empty_error: str,
    source_paths: Iterable[str] = (),
    on_progress: Callable[[int], None] | None = None,
) -> dict:
    """Artikel aus wbdb (source.document, BDO-XML) in eine neue Upload-Session
    schreiben — danach ist es aus Sicht der Prüfungen ein ganz normales
    `directory`, wie ein Server-Pfad oder Upload.

    Dateiname = `source_path` (eindeutig innerhalb des aktuellen Imports;
    `article_id` ist es nicht, siehe WBDB-Doku §9). DB-Inhalt ist
    vertrauenswürdig — anders als bei Uploads gelten hier keine
    Größenlimits/Magic-Byte-Prüfung, wohl aber dieselbe
    Pfad-Escape-Absicherung wie bei `extract_zip`.

    `source_paths`: alle erwarteten Zielpfade, vorab bekannt (aus der Auswahl,
    nicht erst aus der Query-Antwort) — legt die Zielverzeichnisse einmalig an,
    statt bei jeder Datei erneut `mkdir(exist_ok=True)` aufzurufen. Gemessen an
    bwb (34.496 Artikel, 29 Buchstaben-Unterordner): die ~34.470 überflüssigen
    mkdir-Aufrufe kosteten allein mehr Zeit als die komplette Datenbankabfrage
    (165s von 178s Gesamtzeit) — mit Vorab-Anlage sinkt die Gesamtzeit auf ~70s.

    `on_progress(file_count)` wird nach jeder geschriebenen Datei aufgerufen,
    falls gesetzt — Grundlage für die Fortschrittsanzeige in
    `wbdb/load_jobs.py` bei größeren Auswahlen (mehrere zehn Sekunden).
    """
    from ..wbdb.connection import als, verbindung  # lazy: core bleibt ohne wbdb nutzbar

    session_id, dest = new_session()
    dest_resolved = dest.resolve()

    distinct_dirs = {(dest / sp).resolve().parent for sp in source_paths}
    for target_dir in distinct_dirs:
        if target_dir.is_relative_to(dest_resolved):
            target_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    with verbindung() as conn, als(conn, principal):
        with conn.cursor(name=f"materialize_{session_id}") as cur:
            cur.itersize = 200
            cur.execute(query, params)
            for article_id, resource_id, source_path, content in cur:
                target = (dest / source_path).resolve()
                if not target.is_relative_to(dest_resolved):
                    print(f"SECURITY: source_path escape attempt: {source_path!r} ({article_id})")
                    continue
                if target.parent not in distinct_dirs:
                    # source_path aus der DB-Antwort weicht von der vorab
                    # bekannten Auswahl ab (sollte nicht vorkommen) — Fallback
                    # statt eines FileNotFoundError beim Schreiben.
                    target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bytes(content))
                file_count += 1
                if on_progress:
                    on_progress(file_count)

    scanned = scan(dest)
    return {
        "directory": str(dest),
        "file_count": len(scanned),
        "files": scanned,
        "session_id": session_id,
        "errors": [] if file_count else [empty_error],
    }


def materialize_db_selection(
    pairs: set[tuple[str, str]], *, principal: str, on_progress: Callable[[int], None] | None = None,
) -> dict:
    """Eine `(resource_id, source_path)`-Auswahl aus wbdb materialisieren.

    Die Auswahl kommt aus `wbdb/index_store.py::resolve_selection()` (ganze
    Ressourcen, einzelne Buchstaben oder Artikel, gegen den lokalen
    Index-Cache aufgelöst) — das Lesen selbst bleibt hier live und
    RLS-geprüft: der Cache entscheidet nur, was im Baum *angeboten* wird, nie,
    was tatsächlich lesbar ist. `pairs` wird als nicht-leer vorausgesetzt; der
    Router prüft das vorher (422 bei leerer Auswahl).

    Kombinierter Schlüssel (`_PAIR_SEP`) statt eines Joins über resource_id und
    source_path getrennt, siehe Kommentar bei `_MATERIALIZE_BY_PATH_QUERY` —
    `source_path` ist nur innerhalb eines Imports eindeutig (pdl-lt-wbdb
    sql/schema.sql), ein einfacher `resource_id = ANY(...) AND source_path =
    ANY(...)`-Filter könnte sonst über Kreuz falsch matchen.
    """
    keys = [f"{resource_id}{_PAIR_SEP}{source_path}" for resource_id, source_path in sorted(pairs)]
    return _stream_articles_to_session(
        _MATERIALIZE_BY_PATH_QUERY,
        {"keys": keys},
        principal=principal,
        empty_error="Keine Artikel für die gewählte Auswahl gefunden.",
        source_paths=[source_path for _, source_path in pairs],
        on_progress=on_progress,
    )


# ── Datenquellen (datasources.json) ─────────────────────────────────────────

def _make_key(name: str) -> str:
    key = re.sub(r"[^\w]", "_", name.lower())
    return re.sub(r"_+", "_", key).strip("_") or "source"


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    return (p if p.is_absolute() else _PROJECT_ROOT / p).resolve()


def load_datasources() -> list[dict]:
    """Datenquellen aus datasources.json: {name, path, key, exists}.

    `path` ist immer absolut aufgelöst (erster existierender Kandidat gewinnt).
    """
    if not DATASOURCES_FILE.exists():
        return []
    with open(DATASOURCES_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    result: list[dict] = []
    seen: dict[str, int] = {}
    for entry in raw:
        name = str(entry.get("name", "")).strip()
        raw_path = entry.get("path", "")
        if not name or not raw_path:
            continue
        candidates = raw_path if isinstance(raw_path, list) else [raw_path]
        resolved = _resolve(str(candidates[0]))
        for candidate in candidates:
            p = _resolve(str(candidate))
            if p.exists():
                resolved = p
                break
        key = _make_key(name)
        if key in seen:
            seen[key] += 1
            key = f"{key}_{seen[key]}"
        else:
            seen[key] = 0
        usable = resolved.exists() and is_allowed_directory(resolved)
        result.append({"name": name, "path": str(resolved), "key": key, "exists": usable})
    return result
