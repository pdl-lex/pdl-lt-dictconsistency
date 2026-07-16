"""XML-Validierung (Wohlgeformtheit + TEI-Lex 0) — reine Kernlogik."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .common import DEFAULT_CHUNK_SIZE
from .source import XmlFileRef, get_quelle

WELLFORMED = "Wohlgeformtheit (Well-formed XML)"
SCHEMA = "TEI-Lex 0 Schema (RelaxNG)"
TYPES = (WELLFORMED, SCHEMA)

DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent / "teilex0.rng"


@dataclass
class ValidatorProgress:
    """Fortschritt der Validierung: getrennte Listen + Zähler je Fehlerart."""

    files_checked: int
    wellformed: list[dict] = field(default_factory=list)
    schema: list[dict] = field(default_factory=list)
    files_with_wellformed_errors: int = 0
    files_with_schema_errors: int = 0


def load_rng_schema(schema_path: str | Path) -> etree.RelaxNG:
    """RelaxNG-Schema laden."""
    with open(schema_path, "rb") as f:
        schema_doc = etree.parse(f)
    return etree.RelaxNG(schema_doc)


def run_validation(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    validation_type: str,
    schema_path: str | Path | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[ValidatorProgress]:
    """Alle Dateien auf Wohlgeformtheit oder TEI-Lex 0 prüfen.

    Liefert kumulierte Zähler (files_with_*_errors) pro Schritt. Bei
    Schema-Validierung wird das Schema einmal vorab geladen; ein Fehler dabei
    löst eine Exception aus, die der Aufrufer behandeln muss.
    """
    if validation_type not in TYPES:
        raise ValueError(f"Unbekannter Validierungstyp: {validation_type!r}")

    rng_schema = None
    if validation_type == SCHEMA:
        path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
        if not path.exists():
            raise FileNotFoundError(f"Schema-Datei nicht gefunden: {path}")
        rng_schema = load_rng_schema(path)

    base = Path(base_path).expanduser()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    files_checked = 0
    files_with_wf = 0
    files_with_sc = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_wf: list[dict] = []
        chunk_sc: list[dict] = []

        for ref in chunk:
            files_checked += 1
            has_wf_error = False
            has_sc_error = False
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f)
                quelle = get_quelle(doc.getroot(), ref.filename)
                if rng_schema is not None and not rng_schema.validate(doc):
                    has_sc_error = True
                    for error in rng_schema.error_log:
                        chunk_sc.append({
                            "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                            "line": error.line if error.line else 0,
                            "column": error.column if error.column else 0,
                            "error": error.message,
                        })
            except etree.XMLSyntaxError as e:
                has_wf_error = True
                chunk_wf.append({
                    "quelle": "", "subdir": ref.subdir, "filename": ref.filename,
                    "line": e.lineno if e.lineno else 0,
                    "column": e.offset if e.offset else 0,
                    "error": str(e.msg) if e.msg else str(e),
                })
            except Exception as e:  # noqa: BLE001
                has_wf_error = True
                chunk_wf.append({
                    "quelle": "", "subdir": ref.subdir, "filename": ref.filename,
                    "line": 0, "column": 0, "error": str(e),
                })

            if has_wf_error:
                files_with_wf += 1
            if has_sc_error:
                files_with_sc += 1

        yield ValidatorProgress(
            files_checked=files_checked,
            wellformed=chunk_wf,
            schema=chunk_sc,
            files_with_wellformed_errors=files_with_wf,
            files_with_schema_errors=files_with_sc,
        )
