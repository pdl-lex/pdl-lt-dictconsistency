"""
Prüfung auf alte deutsche Rechtschreibung (vor der Reform 1996/2006).
Durchsucht Textinhalte ausgewählter XML-Tags nach bekannten Altschreibungen.
"""
import csv
import io
import re

import reflex as rx
from lxml import etree
from pathlib import Path

from .state import FileState
from .processing import CHUNK_SIZE, append, load, clear, get_quelle
from .components import (
    base_layout,
    page_container,
    page_heading,
    section_heading,
    no_files_warning,
    error_callout,
    results_grid,
    COLOR_DANGER,
    HEADING_SECTION,
)


CONTEXT_WINDOW = 40  # Zeichen links/rechts vom Treffer

DEFAULT_EXCLUDED_TAGS: frozenset[str] = frozenset({
    "autor", "bdo", "beleg-angabe", "beleg-kontext", "beleg-position",
    "beleg-quelle", "beleg-region", "beleg-text", "hoch", "komposita-position",
    "kompositum", "titel", "werk",
})



# ── Integrierte Wortliste (aus tools/spellings/spellings.csv) ─────────────

_SPELLINGS_CSV = Path(__file__).parent.parent / "tools" / "spellings" / "spellings.csv"
_WHITELIST_CSV = Path(__file__).parent.parent / "tools" / "spellings" / "whitelist.csv"


def _load_builtin_spellings() -> list[tuple[str, str]]:
    if not _SPELLINGS_CSV.exists():
        return []
    pairs: list[tuple[str, str]] = []
    with open(_SPELLINGS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            alt = (row.get("alt") or "").strip()
            neu = (row.get("neu") or "").strip()
            if alt and neu:
                pairs.append((alt, neu))
    return pairs


def _load_builtin_whitelist() -> frozenset[str]:
    if not _WHITELIST_CSV.exists():
        return frozenset()
    words: set[str] = set()
    with open(_WHITELIST_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            w = (row.get("wort") or "").strip()
            if w:
                words.add(w)
    return frozenset(words)


BUILTIN_SPELLINGS: list[tuple[str, str]] = _load_builtin_spellings()
BUILTIN_WHITELIST: frozenset[str] = _load_builtin_whitelist()


SPELLING_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "tag", "headerName": "Tag", "sortable": True, "filter": True},
    {"field": "gefunden", "headerName": "Gefunden", "sortable": True, "filter": True},
    {"field": "vorschlag", "headerName": "Vorschlag", "sortable": True, "filter": True},
    {"field": "kontext", "headerName": "Kontext", "sortable": True, "filter": True},
    {"field": "quelle", "headerName": "Gedruckte Ausgabe", "sortable": True, "filter": True},
]


def _compile_patterns(
    spellings: list[tuple[str, str]],
) -> tuple[re.Pattern[str], dict[str, str]]:
    """Compile all spelling pairs into a single alternation regex (case-sensitive).

    One combined pattern is vastly faster than N individual searches because the
    regex engine scans the text once instead of N times.  Longer alternatives are
    listed first so the engine does not prematurely match a shorter prefix.

    Case-sensitive matching is intentional: German nouns are always capitalised,
    so a lowercase verb pattern like 'floß' will not accidentally match the noun
    'Floß' (raft, long vowel, no change after reform).
    """
    sorted_pairs = sorted(spellings, key=lambda x: len(x[0]), reverse=True)
    lookup: dict[str, str] = {old: new for old, new in sorted_pairs}
    alternatives = "|".join(re.escape(old) for old in lookup)
    pattern = re.compile(r"\b(?:" + alternatives + r")\b", re.UNICODE)
    return pattern, lookup


def _exact_line(word: str, from_line: int, lines: list[str]) -> int:
    """Return the first 1-based line >= from_line that contains word."""
    for i in range(max(0, from_line - 1), len(lines)):
        if word in lines[i]:
            return i + 1
    return from_line


