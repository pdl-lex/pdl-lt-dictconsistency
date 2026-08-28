"""Verweisprüfung: Kernlogik (Scan, Klassifizierung, Zielprüfung-Fallback)
sowie die Job-Ebene der API (202 + job_id sofort, Fortschritt per Polling,
Job-Isolation) — analog zu `test_db_load_jobs.py`. Läuft ohne Live-wbdb und
ohne echte HTTP-Requests: `check_targets` wird für die API-Tests gefakt
(Vorbild `_patch_fast_load` in `test_db_load_jobs.py`); die HEAD/GET-
Fallback- und Fehlerbehandlung von `check_targets` selbst wird separat mit
einem gefakten `httpx.Client` geprüft."""
from __future__ import annotations

import time

import httpx
import pytest

from pdl_lt_dictconsistency.api.routers import references as references_router
from pdl_lt_dictconsistency.core import references as core_references
from pdl_lt_dictconsistency.core.references import (
    ReferenceSource,
    build_broken_rows,
    scan_occurrences,
    split_article_reference,
)


@pytest.fixture
def verweis_xml_dir(tmp_path):
    d = tmp_path / "xmldata"
    d.mkdir()
    (d / "artikel.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<bdo>\n"
        '  <verweis ziel="bwb__Elend" ziel-typ="Lemma"/>\n'
        '  <verweis ziel="bwb__Fehlt" ziel-typ="Lemma" fehlt="ja"/>\n'
        '  <bibl url="http://example.com/quelle">Quelle</bibl>\n'
        "  <p>Siehe http://example.org/mehr, für Details.</p>\n"
        "</bdo>\n",
        encoding="utf-8",
    )
    return d


# ── core.references: Scan ────────────────────────────────────────────────

def test_scan_finds_configured_source_and_classifies_kind(verweis_xml_dir):
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], verweis_xml_dir,
        [ReferenceSource(tag="verweis", attribute="ziel")],
        check_http_links=False, include_fehlt_marked=True,
    ))
    occurrences = [o for p in progress for o in p.occurrences]
    targets = {o["target"]: o for o in occurrences}
    assert targets.keys() == {"bwb__Elend", "bwb__Fehlt"}
    assert targets["bwb__Elend"]["kind"] == "artikel"
    assert targets["bwb__Elend"]["fehlt_marked"] is False
    assert targets["bwb__Fehlt"]["fehlt_marked"] is True
    # Ohne artikel-interne Verschachtelung: article_id == target, kein inner_id.
    assert targets["bwb__Elend"]["article_id"] == "bwb__Elend"
    assert targets["bwb__Elend"]["inner_id"] is None


def test_scan_empty_tag_matches_attribute_on_any_tag(tmp_path):
    d = tmp_path / "xmldata"
    d.mkdir()
    (d / "artikel.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<bdo>\n"
        '  <verweis ziel="bwb__Elend"/>\n'
        '  <bezug ziel="bwb__Rute"/>\n'
        '  <sonstiges other="bwb__Ignoriert"/>\n'
        "</bdo>\n",
        encoding="utf-8",
    )
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], d,
        [ReferenceSource(tag="", attribute="ziel")],
        check_http_links=False, include_fehlt_marked=True,
    ))
    occurrences = {o["target"]: o for p in progress for o in p.occurrences}
    assert occurrences.keys() == {"bwb__Elend", "bwb__Rute"}
    # Der real matchende Tag wird verwendet, nicht die leere Konfiguration.
    assert occurrences["bwb__Elend"]["tag"] == "verweis"
    assert occurrences["bwb__Rute"]["tag"] == "bezug"


def test_scan_splits_inner_id_reference(tmp_path):
    d = tmp_path / "xmldata"
    d.mkdir()
    (d / "artikel.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bdo><verweis ziel="bwb__Beere_1bzeta"/></bdo>\n',
        encoding="utf-8",
    )
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], d,
        [ReferenceSource(tag="verweis", attribute="ziel")],
        check_http_links=False, include_fehlt_marked=True,
    ))
    occurrences = [o for p in progress for o in p.occurrences]
    assert len(occurrences) == 1
    o = occurrences[0]
    assert o["target"] == "bwb__Beere_1bzeta"
    assert o["article_id"] == "bwb__Beere"
    assert o["inner_id"] == "bwb__Beere_1bzeta"


