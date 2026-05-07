import reflex as rx
from pathlib import Path
from lxml import etree

from .state import FileState
from .components import (
    base_layout,
    page_heading,
    section_heading,
    no_files_warning,
    error_callout,
    results_grid,
    COLOR_DANGER,
    HEADING_SECTION,
    TEXT_RESULT,
)


NESTING_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "depth", "headerName": "Tiefe", "sortable": True, "filter": True},
    {"field": "details", "headerName": "Pfad", "sortable": True, "filter": True},
]


class NestingState(rx.State):
    """State for XML tag nesting checks."""

    search_mode: str = "Direkte Verschachtelung"
    tag_input: str = ""
    path_input: str = ""
    error_message: str = ""
    nesting_results: list[dict] = []
    files_checked: int = 0
    is_checking: bool = False
    has_checked: bool = False
    _total_files: int = 0

    @rx.var
    def has_results(self) -> bool:
        return len(self.nesting_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.nesting_results)

    @rx.var
    def total_files(self) -> int:
        return self._total_files

    def set_search_mode(self, value: str) -> None:
        self.search_mode = value
        self.nesting_results = []
        self.error_message = ""
        self.has_checked = False

    def set_tag_input(self, value: str) -> None:
        self.tag_input = value

    def set_path_input(self, value: str) -> None:
        self.path_input = value

    @rx.event
    def handle_key_down(self, key: str) -> None:
        if key == "Enter":
            return NestingState.check_nesting

    def download_csv(self):
        from .components import make_csv_download
        return make_csv_download(self.nesting_results, "nesting_results.csv")

    def _pattern_to_xpath(self, pattern: str) -> str:
        """Convert simple path pattern with optional wildcards to XPath.

        Examples:
          sense/cit/sense  ->  //*[local-name()='sense']/*[local-name()='cit']/*[local-name()='sense']
          sense/*/sense    ->  //*[local-name()='sense']/*/*[local-name()='sense']
        """
        parts = [p.strip() for p in pattern.strip().split("/") if p.strip()]
        xpath_parts = []
        for part in parts:
            if part == "*":
                xpath_parts.append("*")
            else:
                xpath_parts.append(f"*[local-name()='{part}']")
        return "//" + "/".join(xpath_parts) if xpath_parts else "//*"

    def _get_depth_and_path(
        self, elem: etree._Element, tag_name: str, direct_only: bool
    ) -> tuple[int, str]:
        """Return (depth, display_path) for a matching element.

        direct_only=True:  only consecutive same-tag ancestors count.
          sense > sense > sense  -> depth 3
          sense > cit > sense    -> depth 1 (not reported)

        direct_only=False: all same-tag ancestors count regardless of intermediate tags.
          sense > sense > sense  -> depth 3
          sense > cit > sense    -> depth 2
        """
        # ancestors from closest to farthest, then reversed to root-first
        ancestors: list[str] = []
        for anc in elem.iterancestors():
            if isinstance(anc.tag, str):
                ancestors.append(etree.QName(anc).localname)
        ancestors.reverse()  # now root-first

        if direct_only:
            # Walk up from immediate parent and count consecutive same-tag elements
            depth = 1
            for anc in reversed(ancestors):
                if anc == tag_name:
                    depth += 1
                else:
                    break
            chain = " > ".join([tag_name] * depth)
            return depth, chain
        else:
            # Count all same-tag ancestors
            same_tag_count = sum(1 for a in ancestors if a == tag_name)
            depth = same_tag_count + 1
            # Build path from outermost matching ancestor to element
            first_match = next(
                (i for i, a in enumerate(ancestors) if a == tag_name), None
            )
            if first_match is not None:
                path = " > ".join(ancestors[first_match:] + [tag_name])
            else:
                path = tag_name
            return depth, path

    async def check_nesting(self):
        """Check all XML files for tag nesting based on the selected mode."""
        self.is_checking = True
        self.has_checked = False
        self.nesting_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_checking = False
            return

        is_path_mode = self.search_mode == "Pfad / Wildcard"
        is_direct = self.search_mode == "Direkte Verschachtelung"

        if is_path_mode:
            if not self.path_input.strip():
                self.error_message = "Bitte geben Sie ein Pfad-Muster ein."
                self.is_checking = False
                return
            xpath = self._pattern_to_xpath(self.path_input)
            tag_name = ""
        else:
            if not self.tag_input.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_checking = False
                return
            tag_name = self.tag_input.strip()
            xpath = f"//*[local-name()='{tag_name}']"

        self._total_files = len(file_state.xml_files_data)
        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_checking = False
            return

        from .processing import CHUNK_SIZE, append, load, clear
        token = self.router.session.client_token
        clear(token, "nesting")
        all_files = list(file_state.xml_files_data)
        parser = etree.XMLParser(dtd_validation=False, load_dtd=False, no_network=True, resolve_entities=False)

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

                    try:
                        elements = doc.xpath(xpath)
                    except etree.XPathEvalError as e:
                        self.error_message = f"Ungültiger Ausdruck: {e}"
                        self.is_checking = False
                        return

                    for elem in elements:
                        if not isinstance(elem, etree._Element):
                            continue
                        if is_path_mode:
                            elem_tag = etree.QName(elem).localname if isinstance(elem.tag, str) else "?"
                            chunk_results.append({
                                "subdir": subdir, "filename": filename,
                                "line": elem.sourceline or 0, "depth": "",
                                "details": f"<{elem_tag}>",
                            })
                        else:
                            depth, path = self._get_depth_and_path(elem, tag_name, is_direct)
                            if depth > 1:
                                chunk_results.append({
                                    "subdir": subdir, "filename": filename,
                                    "line": elem.sourceline or 0,
                                    "depth": depth, "details": path,
                                })

                except Exception as e:
                    print(f"Error in {filename}: {e}")
                    continue

            append(token, "nesting", chunk_results)
            yield

        self.nesting_results = load(token, "nesting")
        self.has_checked = True
        self.is_checking = False


