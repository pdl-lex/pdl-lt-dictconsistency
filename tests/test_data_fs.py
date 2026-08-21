"""Regressionsschutz für den dateisystembasierten Daten-Weg (Scan/Upload/ZIP)
sowie für die Auth-Pflicht auf allen Routern (seit Phase 2)."""
from __future__ import annotations

import io
import json
import zipfile

from pdl_lt_dictconsistency.core import data as core_data
from pdl_lt_dictconsistency.core.validator import WELLFORMED


def test_unauthenticated_request_401(client):
    resp = client.get("/api/data/datasources")
    assert resp.status_code == 401


def test_scan_directory_lists_valid_xml_only(logged_in_client, sample_xml_dir):
    resp = logged_in_client.post("/api/data/scan", json={"directory": str(sample_xml_dir)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_count"] == 2
    names = {f["filename"] for f in body["files"]}
    assert names == {"gut.xml", "kaputt.xml"}


def test_scan_missing_directory_404(logged_in_client, tmp_path):
    resp = logged_in_client.post(
        "/api/data/scan", json={"directory": str(tmp_path / "does-not-exist")}
    )
    assert resp.status_code == 404


def test_data_roots_restriction_403(logged_in_client, sample_xml_dir, tmp_path, monkeypatch):
    other_root = tmp_path / "allowed-elsewhere"
    other_root.mkdir()
    monkeypatch.setenv("LT_DATA_ROOTS", str(other_root))
    resp = logged_in_client.post("/api/data/scan", json={"directory": str(sample_xml_dir)})
    assert resp.status_code == 403


def test_upload_wellformed_xml(logged_in_client):
    content = b'<?xml version="1.0"?><bdo><artikel/></bdo>'
    resp = logged_in_client.post(
        "/api/data/upload", files=[("files", ("neu.xml", content, "application/xml"))]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_count"] == 1
    assert body["errors"] == []
    assert body["session_id"]


def test_upload_rejects_non_xml_extension(logged_in_client):
    resp = logged_in_client.post(
        "/api/data/upload", files=[("files", ("notizen.txt", b"kein xml", "text/plain"))]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_count"] == 0
    assert len(body["errors"]) == 1
    assert "notizen.txt" in body["errors"][0]


def test_upload_zip_extracts_xml_blocks_escape_and_fake_xml(logged_in_client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("legit/good.xml", '<?xml version="1.0"?><bdo/>')
        zf.writestr("../evil.xml", '<?xml version="1.0"?><bdo/>')  # Zip-Slip-Versuch
        zf.writestr("fake.xml", "das ist kein XML")  # falsche Magic-Bytes

    resp = logged_in_client.post(
        "/api/data/upload", files=[("files", ("bundle.zip", buf.getvalue(), "application/zip"))]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_count"] == 1
    assert body["files"][0]["filename"] == "good.xml"
    # Der Escape-Versuch ("../evil.xml") darf nirgends gelandet sein.
    assert not (core_data.UPLOADS_ROOT / "evil.xml").exists()
    assert not list(core_data.UPLOADS_ROOT.rglob("evil.xml"))


def test_delete_upload_session(logged_in_client):
    content = b'<?xml version="1.0"?><bdo/>'
    upload_resp = logged_in_client.post(
        "/api/data/upload", files=[("files", ("a.xml", content, "application/xml"))]
    )
    session_id = upload_resp.json()["session_id"]

    del_resp = logged_in_client.delete(f"/api/data/upload/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "deleted"}

    again = logged_in_client.delete(f"/api/data/upload/{session_id}")
    assert again.status_code == 404


def test_datasources_endpoint_reports_existing_and_missing(logged_in_client, sample_xml_dir, monkeypatch, tmp_path):
    datasources_file = tmp_path / "datasources.json"
    datasources_file.write_text(
        json.dumps(
            [
                {"name": "Vorhanden", "path": str(sample_xml_dir)},
                {"name": "Fehlt", "path": str(tmp_path / "nirgendwo")},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(core_data, "DATASOURCES_FILE", datasources_file)

    resp = logged_in_client.get("/api/data/datasources")
    assert resp.status_code == 200
    body = {d["name"]: d for d in resp.json()}
    assert body["Vorhanden"]["exists"] is True
    assert body["Fehlt"]["exists"] is False


def test_db_resources_requires_principal_without_touching_wbdb(logged_in_client):
    """Nutzer ohne wbdb_principal_id bekommt 403, kein Verbindungsaufbau zu wbdb
    (siehe Plan Phase 3 — kein stiller Fallback auf 'anon')."""
    resp = logged_in_client.get("/api/data/db-resources")
    assert resp.status_code == 403


def test_validator_check_end_to_end(logged_in_client, sample_xml_dir):
    resp = logged_in_client.post(
        "/api/checks/validator",
        json={"directory": str(sample_xml_dir), "validation_type": WELLFORMED},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["files_checked"] == 2
    assert body["files_with_wellformed_errors"] == 1
    assert len(body["wellformed"]) == 1
    assert body["wellformed"][0]["filename"] == "kaputt.xml"
