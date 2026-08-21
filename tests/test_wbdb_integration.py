"""Automatisierte Variante des Phase-0-Spikes: echte wbdb-Verbindung, echter
Principal-Scope, echte Materialisierung von source.document nach XML-Dateien.

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
from pdl_lt_dictconsistency.wbdb.connection import als, verbindung
from pdl_lt_dictconsistency.wbdb.resources import list_resources


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
    """auth.current_scope ist die Grundlage von admin.py's Testen-Knopf — muss
    für die Leserolle wbdb_dictconsistency ohne Fehler abfragbar sein."""
    with verbindung() as conn, als(conn, "anon") as c:
        cur = c.execute("SELECT * FROM auth.current_scope")
        columns = [col.name for col in cur.description]
        rows = cur.fetchall()
    assert columns
    assert isinstance(rows, list)


def test_list_resources_returns_structured_counts():
    with verbindung() as conn:
        resources = list_resources(conn, "anon")
    assert isinstance(resources, list)
    for entry in resources:
        assert entry.keys() == {"resource_id", "article_count"}
        assert entry["article_count"] >= 0


def test_materialize_db_resource_writes_wellformed_xml(tmp_path, monkeypatch):
    """Automatisierte Variante des Phase-0-Bytevergleichs: die aus
    source.document geschriebenen Dateien müssen wohlgeformtes XML sein und
    dürfen den Session-Ordner nicht verlassen (source_path-Escape-Schutz)."""
    monkeypatch.setattr(core_data, "UPLOADS_ROOT", tmp_path / "lt_uploads")

    with verbindung() as conn:
        resources = list_resources(conn, "anon")
    if not resources:
        pytest.skip("Principal 'anon' hat aktuell keine Freigaben in wbdb.")

    smallest = min(resources, key=lambda r: r["article_count"])
    result = core_data.materialize_db_resource([smallest["resource_id"]], principal="anon")

    try:
        assert result["file_count"] == smallest["article_count"]
        dest = core_data.UPLOADS_ROOT / result["session_id"]
        written = list(dest.rglob("*.xml"))
        assert len(written) == result["file_count"]
        for path in written:
            assert path.resolve().is_relative_to(dest.resolve())
            etree.parse(str(path))  # wirft XMLSyntaxError, wenn nicht wohlgeformt
    finally:
        core_data.clear_session(result["session_id"])
