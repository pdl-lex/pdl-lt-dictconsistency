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
    COLOR_DANGER,
    HEADING_SECTION,
)


TAG_CONTENT_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "tag", "headerName": "Tag", "sortable": True, "filter": True},
    {"field": "attribute", "headerName": "Attribut", "sortable": True, "filter": True},
    {"field": "attr_value", "headerName": "Attributwert", "sortable": True, "filter": True},
    {"field": "text", "headerName": "Inhalt", "sortable": True, "filter": True},
    {"field": "quelle", "headerName": "Gedruckte Ausgabe", "sortable": True, "filter": True},
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

    # Attribute search
    attr_search_mode: str = "Einzelnes Attribut"
    single_attr_input: str = ""
    attr_value_input: str = ""
    all_attrs: list[str] = []
    included_attrs: list[str] = []
    excluded_attrs: list[str] = []
    is_loading_attrs: bool = False
    all_attr_values: list[str] = []
    is_loading_attr_values: bool = False

    content_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    is_loading_tags: bool = False
    tag_not_found: bool = False

    # Backend var: cached from FileState for progress display
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

    def _reset_attrs(self) -> None:
        self.all_attrs = []
        self.included_attrs = []
        self.excluded_attrs = []
        self.all_attr_values = []

    def set_search_mode(self, value: str) -> None:
        self.search_mode = value
        self._reset_attrs()

    def set_single_tag_input(self, value: str) -> None:
        self.single_tag_input = value
        self._reset_attrs()

    def set_search_text(self, value: str) -> None:
        self.search_text = value

    def set_include_whitespace(self, value: bool) -> None:
        self.include_whitespace = value

    def set_attr_search_mode(self, value: str) -> None:
        self.attr_search_mode = value

    def set_single_attr_input(self, value: str) -> None:
        self.single_attr_input = value

    def set_attr_value_input(self, value: str) -> None:
        self.attr_value_input = value

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger search on Enter key."""
        if key == "Enter":
            return TagContentState.search_tag_content

    def insert_space(self) -> None:
        self.search_text += " "

    def insert_linebreak(self) -> None:
        self.search_text += "\n"

    def download_csv(self) -> rx.event.EventSpec | None:
        from .components import make_csv_download
        return make_csv_download(self.content_results, "tag_content_results.csv")

    def exclude_tag(self, tag: str) -> None:
        if tag in self.included_tags:
            self.included_tags.remove(tag)
            self.excluded_tags.append(tag)
            self.excluded_tags.sort()
            self._reset_attrs()

    def include_tag(self, tag: str) -> None:
        if tag in self.excluded_tags:
            self.excluded_tags.remove(tag)
            self.included_tags.append(tag)
            self.included_tags.sort()
            self._reset_attrs()

    def exclude_attr(self, attr: str) -> None:
        if attr in self.included_attrs:
            self.included_attrs.remove(attr)
            self.excluded_attrs.append(attr)
            self.excluded_attrs.sort()

    def include_attr(self, attr: str) -> None:
        if attr in self.excluded_attrs:
            self.excluded_attrs.remove(attr)
            self.included_attrs.append(attr)
            self.included_attrs.sort()

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
        self._reset_attrs()

    async def load_all_attrs(self):
        """Collect all unique attribute names from the selected tags across all XML files."""
        self.is_loading_attrs = True
        self.all_attrs = []
        self.included_attrs = []
        self.excluded_attrs = []
        self.all_attr_values = []
        self.error_message = ""
        yield

        if self.search_mode == "Einzelner Tag":
            if not self.single_tag_input.strip():
                self.error_message = "Bitte zuerst einen Tag-Namen eingeben."
                self.is_loading_attrs = False
                return
            tags_filter = [self.single_tag_input.strip()]
        else:
            if not self.included_tags:
                self.error_message = "Keine Tags ausgewählt."
                self.is_loading_attrs = False
                return
            tags_filter = list(self.included_tags)

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_loading_attrs = False
            return

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_loading_attrs = False
            return

        attrs_set: set[str] = set()
        for file_info in file_state.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]
            file_path = base_path / filename if subdir == "." else base_path / subdir / filename
            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)
                for tag_name in tags_filter:
                    xpath = f"//*[local-name()='{tag_name}']"
                    for elem in doc.xpath(xpath):
                        for k in elem.attrib:
                            try:
                                local = etree.QName(k).localname if k.startswith('{') else k
                            except Exception:
                                local = k
                            attrs_set.add(local)
            except Exception as e:
                print(f"Error loading attrs from {filename}: {e}")
                continue

        self.all_attrs = sorted(list(attrs_set))
        self.included_attrs = self.all_attrs.copy()
        self.is_loading_attrs = False

    async def load_all_attr_values(self):
        """Collect all unique values for the selected attributes in the selected tags."""
        self.is_loading_attr_values = True
        self.all_attr_values = []
        self.error_message = ""
        yield

        if self.attr_search_mode == "Einzelnes Attribut":
            if not self.single_attr_input.strip():
                self.error_message = "Bitte einen Attribut-Namen eingeben."
                self.is_loading_attr_values = False
                return
            attrs_to_check = [self.single_attr_input.strip()]
        else:
            if not self.included_attrs:
                self.error_message = "Keine Attribute ausgewählt."
                self.is_loading_attr_values = False
                return
            attrs_to_check = list(self.included_attrs)

        tags_filter: list[str] | None
        if self.search_mode == "Einzelner Tag":
            tags_filter = [self.single_tag_input.strip()] if self.single_tag_input.strip() else None
        else:
            tags_filter = list(self.included_tags) if self.included_tags else None

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_loading_attr_values = False
            return

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_loading_attr_values = False
            return

        values_set: set[str] = set()
        for file_info in file_state.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]
            file_path = base_path / filename if subdir == "." else base_path / subdir / filename
            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)
                if tags_filter:
                    elements = []
                    for tag_name in tags_filter:
                        xpath = f"//*[local-name()='{tag_name}']"
                        elements.extend(doc.xpath(xpath))
                else:
                    elements = [e for e in doc.iter() if isinstance(e.tag, str)]
                for elem in elements:
                    for attr_name in attrs_to_check:
                        val = self._get_attr_value(elem, attr_name)
                        if val is not None:
                            values_set.add(val)
            except Exception as e:
                print(f"Error loading attr values from {filename}: {e}")
                continue

        self.all_attr_values = sorted(list(values_set))
        self.is_loading_attr_values = False

    def _get_attr_value(self, elem: etree._Element, attr_name: str) -> str | None:
        """Get attribute value by local name, handling XML namespaces."""
        val = elem.get(attr_name)
        if val is None:
            for k, v in elem.attrib.items():
                try:
                    local = etree.QName(k).localname if k.startswith('{') else k
                except Exception:
                    local = k
                if local == attr_name:
                    return v
        return val

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

        # Determine attribute filter
        has_attr_filter = False
        attrs_to_filter: list[str] = []
        if self.attr_search_mode == "Einzelnes Attribut":
            if self.single_attr_input.strip():
                attrs_to_filter = [self.single_attr_input.strip()]
                has_attr_filter = True
        else:
            if self.included_attrs:
                attrs_to_filter = list(self.included_attrs)
                has_attr_filter = True

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_searching = False
            return

        from .processing import CHUNK_SIZE, append, load, clear, get_quelle
        token = self.router.session.client_token
        clear(token, "tag_content")
        tag_found_in_documents = False
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
                    with open(file_path, "rb") as f:
                        doc = etree.parse(f)
                    quelle = get_quelle(doc.getroot(), filename)

                    for tag_name in tags_to_search:
                        xpath = f"//*[local-name()='{tag_name}']"
                        elements = doc.xpath(xpath)

                        if is_single_tag_mode and len(elements) > 0:
                            tag_found_in_documents = True

                        for elem in elements:
                            elem_text = self._get_element_text(elem, self.include_whitespace)
                            # Skip whitespace-only structural elements unless filtering by attribute
                            if self.include_whitespace and not has_attr_filter and elem_text:
                                if elem_text.startswith("\n") and not elem_text.strip():
                                    continue

                            # Text match
                            if self.search_text:
                                search_term = self.search_text
                                if not self.include_whitespace:
                                    search_term_normalized = " ".join(search_term.split())
                                    content_match = bool(search_term_normalized) and search_term_normalized in elem_text
                                else:
                                    content_match = search_term in elem_text
                            elif has_attr_filter:
                                content_match = True
                            else:
                                content_match = bool(elem_text)

                            # Attribute match (AND with text match)
                            attr_match = True
                            matched_attr = ""
                            matched_attr_val = ""
                            if has_attr_filter:
                                attr_match = False
                                for attr_name in attrs_to_filter:
                                    val = self._get_attr_value(elem, attr_name)
                                    if val is not None:
                                        if self.attr_value_input.strip():
                                            if self.attr_value_input.strip() in val:
                                                attr_match = True
                                                matched_attr = attr_name
                                                matched_attr_val = val
                                                break
                                        else:
                                            attr_match = True
                                            matched_attr = attr_name
                                            matched_attr_val = val
                                            break

                            if content_match and attr_match:
                                display_text = elem_text
                                if len(display_text) > 200:
                                    display_text = display_text[:200] + "..."
                                display_text = self._format_text_with_visible_whitespace(display_text)
                                chunk_results.append({
                                    "quelle": quelle,
                                    "subdir": subdir, "filename": filename,
                                    "line": elem.sourceline or 0,
                                    "tag": tag_name,
                                    "attribute": matched_attr,
                                    "attr_value": matched_attr_val,
                                    "text": display_text,
                                })

                except Exception as e:
                    print(f"Error searching {filename}: {e}")
                    continue

            append(token, "tag_content", chunk_results)
            yield

        self.content_results = load(token, "tag_content")
        if is_single_tag_mode and not tag_found_in_documents:
            self.tag_not_found = True
        self.is_searching = False


# ============ UI Components ============


def tag_content_input() -> rx.Component:
    """Input form and results table for tag content search."""
    return rx.vstack(
        # === XML-Tags ===
        section_heading("XML-Tags", margin_top="20px"),
        rx.radio_group(
            ["Einzelner Tag", "Mehrere Tags"],
            value=TagContentState.search_mode,
            on_change=TagContentState.set_search_mode,
            direction="row",
            spacing="4",
        ),
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
        # === Attribute ===
        section_heading("Attribute", margin_top="20px"),
        rx.radio_group(
            ["Einzelnes Attribut", "Mehrere Attribute"],
            value=TagContentState.attr_search_mode,
            on_change=TagContentState.set_attr_search_mode,
            direction="row",
            spacing="4",
        ),
        rx.cond(
            TagContentState.attr_search_mode == "Einzelnes Attribut",
            rx.vstack(
                rx.text("Geben Sie den Attribut-Namen ein (leer lassen für keine Attribut-Filterung):", size="2"),
                rx.input(
                    value=TagContentState.single_attr_input,
                    placeholder="z.B. type oder xml:id",
                    on_change=TagContentState.set_single_attr_input,
                    on_key_down=TagContentState.handle_key_down,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.cond(
            TagContentState.attr_search_mode == "Mehrere Attribute",
            rx.vstack(
                rx.cond(
                    (TagContentState.all_attrs.length() == 0)
                    & ~TagContentState.is_loading_attrs,
                    rx.button(
                        "Attribute aus Dokumenten laden",
                        on_click=TagContentState.load_all_attrs,
                        variant="solid",
                    ),
                ),
                rx.cond(
                    TagContentState.is_loading_attrs,
                    rx.hstack(
                        rx.spinner(),
                        rx.callout("Lade Attribute aus Dokumenten..."),
                        spacing="2",
                        align="center",
                    ),
                ),
                rx.cond(
                    TagContentState.included_attrs.length() > 0,
                    rx.vstack(
                        rx.heading("Durchsuchte Attribute", size="2", color=HEADING_SECTION),
                        rx.text("Klicken Sie auf das X, um Attribute auszuschließen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.included_attrs,
                                lambda attr: rx.badge(
                                    rx.hstack(
                                        rx.text(attr),
                                        rx.icon("x", size=14, cursor="pointer", on_click=TagContentState.exclude_attr(attr)),
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
                rx.cond(
                    TagContentState.excluded_attrs.length() > 0,
                    rx.vstack(
                        rx.heading("Ausgeschlossene Attribute", size="2", color=COLOR_DANGER),
                        rx.text("Klicken Sie auf einen Attribut-Namen, um ihn wieder hinzuzufügen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.excluded_attrs,
                                lambda attr: rx.badge(
                                    attr,
                                    color_scheme=COLOR_DANGER,
                                    cursor="pointer",
                                    on_click=TagContentState.include_attr(attr),
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
        # Attribute value input
        rx.vstack(
            rx.text("Attributwert (optional):", size="2"),
            rx.text("Leer lassen, um alle Elemente mit dem Attribut zu finden.", size="1", color="gray", font_style="italic"),
            rx.hstack(
                rx.input(
                    value=TagContentState.attr_value_input,
                    placeholder="Attributwert eingeben...",
                    on_change=TagContentState.set_attr_value_input,
                    on_key_down=TagContentState.handle_key_down,
                    flex="1",
                    font_family="monospace",
                ),
                rx.button(
                    rx.cond(
                        TagContentState.is_loading_attr_values,
                        rx.hstack(rx.spinner(size="2"), rx.text("Lädt..."), spacing="1"),
                        rx.text("Werte laden"),
                    ),
                    on_click=TagContentState.load_all_attr_values,
                    variant="outline",
                    disabled=TagContentState.is_loading_attr_values,
                ),
                width="100%",
                spacing="2",
            ),
            rx.cond(
                TagContentState.all_attr_values.length() > 0,
                rx.vstack(
                    rx.text("Vorhandene Werte (klicken zum Übernehmen):", size="1", color="gray"),
                    rx.box(
                        rx.foreach(
                            TagContentState.all_attr_values,
                            lambda val: rx.badge(
                                val,
                                cursor="pointer",
                                on_click=TagContentState.set_attr_value_input(val),
                                margin="2px",
                                color_scheme="blue",
                            ),
                        ),
                        display="flex",
                        flex_wrap="wrap",
                        gap="5px",
                        padding="10px",
                        border="1px solid var(--gray-6)",
                        border_radius="4px",
                        min_height="40px",
                        max_height="150px",
                        overflow_y="auto",
                    ),
                    spacing="1",
                    width="100%",
                ),
            ),
            spacing="1",
            width="100%",
        ),
        # === Inhalt ===
        section_heading("Inhalt", margin_top="20px"),
        rx.checkbox(
            "Leerzeichen und Zeilenumbrüche in der Suche berücksichtigen",
            checked=TagContentState.include_whitespace,
            on_change=TagContentState.set_include_whitespace,
        ),
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
                    download_handler=TagContentState.download_csv,
                    show_preview=True,
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
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def tag_content_page() -> rx.Component:
    """Page layout for tag content search."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("INHALT & LEERE TAGS"),
                no_files_warning(),
                rx.text("Durchsuchen Sie Tags nach bestimmten Inhalten oder finden Sie nicht-leere Tags."),
                tag_content_input(),
                spacing="4",
            ),
        )
    )
