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
)


PATHFINDER_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "full_path", "headerName": "XPath", "sortable": True, "filter": True},
    {"field": "text_content", "headerName": "Inhalt", "sortable": True, "filter": True},
]


class PathfinderState(rx.State):
    """State for tag/path search. Independent from FileState, loads file data on demand."""

    user_input: str = ""
    path_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    debug_output: str = ""
    error_message: str = ""

    # File preview
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    # Backend var: cached directory path for synchronous preview access
    _directory_path: str = ""

    @rx.var
    def has_results(self) -> bool:
        """Check if search produced any results."""
        return len(self.path_results) > 0

    @rx.var
    def results_count(self) -> int:
        """Return number of search results."""
        return len(self.path_results)

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Format preview content with line numbers, highlighting the target line."""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        max_line_num = len(lines)
        num_width = len(str(max_line_num))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            escaped_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            if i == self.preview_line:
                html_lines.append(
                    f'<div style="background-color: var(--yellow-3); border-left: 3px solid var(--yellow-9);">'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f"<span>{escaped_line}</span>"
                    f"</div>"
                )
            else:
                html_lines.append(
                    f"<div>"
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f"<span>{escaped_line}</span>"
                    f"</div>"
                )

        return "\n".join(html_lines)

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger search on Enter key."""
        if key == "Enter":
            return PathfinderState.search_path

    @rx.event
    def set_text(self, value: str) -> None:
        """Update the search input field."""
        self.user_input = value

    def set_selected_rows(self, rows: list[dict]) -> None:
        """Store selected grid rows."""
        self.selected_rows = rows if rows else []

    def open_file_preview(self, row_data: dict) -> None:
        """Open file preview dialog for the selected row. Uses cached _directory_path."""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            base_path = Path(self._directory_path).expanduser()
            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.show_preview_dialog = True

        except Exception as e:
            print(f"Error opening preview: {e}")
            self.error_message = f"Fehler beim Öffnen der Datei: {str(e)}"

    def close_preview(self) -> None:
        """Close the file preview dialog."""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_selected_file(self) -> None:
        """Open preview for the currently selected grid row."""
        if self.selected_rows and len(self.selected_rows) > 0:
            self.open_file_preview(self.selected_rows[0])

    def download_csv(self) -> rx.event.EventSpec | None:
        """Download search results as CSV."""
        from .components import make_csv_download
        return make_csv_download(self.path_results, "pathfinder_results.csv")

    def _parse_user_input(self) -> dict:
        """Parse user input into search parameters (simple tag, path, or wildcard)."""
        if "/" not in self.user_input:
            result = {"type": "simple", "elements": [self.user_input.lower().strip()]}
        elif "*" not in self.user_input:
            result = {
                "type": "path",
                "elements": self.user_input.lower().strip().split("/"),
            }
        else:
            result = {
                "type": "wildcard",
                "elements": self.user_input.lower().strip().split("/"),
            }

        self.debug_output = str(result)
        return result

    def _build_xpath(self, search_params: dict) -> str | None:
        """Build XPath expression from parsed search parameters."""
        if search_params["type"] == "simple":
            tag = search_params["elements"][0]
            return f"//*[local-name()='{tag}']"

        elif search_params["type"] == "path":
            path_parts = []
            for elem in search_params["elements"]:
                path_parts.append(f"*[local-name()='{elem}']")
            return "//" + "/".join(path_parts)

        elif search_params["type"] == "wildcard":
            path_parts = []
            for elem in search_params["elements"]:
                if elem == "*":
                    path_parts.append("*")
                else:
                    path_parts.append(f"*[local-name()='{elem}']")
            return "//" + "//".join(path_parts)

        return None

    async def search_path(self):
        """Search all XML files for the given tag/path pattern."""
        self.is_searching = True
        self.debug_output = ""
        self.path_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        # Load file data from FileState on demand
        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_searching = False
            return

        # Cache directory path for synchronous preview access
        self._directory_path = file_state.directory_path

        search_params = self._parse_user_input()
        if search_params is None:
            self.is_searching = False
            return

        base_path = Path(file_state.directory_path).expanduser()
        results: list[dict] = []

        for file_info in file_state.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                xpath = self._build_xpath(search_params)
                elements = doc.xpath(xpath)

                for elem in elements:
                    # Build full path by walking up from element to root
                    path_parts: list[str] = []
                    current = elem
                    while current is not None:
                        path_parts.insert(0, etree.QName(current).localname)
                        current = current.getparent()
                    full_path = "/".join(path_parts)

                    text_content = (elem.text or "").strip()
                    if len(text_content) > 100:
                        text_content = text_content[:100] + "..."

                    results.append(
                        {
                            "subdir": subdir,
                            "filename": filename,
                            "line": elem.sourceline or 0,
                            "full_path": full_path,
                            "text_content": text_content,
                        }
                    )

            except Exception as e:
                print(e)
                continue

            if self.files_checked % 10 == 0:
                self.path_results = results
                yield

        self.path_results = results
        self.debug_output = f"{len(results)} Vorkommen gefunden"
        self.is_searching = False


