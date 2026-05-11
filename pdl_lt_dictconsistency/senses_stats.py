import reflex as rx
from pathlib import Path
from lxml import etree

from .state import FileState
from .components import (
    base_layout,
    page_container,
    page_heading,
    section_heading,
    no_files_warning,
    error_callout,
    results_grid,
    HEADING_SECTION,
    TEXT_RESULT,
)


SENSES_STATS_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "count", "headerName": "Anzahl", "sortable": True, "filter": True},
    {"field": "min_length", "headerName": "Min. Länge", "sortable": True, "filter": True},
    {"field": "max_length", "headerName": "Max. Länge", "sortable": True, "filter": True},
    {"field": "avg_length", "headerName": "Ø Länge", "sortable": True, "filter": True},
    {"field": "quelle", "headerName": "Gedruckte Ausgabe", "sortable": True, "filter": True},
]


class SensesStatsState(rx.State):
    """State for sense/meaning tag statistics."""

    tag_input: str = "sense"
    error_message: str = ""
    stats_results: list[dict] = []
    files_checked: int = 0
    is_checking: bool = False
    has_checked: bool = False
    _total_files: int = 0

    @rx.var
    def has_results(self) -> bool:
        return len(self.stats_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.stats_results)

    @rx.var
    def total_files(self) -> int:
        return self._total_files

    def set_tag_input(self, value: str) -> None:
        self.tag_input = value

    @rx.event
    def handle_key_down(self, key: str) -> None:
        if key == "Enter":
            return SensesStatsState.check_stats

    def download_csv(self):
        from .components import make_csv_download
        return make_csv_download(self.stats_results, "senses_stats.csv")

    async def check_stats(self):
        """Compute per-file statistics for the specified tag."""
        self.is_checking = True
        self.has_checked = False
        self.stats_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_checking = False
            return

        tag_name = self.tag_input.strip()
        if not tag_name:
            self.error_message = "Bitte geben Sie einen Tag-Namen ein."
            self.is_checking = False
            return

        self._total_files = len(file_state.xml_files_data)
        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_checking = False
            return

        from .processing import CHUNK_SIZE, append, load, clear, get_quelle
        token = self.router.session.client_token
        clear(token, "senses")
        xpath = f"//*[local-name()='{tag_name}']"
        parser = etree.XMLParser(dtd_validation=False, load_dtd=False, no_network=True, resolve_entities=False)
        all_files = list(file_state.xml_files_data)

        for chunk_start in range(0, len(all_files), CHUNK_SIZE):
            chunk = all_files[chunk_start : chunk_start + CHUNK_SIZE]
            chunk_results: list[dict] = []

            for file_info in chunk:
                subdir = file_info["subdir"]
                filename = file_info["filename"]
                file_path = (
                    base_path / filename if subdir == "."
                    else base_path / subdir / filename
                )
                self.files_checked += 1

                try:
                    with open(file_path, "rb") as f:
                        doc = etree.parse(f, parser)
                    quelle = get_quelle(doc.getroot(), filename)
                    elements = doc.xpath(xpath)
                    count = len(elements)
                    if count == 0:
                        chunk_results.append({
                            "quelle": quelle, "subdir": subdir, "filename": filename,
                            "count": 0, "min_length": "-", "max_length": "-", "avg_length": "-",
                        })
                    else:
                        lengths = [
                            len("".join(elem.itertext()))
                            for elem in elements if isinstance(elem, etree._Element)
                        ]
                        avg = round(sum(lengths) / len(lengths), 1) if lengths else 0
                        chunk_results.append({
                            "quelle": quelle, "subdir": subdir, "filename": filename, "count": count,
                            "min_length": min(lengths) if lengths else "-",
                            "max_length": max(lengths) if lengths else "-",
                            "avg_length": avg,
                        })
                except Exception as e:
                    print(f"Error in {filename}: {e}")
                    continue

            append(token, "senses", chunk_results)
            yield

        self.stats_results = load(token, "senses")
        self.has_checked = True
        self.is_checking = False


# ============ UI Components ============


def senses_stats_form() -> rx.Component:
    """Input form and results table for sense/meaning statistics."""
    return rx.vstack(
        section_heading("Tag-Name", margin_top="20px"),
        rx.text("Geben Sie den Tag-Namen ein, der eine Bedeutung repräsentiert:", size="2"),
        rx.hstack(
            rx.input(
                value=SensesStatsState.tag_input,
                placeholder="z.B. sense",
                on_change=SensesStatsState.set_tag_input,
                on_key_down=SensesStatsState.handle_key_down,
                width="300px",
            ),
            rx.button(
                rx.cond(
                    SensesStatsState.is_checking,
                    rx.hstack(rx.spinner(size="3"), rx.text("Prüfe..."), spacing="2"),
                    rx.text("Auswertung starten"),
                ),
                on_click=SensesStatsState.check_stats,
                variant="solid",
                disabled=SensesStatsState.is_checking | ~FileState.has_files,
            ),
            spacing="3",
            align="end",
            width="100%",
        ),
        # Progress
        rx.cond(
            SensesStatsState.is_checking,
            rx.hstack(
                rx.spinner(),
                rx.text(
                    "Durchsuche ",
                    SensesStatsState.files_checked,
                    " / ",
                    SensesStatsState.total_files,
                    " Dateien...",
                    color=HEADING_SECTION,
                ),
                spacing="2",
                align="center",
            ),
        ),
        error_callout(SensesStatsState.error_message),
        # Results
        rx.cond(
            SensesStatsState.has_results,
            rx.vstack(
                section_heading("Ergebnisse"),
                rx.text(
                    SensesStatsState.results_count,
                    " Dateien ausgewertet",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                results_grid(
                    grid_id="senses_stats_grid",
                    row_data=SensesStatsState.stats_results,
                    column_defs=SENSES_STATS_COLUMN_DEFS,
                    csv_filename="senses_stats.csv",
                    download_handler=SensesStatsState.download_csv,
                    show_preview=False,
                ),
                spacing="3",
                width="100%",
            ),
            rx.cond(
                SensesStatsState.has_checked & ~SensesStatsState.is_checking,
                rx.callout(
                    "Keine Dateien ausgewertet.",
                    icon="info",
                    color_scheme="gray",
                ),
            ),
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def senses_stats_page() -> rx.Component:
    """Page layout for sense/meaning statistics."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("ANZAHL UND LÄNGE"),
                no_files_warning(),
                rx.text(
                    "Wertet pro XML-Datei aus, wie viele Einträge eines Tags vorhanden sind "
                    "und wie lang deren Textinhalt ist (Minimum, Maximum, Durchschnitt)."
                ),
                senses_stats_form(),
                spacing="4",
            ),
        )
    )
