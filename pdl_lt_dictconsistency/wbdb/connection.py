"""Verbindung zu wbdb — Rolle wbdb_dictconsistency, principal-gebundene Transaktionen.

Siehe setup/Readme Access WBDB.md §4. `set_config(..., true)` statt `SET LOCAL`:
der Principal kommt parametrisiert rein, nie String-formatiert in die Anweisung.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

_pool: ConnectionPool | None = None


def default_principal() -> str:
    """WBDB_PRINCIPAL-Fallback für nicht-interaktive Nutzung (z. B. eigene Skripte).

    Seit Phase 3 (Pro-Nutzer-Principal) verwendet die App selbst diese Funktion
    nicht mehr — jeder angemeldete Nutzer bekommt seinen eigenen, in `auth.users`
    hinterlegten Principal; ohne Zuordnung gibt es keinen DB-Zugriff, kein
    stiller Fallback auf 'anon'.
    """
    return os.environ.get("WBDB_PRINCIPAL", "anon")


def index_principal() -> str:
    """Principal für den Artikelindex-Reindex — eigens in wbdb angelegt, mit
    restricted-Grants auf jede Ressource/Collection, damit der Cache nie
    schmaler ist als das, was einzelne Nutzer sehen dürfen. Kein stiller
    Fallback auf WBDB_PRINCIPAL/anon, analog zu `_require_principal()` in
    api/routers/data.py."""
    principal = os.environ.get("WBDB_INDEX_PRINCIPAL", "").strip()
    if not principal:
        raise RuntimeError(
            "WBDB_INDEX_PRINCIPAL ist nicht gesetzt — der Reindex braucht einen "
            "eigenen wbdb-Principal mit Grants auf jede Ressource (siehe README)."
        )
    return principal


def _conninfo() -> dict:
    return dict(
        # 127.0.0.1 statt "localhost": unter Windows verzögert die IPv6-Route
        # sonst jeden Verbindungsaufbau um ~2 Minuten, bis sie ins Timeout läuft.
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        dbname=os.environ.get("POSTGRES_DB", "wbdb"),
        user=os.environ["WBDB_READER_USER"],
        password=os.environ["WBDB_READER_PASSWORD"],
    )


def init_pool() -> None:
    """Einmal beim App-Start aufgerufen (lifespan) — sonst öffnet jede Anfrage
    eine neue Verbindung samt TCP-/Auth-Handshake. Fehlende wbdb-Zugangsdaten
    (Tests, lokale Entwicklung ohne wbdb) sind kein Fehler: `verbindung()`
    fällt dann weiterhin auf eine direkte, lazy Verbindung pro Aufruf zurück,
    genau wie zuvor ganz ohne Pool."""
    global _pool
    if _pool is not None:
        return
    if not os.environ.get("WBDB_READER_USER") or not os.environ.get("WBDB_READER_PASSWORD"):
        return
    _pool = ConnectionPool(kwargs=_conninfo(), min_size=1, max_size=10, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def verbindung() -> psycopg.Connection:
    """Verbindung als Rolle wbdb_dictconsistency (rein lesend) — aus dem Pool,
    wenn die App läuft, sonst eine direkte Verbindung (Skripte/Tests außerhalb
    des FastAPI-Lifespans, z. B. tests/test_wbdb_integration.py)."""
    if _pool is not None:
        return _pool.connection()
    return psycopg.connect(**_conninfo())


@contextmanager
def als(conn: psycopg.Connection, principal: str) -> Iterator[psycopg.Connection]:
    """Transaktion, die für genau diesen Principal läuft.

    Ohne gesetzten Principal liefert jede Abfrage still null Zeilen (kein
    Fehler) — siehe WBDB-Doku §2. `set_config(..., true)` ist transaktionslokal,
    also unabhängig davon sicher, ob `conn` aus einem Pool stammt.
    """
    with conn.transaction():
        conn.execute("SELECT set_config('wbdb.principal', %s, true)", (principal,))
        yield conn


def current_scope(conn: psycopg.Connection, principal: str) -> list[tuple[str, str]]:
    """`(resource_id, collection_id)`-Paare, die `principal` gerade sehen darf.

    Klein by construction (siehe pdl-lt-wbdb sql/zugriff.sql), daher live bei
    jeder Anfrage neu geprüft statt gecacht — Grundlage für jede Filterung des
    lokalen Artikelindex-Caches gegen echte wbdb-Freigaben."""
    with als(conn, principal) as c:
        rows = c.execute("SELECT resource_id, collection_id FROM auth.current_scope").fetchall()
    return [(r[0], r[1]) for r in rows]
