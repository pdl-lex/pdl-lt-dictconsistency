"""Unit-Tests für den lokalen Artikelindex-Cache — ohne Live-wbdb-Verbindung:
`current_scope()` wird gemockt, die SQLite-Logik (Scope-Filterung,
Auswahl-Auflösung) läuft gegen eine isolierte lokale DB (`isolated_env`)."""
from __future__ import annotations

import pytest

from pdl_lt_dictconsistency.auth import db as local_db
from pdl_lt_dictconsistency.wbdb import index_store


@pytest.mark.parametrize("source_path, expected", [
    ("wbf/B/Bergfex.xml", "B"),
    ("bwb/Ü/ueberdrehen.xml", "Ü"),
    ("awb/Foo.xml", index_store.NO_LETTER),
    ("Foo.xml", index_store.NO_LETTER),
])
def test_derive_letter(source_path, expected):
    assert index_store.derive_letter(source_path) == expected


def _seed(build_id: int, rows: list[tuple]) -> None:
    with local_db.connect() as conn:
        conn.executemany(
            "INSERT INTO wbdb_index_article "
            "(build_id, resource_id, collection_id, letter, source_path, article_id, lemma, pos) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(build_id, *r) for r in rows],
        )


@pytest.fixture
def seeded_index(isolated_env, monkeypatch):
    """Ein Build mit drei Artikeln in zwei Ressourcen/Collections, plus ein
    gemockter Scope, der nur `wbf`/`bdo-public` freigibt."""
    index_store.init_db()
    with local_db.connect() as conn:
        build_id = conn.execute(
            "INSERT INTO wbdb_index_build (status, row_count) VALUES ('ok', 3)"
        ).lastrowid
        conn.execute("UPDATE wbdb_index_current SET build_id = ? WHERE id = 1", (build_id,))

    _seed(build_id, [
        ("wbf", "bdo-public", "A", "wbf/A/Abend.xml", "wbf__abend", "Abend", "Subst."),
        ("wbf", "bdo-public", "B", "wbf/B/Berg.xml", "wbf__berg", "Berg", "Subst."),
        ("bwb", "bdo-intern", "A", "bwb/A/Arbeit.xml", "bwb__arbeit", "Arbeit", "Subst."),
    ])

    monkeypatch.setattr(index_store, "_current_scope", lambda principal: [("wbf", "bdo-public")])
    return build_id


def test_get_tree_only_includes_in_scope_resources(seeded_index):
    tree = index_store.get_tree("someone")
    assert {r["resource_id"] for r in tree} == {"wbf"}
    wbf = next(r for r in tree if r["resource_id"] == "wbf")
    assert wbf["article_count"] == 2
    assert {l["letter"] for l in wbf["letters"]} == {"A", "B"}


def test_get_letter_articles_filters_by_scope(seeded_index):
    assert len(index_store.get_letter_articles("someone", "wbf", "A")) == 1
    assert index_store.get_letter_articles("someone", "bwb", "A") == []


def test_search_matches_lemma_and_article_id_case_insensitively(seeded_index):
    hits = index_store.search("someone", "berg")
    assert len(hits) == 1
    assert hits[0]["article_id"] == "wbf__berg"
    assert index_store.search("someone", "arbeit") == []  # bwb ist außerhalb des Scopes


def test_resolve_selection_dedupes_overlapping_picks(seeded_index):
    pairs = index_store.resolve_selection(
        "someone",
        resource_ids=["wbf"],
        resource_letters=[],
        articles=[("wbf", "wbf/A/Abend.xml")],  # bereits durch die Ressourcen-Auswahl abgedeckt
    )
    assert pairs == {("wbf", "wbf/A/Abend.xml"), ("wbf", "wbf/B/Berg.xml")}


def test_resolve_selection_drops_out_of_scope_articles(seeded_index):
    pairs = index_store.resolve_selection(
        "someone", resource_ids=[], resource_letters=[], articles=[("bwb", "bwb/A/Arbeit.xml")],
    )
    assert pairs == set()


def test_get_tree_empty_scope_returns_empty_list(seeded_index, monkeypatch):
    monkeypatch.setattr(index_store, "_current_scope", lambda principal: [])
    assert index_store.get_tree("someone") == []


def test_get_tree_raises_index_not_built_without_a_build(isolated_env, monkeypatch):
    index_store.init_db()
    monkeypatch.setattr(index_store, "_current_scope", lambda principal: [("wbf", "bdo-public")])
    with pytest.raises(index_store.IndexNotBuilt):
        index_store.get_tree("someone")