# ============ UI Components ============


def pathfinder_input() -> rx.Component:
    """Input form and results table for tag/path search."""
    return rx.vstack(
        rx.text(
            "Bitte geben Sie einen einzelnen XML-Tag oder einen Pfad (ohne Anführungszeichen) ein, nach dem gesucht werden soll."
        ),
        rx.text(
            "Beispiel: 'bedeutung' sucht nach allen Vorkommen des Tags 'bedeutung'",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),
        rx.text(
            "Beispiel: 'sense/sense' sucht nach allen Stellen, in denen ein sense-Tag innerhalb eines sense-Tags auftaucht (ohne weitere Verschachtelung)",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),
        rx.text(
            "Beispiel: 'sense/*/bibl' sucht nach allen Stellen, in denen ein bibl-Tag innerhalb eines sense-Tags auftaucht. Das * bedeutet, dass noch andere Ebenen dazwischen vorkommen können. Es wird also auch sense/cit/bibl gefunden.",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),
        rx.hstack(
            rx.input(
                value=PathfinderState.user_input,
                placeholder="Tag oder Pfad eingeben...",
                on_change=PathfinderState.set_text,
                on_key_down=PathfinderState.handle_key_down,
                disabled=PathfinderState.is_searching,
                width="100%",
            ),
            rx.button(
                rx.cond(
                    PathfinderState.is_searching,
                    rx.hstack(
                        rx.spinner(size="3"),
                        rx.text("Suchen..."),
                        spacing="2",
                    ),
                    rx.text("Suchen"),
                ),
                on_click=PathfinderState.search_path,
                variant="solid",
                disabled=PathfinderState.is_searching,
            ),
            width="100%",
        ),
        rx.cond(
            PathfinderState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.callout("Durchsuche XML-Dateien nach angegebenem Pfad."),
                spacing="2",
                align="center",
            ),
        ),
        error_callout(PathfinderState.error_message),
        rx.cond(
            PathfinderState.has_results,
            rx.vstack(
                section_heading("Ergebnisse"),
                rx.text(
                    PathfinderState.results_count,
                    " Pfade gefunden",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                results_grid(
                    grid_id="path_results_grid",
                    row_data=PathfinderState.path_results,
                    column_defs=PATHFINDER_COLUMN_DEFS,
                    csv_filename="pathfinder_results.csv",
                    row_selection_handler=PathfinderState.set_selected_rows,
                    download_handler=PathfinderState.download_csv,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=PathfinderState.open_selected_file,
                        variant="outline",
                        disabled=PathfinderState.selected_rows.length() == 0,
                    ),
                    rx.text(
                        "Wählen Sie eine Zeile aus und klicken Sie auf 'Datei öffnen'.",
                        size="1",
                        color="gray",
                        font_style="italic",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            rx.text(
                PathfinderState.debug_output,
                color=HEADING_SECTION,
                size="2",
            ),
        ),
        # File preview dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(PathfinderState.preview_filename),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=PathfinderState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Treffer in Zeile: ",
                        PathfinderState.preview_line,
                    ),
                    rx.box(
                        rx.html(PathfinderState.preview_content_with_line_numbers),
                        width="100%",
                        height="500px",
                        overflow_y="scroll",
                        padding="10px",
                        background_color="var(--gray-2)",
                        border="1px solid var(--gray-6)",
                        border_radius="4px",
                        font_family="monospace",
                        font_size="12px",
                        line_height="1.5",
                    ),
                    rx.hstack(
                        rx.button(
                            "Schließen",
                            on_click=PathfinderState.close_preview,
                            variant="solid",
                        ),
                        width="100%",
                        justify="end",
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="900px",
                width="90vw",
            ),
            open=PathfinderState.show_preview_dialog,
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def pathfinder_page() -> rx.Component:
    """Page layout for tag/path search."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("TAG- UND PFADSUCHE"),
                no_files_warning(),
                pathfinder_input(),
                spacing="4",
            ),
        )
    )
