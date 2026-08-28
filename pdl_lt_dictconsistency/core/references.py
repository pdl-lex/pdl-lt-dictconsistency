"""Verweisprüfung — reine Kernlogik (Reflex-unabhängig).

Zwei Phasen: erst werden alle Verweis-Fundstellen gesammelt (Fortschritt
nach Dateien, `scan_occurrences`), dann deren Ziele geprüft (Fortschritt
nach geprüften Zielen, `check_targets`) — Artikel-Referenzen (Werte, die
nicht mit `http` beginnen) live gegen wbdb (RLS-gefiltert über den
Principal), `http(s)`-Links über echte HTTP-Requests. `run_reference_check`
orchestriert beide Phasen und liefert eine Ergebnisliste wie
`GenericCheckResponse` — nur kaputte Verweise (Ziel existiert nicht / Link
nicht erreichbar), analog zu Validator/Einmaligkeit/Verschachtelung.

Ein Artikel-Ziel wie `bwb__Elend` ist identisch mit `article_id` in
`source.article` (siehe `setup/Readme Access WBDB.md` §1/§9). Manche Ziele
verweisen aber nicht auf einen eigenen Artikel, sondern auf eine
artikel-interne ID (z. B. eine `bedeutung-position`): `bwb__Beere_1bζ`
verweist auf den Artikel `bwb__Beere` (alles bis zum letzten Unterstrich
*nach* dem `<resource>__`-Trenner) und dort auf die ID `bwb__Beere_1bζ`
selbst — zu unterscheiden von einem echten eigenen Artikel wie `bwb__Bach1`
(kein weiterer Unterstrich nach dem Trenner). `split_article_reference()`
löst das auf; `check_targets()` prüft in diesem Fall zweistufig: erst
Artikel-Existenz, dann (nur wenn der Artikel existiert) ob die ID irgendwo
als Attributwert im Artikelinhalt vorkommt.

Manche Ziele lassen das Ressourcen-Präfix ganz weg (beobachtet bei wbf:
`<artikel id="wbf__Aaronsrute" wb="wbf">` enthält `<verweis ziel="Aaron">`,
gemeint ist `wbf__Aaron`). Das ist keine wbf-Eigenheit im Code — statt
eine Ressource fest zu verdrahten, liest `_document_resource()` das
`@wb`-Attribut des referenzierenden Dokuments (gleiche Stelle wie
`get_quelle()`) und `split_article_reference()` stellt es einem Ziel ohne
`__`-Trenner voran. Das greift für jede Ressource mit dieser Eigenheit,
nicht nur wbf, und lässt Ziele mit eigenem Präfix unangetastet.

Eine Verweisquelle (`ReferenceSource`) mit leerem `tag` bedeutet „dieses
Attribut auf einem beliebigen Tag" statt eines konkreten Tags — praktisch,
wenn ein Attributname wie `ziel` auf mehreren unterschiedlichen Tags
vorkommt und nicht jede Kombination einzeln eingetragen werden soll.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

import httpx
from lxml import etree

from .common import DEFAULT_CHUNK_SIZE, ensure_tag_name
from .source import XmlFileRef, get_quelle, make_parser
from .tag_content import get_attr_value

ARTICLE_BATCH = 5000
URL_TIMEOUT_SECONDS = 8.0
URL_MAX_WORKERS = 8
FEHLT_ATTR = "fehlt"
FEHLT_VALUE = "ja"

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_URL_TRIM_CHARS = ".,;:!?)]}»\"'"


class PrincipalRequiredError(RuntimeError):
    """Artikel-Referenzen sollen geprüft werden, aber der Nutzer hat keinen wbdb-Principal."""


@dataclass
class ReferenceSource:
    tag: str
    attribute: str


@dataclass
class ScanProgress:
    """Fortschritt der Fundstellen-Suche (Phase 1)."""

    files_checked: int
    occurrences: list[dict] = field(default_factory=list)


def _extract_urls(text: str | None) -> list[str]:
    """http(s)-URLs aus Fließtext extrahieren, Satzzeichen am Ende abschneiden."""
    if not text:
        return []
    return [u for m in _URL_RE.findall(text) if (u := m.rstrip(_URL_TRIM_CHARS))]


def split_article_reference(target: str, resource: str | None = None) -> tuple[str, str | None]:
    """BDO-Artikelreferenzen sind ``<resource>__<lemma>``. Enthält der Teil
    nach diesem trennenden ``__`` noch einen weiteren Unterstrich, ist das
    eine artikel-interne ID (z. B. ``bwb__Beere_1bζ`` -> Artikel
    ``bwb__Beere``, ID ``bwb__Beere_1bζ``) statt eines eigenen Artikels wie
    ``bwb__Bach1`` (kein weiterer Unterstrich nach dem Trenner). Liefert
    (article_id, inner_id) — inner_id ist None ohne diese Verschachtelung.

    Fehlt im Ziel selbst jedes Präfix (kein ``__`` enthalten) und ist
    ``resource`` gegeben (Ressource des referenzierenden Dokuments, siehe
    ``_document_resource``), wird ``<resource>__`` vorangestellt — manche
    Verweise lassen das Präfix weg (siehe Moduldoc)."""
    sep = target.find("__")
    if sep == -1:
        if resource:
            return f"{resource}__{target}", None
        return target, None
    rest = target[sep + 2 :]
    if "_" not in rest:
        return target, None
    lemma_part, _, _suffix = rest.rpartition("_")
    if not lemma_part:
        return target, None
    return target[: sep + 2] + lemma_part, target


def _classify_target(target: str, resource: str | None) -> tuple[str, str | None, str | None]:
    """(kind, article_id, inner_id) — article_id/inner_id nur für kind='artikel'."""
    if target.lower().startswith(("http://", "https://")):
        return "link", None, None
    article_id, inner_id = split_article_reference(target, resource)
    return "artikel", article_id, inner_id


def _local_name(name) -> str:
    try:
        return etree.QName(name).localname
    except Exception:
        return str(name)


def _document_resource(root) -> str | None:
    """Ressourcen-Kürzel (bwb/wbf/dibs/…) des Dokuments, aus ``@wb`` auf der
    Wurzel oder einem ihrer ersten drei Kinder (gleiche Stelle wie
    ``get_quelle``) — Grundlage, um Verweisziele ohne eigenes
    Ressourcen-Präfix aufzulösen (siehe Moduldoc)."""
    if root is None:
        return None
    for elem in [root, *list(root)[:3]]:
        wb = elem.get("wb")
        if wb and wb.strip():
            return wb.strip().lower()
    return None


def scan_occurrences(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    sources: list[ReferenceSource],
    *,
    check_http_links: bool = False,
    include_fehlt_marked: bool = True,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[ScanProgress]:
    """Verweis-Fundstellen sammeln. Existenz/Erreichbarkeit wird hier noch nicht geprüft.

    Ein leerer Tag-Name in einer Quelle bedeutet „dieses Attribut auf einem
    beliebigen Tag" (siehe Moduldoc) statt eines konkreten Tags."""
    sources = [
        ReferenceSource(
            tag=ensure_tag_name(s.tag) if s.tag.strip() else "",
            attribute=ensure_tag_name(s.attribute),
        )
        for s in sources
    ]

    base = Path(base_path).expanduser()
    parser = make_parser()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    files_checked = 0

    for chunk_start in range(0, len(refs), chunk_size):
        chunk = refs[chunk_start : chunk_start + chunk_size]
        chunk_occurrences: list[dict] = []

        for ref in chunk:
            files_checked += 1
            try:
                with open(ref.resolve(base), "rb") as f:
                    doc = etree.parse(f, parser)
                root = doc.getroot()
                quelle = get_quelle(root, ref.filename)
                resource = _document_resource(root)
                seen: set[tuple] = set()

                def add(elem, tag: str, attribute: str, raw_target: str) -> None:
                    target = raw_target.strip()
                    if not target:
                        return
                    line = elem.sourceline or 0
                    key = (line, tag, attribute, target)
                    if key in seen:
                        return
                    seen.add(key)
                    fehlt_marked = get_attr_value(elem, FEHLT_ATTR) == FEHLT_VALUE
                    if fehlt_marked and not include_fehlt_marked:
                        return
                    kind, article_id, inner_id = _classify_target(target, resource)
                    chunk_occurrences.append({
                        "quelle": quelle, "subdir": ref.subdir, "filename": ref.filename,
                        "line": line, "tag": tag, "attribute": attribute, "target": target,
                        "kind": kind, "article_id": article_id, "inner_id": inner_id,
                        "fehlt_marked": fehlt_marked,
                    })

                for source in sources:
                    if source.tag:
                        elems = doc.xpath(f"//*[local-name()='{source.tag}']")
                    else:
                        elems = doc.xpath(f"//*[@*[local-name()='{source.attribute}']]")
                    for elem in elems:
                        val = get_attr_value(elem, source.attribute)
                        if val is not None:
                            add(elem, source.tag or _local_name(elem.tag), source.attribute, val)

                if check_http_links:
                    for elem in doc.iter():
                        if not isinstance(elem.tag, str):
                            continue  # Kommentare, Processing Instructions etc.
                        tag = _local_name(elem.tag)
                        for attr_qname, attr_val in elem.attrib.items():
                            if attr_val.lower().startswith(("http://", "https://")):
                                add(elem, tag, _local_name(attr_qname), attr_val)
                        for url in _extract_urls(elem.text):
                            add(elem, tag, "#text", url)
                        for url in _extract_urls(elem.tail):
                            add(elem, tag, "#text", url)
            except Exception as e:  # noqa: BLE001
                print(f"references: Fehler in {ref.filename}: {e}")
                continue

        yield ScanProgress(files_checked=files_checked, occurrences=chunk_occurrences)


