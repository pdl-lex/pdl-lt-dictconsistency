"""Gemeinsame Fixtures: isolierte lokale Auth-DB/Uploads, TestClient, Test-Nutzer."""
from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from pdl_lt_dictconsistency.auth import db as auth_db
from pdl_lt_dictconsistency.auth.passwords import hash_password
from pdl_lt_dictconsistency.core import data as core_data


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Frische lokale SQLite-DB und ein Wegwerf-Upload-Root pro Test.

    Verhindert, dass Tests die echte local.db oder den System-Temp-Ordner
    lt_uploads berühren.
    """
    monkeypatch.setenv(auth_db.LOCAL_DB_PATH_ENV, str(tmp_path / "test_local.db"))
    monkeypatch.delenv("LT_DATA_ROOTS", raising=False)
    monkeypatch.setattr(core_data, "UPLOADS_ROOT", tmp_path / "lt_uploads")
    return tmp_path


@pytest.fixture
def client(isolated_env) -> Iterator[TestClient]:
    from pdl_lt_dictconsistency.api.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user() -> Callable[..., None]:
    """Legt einen lokalen Nutzer direkt in der (isolierten) Auth-DB an,
    ohne über den Admin-Endpunkt oder das interaktive Bootstrap-Skript zu gehen."""

    def _make_user(
        username: str,
        password: str,
        *,
        is_admin: bool = False,
        active: bool = True,
        principal: str | None = None,
    ) -> None:
        auth_db.init_db()
        with auth_db.connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, wbdb_principal_id, is_admin, active) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, hash_password(password), principal, int(is_admin), int(active)),
            )

    return _make_user


@pytest.fixture
def logged_in_client(client: TestClient, make_user) -> TestClient:
    """Angemeldeter, nicht-privilegierter Nutzer."""
    make_user("alice", "alicepass123")
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "alicepass123"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def admin_client(client: TestClient, make_user) -> TestClient:
    """Angemeldeter Admin-Nutzer."""
    make_user("admin1", "adminpass123", is_admin=True)
    resp = client.post("/api/auth/login", json={"username": "admin1", "password": "adminpass123"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def sample_xml_dir(tmp_path):
    """Kleines Test-Verzeichnis: eine wohlgeformte und eine kaputte XML-Datei."""
    d = tmp_path / "xmldata"
    d.mkdir()
    (d / "gut.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bdo><artikel wb="wbf"><stichwort>Katze</stichwort></artikel></bdo>\n',
        encoding="utf-8",
    )
    sub = d / "sub"
    sub.mkdir()
    (sub / "kaputt.xml").write_text("<bdo><artikel>unclosed", encoding="utf-8")
    return d