def test_scan_resolves_bare_target_against_document_resource(tmp_path):
    d = tmp_path / "xmldata"
    d.mkdir()
    (d / "artikel.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bdo>\n'
        '  <artikel id="wbf__Aaronsrute" wb="wbf">\n'
        '    <verweis ziel="Aaron"/>\n'
        '    <verweis ziel="bwb__Elend"/>\n'
        "  </artikel>\n"
        "</bdo>\n",
        encoding="utf-8",
    )
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], d,
        [ReferenceSource(tag="verweis", attribute="ziel")],
        check_http_links=False, include_fehlt_marked=True,
    ))
    occurrences = {o["target"]: o for p in progress for o in p.occurrences}
    # Kein eigenes Präfix im Ziel -> Ressource des Dokuments (@wb) ergänzt.
    assert occurrences["Aaron"]["article_id"] == "wbf__Aaron"
    assert occurrences["Aaron"]["inner_id"] is None
    # Ziel mit eigenem Präfix bleibt unangetastet, auch in einem wbf-Dokument.
    assert occurrences["bwb__Elend"]["article_id"] == "bwb__Elend"


def test_scan_excludes_fehlt_marked_when_disabled(verweis_xml_dir):
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], verweis_xml_dir,
        [ReferenceSource(tag="verweis", attribute="ziel")],
        check_http_links=False, include_fehlt_marked=False,
    ))
    occurrences = [o for p in progress for o in p.occurrences]
    assert {o["target"] for o in occurrences} == {"bwb__Elend"}


def test_scan_http_links_found_in_attributes_and_text(verweis_xml_dir):
    progress = list(scan_occurrences(
        [{"subdir": ".", "filename": "artikel.xml"}], verweis_xml_dir,
        [], check_http_links=True, include_fehlt_marked=True,
    ))
    occurrences = [o for p in progress for o in p.occurrences]
    links = {o["target"]: o for o in occurrences if o["kind"] == "link"}
    assert links["http://example.com/quelle"]["attribute"] == "url"
    assert links["http://example.com/quelle"]["tag"] == "bibl"
    # Freitext-URL: Satzzeichen (Komma) am Ende abgeschnitten, attribute='#text'.
    assert "http://example.org/mehr" in links
    assert links["http://example.org/mehr"]["attribute"] == "#text"
    assert links["http://example.org/mehr"]["tag"] == "p"


def test_scan_rejects_invalid_tag_name(verweis_xml_dir):
    from pdl_lt_dictconsistency.core.common import InvalidExpressionError

    with pytest.raises(InvalidExpressionError):
        list(scan_occurrences(
            [{"subdir": ".", "filename": "artikel.xml"}], verweis_xml_dir,
            [ReferenceSource(tag="verweis' or '1'='1", attribute="ziel")],
            check_http_links=False, include_fehlt_marked=True,
        ))


# ── core.references: split_article_reference ─────────────────────────────

def test_split_article_reference_distinguishes_suffix_from_inner_id():
    # Eigene Artikel (Ziffernsuffix direkt am Trenner, kein weiterer Unterstrich).
    assert split_article_reference("bwb__Bach1") == ("bwb__Bach1", None)
    assert split_article_reference("bwb__Bach2") == ("bwb__Bach2", None)
    assert split_article_reference("bwb__Beere") == ("bwb__Beere", None)
    # Artikel-interne ID (weiterer Unterstrich nach dem Trenner).
    assert split_article_reference("bwb__Beere_1bzeta") == ("bwb__Beere", "bwb__Beere_1bzeta")
    # Kein Trenner gefunden -> unverändert durchreichen.
    assert split_article_reference("keine-referenz") == ("keine-referenz", None)