def _collect_attribute_values(content: bytes) -> set[str]:
    """Alle Attributwerte eines BDO-XML-Artikelinhalts sammeln — Grundlage für
    den artikel-internen ID-Vorkommen-Check (siehe Moduldoc)."""
    try:
        root = etree.fromstring(content, parser=make_parser())
    except Exception:
        return set()
    values: set[str] = set()
    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue
        values.update(elem.attrib.values())
    return values


def check_targets(
    occurrences: list[dict],
    *,
    principal: str | None,
    on_progress: Callable[[int, int], None] | None = None,
    timeout: float = URL_TIMEOUT_SECONDS,
    max_workers: int = URL_MAX_WORKERS,
) -> tuple[set[str], dict[str, set[str]], dict[str, str]]:
    """Ziele prüfen (Phase 2). Liefert (existierende Artikel-IDs,
    {article_id: im Artikel vorkommende Attributwerte} — nur für Artikel mit
    mind. einer artikel-internen ID-Referenz, {url: Fehlergrund})."""
    article_ids_all = sorted({o["article_id"] for o in occurrences if o["kind"] == "artikel"})
    inner_check_candidates = sorted({
        o["article_id"] for o in occurrences if o["kind"] == "artikel" and o["inner_id"]
    })
    link_targets = sorted({o["target"] for o in occurrences if o["kind"] == "link"})
    total = len(article_ids_all) + len(inner_check_candidates) + len(link_targets)
    done = 0
    if on_progress:
        on_progress(done, total)

    def tick() -> None:
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    existing_ids: set[str] = set()
    known_ids_by_article: dict[str, set[str]] = {}
    if article_ids_all:
        if not principal:
            raise PrincipalRequiredError(
                "Kein Datenbank-Zugriff: Ihrem Konto ist kein wbdb-Principal zugeordnet — "
                "Artikel-Verweise können nicht geprüft werden."
            )
        from ..wbdb.connection import als, verbindung  # lazy: core bleibt ohne wbdb nutzbar

        with verbindung() as conn, als(conn, principal) as c:
            for i in range(0, len(article_ids_all), ARTICLE_BATCH):
                batch = article_ids_all[i : i + ARTICLE_BATCH]
                rows = c.execute(
                    "SELECT DISTINCT article_id FROM source.article WHERE article_id = ANY(%(ids)s::text[])",
                    {"ids": batch},
                ).fetchall()
                existing_ids.update(r[0] for r in rows)
                for _ in batch:
                    tick()

            to_fetch = [aid for aid in inner_check_candidates if aid in existing_ids]
            for aid in inner_check_candidates:
                if aid not in existing_ids:
                    tick()  # Basisartikel fehlt schon — kein Inhalt zu holen
            for i in range(0, len(to_fetch), ARTICLE_BATCH):
                batch = to_fetch[i : i + ARTICLE_BATCH]
                rows = c.execute(
                    "SELECT a.article_id, o.content FROM source.article a "
                    "JOIN source.document o USING (content_sha256) "
                    "WHERE a.article_id = ANY(%(ids)s::text[])",
                    {"ids": batch},
                ).fetchall()
                for article_id, content in rows:
                    known_ids_by_article.setdefault(article_id, set()).update(
                        _collect_attribute_values(bytes(content))
                    )
                for _ in batch:
                    tick()

    url_failures: dict[str, str] = {}
    if link_targets:
        headers = {"User-Agent": "pdl-lt-dictconsistency-verweispruefung/1.0"}
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:

            def check_one(url: str) -> tuple[str, str | None]:
                try:
                    status = client.head(url).status_code
                    if status >= 400 or status in (405, 501):
                        with client.stream("GET", url) as resp:
                            status = resp.status_code
                    return url, None if status < 400 else f"HTTP {status}"
                except httpx.TimeoutException:
                    return url, "Zeitüberschreitung"
                except httpx.ConnectError:
                    return url, "nicht erreichbar (Verbindung fehlgeschlagen)"
                except httpx.HTTPError as e:
                    return url, f"Fehler: {e}"

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(check_one, url) for url in link_targets]
                for future in as_completed(futures):
                    url, failure = future.result()
                    if failure:
                        url_failures[url] = failure
                    tick()

    return existing_ids, known_ids_by_article, url_failures


