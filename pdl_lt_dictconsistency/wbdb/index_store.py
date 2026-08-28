"""Lokaler Cache des wbdb-Artikelbestands — Baum-Browser + schnelles Laden.

Ein admin-ausgelöster Reindex liest `source.article` komplett (unter einem
eigens dafür angelegten wbdb-Principal mit Grants auf jede Ressource/Collection,
siehe `wbdb/connection.py::index_principal()`) und speichert es lokal in
SQLite. Browsing (Baum, Suche) läuft danach ausschließlich gegen diesen Cache,
gefiltert bei *jeder* Anfrage über den live geprüften Scope des anfragenden
Principals (`wbdb/connection.py::current_scope()`) — nie über einen beim
Reindex eingefrorenen Scope. Das eigentliche Laden bleibt trotzdem live und
RLS-geprüft (`core/data.py::materialize_db_selection()`): der Cache entscheidet
nur, was im Baum *angeboten* wird, nie, was tatsächlich lesbar ist.

Generationswechsel wie in wbdb selbst (import/current_import): ein Build
schreibt komplett neue Zeilen unter einer neuen build_id; erst nach Erfolg wird
der Zeiger umgelegt und der alte Build gelöscht (ON DELETE CASCADE). Ein
fehlgeschlagener Build hinterlässt nichts Halbfertiges, der alte Snapshot
bleibt während des gesamten Laufs nutzbar.
"""
from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from datetime import datetime, timezone

from ..auth import db as local_db
from . import connection as wbdb_connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wbdb_index_build (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    row_count INTEGER,
    error TEXT,
    triggered_by TEXT
);