def _find_in_text(
    text: str,
    pattern: re.Pattern[str],
    lookup: dict[str, str],
) -> list[dict]:
    """Return all old-spelling matches found in text."""
    if not text or not text.strip():
        return []
    results = []
    text_single_line = text.replace("\n", " ").replace("\r", " ")
    for m in pattern.finditer(text_single_line):
        found = m.group(0)
        s, e = m.start(), m.end()
        ctx_s = max(0, s - CONTEXT_WINDOW)
        ctx_e = min(len(text_single_line), e + CONTEXT_WINDOW)
        prefix = "…" if ctx_s > 0 else ""
        suffix = "…" if ctx_e < len(text_single_line) else ""
        context = prefix + text_single_line[ctx_s:ctx_e].strip() + suffix
        results.append({"gefunden": found, "vorschlag": lookup[found], "kontext": context})
    return results


# Pre-compile built-in patterns once at module load (avoids recompilation on every run).
_BUILTIN_PATTERN, _BUILTIN_LOOKUP = (
    _compile_patterns(BUILTIN_SPELLINGS) if BUILTIN_SPELLINGS else (re.compile(r"(?!x)x"), {})
)


# ── State ──────────────────────────────────────────────────────────────────


class SpellingState(rx.State):
    """State for old-spelling detection."""

    # Tag selection
    all_tags: list[str] = []
    included_tags: list[str] = []
    excluded_tags: list[str] = []
    is_loading_tags: bool = False

    # Custom word list
    custom_list_mode: str = "extend"
    custom_spellings: list[dict] = []  # [{"alt": str, "neu": str}]
    custom_list_info: str = ""

    # Dialog
    show_wordlist_dialog: bool = False

    # Results
    spelling_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    error_message: str = ""
    _total_files: int = 0

    @rx.var
    def has_results(self) -> bool:
        return len(self.spelling_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.spelling_results)

    @rx.var
    def total_files(self) -> int:
        return self._total_files

    @rx.var
    def custom_list_count(self) -> int:
        return len(self.custom_spellings)

    @rx.var
    def active_spellings_count(self) -> int:
        if self.custom_list_mode == "replace":
            return len(self.custom_spellings)
        return len(BUILTIN_SPELLINGS) + len(self.custom_spellings)

    @rx.var
    def builtin_list_as_dicts(self) -> list[dict]:
        return [{"alt": old, "neu": new} for old, new in BUILTIN_SPELLINGS]

    def set_custom_list_mode(self, value: str) -> None:
        self.custom_list_mode = value

    def open_wordlist_dialog(self) -> None:
        self.show_wordlist_dialog = True

    def close_wordlist_dialog(self) -> None:
        self.show_wordlist_dialog = False

    def set_show_wordlist_dialog(self, value: bool) -> None:
        self.show_wordlist_dialog = value

    def exclude_tag(self, tag: str) -> None:
        if tag in self.included_tags:
            self.included_tags.remove(tag)
            self.excluded_tags.append(tag)
            self.excluded_tags.sort()

    def include_tag(self, tag: str) -> None:
        if tag in self.excluded_tags:
            self.excluded_tags.remove(tag)
            self.included_tags.append(tag)
            self.included_tags.sort()

    def clear_custom_list(self) -> None:
        self.custom_spellings = []
        self.custom_list_info = ""

    def download_csv(self) -> rx.event.EventSpec | None:
        from .components import make_csv_download
        return make_csv_download(self.spelling_results, "spelling_results.csv")

    def download_builtin_csv(self) -> rx.event.EventSpec | None:
        from .components import make_csv_download
        data = [{"alt": old, "neu": new} for old, new in BUILTIN_SPELLINGS]
        return make_csv_download(data, "wortliste_altschreibung.csv")

    def download_tags_csv(self) -> rx.event.EventSpec | None:
        from .components import make_csv_download
        data = [
            {"tag": t, "inkludiert": "ja" if t in self.included_tags else "nein"}
            for t in self.all_tags
        ]
        return make_csv_download(data, "tags_konfiguration.csv")

    async def handle_tags_csv_upload(self, files: list[rx.UploadFile]) -> None:
        if not files or not self.all_tags:
            return
        f = files[0]
        try:
            raw = await f.read()
            text = raw.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            all_tags_set = set(self.all_tags)
            new_included: list[str] = []
            new_excluded: list[str] = []
            mentioned: set[str] = set()
            for row in reader:
                keys = {k.strip().lower(): v.strip().lower() for k, v in row.items() if k}
                tag = keys.get("tag", "")
                if tag not in all_tags_set:
                    continue
                mentioned.add(tag)
                if keys.get("inkludiert", "ja") in ("ja", "yes", "true", "1"):
                    new_included.append(tag)
                else:
                    new_excluded.append(tag)
            # Tags not mentioned in CSV stay included
            for t in self.all_tags:
                if t not in mentioned:
                    new_included.append(t)
            self.included_tags = sorted(new_included)
            self.excluded_tags = sorted(new_excluded)
        except Exception as e:
            self.error_message = f"Fehler beim Lesen der Tag-CSV: {e}"

    async def load_all_tags(self):
        """Collect all unique tag names from all XML files."""
        self.is_loading_tags = True
        self.all_tags = []
        self.included_tags = []
        self.excluded_tags = []
        self.error_message = ""
        yield

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_loading_tags = False
            return

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_loading_tags = False
            return

        tags_set: set[str] = set()
        for file_info in file_state.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]
            file_path = base_path / filename if subdir == "." else base_path / subdir / filename
            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)
                for elem in doc.iter():
                    if not isinstance(elem.tag, str):
                        continue
                    try:
                        tag_name = etree.QName(elem).localname
                    except Exception:
                        continue
                    if tag_name in tags_set:
                        continue  # already confirmed as text-bearing
                    # Only include tags that carry non-whitespace text content
                    has_text = bool(elem.text and elem.text.strip()) or any(
                        child.tail and child.tail.strip() for child in elem
                    )
                    if has_text:
                        tags_set.add(tag_name)
            except Exception as e:
                print(f"Error loading tags from {filename}: {e}")
                continue

        all_sorted = sorted(tags_set)
        self.all_tags = all_sorted
        self.included_tags = [t for t in all_sorted if t not in DEFAULT_EXCLUDED_TAGS]
        self.excluded_tags = [t for t in all_sorted if t in DEFAULT_EXCLUDED_TAGS]
        self.is_loading_tags = False

    async def handle_csv_upload(self, files: list[rx.UploadFile]) -> None:
        """Parse uploaded CSV file (columns: alt, neu) and store entries."""
        if not files:
            return
        f = files[0]
        try:
            raw = await f.read()
            text = raw.decode("utf-8-sig")  # handle BOM
            reader = csv.DictReader(io.StringIO(text))
            # Accept headers: alt/neu, old/new, Alt/Neu, etc.
            rows = []
            for row in reader:
                keys = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                alt = keys.get("alt") or keys.get("old") or keys.get("alte schreibung") or ""
                neu = keys.get("neu") or keys.get("new") or keys.get("neue schreibung") or ""
                if alt and neu:
                    rows.append({"alt": alt, "neu": neu})
            if not rows:
                self.custom_list_info = "Keine gültigen Einträge gefunden. Erwartete Spalten: alt, neu"
                return
            self.custom_spellings = rows
            self.custom_list_info = f"{len(rows)} Einträge aus {f.filename} geladen."
        except Exception as e:
            self.custom_list_info = f"Fehler beim Lesen der CSV: {e}"

    async def search_spellings(self):
        """Search selected tags for old spellings."""
        self.is_searching = True
        self.spelling_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        if not self.included_tags:
            self.error_message = "Keine Tags zum Durchsuchen ausgewählt."
            self.is_searching = False
            return

        # Build active spelling list
        custom = [(d["alt"], d["neu"]) for d in self.custom_spellings]
        if self.custom_list_mode == "replace":
            active: list[tuple[str, str]] = custom
        else:
            active = list(BUILTIN_SPELLINGS) + custom

        if not active:
            self.error_message = "Keine Wörterliste aktiv."
            self.is_searching = False
            return

        # Reuse pre-compiled pattern when no custom entries are added
        if self.custom_list_mode == "extend" and not custom:
            pattern, lookup = _BUILTIN_PATTERN, _BUILTIN_LOOKUP
        else:
            pattern, lookup = _compile_patterns(active)

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_searching = False
            return

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_searching = False
            return

        self._total_files = len(file_state.xml_files_data)
        tags_to_search = set(self.included_tags)
        token = self.router.session.client_token
        clear(token, "spelling")
        all_files = list(file_state.xml_files_data)

        for chunk_start in range(0, len(all_files), CHUNK_SIZE):
            chunk = all_files[chunk_start : chunk_start + CHUNK_SIZE]
            chunk_results: list[dict] = []

            for file_info in chunk:
                subdir = file_info["subdir"]
                filename = file_info["filename"]
                file_path = base_path / filename if subdir == "." else base_path / subdir / filename
                self.files_checked += 1

                try:
                    with open(file_path, "rb") as fh:
                        raw = fh.read()
                    doc = etree.parse(io.BytesIO(raw))
                    file_lines = raw.decode("utf-8", errors="replace").splitlines()
                    quelle = get_quelle(doc.getroot(), filename)

                    for elem in doc.iter():
                        raw_tag = elem.tag
                        if not isinstance(raw_tag, str):
                            continue
                        # Strip namespace prefix without creating a QName object
                        tag_name = raw_tag.split("}", 1)[1] if "}" in raw_tag else raw_tag
                        if tag_name not in tags_to_search:
                            continue

                        # Search each text segment separately to get accurate line numbers.
                        # elem.text belongs to the element's own opening-tag line;
                        # child.tail follows the child's closing tag (reported on
                        # child.sourceline, which is the child's opening-tag line —
                        # the closest lxml can give us without raw-offset parsing).
                        segments: list[tuple[str | None, int]] = []
                        if elem.text:
                            segments.append((elem.text, elem.sourceline or 0))
                        for child in elem:
                            if child.tail:
                                segments.append((child.tail, child.sourceline or elem.sourceline or 0))

                        for text, hint_line in segments:
                            for hit in _find_in_text(text, pattern, lookup):
                                chunk_results.append({
                                    "quelle": quelle,
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": _exact_line(hit["gefunden"], hint_line, file_lines),
                                    "tag": tag_name,
                                    "gefunden": hit["gefunden"],
                                    "vorschlag": hit["vorschlag"],
                                    "kontext": hit["kontext"],
                                })
                except Exception as e:
                    print(f"Error searching {filename}: {e}")
                    continue

            append(token, "spelling", chunk_results)
            yield

        self.spelling_results = load(token, "spelling")
        self.is_searching = False


