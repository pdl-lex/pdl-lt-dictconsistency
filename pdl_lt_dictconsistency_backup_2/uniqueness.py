import reflex as rx
from pathlib import Path
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout, page_heading, section_heading, no_files_warning, COLOR_DANGER, HEADING_SECTION, TEXT_RESULT


class UniquenessState(rx.State):
    """State for uniqueness checks. Independent from FileState, loads file data on demand."""

    check_mode: str = "Tag"  # "Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"
    tag_name: str = ""
    tag_content: str = ""
    attribute_name: str = ""
    error_message: str = ""

    uniqueness_results: list[dict] = []
    files_checked: int = 0
    is_checking: bool = False

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
        """Check if any uniqueness violations were found."""
        return len(self.uniqueness_results) > 0

    @rx.var
    def results_count(self) -> int:
        """Return number of uniqueness violations."""
        return len(self.uniqueness_results)

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

    def set_check_mode(self, value: str) -> None:
        """Switch between uniqueness check modes."""
        self.check_mode = value

    def set_tag_name(self, value: str) -> None:
        """Update tag name input."""
        self.tag_name = value

    def set_tag_content(self, value: str) -> None:
        """Update tag content input."""
        self.tag_content = value

    def set_attribute_name(self, value: str) -> None:
        """Update attribute name input."""
        self.attribute_name = value

    def set_selected_rows(self, rows: list[dict]) -> None:
        """Store selected grid rows."""
        self.selected_rows = rows if rows else []

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger uniqueness check on Enter key."""
        if key == "Enter":
            return UniquenessState.check_uniqueness

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

    def _get_attribute_value(self, elem: etree._Element, attr_name: str) -> str | None:
        """Get attribute value, supporting namespace attributes like xml:id."""
        for attr_key, attr_value in elem.attrib.items():
            # Direct match (e.g. "type" == "type")
            if attr_key == attr_name:
                return attr_value

            # Namespace match (e.g. "{http://...}id" == "xml:id")
            if "}" in attr_key and ":" in attr_name:
                local_name = attr_key.split("}", 1)[1]
                prefix, local_input = attr_name.split(":", 1)

                if local_name == local_input:
                    namespace_uri = attr_key.split("}", 1)[0] + "}"
                    if prefix == "xml" and "XML/1998/namespace" in namespace_uri:
                        return attr_value

        return None

    async def check_uniqueness(self):
        """Run uniqueness check based on the selected mode."""
        self.is_checking = True
        self.uniqueness_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        # Load file data from FileState on demand
        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_checking = False
            return

        # Cache for synchronous preview access
        self._directory_path = file_state.directory_path

        # Validate inputs
        if self.check_mode == "Tag":
            if not self.tag_name.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Tag-Inhalt":
            if not self.tag_name.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Tag & Attribut":
            if not self.tag_name.strip() or not self.attribute_name.strip():
                self.error_message = "Bitte geben Sie Tag-Namen und Attribut-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Attribut":
            if not self.attribute_name.strip():
                self.error_message = "Bitte geben Sie einen Attribut-Namen ein."
                self.is_checking = False
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
                # Parser without DTD/ID validation to handle documents with ID duplicates
                parser = etree.XMLParser(
                    dtd_validation=False,
                    load_dtd=False,
                    no_network=True,
                    resolve_entities=False,
                )
                with open(file_path, "rb") as f:
                    doc = etree.parse(f, parser)

                if self.check_mode == "Tag":
                    # Check if tag appears more than once
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    if len(elements) > 1:
                        first_line = elements[0].sourceline or 0
                        results.append(
                            {
                                "subdir": subdir,
                                "filename": filename,
                                "line": first_line,
                                "error_type": f"Tag '{self.tag_name.strip()}' kommt {len(elements)}x vor",
                                "details": f"Erwartet: 1x, Gefunden: {len(elements)}x",
                            }
                        )

                elif self.check_mode == "Tag-Inhalt":
                    # Check if tag contents are unique within document
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    content_map: dict[str, list[int]] = {}
                    for elem in elements:
                        content = (elem.text or "").strip()
                        if content:
                            line = elem.sourceline or 0
                            if content not in content_map:
                                content_map[content] = []
                            content_map[content].append(line)

                    for content, lines in content_map.items():
                        if len(lines) > 1:
                            preview_text = (
                                content if len(content) <= 50 else content[:50] + "..."
                            )
                            results.append(
                                {
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": lines[0],
                                    "error_type": f"Inhalt '{preview_text}' in Tag '{self.tag_name.strip()}' kommt {len(lines)}x vor",
                                    "details": f"Zeilen: {', '.join(map(str, lines))}",
                                }
                            )

                elif self.check_mode == "Tag & Attribut":
                    # Check if attribute values are unique within tag
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    attr_map: dict[str, list[int]] = {}
                    for elem in elements:
                        attr_value = self._get_attribute_value(
                            elem, self.attribute_name.strip()
                        )
                        if attr_value:
                            line = elem.sourceline or 0
                            if attr_value not in attr_map:
                                attr_map[attr_value] = []
                            attr_map[attr_value].append(line)

                    for attr_value, lines in attr_map.items():
                        if len(lines) > 1:
                            results.append(
                                {
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": lines[0],
                                    "error_type": f"Attribut '{self.attribute_name.strip()}' mit Wert '{attr_value}' in Tag '{self.tag_name.strip()}' kommt {len(lines)}x vor",
                                    "details": f"Zeilen: {', '.join(map(str, lines))}",
                                }
                            )

                elif self.check_mode == "Attribut":
                    # Check if attribute values are unique across all tags
                    all_elements = doc.xpath("//*")

                    attr_map_full: dict[str, list[tuple[str, int]]] = {}
                    for elem in all_elements:
                        attr_value = self._get_attribute_value(
                            elem, self.attribute_name.strip()
                        )
                        if attr_value:
                            line = elem.sourceline or 0
                            tag_name = etree.QName(elem).localname
                            if attr_value not in attr_map_full:
                                attr_map_full[attr_value] = []
                            attr_map_full[attr_value].append((tag_name, line))

                    for attr_value, occurrences in attr_map_full.items():
                        if len(occurrences) > 1:
                            tag_list = ", ".join(
                                [f"{tag}:{line}" for tag, line in occurrences]
                            )
                            results.append(
                                {
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": occurrences[0][1],
                                    "error_type": f"Attribut '{self.attribute_name.strip()}' mit Wert '{attr_value}' kommt {len(occurrences)}x vor",
                                    "details": f"In: {tag_list}",
                                }
                            )

            except Exception as e:
                print(f"Error in {filename}: {e}")
                continue

            if self.files_checked % 10 == 0:
                self.uniqueness_results = results.copy()
                yield

        self.uniqueness_results = results
        self.is_checking = False


# ============ UI Components ============


def uniqueness_check() -> rx.Component:
    """Input form and results table for uniqueness checks."""

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
            field="error_type",
            header_name="Fehlertyp",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="details",
            header_name="Details",
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        rx.heading("Einmaligkeitsprüfung", size="4", color=HEADING_SECTION),
        rx.text(
            "Prüft, ob Tags, Inhalte oder Attribute innerhalb eines Dokuments einmalig sind.",
            size="2",
            color=TEXT_RESULT,
        ),
        rx.spacer(height="20px"),
        # Mode selection
        section_heading("Prüfmodus", margin_top="0px"),
        rx.radio(
            ["Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"],
            value=UniquenessState.check_mode,
            on_change=UniquenessState.set_check_mode,
            direction="column",
            spacing="2",
        ),
        rx.spacer(height="20px"),
        # Input fields based on mode
        rx.cond(
            UniquenessState.check_mode == "Tag",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. title",
                    on_change=UniquenessState.set_tag_name,
                    on_key_down=UniquenessState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.cond(
            UniquenessState.check_mode == "Tag-Inhalt",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. author",
                    on_change=UniquenessState.set_tag_name,
                    on_key_down=UniquenessState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.cond(
            UniquenessState.check_mode == "Tag & Attribut",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. entry",
                    on_change=UniquenessState.set_tag_name,
                    on_key_down=UniquenessState.handle_key_down,
                    width="100%",
                ),
                rx.text("Attribut-Name:", weight="bold", size="2", margin_top="10px"),
                rx.input(
                    value=UniquenessState.attribute_name,
                    placeholder="z.B. xml:id",
                    on_change=UniquenessState.set_attribute_name,
                    on_key_down=UniquenessState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.cond(
            UniquenessState.check_mode == "Attribut",
            rx.vstack(
                rx.text("Attribut-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.attribute_name,
                    placeholder="z.B. xml:id",
                    on_change=UniquenessState.set_attribute_name,
                    on_key_down=UniquenessState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.spacer(height="20px"),
        # Check button
        rx.button(
            rx.cond(
                UniquenessState.is_checking,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Prüfe..."),
                    spacing="2",
                ),
                rx.text("Prüfung starten"),
            ),
            on_click=UniquenessState.check_uniqueness,
            variant="solid",
            disabled=UniquenessState.is_checking,
        ),
        rx.cond(
            UniquenessState.is_checking,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    f"Durchsuche Dokumente... ({UniquenessState.files_checked} geprüft)",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.cond(
            UniquenessState.error_message != "",
            rx.callout(
                UniquenessState.error_message,
                icon="message-circle-warning",
                color_scheme=COLOR_DANGER,
            ),
        ),
        section_heading("Ergebnisse"),
        rx.cond(
            UniquenessState.has_results,
            rx.vstack(
                rx.text(
                    UniquenessState.results_count,
                    " Fehler gefunden",
                    color=COLOR_DANGER,
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="uniqueness_results_grid",
                    row_data=UniquenessState.uniqueness_results,
                    column_defs=column_defs,
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={
                        "fileName": "uniqueness_errors.csv",
                        "allColumns": True,
                        "columnSeparator": ";",
                        "exportMode": "csv",
                    },
                    dom_layout="autoHeight",
                    height="None",
                    column_size="sizeToFit",
                    row_selection={"mode": "singleRow"},
                    on_selection_changed=UniquenessState.set_selected_rows,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=UniquenessState.open_selected_file,
                        variant="outline",
                        disabled=UniquenessState.selected_rows.length() == 0,
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
            rx.cond(
                UniquenessState.has_results,
                rx.callout(
                    "Keine Fehler gefunden - alle geprüften Elemente sind einmalig.",
                    icon="check",
                ),
            ),
        ),
        # File preview dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            UniquenessState.preview_filename,
                        ),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=UniquenessState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Zeile: ",
                        UniquenessState.preview_line,
                    ),
                    rx.box(
                        rx.html(
                            UniquenessState.preview_content_with_line_numbers,
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
                            on_click=UniquenessState.close_preview,
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
            open=UniquenessState.show_preview_dialog,
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def uniqueness_page() -> rx.Component:
    """Page layout for uniqueness checks."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("EINMALIGKEIT"),
                no_files_warning(),
                uniqueness_check(),
                spacing="4",
            ),
        )
    )