def test_split_article_reference_prefixes_bare_target_with_resource():
    # Kein "__" im Ziel -> Ressource wird vorangestellt (z. B. wbf-Verweise
    # ohne eigenes Präfix, siehe Moduldoc).
    assert split_article_reference("Aaron", resource="wbf") == ("wbf__Aaron", None)
    # Ohne Ressource unverändert (bestehendes Verhalten).
    assert split_article_reference("Aaron") == ("Aaron", None)
    # Ziel mit eigenem Präfix bleibt unangetastet, auch mit resource gesetzt.
    assert split_article_reference("bwb__Elend", resource="wbf") == ("bwb__Elend", None)


# ── core.references: build_broken_rows ───────────────────────────────────

def test_build_broken_rows_filters_ok_targets():
    occurrences = [
        {"target": "bwb__Elend", "kind": "artikel", "article_id": "bwb__Elend", "inner_id": None},
        {"target": "bwb__Fehlt", "kind": "artikel", "article_id": "bwb__Fehlt", "inner_id": None},
        {"target": "bwb__Beere_1bz", "kind": "artikel", "article_id": "bwb__Beere", "inner_id": "bwb__Beere_1bz"},
        {"target": "bwb__Beere_9zz", "kind": "artikel", "article_id": "bwb__Beere", "inner_id": "bwb__Beere_9zz"},
        {"target": "http://ok.example", "kind": "link", "article_id": None, "inner_id": None},
        {"target": "http://broken.example", "kind": "link", "article_id": None, "inner_id": None},
    ]
    rows = build_broken_rows(
        occurrences,
        existing_ids={"bwb__Elend", "bwb__Beere"},
        known_ids_by_article={"bwb__Beere": {"bwb__Beere_1bz"}},
        url_failures={"http://broken.example": "HTTP 404"},
    )
    assert {r["target"]: r["status"] for r in rows} == {
        "bwb__Fehlt": "Artikel bwb__Fehlt nicht in der Datenbank gefunden",
        "bwb__Beere_9zz": "ID nicht im Artikel bwb__Beere gefunden",
        "http://broken.example": "HTTP 404",
    }


# ── core.references: check_targets (gefaktes httpx.Client) ──────────────

class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeClient:
    """Simuliert HEAD/GET-Fallback + Ausnahmen, ohne echte Netzwerkzugriffe."""

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def head(self, url):
        if url == "https://ok.example/a":
            return _FakeResponse(200)
        if url == "https://head-not-allowed.example/b":
            return _FakeResponse(405)
        if url == "https://timeout.example/c":
            raise httpx.TimeoutException("timed out")
        if url == "https://unreachable.example/d":
            raise httpx.ConnectError("no route")
        return _FakeResponse(404)

    def stream(self, method, url):
        assert method == "GET"
        # GET-Fallback: b existiert wirklich (HEAD nur nicht erlaubt), e bleibt kaputt.
        return _FakeResponse(200 if url == "https://head-not-allowed.example/b" else 404)


def test_check_targets_head_get_fallback_and_errors(monkeypatch):
    monkeypatch.setattr(core_references.httpx, "Client", _FakeClient)
    occurrences = [
        {"target": "https://ok.example/a", "kind": "link"},
        {"target": "https://head-not-allowed.example/b", "kind": "link"},
        {"target": "https://timeout.example/c", "kind": "link"},
        {"target": "https://unreachable.example/d", "kind": "link"},
        {"target": "https://not-found.example/e", "kind": "link"},
    ]
    existing_ids, known_ids_by_article, url_failures = core_references.check_targets(occurrences, principal=None)
    assert existing_ids == set()
    assert known_ids_by_article == {}
    assert "https://ok.example/a" not in url_failures
    assert "https://head-not-allowed.example/b" not in url_failures  # GET-Fallback war ok
    assert url_failures["https://timeout.example/c"] == "Zeitüberschreitung"
    assert url_failures["https://unreachable.example/d"] == "nicht erreichbar (Verbindung fehlgeschlagen)"
    assert url_failures["https://not-found.example/e"] == "HTTP 404"