# ── UI Components ──────────────────────────────────────────────────────────


def _tag_section() -> rx.Component:
    """Tag include/exclude controls."""
    return rx.vstack(
        rx.cond(
            (SpellingState.all_tags.length() == 0) & ~SpellingState.is_loading_tags,
            rx.button(
                "Tags aus Dokumenten laden",
                on_click=SpellingState.load_all_tags,
                variant="solid",
            ),
        ),
        rx.cond(
            SpellingState.is_loading_tags,
            rx.hstack(rx.spinner(), rx.callout("Lade Tags…"), spacing="2", align="center"),
        ),
        rx.cond(
            SpellingState.included_tags.length() > 0,
            rx.vstack(
                rx.heading("Durchsuchte Tags", size="2", color=HEADING_SECTION),
                rx.text("Klicken Sie auf ×, um einen Tag auszuschließen:", size="1", color="gray"),
                rx.box(
                    rx.foreach(
                        SpellingState.included_tags,
                        lambda tag: rx.badge(
                            rx.hstack(
                                rx.text(tag),
                                rx.icon("x", size=14, cursor="pointer",
                                        on_click=SpellingState.exclude_tag(tag)),
                                spacing="1",
                            ),
                            margin="2px",
                        ),
                    ),
                    display="flex", flex_wrap="wrap", gap="5px",
                    padding="10px", border="1px solid var(--gray-6)",
                    border_radius="4px", min_height="50px",
                ),
                spacing="2", width="100%",
            ),
        ),
        rx.cond(
            SpellingState.excluded_tags.length() > 0,
            rx.vstack(
                rx.heading("Ausgeschlossene Tags", size="2", color=COLOR_DANGER),
                rx.text("Klicken Sie auf einen Tag, um ihn wieder einzuschließen:", size="1", color="gray"),
                rx.box(
                    rx.foreach(
                        SpellingState.excluded_tags,
                        lambda tag: rx.badge(
                            tag,
                            color_scheme=COLOR_DANGER,
                            cursor="pointer",
                            on_click=SpellingState.include_tag(tag),
                            margin="2px",
                        ),
                    ),
                    display="flex", flex_wrap="wrap", gap="5px",
                    padding="10px", border="1px solid var(--gray-6)",
                    border_radius="4px", min_height="50px",
                ),
                spacing="2", width="100%", margin_top="10px",
            ),
        ),
        rx.cond(
            SpellingState.all_tags.length() > 0,
            rx.hstack(
                rx.button(
                    rx.icon("download", size=14),
                    "Konfiguration herunterladen",
                    on_click=SpellingState.download_tags_csv,
                    variant="outline",
                    size="2",
                ),
                rx.upload(
                    rx.button(
                        rx.icon("upload", size=14),
                        "Konfiguration hochladen",
                        variant="outline",
                        size="2",
                    ),
                    id="tags_csv_upload",
                    accept={"text/csv": [".csv"], "text/plain": [".csv", ".txt"]},
                    max_files=1,
                    on_drop=SpellingState.handle_tags_csv_upload(
                        rx.upload_files(upload_id="tags_csv_upload")
                    ),
                    border="none",
                    padding="0",
                ),
                spacing="2",
                flex_wrap="wrap",
                margin_top="10px",
            ),
        ),
        spacing="3", width="100%",
    )


