"""Einen lokalen Admin-Account anlegen oder das Passwort eines bestehenden
Accounts zurücksetzen.

Nutzung:
    uv run python tools/create_admin_user.py <username> [--principal ID]

Das Passwort wird interaktiv abgefragt (nicht als Argument — landet sonst in
der Shell-History).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdl_lt_dictconsistency.auth import db  # noqa: E402
from pdl_lt_dictconsistency.auth.passwords import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--principal", default=None, help="wbdb principal_id (optional)")
    args = parser.parse_args()

    password = getpass.getpass("Passwort: ")
    if password != getpass.getpass("Passwort (Wiederholung): "):
        raise SystemExit("Passwörter stimmen nicht überein.")

    db.init_db()
    password_hash = hash_password(password)
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (args.username,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET password_hash = ?, is_admin = 1, active = 1, "
                "wbdb_principal_id = ? WHERE id = ?",
                (password_hash, args.principal, existing["id"]),
            )
            print(f"Passwort für {args.username!r} aktualisiert (Admin).")
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, wbdb_principal_id, is_admin) "
                "VALUES (?, ?, ?, 1)",
                (args.username, password_hash, args.principal),
            )
            print(f"Admin-Account {args.username!r} angelegt.")


if __name__ == "__main__":
    main()