CREATE TABLE IF NOT EXISTS wbdb_index_article (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id INTEGER NOT NULL REFERENCES wbdb_index_build(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    letter TEXT NOT NULL,
    source_path TEXT NOT NULL,
    article_id TEXT NOT NULL,
    lemma TEXT,
    pos TEXT
);
CREATE INDEX IF NOT EXISTS idx_wia_browse ON wbdb_index_article(build_id, resource_id, letter);
CREATE INDEX IF NOT EXISTS idx_wia_scope  ON wbdb_index_article(build_id, resource_id, collection_id);
CREATE INDEX IF NOT EXISTS idx_wia_lemma  ON wbdb_index_article(build_id, lemma COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_wia_artid  ON wbdb_index_article(build_id, article_id COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS wbdb_index_current (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    build_id INTEGER REFERENCES wbdb_index_build(id)
);
"""

BATCH = 500
STALE_RUNNING_SECONDS = 15 * 60
SEARCH_LIMIT = 500
NO_LETTER = "–"  # Fallback für source_path ohne Buchstaben-Segment (< 3 Teile)

_ARTICLE_QUERY = """
    SELECT article_id, resource_id, collection_id, source_path, lemma, pos
    FROM source.article
"""


class IndexNotBuilt(Exception):
    """Kein Build vorhanden — Browse-Endpunkte antworten darauf mit 409."""


class RebuildInProgress(Exception):
    """Ein Build läuft bereits (jünger als STALE_RUNNING_SECONDS) — 409."""


def init_db() -> None:
    """Schema anlegen, falls noch nicht vorhanden. Idempotent, beim App-Start
    aufgerufen (api/main.py lifespan, neben auth.db.init_db())."""
    with local_db.connect() as conn:
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO wbdb_index_current (id, build_id) VALUES (1, NULL)")


def derive_letter(source_path: str) -> str:
    """Buchstabe = zweites Pfadsegment (`<ressource>/<Buchstabe>/<Datei>`), wie
    von der BDO-Lieferung foldiert (pdl-lt-wbdb ingest/import_zip.py, bestätigt
    für bdo-xml). Für Formate ohne diese Struktur (bislang unverifiziert für
    awb-tei/bwb-intern-xml) ein Fallback-Bucket statt eines Absturzes."""
    parts = source_path.split("/")
    return parts[1] if len(parts) >= 3 else NO_LETTER


def _parse_sqlite_datetime(value: str) -> float:
    """`datetime('now')` liefert UTC ohne Offset — als UTC-Epoch interpretieren,
    damit der Vergleich mit `time.time()` stimmt."""
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


def get_status() -> dict | None:
    with local_db.connect() as conn:
        row = conn.execute(
            "SELECT b.id AS build_id, b.started_at, b.finished_at, b.status, "
            "b.row_count, b.error, b.triggered_by "
            "FROM wbdb_index_current c JOIN wbdb_index_build b ON b.id = c.build_id "
            "WHERE c.id = 1"
        ).fetchone()
    return dict(row) if row else None


def _current_build_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT build_id FROM wbdb_index_current WHERE id = 1").fetchone()
    return row["build_id"] if row and row["build_id"] is not None else None


def _require_current_build(conn: sqlite3.Connection) -> int:
    build_id = _current_build_id(conn)
    if build_id is None:
        raise IndexNotBuilt("Noch kein Artikelindex aufgebaut.")
    return build_id


def rebuild_index(*, triggered_by: str) -> dict:
    """Liest `source.article` komplett unter dem Index-Principal, schreibt es
    unter einer neuen build_id, schwenkt den Zeiger erst nach Erfolg um."""
    principal = wbdb_connection.index_principal()

    with local_db.connect() as conn:
        running = conn.execute(
            "SELECT id, started_at FROM wbdb_index_build WHERE status = 'running' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if running is not None:
            age = time.time() - _parse_sqlite_datetime(running["started_at"])
            if age < STALE_RUNNING_SECONDS:
                raise RebuildInProgress(
                    f"Reindex läuft bereits seit {age:.0f}s (build_id={running['id']})."
                )
            conn.execute("DELETE FROM wbdb_index_build WHERE id = ?", (running["id"],))
        build_id = conn.execute(
            "INSERT INTO wbdb_index_build (triggered_by) VALUES (?)", (triggered_by,)
        ).lastrowid

    row_count = 0
    try:
        with wbdb_connection.verbindung() as pg_conn, wbdb_connection.als(pg_conn, principal):
            with pg_conn.cursor(name=f"wbdb_reindex_{build_id}") as pg_cur:
                pg_cur.itersize = 200
                pg_cur.execute(_ARTICLE_QUERY)
                batch: list[tuple] = []
                with local_db.connect() as conn:
                    for article_id, resource_id, collection_id, source_path, lemma, pos in pg_cur:
                        batch.append((
                            build_id, resource_id, collection_id,
                            derive_letter(source_path), source_path, article_id, lemma, pos,
                        ))
                        if len(batch) >= BATCH:
                            _insert_batch(conn, batch)
                            row_count += len(batch)
                            batch = []
                    if batch:
                        _insert_batch(conn, batch)
                        row_count += len(batch)
    except Exception as e:
        with local_db.connect() as conn:
            conn.execute(
                "UPDATE wbdb_index_build SET status = 'error', finished_at = datetime('now'), error = ? "
                "WHERE id = ?",
                (str(e), build_id),
            )
        raise

    with local_db.connect() as conn:
        conn.execute(
            "UPDATE wbdb_index_build SET status = 'ok', finished_at = datetime('now'), row_count = ? "
            "WHERE id = ?",
            (row_count, build_id),
        )
        conn.execute("UPDATE wbdb_index_current SET build_id = ? WHERE id = 1", (build_id,))
        conn.execute("DELETE FROM wbdb_index_build WHERE id != ? AND status != 'running'", (build_id,))

    status = get_status()
    assert status is not None
    return status


def _insert_batch(conn: sqlite3.Connection, batch: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO wbdb_index_article "
        "(build_id, resource_id, collection_id, letter, source_path, article_id, lemma, pos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        batch,
    )


def _scope_clause(scope: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """`(resource_id = ? AND collection_id = ?) OR ...` — der Scope ist klein
    (Ressourcen x Collections, siehe pdl-lt-wbdb sql/zugriff.sql), eine
    OR-Kette reicht statt SQLite-Tupel-IN-Gymnastik."""
    if not scope:
        return "0", []
    parts = ["(resource_id = ? AND collection_id = ?)"] * len(scope)
    params = [v for pair in scope for v in pair]
    return " OR ".join(parts), params


def _current_scope(principal: str) -> list[tuple[str, str]]:
    with wbdb_connection.verbindung() as pg_conn:
        return wbdb_connection.current_scope(pg_conn, principal)


def get_tree(principal: str) -> list[dict]:
    """Ressourcen + Buchstaben mit Zählung, gefiltert über den live geprüften
    Scope von `principal`. Leerer Scope → leere Liste, kein Fehler."""
    scope = _current_scope(principal)
    if not scope:
        return []

    with local_db.connect() as conn:
        build_id = _require_current_build(conn)
        clause, params = _scope_clause(scope)
        rows = conn.execute(
            f"SELECT resource_id, letter, count(*) AS n FROM wbdb_index_article "
            f"WHERE build_id = ? AND ({clause}) GROUP BY resource_id, letter "
            f"ORDER BY resource_id, letter",
            [build_id, *params],
        ).fetchall()

    resources: dict[str, dict] = {}
    for row in rows:
        entry = resources.setdefault(
            row["resource_id"], {"resource_id": row["resource_id"], "article_count": 0, "letters": []}
        )
        entry["letters"].append({"letter": row["letter"], "article_count": row["n"]})
        entry["article_count"] += row["n"]
    return list(resources.values())


def get_letter_articles(principal: str, resource_id: str, letter: str) -> list[dict]:
    scope = _current_scope(principal)
    with local_db.connect() as conn:
        build_id = _require_current_build(conn)
        clause, params = _scope_clause(scope)
        rows = conn.execute(
            f"SELECT source_path, article_id, lemma, pos FROM wbdb_index_article "
            f"WHERE build_id = ? AND resource_id = ? AND letter = ? AND ({clause}) "
            f"ORDER BY COALESCE(lemma, article_id) COLLATE NOCASE",
            [build_id, resource_id, letter, *params],
        ).fetchall()
    return [dict(r) for r in rows]


def search(principal: str, q: str) -> list[dict]:
    q = q.strip()
    if not q:
        return []
    scope = _current_scope(principal)
    with local_db.connect() as conn:
        build_id = _require_current_build(conn)
        clause, params = _scope_clause(scope)
        rows = conn.execute(
            f"SELECT resource_id, letter, source_path, article_id, lemma FROM wbdb_index_article "
            f"WHERE build_id = ? AND ({clause}) AND "
            f"(instr(lower(coalesce(lemma, '')), lower(?)) > 0 OR instr(lower(article_id), lower(?)) > 0) "
            f"ORDER BY resource_id, letter, COALESCE(lemma, article_id) COLLATE NOCASE "
            f"LIMIT {SEARCH_LIMIT}",
            [build_id, *params, q, q],
        ).fetchall()
    return [dict(r) for r in rows]


def search_files(principal: str, q: str, resource_ids: Iterable[str] | None = None) -> list[dict]:
    """Substring-Suche über den Dateinamen (letztes Segment von `source_path`)
    — Grundlage der Artikelsuche. Anders als `search()` (Lemma/Artikel-ID) geht
    es hier um den Dateinamen selbst, den der Cache schon kennt; kein
    zusätzlicher Spaltenindex nötig, da die Filterung nach dem Basisnamen
    (statt dem vollen Pfad) pro Suche in Python passiert — die Zeilenzahl pro
    Scope bleibt klein genug (siehe `_scope_clause`-Kommentar), dass das nicht
    ins Gewicht fällt.
    """
    q = q.strip().lower()
    if not q:
        return []
    scope = _current_scope(principal)
    if not scope:
        return []
    with local_db.connect() as conn:
        build_id = _require_current_build(conn)
        clause, params = _scope_clause(scope)
        sql = (
            f"SELECT resource_id, letter, source_path, article_id, lemma FROM wbdb_index_article "
            f"WHERE build_id = ? AND ({clause})"
        )
        args: list = [build_id, *params]
        ids = [r for r in (resource_ids or []) if r]
        if ids:
            sql += f" AND resource_id IN ({','.join('?' for _ in ids)})"
            args.extend(ids)
        rows = conn.execute(sql, args).fetchall()

    hits = [
        dict(r) for r in rows
        if q in r["source_path"].rsplit("/", 1)[-1].lower()
    ]
    hits.sort(key=lambda h: (h["resource_id"], h["letter"], (h["lemma"] or h["article_id"]).lower()))
    return hits[:SEARCH_LIMIT]


def resolve_selection(
    principal: str,
    resource_ids: Iterable[str],
    resource_letters: Iterable[tuple[str, str]],
    articles: Iterable[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Löst eine Baum-Auswahl gegen den aktuellen Build und den live geprüften
    Scope in `(resource_id, source_path)`-Paare auf. Liefert nur *Kandidaten*
    — das eigentliche Lesen bleibt RLS-geprüft
    (`core/data.py::materialize_db_selection`). Ein Artikel, der im Cache
    steht, aber gerade außerhalb des Scopes liegt (z. B. Grant zwischenzeitlich
    entzogen), wird still ausgelassen statt einen Fehler zu werfen — dieselbe
    "leerer Scope = leeres Ergebnis"-Konvention wie überall sonst in diesem Modul.
    """
    scope = _current_scope(principal)
    if not scope:
        return set()

    result: set[tuple[str, str]] = set()
    with local_db.connect() as conn:
        build_id = _require_current_build(conn)
        clause, scope_params = _scope_clause(scope)

        for resource_id in resource_ids:
            rows = conn.execute(
                f"SELECT source_path FROM wbdb_index_article "
                f"WHERE build_id = ? AND resource_id = ? AND ({clause})",
                [build_id, resource_id, *scope_params],
            ).fetchall()
            result.update((resource_id, r["source_path"]) for r in rows)

        for resource_id, letter in resource_letters:
            rows = conn.execute(
                f"SELECT source_path FROM wbdb_index_article "
                f"WHERE build_id = ? AND resource_id = ? AND letter = ? AND ({clause})",
                [build_id, resource_id, letter, *scope_params],
            ).fetchall()
            result.update((resource_id, r["source_path"]) for r in rows)

        for resource_id, source_path in articles:
            row = conn.execute(
                f"SELECT 1 FROM wbdb_index_article "
                f"WHERE build_id = ? AND resource_id = ? AND source_path = ? AND ({clause})",
                [build_id, resource_id, source_path, *scope_params],
            ).fetchone()
            if row is not None:
                result.add((resource_id, source_path))

    return result