# ============ UI Components ============


def nesting_check() -> rx.Component:
    """Input form and results table for nesting checks."""
    return rx.vstack(
        section_heading("Prüfmodus", margin_top="20px"),
        rx.radio(
            ["Direkte Verschachtelung", "Beliebige Verschachtelung", "Pfad / Wildcard"],
            value=NestingState.search_mode,
            on_change=NestingState.set_search_mode,
            direction="column",
            spacing="2",
        ),
        # Mode descriptions
        rx.cond(
            NestingState.search_mode == "Direkte Verschachtelung",
            rx.callout(
                "Zählt nur direkt aufeinanderfolgende Verschachtelungen desselben Tags. "
                "sense > sense > sense = Tiefe 3,  sense > cit > sense = nicht gewertet.",
                icon="info",
                color_scheme="blue",
                size="1",
            ),
        ),
        rx.cond(
            NestingState.search_mode == "Beliebige Verschachtelung",
            rx.callout(
                "Zählt alle Vorfahren desselben Tags, auch wenn andere Tags dazwischen liegen. "
                "sense > sense > sense = Tiefe 3,  sense > cit > sense = Tiefe 2.",
                icon="info",
                color_scheme="blue",
                size="1",
            ),
        ),
        rx.cond(
            NestingState.search_mode == "Pfad / Wildcard",
            rx.callout(
                "Sucht nach einem bestimmten Pfad-Muster. "
                "/ steht für direktes Kind-Element, * für beliebigen Tag-Namen. "
                "Beispiele: sense/cit/sense  ·  sense/*/form  ·  entry/sense",
                icon="info",
                color_scheme="blue",
                size="1",
            ),
        ),
        # Tag name input (modes 1 & 2)
        rx.cond(
            NestingState.search_mode != "Pfad / Wildcard",
            rx.vstack(
                section_heading("Tag-Name", margin_top="20px"),
                rx.input(
                    value=NestingState.tag_input,
                    placeholder="z.B. sense",
                    on_change=NestingState.set_tag_input,
                    on_key_down=NestingState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        # Path input (mode 3)
        rx.cond(
            NestingState.search_mode == "Pfad / Wildcard",
            rx.vstack(
                section_heading("Pfad-Muster", margin_top="20px"),
                rx.text(
                    "Verwenden Sie / für direkte Kind-Elemente und * als Platzhalter.",
                    size="1",
                    color="gray",
                ),
                rx.input(
                    value=NestingState.path_input,
                    placeholder="z.B. sense/cit/sense  oder  entry/*/form",
                    on_change=NestingState.set_path_input,
                    on_key_down=NestingState.handle_key_down,
                    width="100%",
                    font_family="monospace",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        # Check button
        rx.button(
            rx.cond(
                NestingState.is_checking,
                rx.hstack(rx.spinner(size="3"), rx.text("Prüfe..."), spacing="2"),
                rx.text("Prüfung starten"),
            ),
            on_click=NestingState.check_nesting,
            variant="solid",
            disabled=NestingState.is_checking | ~FileState.has_files,
            margin_top="10px",
        ),
        # Progress
        rx.cond(
            NestingState.is_checking,
            rx.hstack(
                rx.spinner(),
                rx.text(
                    "Durchsuche ",
                    NestingState.files_checked,
                    " / ",
                    NestingState.total_files,
                    " Dateien...",
                    color=HEADING_SECTION,
                ),
                spacing="2",
                align="center",
            ),
        ),
        error_callout(NestingState.error_message),
        # Results
        rx.cond(
            NestingState.has_results,
            rx.vstack(
                section_heading("Ergebnisse"),
                rx.text(
                    NestingState.results_count,
                    " Treffer gefunden",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                results_grid(
                    grid_id="nesting_results_grid",
                    row_data=NestingState.nesting_results,
                    column_defs=NESTING_COLUMN_DEFS,
                    csv_filename="nesting_results.csv",
                    download_handler=NestingState.download_csv,
                    show_preview=True,
                ),
                spacing="3",
                width="100%",
            ),
            rx.cond(
                NestingState.has_checked & ~NestingState.is_checking,
                rx.callout(
                    "Keine Verschachtelungen gefunden.",
                    icon="check",
                    color_scheme="green",
                ),
            ),
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def nesting_page() -> rx.Component:
    """Page layout for nesting checks."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("VERSCHACHTELUNG"),
                no_files_warning(),
                rx.text(
                    "Prüft, wie tief ein Tag in sich selbst verschachtelt ist, "
                    "oder sucht nach bestimmten Pfad-Mustern im XML-Baum."
                ),
                nesting_check(),
                spacing="4",
            ),
        )
    )
