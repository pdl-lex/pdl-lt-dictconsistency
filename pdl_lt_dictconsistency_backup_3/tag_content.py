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


TAG_CONTENT_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "tag", "headerName": "Tag", "sortable": True, "filter": True},
    {"field": "text", "headerName": "Inhalt", "sortable": True, "filter": True},
]


class TagContentState(rx.State):
    """State for tag content search. Independent from FileState, loads file data on demand."""

    search_mode: str = "Einzelner Tag"
    single_tag_input: str = ""
    search_text: str = ""
    include_whitespace: bool = True
    error_message: str = ""

    # Tag collections discovered from documents
    all_tags: list[str] = []
    included_tags: list[str] = []
    excluded_tags: list[str] = []

    content_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    is_loading_tags: bool = False
    tag_not_found: bool = False

    # File preview
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    # Backend vars: cached from FileState for synchronous access
    _directory_path: str = ""
    _total_files: int = 0

    @rx.var
    def has_results(self) -> bool:
        """Check if search produced any results."""
        return len(self.content_results) > 0

    @rx.var
    def results_count(self) -> int:
        """Return number of search results."""
        return len(self.content_results)

    @rx.var
    def total_files(self) -> int:
        """Return total file count for progress display."""
        return self._total_files

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

    def set_search_mode(self, value: str) -> None:
        """Switch between single tag and multi-tag search mode."""
        self.search_mode = value

    def set_single_tag_input(self, value: str) -> None:
        """Update single tag input field."""
        self.single_tag_input = value

    def set_search_text(self, value: str) -> None:
        """Update search text field."""
        self.search_text = value

    def set_include_whitespace(self, value: bool) -> None:
        """Toggle whitespace-sensitive search."""
        self.include_whitespace = value

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger search on Enter key."""
        if key == "Enter":
            return TagContentState.search_tag_content

    def insert_space(self) -> None:
        """Append a space character to the search text."""
        self.search_text += " "

    def insert_linebreak(self) -> None:
        """Append a newline character to the search text."""
        self.search_text += "\n"

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
        return make_csv_download(self.content_results, "tag_content_results.csv")

    def exclude_tag(self, tag: str) -> None:
        """Move tag from included to excluded list."""
        if tag in self.included_tags:
            self.included_tags.remove(tag)
            self.excluded_tags.append(tag)
            self.excluded_tags.sort()

    def include_tag(self, tag: str) -> None:
        """Move tag from excluded to included list."""
        if tag in self.excluded_tags:
            self.excluded_tags.remove(tag)
            self.included_tags.append(tag)
            self.included_tags.sort()

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

        self._directory_path = file_state.directory_path
        base_path = Path(file_state.directory_path).expanduser()
        tags_set: set[str] = set()

        for file_info in file_state.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                for elem in doc.iter():
                    if isinstance(elem.tag, str):
                        try:
                            tag_name = etree.QName(elem).localname
                            tags_set.add(tag_name)
                        except Exception as e:
                            print(f"Error processing element in {filename}: {e}")
                            continue

            except Exception as e:
                print(f"Error loading tags from {filename}: {e}")
                continue

        self.all_tags = sorted(list(tags_set))
        self.included_tags = self.all_tags.copy()
        self.is_loading_tags = False

    def _get_element_text(self, elem: etree._Element, include_whitespace: bool) -> str:
        """Extract direct text content from element (excluding child element text)."""
        text = elem.text or ""
        if not include_whitespace:
            text = text.strip()
            text = " ".join(text.split())
        return text

    def _format_text_with_visible_whitespace(self, text: str) -> str:
        """Replace whitespace characters with visible symbols."""
        text = text.replace(" ", "·")
        text = text.replace("\n", "↵\n")
        text = text.replace("\r", "↵")
        return text

    async def search_tag_content(self):
        """Search tag contents based on current search criteria."""
        self.is_searching = True
        self.content_results = []
        self.files_checked = 0
        self.error_message = ""
        self.tag_not_found = False
        yield

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_searching = False
            return

        self._directory_path = file_state.directory_path
        self._total_files = len(file_state.xml_files_data)

        # Determine tags to search
        is_single_tag_mode = False
        if self.search_mode == "Einzelner Tag":
            if not self.single_tag_input.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_searching = False
                return
            tags_to_search = [self.single_tag_input.strip()]
            is_single_tag_mode = True
        else:
            if not self.included_tags:
                self.error_message = "Keine Tags zum Durchsuchen ausgewählt."
                self.is_searching = False
                return
            tags_to_search = self.included_tags

        base_path = Path(file_state.directory_path).expanduser()
        results: list[dict] = []
        tag_found_in_documents = False

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

                for tag_name in tags_to_search:
                    xpath = f"//*[local-name()='{tag_name}']"
                    elements = doc.xpath(xpath)

                    if is_single_tag_mode and len(elements) > 0:
                        tag_found_in_documents = True

                    for elem in elements:
                        elem_text = self._get_element_text(elem, self.include_whitespace)

                        # Skip formatting whitespace (indentation after newlines)
                        if self.include_whitespace and elem_text:
                            if elem_text.startswith("\n") and not elem_text.strip():
                                continue

                        match = False
                        if self.search_text:
                            search_term = self.search_text
                            if not self.include_whitespace:
                                search_term_normalized = " ".join(search_term.split())
                                if search_term_normalized and search_term_normalized in elem_text:
                                    match = True
                            else:
                                if search_term in elem_text:
                                    match = True
                        else:
                            if elem_text:
                                match = True

                        if match:
                            display_text = elem_text
                            if len(display_text) > 200:
                                display_text = display_text[:200] + "..."
                            display_text = self._format_text_with_visible_whitespace(display_text)

                            results.append(
                                {
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": elem.sourceline or 0,
                                    "tag": tag_name,
                                    "text": display_text,
                                }
                            )

            except Exception as e:
                print(f"Error searching {filename}: {e}")
                continue

            if self.files_checked % 10 == 0:
                self.content_results = results.copy()
                yield

        self.content_results = results
        if is_single_tag_mode and not tag_found_in_documents:
            self.tag_not_found = True
        self.is_searching = False


# ============ UI Components ============


def tag_content_input() -> rx.Component:
    """Input form and results table for tag content search."""
    return rx.vstack(
        section_heading("Suchmodus", margin_top="20px"),
        # Mode selection
        rx.radio_group(
            ["Einzelner Tag", "Mehrere Tags"],
            value=TagContentState.search_mode,
            on_change=TagContentState.set_search_mode,
            direction="row",
            spacing="4",
        ),
        # Single tag mode
        rx.cond(
            TagContentState.search_mode == "Einzelner Tag",
            rx.vstack(
                rx.text("Geben Sie den Tag-Namen ein (ohne Klammern):", size="2"),
                rx.input(
                    value=TagContentState.single_tag_input,
                    placeholder="z.B. entry oder sense",
                    on_change=TagContentState.set_single_tag_input,
                    on_key_down=TagContentState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        # Multi-tag mode
        rx.cond(
            TagContentState.search_mode == "Mehrere Tags",
            rx.vstack(
                rx.cond(
                    (TagContentState.all_tags.length() == 0)
                    & ~TagContentState.is_loading_tags,
                    rx.button(
                        "Tags aus Dokumenten laden",
                        on_click=TagContentState.load_all_tags,
                        variant="solid",
                    ),
                ),
                rx.cond(
                    TagContentState.is_loading_tags,
                    rx.hstack(
                        rx.spinner(),
                        rx.callout("Lade Tags aus allen Dokumenten..."),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Included tags
                rx.cond(
                    TagContentState.included_tags.length() > 0,
                    rx.vstack(
                        rx.heading("Durchsuchte Tags", size="2", color=HEADING_SECTION),
                        rx.text("Klicken Sie auf das X, um Tags auszuschließen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.included_tags,
                                lambda tag: rx.badge(
                                    rx.hstack(
                                        rx.text(tag),
                                        rx.icon("x", size=14, cursor="pointer", on_click=TagContentState.exclude_tag(tag)),
                                        spacing="1",
                                    ),
                                    margin="2px",
                                ),
                            ),
                            display="flex",
                            flex_wrap="wrap",
                            gap="5px",
                            padding="10px",
                            border="1px solid var(--gray-6)",
                            border_radius="4px",
                            min_height="50px",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                # Excluded tags
                rx.cond(
                    TagContentState.excluded_tags.length() > 0,
                    rx.vstack(
                        rx.heading("Ausgeschlossene Tags", size="2", color=COLOR_DANGER),
                        rx.text("Klicken Sie auf einen Tag, um ihn wieder hinzuzufügen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.excluded_tags,
                                lambda tag: rx.badge(
                                    tag,
                                    color_scheme=COLOR_DANGER,
                                    cursor="pointer",
                                    on_click=TagContentState.include_tag(tag),
                                    margin="2px",
                                ),
                            ),
                            display="flex",
                            flex_wrap="wrap",
                            gap="5px",
                            padding="10px",
                            border="1px solid var(--gray-6)",
                            border_radius="4px",
                            min_height="50px",
                        ),
                        spacing="2",
                        width="100%",
                        margin_top="10px",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        section_heading("Suchoptionen", margin_top="20px"),
        # Whitespace option
        rx.checkbox(
            "Leerzeichen und Zeilenumbrüche in der Suche berücksichtigen",
            checked=TagContentState.include_whitespace,
            on_change=TagContentState.set_include_whitespace,
        ),
        # Text search
        rx.vstack(
            rx.text("Suchtext (optional):", size="2"),
            rx.text("Leer lassen, um alle nicht-leeren Tags zu finden.", size="1", color="gray", font_style="italic"),
            rx.hstack(
                rx.input(
                    value=TagContentState.search_text,
                    placeholder="Text zum Suchen eingeben...",
                    on_change=TagContentState.set_search_text,
                    on_key_down=TagContentState.handle_key_down,
                    flex="1",
                    font_family="monospace",
                ),
                rx.button("·", on_click=TagContentState.insert_space, variant="outline", color_scheme="gray", size="2", title="Leerzeichen einfügen"),
                rx.button("↵", on_click=TagContentState.insert_linebreak, variant="outline", color_scheme="gray", size="2", title="Zeilenumbruch einfügen"),
                width="100%",
                spacing="2",
            ),
            rx.cond(
                TagContentState.search_text != "",
                rx.box(
                    rx.text(
                        "Vorschau: ",
                        TagContentState.search_text.replace(" ", "·").replace("\n", "↵\n").replace("\r", "↵"),
                        size="1",
                        font_family="monospace",
                        color=HEADING_SECTION,
                    ),
                    padding="5px 10px",
                    background_color="var(--gray-3)",
                    border="1px solid var(--gray-6)",
                    border_radius="4px",
                    width="100%",
                ),
            ),
            spacing="1",
            width="100%",
        ),
        # Search button
        rx.button(
            rx.cond(
                TagContentState.is_searching,
                rx.hstack(rx.spinner(size="3"), rx.text("Suchen..."), spacing="2"),
                rx.text("Suchen"),
            ),
            on_click=TagContentState.search_tag_content,
            variant="solid",
            disabled=TagContentState.is_searching | ~FileState.has_files,
            margin_top="10px",
        ),
        # Search progress
        rx.cond(
            TagContentState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.text("Durchsuche ", TagContentState.files_checked, " / ", TagContentState.total_files, " Dateien...", color=HEADING_SECTION),
                spacing="2",
                align="center",
            ),
        ),
        error_callout(TagContentState.error_message),
        # Results
        rx.cond(
            TagContentState.has_results,
            rx.vstack(
                section_heading("Ergebnisse"),
                rx.text(TagContentState.results_count, " Treffer gefunden", color=HEADING_SECTION, size="2", weight="bold"),
                results_grid(
                    grid_id="tag_content_grid",
                    row_data=TagContentState.content_results,
                    column_defs=TAG_CONTENT_COLUMN_DEFS,
                    csv_filename="tag_content_results.csv",
                    row_selection_handler=TagContentState.set_selected_rows,
                    download_handler=TagContentState.download_csv,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(rx.icon("file-text", size=16), rx.text("Datei öffnen"), spacing="2"),
                        on_click=TagContentState.open_selected_file,
                        variant="outline",
                        disabled=TagContentState.selected_rows.length() == 0,
                    ),
                    rx.text("Wählen Sie eine Zeile aus und klicken Sie auf 'Datei öffnen'.", size="1", color="gray", font_style="italic"),
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            rx.cond(
                ~TagContentState.is_searching,
                rx.cond(
                    TagContentState.tag_not_found,
                    rx.callout(
                        ["Der Tag '", TagContentState.single_tag_input, "' wurde in keinem Dokument gefunden."],
                        icon="circle-x",
                        color_scheme=COLOR_DANGER,
                    ),
                    rx.callout("Keine Treffer gefunden.", icon="info", color_scheme="gray"),
                ),
            ),
        ),
        # File preview dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(TagContentState.preview_filename),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(rx.icon("x"), variant="ghost", on_click=TagContentState.close_preview),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description("Treffer in Zeile: ", TagContentState.preview_line),
                    rx.box(
                        rx.html(TagContentState.preview_content_with_line_numbers),
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
                        rx.button("Schließen", on_click=TagContentState.close_preview, variant="solid"),
                        width="100%",
                        justify="end",
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="900px",
                width="90vw",
            ),
            open=TagContentState.show_preview_dialog,
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def tag_content_page() -> rx.Component:
    """Page layout for tag content search."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("INHALT & LEERE TAGS"),
                no_files_warning(),
                rx.text("Durchsuchen Sie Tags nach bestimmten Inhalten oder finden Sie nicht-leere Tags."),
                tag_content_input(),
                spacing="4",
            ),
        )
    )
