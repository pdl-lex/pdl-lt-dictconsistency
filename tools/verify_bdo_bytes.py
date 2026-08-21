"""Phase-0-Spike: Byte-Vergleich BDO-XML aus wbdb (source.document) gegen die
bisherige lokale Datei — verifiziert, dass beide Quellen dasselbe Artefakt
liefern, bevor core/data.py auf wbdb aufbaut.

Aufruf:
    uv run python tools/verify_bdo_bytes.py wbf__Katze "pfad/zu/Katze.xml"
    uv run python tools/verify_bdo_bytes.py wbf__Katze   # nur DB-Seite ausgeben
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdl_lt_dictconsistency.wbdb.connection import als, verbindung  # noqa: E402

QUERY = """
SELECT a.article_id, a.resource_id, a.source_path, a.content_sha256,
       length(o.content) AS size, o.content
FROM source.article a
JOIN source.document o USING (content_sha256)
WHERE a.article_id = %s
"""


def main() -> None:
    if len(sys.argv) < 2:
        print('Aufruf: verify_bdo_bytes.py <article_id> ["lokale_datei"]')
        raise SystemExit(1)
    article_id = sys.argv[1]
    local_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    with verbindung() as conn, als(conn, "anon") as c:
        rows = c.execute(QUERY, (article_id,)).fetchall()

    if not rows:
        print(
            f"Kein Artikel gefunden für article_id={article_id!r} "
            "(Principal 'anon' hat evtl. keine Freigabe, oder die id existiert nicht)."
        )
        raise SystemExit(1)

    print(f"{len(rows)} Treffer für article_id={article_id!r} "
          "(article_id ist nicht eindeutig, siehe WBDB-Doku §9):")
    for aid, resource_id, source_path, sha256, size, _content in rows:
        print(f"  resource_id={resource_id}  source_path={source_path!r}  "
              f"sha256={sha256[:12]}…  size={size} Bytes")

    if local_path is None:
        print("\nKeine lokale Datei zum Vergleich übergeben — nur DB-Seite ausgegeben.")
        return

    if len(rows) > 1:
        print("\nMehrere Treffer — vergleiche gegen den ersten (nach resource_id/source_path prüfen).")

    local_bytes = local_path.read_bytes()
    db_bytes = bytes(rows[0][5])
    print(f"\nLokale Datei: {local_path}  ({len(local_bytes)} Bytes)")
    print(f"DB (source.document): {len(db_bytes)} Bytes")
    if local_bytes == db_bytes:
        print("Byte-identisch.")
    else:
        print("NICHT byte-identisch — Diff prüfen, bevor darauf aufgebaut wird.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
