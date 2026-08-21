"""Wörterbücher (resource_id), wie sie der aktuelle Principal sehen darf."""
from __future__ import annotations

import psycopg

from .connection import als


def list_resources(conn: psycopg.Connection, principal: str) -> list[dict]:
    """Alle resource_id, die `principal` sehen darf, mit Artikelanzahl.

    resource_id ist nicht auf die drei aus datasources.json bekannten
    Wörterbücher beschränkt — es gibt z. B. auch `awb` und eigene
    resource_ids für unveröffentlichten Bestand wie `bwb-intern`. Durch RLS
    unter `als()` sieht die Abfrage ohnehin nur, was `principal` freigegeben
    ist (WBDB-Doku §2).
    """
    with als(conn, principal) as c:
        rows = c.execute(
            "SELECT resource_id, count(*) FROM source.article "
            "GROUP BY resource_id ORDER BY resource_id"
        ).fetchall()
    return [{"resource_id": resource_id, "article_count": count} for resource_id, count in rows]
