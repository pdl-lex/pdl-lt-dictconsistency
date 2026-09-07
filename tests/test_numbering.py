"""Tests für die Bedeutungsnummerierungs-Prüfung (core/numbering.py)."""
from __future__ import annotations

from pdl_lt_dictconsistency.core.numbering import NumberingLevel, run_numbering
from pdl_lt_dictconsistency.core.source import scan_xml_files


def _write(tmp_path, name: str, body: str):
    (tmp_path / name).write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<bdo><artikel>{body}</artikel></bdo>\n',
        encoding="utf-8",
    )


def _run(tmp_path, *, levels, max_depth, tag_name="bedeutung-position", attribute_name="nr"):
    files = scan_xml_files(tmp_path)
    results: list[dict] = []
    for progress in run_numbering(
        files, tmp_path, tag_name=tag_name, attribute_name=attribute_name,
        levels=levels, max_depth=max_depth,
    ):
        results.extend(progress.results)
    return results


BWB_SCHEME = [
    NumberingLevel("arabisch", empty_rule="einzelbedeutung"),
    NumberingLevel("kleinbuchstabe", empty_rule="immer"),
    NumberingLevel("griechisch", empty_rule="immer"),
    NumberingLevel("roemisch_klein", empty_rule="immer"),
]


def test_valid_flat_sequence_has_no_errors(tmp_path):
    _write(tmp_path, "ok.xml", """
        <bedeutung-position nr="1"/>
        <bedeutung-position nr="2"/>
        <bedeutung-position nr="3"/>
    """)
    assert _run(tmp_path, levels=BWB_SCHEME, max_depth=4) == []


def test_valid_nested_sequence_like_austreten(tmp_path):
    _write(tmp_path, "austreten.xml", """
        <bedeutung-position nr="1">
            <bedeutung-position nr="1a"/>
            <bedeutung-position nr="1b"/>
            <bedeutung-position>
                <erklaerung>Übertr.</erklaerung>
            </bedeutung-position>
        </bedeutung-position>
        <bedeutung-position nr="2"/>
    """)
    assert _run(tmp_path, levels=BWB_SCHEME, max_depth=4) == []


def test_format_error(tmp_path):
    _write(tmp_path, "format.xml", """
        <bedeutung-position nr="1"/>
        <bedeutung-position nr="2aa"/>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Formatfehler"
    assert results[0]["gefunden"] == "2aa"


def test_sequence_error_gap(tmp_path):
    _write(tmp_path, "gap.xml", """
        <bedeutung-position nr="1"/>
        <bedeutung-position nr="3"/>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Sequenzfehler"
    assert results[0]["gefunden"] == "3"
    assert results[0]["erwartet"] == "2"


def test_parent_prefix_error(tmp_path):
    _write(tmp_path, "prefix.xml", """
        <bedeutung-position nr="1">
            <bedeutung-position nr="2a"/>
        </bedeutung-position>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Elternfehler"
    assert results[0]["erwartet"] == "Präfix '1'"


def test_missing_number_not_allowed_on_top_level(tmp_path):
    _write(tmp_path, "missing.xml", """
        <bedeutung-position nr="1"/>
        <bedeutung-position/>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Nummer fehlt"


def test_missing_number_allowed_on_sub_level(tmp_path):
    _write(tmp_path, "missing_sub.xml", """
        <bedeutung-position nr="1">
            <bedeutung-position/>
            <bedeutung-position nr="1a"/>
        </bedeutung-position>
    """)
    assert _run(tmp_path, levels=BWB_SCHEME, max_depth=4) == []


def test_depth_exceeded(tmp_path):
    _write(tmp_path, "deep.xml", """
        <bedeutung-position nr="1">
            <bedeutung-position nr="1a">
                <bedeutung-position nr="1aα">
                    <bedeutung-position nr="1aαi">
                        <bedeutung-position nr="1aαia"/>
                    </bedeutung-position>
                </bedeutung-position>
            </bedeutung-position>
        </bedeutung-position>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Tiefe überschritten"


def test_all_arabic_levels(tmp_path):
    _write(tmp_path, "arabic.xml", """
        <bedeutung-position nr="1">
            <bedeutung-position nr="11"/>
            <bedeutung-position nr="12"/>
        </bedeutung-position>
        <bedeutung-position nr="2"/>
    """)
    levels = [NumberingLevel("arabisch"), NumberingLevel("arabisch")]
    assert _run(tmp_path, levels=levels, max_depth=2) == []


def test_single_sense_without_number_is_allowed(tmp_path):
    """Häufigstes reales Muster: Einträge mit genau einer Bedeutung tragen
    gar kein nr-Attribut (z. B. bwb__Zachenband_0). Mit der Regel
    'einzelbedeutung' ist das kein Fehler."""
    _write(tmp_path, "single.xml", '<bedeutung-position id="x_0"/>')
    assert _run(tmp_path, levels=BWB_SCHEME, max_depth=4) == []


def test_cascading_errors_are_suppressed(tmp_path):
    """Ist eine Bedeutung schon fehlerhaft, werden Folgefehler in ihrem
    Teilbaum nicht zusätzlich gemeldet (ihre Nummer ist als Präfix für
    Kinder ohnehin nicht mehr verlässlich)."""
    _write(tmp_path, "cascade.xml", """
        <bedeutung-position nr="I">
            <bedeutung-position nr="1">
                <bedeutung-position nr="1a"/>
            </bedeutung-position>
        </bedeutung-position>
    """)
    results = _run(tmp_path, levels=BWB_SCHEME, max_depth=4)
    assert len(results) == 1
    assert results[0]["error_type"] == "Formatfehler"
    assert results[0]["gefunden"] == "I"