def _wordlist_dialog() -> rx.Component:
    """Dialog showing the complete built-in spelling list."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.dialog.title("Integrierte Wortliste"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon("x"),
                            variant="ghost",
                            on_click=SpellingState.close_wordlist_dialog,
                        ),
                    ),
                    width="100%",
                    align_items="center",
                ),
                rx.dialog.description(
                    f"{len(BUILTIN_SPELLINGS)} Einträge · "
                    "ß-Regeln, ph→f, Getrenntschreibung, sonstige Wortformänderungen"
                ),
                rx.button(
                    rx.icon("download", size=16),
                    "Als CSV herunterladen",
                    on_click=SpellingState.download_builtin_csv,
                    variant="outline",
                    size="2",
                ),
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Alte Schreibung"),
                                rx.table.column_header_cell("Neue Schreibung"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                SpellingState.builtin_list_as_dicts,
                                lambda row: rx.table.row(
                                    rx.table.cell(
                                        rx.text(row["alt"], font_family="monospace", size="2"),
                                    ),
                                    rx.table.cell(
                                        rx.text(row["neu"], font_family="monospace", size="2"),
                                    ),
                                ),
                            ),
                        ),
                        width="100%",
                    ),
                    overflow_y="auto",
                    max_height="60vh",
                    border="1px solid var(--gray-6)",
                    border_radius="4px",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="500px",
        ),
        open=SpellingState.show_wordlist_dialog,
        on_open_change=SpellingState.set_show_wordlist_dialog,
    )


def _wordlist_section() -> rx.Component:
    """Custom word list upload controls."""
    return rx.vstack(
        rx.text(
            "Integrierte Wortliste: ",
            rx.text.span(str(len(BUILTIN_SPELLINGS)), weight="bold"),
            " Einträge (ß-Regeln, ph→f, Getrenntschreibung, sonstige).",
            size="2",
        ),
        rx.hstack(
            rx.button(
                rx.icon("list", size=14),
                "Wortliste anzeigen",
                on_click=SpellingState.open_wordlist_dialog,
                variant="outline",
                size="2",
            ),
            rx.button(
                rx.icon("download", size=14),
                "Wortliste herunterladen",
                on_click=SpellingState.download_builtin_csv,
                variant="outline",
                size="2",
            ),
            rx.upload(
                rx.button(
                    rx.icon("upload", size=14),
                    "Wortliste hochladen",
                    variant="outline",
                    size="2",
                ),
                id="spelling_csv_upload",
                accept={"text/csv": [".csv"], "text/plain": [".csv", ".txt"]},
                max_files=1,
                on_drop=SpellingState.handle_csv_upload(
                    rx.upload_files(upload_id="spelling_csv_upload")
                ),
                border="none",
                padding="0",
            ),
            spacing="2",
            flex_wrap="wrap",
        ),
        rx.hstack(
            rx.text("Modus:", size="2", weight="bold"),
            rx.radio_group(
                ["Ergänzen", "Ersetzen"],
                value=rx.cond(
                    SpellingState.custom_list_mode == "extend", "Ergänzen", "Ersetzen"
                ),
                on_change=lambda v: SpellingState.set_custom_list_mode(
                    rx.cond(v == "Ergänzen", "extend", "replace")
                ),
                direction="row",
                spacing="4",
            ),
            align="center",
            spacing="3",
        ),
        rx.cond(
            SpellingState.custom_list_info != "",
            rx.hstack(
                rx.callout(SpellingState.custom_list_info, icon="info", color_scheme="blue"),
                rx.button(
                    "Liste löschen",
                    on_click=SpellingState.clear_custom_list,
                    variant="outline",
                    color_scheme=COLOR_DANGER,
                    size="2",
                ),
                spacing="3",
                align="center",
            ),
        ),
        spacing="3", width="100%",
    )


def spelling_input() -> rx.Component:
    """Main input form for spelling check."""
    return rx.vstack(
        _wordlist_dialog(),
        section_heading("Tags auswählen", margin_top="20px"),
        _tag_section(),
        section_heading("Wortliste", margin_top="20px"),
        _wordlist_section(),
        # Search button
        rx.button(
            rx.cond(
                SpellingState.is_searching,
                rx.hstack(rx.spinner(size="3"), rx.text("Suchen…"), spacing="2"),
                rx.text("Prüfen"),
            ),
            on_click=SpellingState.search_spellings,
            variant="solid",
            disabled=SpellingState.is_searching | ~FileState.has_files,
            margin_top="10px",
        ),
        # Progress
        rx.cond(
            SpellingState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.text(
                    "Durchsuche ",
                    SpellingState.files_checked,
                    " / ",
                    SpellingState.total_files,
                    " Dateien…",
                    color=HEADING_SECTION,
                ),
                spacing="2",
                align="center",
            ),
        ),
        error_callout(SpellingState.error_message),
        # Results
        rx.cond(
            SpellingState.has_results,
            rx.vstack(
                section_heading("Ergebnisse"),
                rx.text(
                    SpellingState.results_count,
                    " Treffer gefunden",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                results_grid(
                    grid_id="spelling_grid",
                    row_data=SpellingState.spelling_results,
                    column_defs=SPELLING_COLUMN_DEFS,
                    csv_filename="spelling_results.csv",
                    download_handler=SpellingState.download_csv,
                    show_preview=True,
                ),
                spacing="3",
                width="100%",
            ),
            rx.cond(
                ~SpellingState.is_searching,
                rx.callout("Keine Treffer gefunden.", icon="info", color_scheme="gray"),
            ),
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def spelling_page() -> rx.Component:
    """Page layout for old-spelling detection."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("RECHTSCHREIBUNG"),
                no_files_warning(),
                rx.text(
                    "Durchsucht Textfelder auf Schreibweisen, die vor der deutschen "
                    "Rechtschreibreform 1996/2006 korrekt waren. Geeignet für hochdeutsche "
                    "Anteile (Definitionen, Etymologie, Literatur) in Dialektwörterbüchern."
                ),
                spelling_input(),
                spacing="4",
            ),
        )
    )