def test_check_targets_requires_principal_for_article_targets():
    occurrences = [{"target": "bwb__Elend", "kind": "artikel", "article_id": "bwb__Elend", "inner_id": None}]
    with pytest.raises(core_references.PrincipalRequiredError):
        core_references.check_targets(occurrences, principal=None)


# ── API-Ebene: Job-Mechanik (202 + Polling), gefakter check_targets ──────

def _patch_fast_check(monkeypatch, *, existing_ids=frozenset(), url_failures=None):
    url_failures = url_failures or {}

    def fake_check_targets(occurrences, *, principal, on_progress=None, **kwargs):
        for i in range(1, len(occurrences) + 1):
            if on_progress:
                on_progress(i, len(occurrences))
        return set(existing_ids), {}, dict(url_failures)

    monkeypatch.setattr(core_references, "check_targets", fake_check_targets)


def test_references_run_returns_job_then_completes(logged_in_client, verweis_xml_dir, monkeypatch):
    _patch_fast_check(monkeypatch, existing_ids={"bwb__Elend"})

    start = logged_in_client.post("/api/checks/references/run", json={
        "directory": str(verweis_xml_dir),
        "sources": [{"tag": "verweis", "attribute": "ziel"}],
    })
    assert start.status_code == 202
    body = start.json()
    assert body["total"] == 1  # eine Datei
    job_id = body["job_id"]

    for _ in range(100):
        resp = logged_in_client.get(f"/api/checks/references/run/{job_id}")
        assert resp.status_code == 200
        s = resp.json()
        if s["status"] != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Job wurde nicht fertig")

    assert s["status"] == "ok"
    assert s["phase"] == "checking"
    targets = {r["target"] for r in s["result"]["results"]}
    assert targets == {"bwb__Fehlt"}  # bwb__Elend existiert laut Fake, bwb__Fehlt nicht


def test_references_run_requires_source_or_http_check(logged_in_client, verweis_xml_dir):
    resp = logged_in_client.post("/api/checks/references/run", json={
        "directory": str(verweis_xml_dir), "sources": [],
    })
    assert resp.status_code == 422


def test_references_job_visible_only_to_its_owner(isolated_env, make_user, monkeypatch, verweis_xml_dir):
    from fastapi.testclient import TestClient

    from pdl_lt_dictconsistency.api.main import app

    make_user("carol", "carolpass123")
    make_user("erin", "erinpass123")
    _patch_fast_check(monkeypatch)

    with TestClient(app) as carol, TestClient(app) as erin:
        assert carol.post("/api/auth/login", json={"username": "carol", "password": "carolpass123"}).status_code == 200
        assert erin.post("/api/auth/login", json={"username": "erin", "password": "erinpass123"}).status_code == 200

        start = carol.post("/api/checks/references/run", json={
            "directory": str(verweis_xml_dir), "check_http_links": True,
        })
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        assert erin.get(f"/api/checks/references/run/{job_id}").status_code == 404
        assert carol.get(f"/api/checks/references/run/{job_id}").status_code == 200


def test_references_run_reports_missing_principal_error(logged_in_client, verweis_xml_dir):
    # kein monkeypatch: der echte check_targets läuft, findet Artikel-Ziele,
    # aber der Testnutzer hat keinen wbdb-Principal.
    start = logged_in_client.post("/api/checks/references/run", json={
        "directory": str(verweis_xml_dir),
        "sources": [{"tag": "verweis", "attribute": "ziel"}],
    })
    job_id = start.json()["job_id"]

    for _ in range(100):
        s = logged_in_client.get(f"/api/checks/references/run/{job_id}").json()
        if s["status"] != "running":
            break
        time.sleep(0.02)

    assert s["status"] == "error"
    assert "wbdb-Principal" in s["error"]


def test_references_router_registered():
    # kleine Absicherung, dass der Router unter dem erwarteten Präfix hängt
    # (main.py-Registrierung), statt es indirekt nur über 404 zu erraten.
    assert references_router.router.prefix == "/checks/references"