def build_broken_rows(
    occurrences: list[dict],
    existing_ids: set[str],
    known_ids_by_article: dict[str, set[str]],
    url_failures: dict[str, str],
) -> list[dict]:
    """Nur kaputte Verweise als Ergebniszeilen: Artikel existiert nicht, oder
    (bei artikel-interner ID) der Artikel existiert zwar, aber die ID kommt
    darin nicht vor; bzw. Link nicht erreichbar."""
    rows: list[dict] = []
    for o in occurrences:
        if o["kind"] == "artikel":
            article_id = o["article_id"]
            if article_id not in existing_ids:
                status = f"Artikel {article_id} nicht in der Datenbank gefunden"
            elif o["inner_id"] and o["inner_id"] not in known_ids_by_article.get(article_id, ()):
                status = f"ID nicht im Artikel {article_id} gefunden"
            else:
                continue
        else:
            failure = url_failures.get(o["target"])
            if failure is None:
                continue
            status = failure
        rows.append({**o, "status": status})
    return rows


def run_reference_check(
    files: Iterable[XmlFileRef | dict],
    base_path: str | Path,
    *,
    sources: list[ReferenceSource],
    check_http_links: bool,
    include_fehlt_marked: bool,
    principal: str | None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Orchestriert Scan (Phase 1) + Zielprüfung (Phase 2), liefert eine
    Antwort in der Form von `GenericCheckResponse` (nur kaputte Verweise)."""
    started = time.perf_counter()
    refs = [f if isinstance(f, XmlFileRef) else XmlFileRef.from_dict(f) for f in files]
    total_files = len(refs)
    occurrences: list[dict] = []
    files_checked = 0

    for progress in scan_occurrences(
        refs, base_path, sources,
        check_http_links=check_http_links, include_fehlt_marked=include_fehlt_marked,
    ):
        occurrences.extend(progress.occurrences)
        files_checked = progress.files_checked
        if on_progress:
            on_progress("scanning", files_checked, total_files)

    def report_checking(done: int, total: int) -> None:
        if on_progress:
            on_progress("checking", done, total)

    existing_ids, known_ids_by_article, url_failures = check_targets(
        occurrences, principal=principal, on_progress=report_checking,
    )
    results = build_broken_rows(occurrences, existing_ids, known_ids_by_article, url_failures)

    return {
        "results": results,
        "files_checked": files_checked,
        "result_count": len(results),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
