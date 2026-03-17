import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout


class PathfinderState(FileState):
    """State für Pathfinder - erbt von FileState um Zugriff auf xml_files_data zu haben"""

    user_input: str = ""
    path_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    debug_output: str = ""

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.path_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.path_results)

    @rx.var
    def path_results_df(self) -> pd.DataFrame:
        if not self.path_results:
            return pd.DataFrame()
        return pd.DataFrame(self.path_results)

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Formatiert den Vorschau-Inhalt mit Zeilennummern und hebt die Zielzeile hervor"""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        max_line_num = len(lines)
        num_width = len(str(max_line_num))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            # HTML-Escaping für den Zeileninhalt
            escaped_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            # Zielzeile hervorheben
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
    def handle_key_down(self, key: str):
        if key == "Enter":
            return PathfinderState.search_path

    @rx.event
    def set_text(self, value: str):
        self.user_input = value

    def _reset_validation_results(self):
        """Setzt Suchergebnisse zurück wenn neue Daten geladen werden"""
        self.path_results = []
        self.files_checked = 0
        self.debug_output = ""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0
        # user_input bleibt erhalten

    def open_file_preview(self, row_data: dict):
        """Öffnet Dateivorschau-Dialog für die ausgewählte Zeile"""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            # Vollständigen Dateipfad erstellen
            base_path = Path(self.directory_path).expanduser()
            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            # Datei lesen
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # State aktualisieren
            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.show_preview_dialog = True

        except Exception as e:
            print(f"Fehler beim Öffnen der Vorschau: {e}")
            self.error_message = f"Fehler beim Öffnen der Datei: {str(e)}"

    def close_preview(self):
        """Schließt den Vorschau-Dialog"""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_selected_file(self):
        """Öffnet die ausgewählte Datei in der Vorschau"""
        if self.selected_rows and len(self.selected_rows) > 0:
            self.open_file_preview(self.selected_rows[0])

    def set_selected_rows(self, rows):
        """Speichert die ausgewählten Zeilen"""
        self.selected_rows = rows if rows else []

    def _parse_user_input(self):
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

    def _build_xpath(self, search_params):
        if search_params["type"] == "simple":
            tag = search_params["elements"][0]
            return f"//*[local-name()='{tag}']"

        elif search_params["type"] == "path":
            path_parts = []
            for elem in search_params["elements"]:
                path_parts.append(f"*[local-name()='{elem}']")
            xpath = "//" + "/".join(path_parts)
            return xpath

        elif search_params["type"] == "wildcard":
            path_parts = []
            for elem in search_params["elements"]:
                if elem == "*":
                    path_parts.append("*")
                else:
                    path_parts.append(f"*[local-name()='{elem}']")
            xpath = "//" + "//".join(path_parts)
            return xpath

        return None

    async def search_path(self):
        self.is_searching = True
        self.debug_output = ""
        self.path_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        search_params = self._parse_user_input()

        if search_params is None:
            self.is_searching = False
            return

        base_path = Path(self.directory_path).expanduser()
        results = []

        for file_info in self.xml_files_data:
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
                    path_parts = []
                    current = elem

                    # generate the full path, walking up from the current element to the top (via .getparent)
                    # etree.QName(current).localname: get the localname, i.e. the tag
                    # insert(0, ...):  reverse insertion order, so the path starts at the top
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
                yield  # update UI

        self.path_results = results
        self.debug_output = f"{len(results)} Vorkommen gefunden"
        self.is_searching = False


def pathfinder_input() -> rx.Component:

    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="line",
            header_name="Zeile",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="full_path",
            header_name="XPath",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="text_content",
            header_name="Inhalt",
            sortable=True,
            filter=True,
        ),
    ]

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
                color_scheme="jade",
            ),
            width="100%",
        ),
        rx.cond(
            PathfinderState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Durchsuche XML-Dateien nach angegebenem Pfad.",
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.cond(
            PathfinderState.error_message != "",
            rx.callout(
                PathfinderState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),
        rx.cond(
            PathfinderState.has_results,
            rx.vstack(
                rx.text(
                    PathfinderState.results_count,
                    " Pfade gefunden",
                    color="var(--jade-11)",
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="path_results_grid",
                    row_data=PathfinderState.path_results,
                    column_defs=column_defs,
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={
                        "fileName": "xml_files.csv",
                        "allColumns": True,
                        "columnSeparator": ";",
                        "exportMode": "csv",
                    },
                    dom_layout="autoHeight",
                    height="None",
                    column_size="sizeToFit",
                    row_selection={"mode": "singleRow"},
                    on_selection_changed=PathfinderState.set_selected_rows,
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
                        color_scheme="jade",
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
                color="var(--jade-11)",
                size="2",
            ),
        ),
        # Dateivorschau-Dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            PathfinderState.preview_filename,
                        ),
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
                        rx.html(
                            PathfinderState.preview_content_with_line_numbers,
                        ),
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
                            color_scheme="jade",
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
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading(
                    "TAG- UND PFADSUCHE",
                    size="4",
                    color="var(--jade-12)",
                    weight="light",
                ),
                rx.cond(
                    ~FileState.has_files,
                    rx.callout(
                        "Bitte zuerst unter 'Daten' Dateien laden.",
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                ),
                pathfinder_input(),
                spacing="4",
            ),
        )
    )
