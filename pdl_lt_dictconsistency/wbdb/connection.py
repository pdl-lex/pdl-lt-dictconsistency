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

load_dotenv()


def default_principal() -> str:
    """WBDB_PRINCIPAL-Fallback für nicht-interaktive Nutzung (z. B. eigene Skripte).

    Seit Phase 3 (Pro-Nutzer-Principal) verwendet die App selbst diese Funktion
    nicht mehr — jeder angemeldete Nutzer bekommt seinen eigenen, in `auth.users`
    hinterlegten Principal; ohne Zuordnung gibt es keinen DB-Zugriff, kein
    stiller Fallback auf 'anon'.
    """
    return os.environ.get("WBDB_PRINCIPAL", "anon")


def verbindung() -> psycopg.Connection:
    """Neue Verbindung als Rolle wbdb_dictconsistency (rein lesend)."""
    return psycopg.connect(
        # 127.0.0.1 statt "localhost": unter Windows verzögert die IPv6-Route
        # sonst jeden Verbindungsaufbau um ~2 Minuten, bis sie ins Timeout läuft.
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        dbname=os.environ.get("POSTGRES_DB", "wbdb"),
        user=os.environ["WBDB_READER_USER"],
        password=os.environ["WBDB_READER_PASSWORD"],
    )


@contextmanager
def als(conn: psycopg.Connection, principal: str) -> Iterator[psycopg.Connection]:
    """Transaktion, die für genau diesen Principal läuft.

    Ohne gesetzten Principal liefert jede Abfrage still null Zeilen (kein
    Fehler) — siehe WBDB-Doku §2.
    """
    with conn.transaction():
        conn.execute("SELECT set_config('wbdb.principal', %s, true)", (principal,))
        yield conn
