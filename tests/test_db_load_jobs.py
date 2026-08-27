"""API-Ebene des Hintergrund-Jobs für /data/db-load: 202 + job_id sofort,
Fortschritt über Polling, Job-Isolation zwischen Nutzern. Läuft ohne Live-wbdb
— index_store.resolve_selection() und core.data.materialize_db_selection()
sind gefakt, damit nur der Job-Mechanismus selbst geprüft wird (die echte
Materialisierung hat ihre eigenen Tests in test_wbdb_integration.py)."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from pdl_lt_dictconsistency.api.routers import db_index


def _patch_fast_load(monkeypatch, *, pairs=None, delay=0.0):
    pairs = pairs if pairs is not None else {("wbf", "wbf/A/Abend.xml")}

    def fake_resolve(principal, resource_ids, resource_letters, articles):
        return set(pairs)

    def fake_materialize(pairs, *, principal, on_progress=None):
        for i in range(1, len(pairs) + 1):
            if delay:
                time.sleep(delay)
            if on_progress:
                on_progress(i)
        return {
            "directory": "/tmp/fake-session", "file_count": len(pairs),
            "files": [], "session_id": "fake-session", "errors": [],
        }

    monkeypatch.setattr(db_index.index_store, "resolve_selection", fake_resolve)
    monkeypatch.setattr(db_index.data, "materialize_db_selection", fake_materialize)


def test_db_load_returns_job_immediately_then_completes(logged_in_client, monkeypatch, make_user):
    make_user("bob", "bobpass123", principal="anon")
    resp = logged_in_client.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    assert resp.status_code == 200

    _patch_fast_load(monkeypatch, pairs={("wbf", "a"), ("wbf", "b"), ("wbf", "c")})

    start = logged_in_client.post("/api/data/db-load", json={"resource_ids": ["wbf"]})
    assert start.status_code == 202
    body = start.json()
    assert body["total"] == 3
    job_id = body["job_id"]

    for _ in range(50):
        status = logged_in_client.get(f"/api/data/db-load/{job_id}")
        assert status.status_code == 200
        s = status.json()
        if s["status"] != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Job wurde nicht fertig")

    assert s["status"] == "ok"
    assert s["done"] == 3
    assert s["total"] == 3
    assert s["result"]["file_count"] == 3


def test_db_load_job_visible_only_to_its_owner(isolated_env, make_user, monkeypatch):
    # logged_in_client/admin_client share one TestClient's cookie jar — a second
    # login there would silently replace the first. Two independent TestClient
    # instances give two genuinely separate sessions to compare.
    from pdl_lt_dictconsistency.api.main import app

    make_user("carol", "carolpass123", principal="anon")
    make_user("erin", "erinpass123", principal="anon")

    _patch_fast_load(monkeypatch, delay=0.05)

    with TestClient(app) as carol, TestClient(app) as erin:
        assert carol.post("/api/auth/login", json={"username": "carol", "password": "carolpass123"}).status_code == 200
        assert erin.post("/api/auth/login", json={"username": "erin", "password": "erinpass123"}).status_code == 200

        start = carol.post("/api/data/db-load", json={"resource_ids": ["wbf"]})
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        assert erin.get(f"/api/data/db-load/{job_id}").status_code == 404
        assert carol.get(f"/api/data/db-load/{job_id}").status_code == 200


def test_db_load_reports_materialize_error(logged_in_client, monkeypatch, make_user):
    make_user("dave", "davepass123", principal="anon")
    resp = logged_in_client.post("/api/auth/login", json={"username": "dave", "password": "davepass123"})
    assert resp.status_code == 200

    def fake_resolve(principal, resource_ids, resource_letters, articles):
        return {("wbf", "a")}

    def fake_materialize(pairs, *, principal, on_progress=None):
        raise RuntimeError("wbdb nicht erreichbar")

    monkeypatch.setattr(db_index.index_store, "resolve_selection", fake_resolve)
    monkeypatch.setattr(db_index.data, "materialize_db_selection", fake_materialize)

    start = logged_in_client.post("/api/data/db-load", json={"resource_ids": ["wbf"]})
    job_id = start.json()["job_id"]

    for _ in range(50):
        s = logged_in_client.get(f"/api/data/db-load/{job_id}").json()
        if s["status"] != "running":
            break
        time.sleep(0.02)

    assert s["status"] == "error"
    assert "wbdb nicht erreichbar" in s["error"]
