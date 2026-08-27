"""Automatisierte Variante des Phase-0-Spikes: echte wbdb-Verbindung, echter
Principal-Scope, echte Materialisierung von source.document nach XML-Dateien,
sowie (wo WBDB_INDEX_PRINCIPAL gesetzt ist) der Artikelindex-Reindex.

Wird übersprungen, wenn keine wbdb erreichbar ist (z. B. der lokale
Docker-Container 'wbdb' läuft nicht) oder die Reader-Zugangsdaten fehlen —
CI ohne Datenbank soll grün bleiben, nicht raten.
"""
from __future__ import annotations

import os

import psycopg
import pytest
from lxml import etree

from pdl_lt_dictconsistency.core import data as core_data
from pdl_lt_dictconsistency.wbdb import index_store
from pdl_lt_dictconsistency.wbdb.connection import als, current_scope, verbindung


def _wbdb_reachable() -> bool:
    if not os.environ.get("WBDB_READER_USER") or not os.environ.get("WBDB_READER_PASSWORD"):
        return False
    try:
        with psycopg.connect(
            host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            port=os.environ.get("POSTGRES_PORT", "5433"),
            dbname=os.environ.get("POSTGRES_DB", "wbdb"),
            user=os.environ["WBDB_READER_USER"],
            password=os.environ["WBDB_READER_PASSWORD"],
            connect_timeout=3,
        ) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _wbdb_reachable(),
    reason="wbdb nicht erreichbar (Docker-Container 'wbdb' läuft nicht oder Zugangsdaten fehlen)",
)


def test_current_scope_readable_for_anon():
    """auth.current_scope ist die Grundlage von admin.py's Testen-Knopf und von
    jedem Baum-Browse-Endpunkt (routers/db_index.py) — muss für die Leserolle
    wbdb_dictconsistency ohne Fehler abfragbar sein."""
    with verbindung() as conn:
        scope = current_scope(conn, "anon")
    assert isinstance(scope, list)
    for resource_id, collection_id in scope:
        assert resource_id and collection_id


def test_materialize_db_selection_writes_wellformed_xml(tmp_path, monkeypatch):
    """Automatisierte Variante des Phase-0-Bytevergleichs: die aus
    source.document geschriebenen Dateien müssen wohlgeformtes XML sein und
    dürfen den Session-Ordner nicht verlassen (source_path-Escape-Schutz).
    Fragt die zu materialisierenden Pfade direkt aus wbdb ab, unabhängig vom
    lokalen Index-Cache (der hat seinen eigenen Test unten)."""
    monkeypatch.setattr(core_data, "UPLOADS_ROOT", tmp_path / "lt_uploads")

    with verbindung() as conn, als(conn, "anon") as c:
        counts = c.execute("SELECT resource_id, count(*) FROM source.article GROUP BY resource_id").fetchall()
    if not counts:
        pytest.skip("Principal 'anon' hat aktuell keine Freigaben in wbdb.")
    smallest_resource, expected_count = min(counts, key=lambda r: r[1])

    with verbindung() as conn, als(conn, "anon") as c:
        paths = c.execute(
            "SELECT source_path FROM source.article WHERE resource_id = %s", (smallest_resource,)
        ).fetchall()
    pairs = {(smallest_resource, p[0]) for p in paths}

    result = core_data.materialize_db_selection(pairs, principal="anon")

    try:
        assert result["file_count"] == expected_count
        dest = core_data.UPLOADS_ROOT / result["session_id"]
        written = list(dest.rglob("*.xml"))
        assert len(written) == result["file_count"]
        for path in written:
            assert path.resolve().is_relative_to(dest.resolve())
            etree.parse(str(path))  # wirft XMLSyntaxError, wenn nicht wohlgeformt
    finally:
        core_data.clear_session(result["session_id"])


def _index_principal_configured() -> bool:
    return bool(os.environ.get("WBDB_INDEX_PRINCIPAL", "").strip())


@pytest.mark.skipif(not _index_principal_configured(), reason="WBDB_INDEX_PRINCIPAL nicht gesetzt")
def test_rebuild_index_matches_live_count(isolated_env):
    """Reindex-Zeilenzahl muss mit einer direkten, live abgefragten Zählung
    unter demselben Principal übereinstimmen — Regressionsanker gegen die
    frühere list_resources()-Logik."""
    index_store.init_db()
    status = index_store.rebuild_index(triggered_by="test")
    assert status["status"] == "ok"

    with verbindung() as conn, als(conn, os.environ["WBDB_INDEX_PRINCIPAL"]) as c:
        (live_count,) = c.execute("SELECT count(*) FROM source.article").fetchone()
    assert status["row_count"] == live_count


@pytest.mark.skipif(not _index_principal_configured(), reason="WBDB_INDEX_PRINCIPAL nicht gesetzt")
def test_rebuild_then_resolve_and_materialize_whole_resource(isolated_env, tmp_path, monkeypatch):
    """Ende-zu-Ende: Reindex -> Baum lesen -> Ressourcen-Auswahl auflösen ->
    laden, gegen den Principal 'anon' (dessen Scope typischerweise eine echte
    Teilmenge des Index-Principals ist)."""
    monkeypatch.setattr(core_data, "UPLOADS_ROOT", tmp_path / "lt_uploads")
    index_store.init_db()
    index_store.rebuild_index(triggered_by="test")

    tree = index_store.get_tree("anon")
    if not tree:
        pytest.skip("Principal 'anon' hat aktuell keine Freigaben in wbdb.")
    resource_id = min(tree, key=lambda r: r["article_count"])["resource_id"]

    pairs = index_store.resolve_selection("anon", [resource_id], [], [])
    assert pairs

    result = core_data.materialize_db_selection(pairs, principal="anon")
    try:
        assert result["file_count"] == len(pairs)
    finally:
        core_data.clear_session(result["session_id"])
