import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout


class TagContentState(FileState):
    """State für Tag-Inhalts-Suche - erbt von FileState um Zugriff auf xml_files_data zu haben"""

    search_mode: str = "Einzelner Tag"
    single_tag_input: str = ""
    search_text: str = ""
    include_whitespace: bool = True

    # Alle gefundenen Tags aus den Dokumenten
    all_tags: list[str] = []
    # Tags die durchsucht werden sollen
    included_tags: list[str] = []
    # Tags die ausgeschlossen wurden
    excluded_tags: list[str] = []

    content_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    is_loading_tags: bool = False
    tag_not_found: bool = False  # Für "Einzelner Tag" Modus: Tag existiert gar nicht

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.content_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.content_results)

    @rx.var
    def content_results_df(self) -> pd.DataFrame:
        if not self.content_results:
            return pd.DataFrame()
        return pd.DataFrame(self.content_results)

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

    def set_search_mode(self, value: str):
        self.search_mode = value

    def set_single_tag_input(self, value: str):
        self.single_tag_input = value

    def set_search_text(self, value: str):
        self.search_text = value

    def set_include_whitespace(self, value: bool):
        self.include_whitespace = value

    def insert_space(self):
        """Fügt ein Leerzeichen zum Suchtext hinzu"""
        self.search_text += " "

    def insert_linebreak(self):
        """Fügt einen Zeilenumbruch zum Suchtext hinzu"""
        self.search_text += "\n"

    def _reset_validation_results(self):
        """Setzt Ergebnisse und abgeleitete Daten zurück wenn neue Daten geladen werden"""
        # Nur Ergebnisse und abgeleitete Daten zurücksetzen, NICHT Benutzereingaben
        self.all_tags = []
        self.included_tags = []
        self.excluded_tags = []
        self.content_results = []
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0
        # search_text, single_tag_input, search_mode, include_whitespace bleiben erhalten

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

    def exclude_tag(self, tag: str):
        """Verschiebt Tag von included zu excluded"""
        if tag in self.included_tags:
            self.included_tags.remove(tag)
            self.excluded_tags.append(tag)
            self.excluded_tags.sort()

    def include_tag(self, tag: str):
        """Verschiebt Tag von excluded zu included"""
        if tag in self.excluded_tags:
            self.excluded_tags.remove(tag)
            self.included_tags.append(tag)
            self.included_tags.sort()

    async def load_all_tags(self):
        """Lädt alle einzigartigen Tags aus allen XML-Dateien"""
        self.is_loading_tags = True
        self.all_tags = []
        self.included_tags = []
        self.excluded_tags = []
        self.error_message = ""
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_loading_tags = False
            return

        base_path = Path(self.directory_path).expanduser()
        tags_set = set()

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Alle Tags im Dokument sammeln
                for elem in doc.iter():
                    # Nur echte Elemente verarbeiten (keine Kommentare, PIs, etc.)
                    if isinstance(elem.tag, str):
                        try:
                            tag_name = etree.QName(elem).localname
                            tags_set.add(tag_name)
                        except Exception as e:
                            print(f"Fehler beim Verarbeiten eines Elements in {filename}: {e}")
                            continue

            except Exception as e:
                print(f"Fehler beim Laden von Tags aus {filename}: {e}")
                continue

        # Sortierte Liste erstellen
        self.all_tags = sorted(list(tags_set))
        self.included_tags = self.all_tags.copy()
        self.is_loading_tags = False

    def _get_element_text(self, elem, include_whitespace: bool) -> str:
        """Extrahiert Text aus Element (ohne Child-Element-Text)"""
        text = elem.text or ""

        if not include_whitespace:
            # Leerzeichen und Zeilenumbrüche entfernen
            text = text.strip()
            text = " ".join(text.split())

        return text

    def _format_text_with_visible_whitespace(self, text: str) -> str:
        """Macht Leerzeichen und Zeilenumbrüche sichtbar"""
        # Ersetze Leerzeichen durch ·
        text = text.replace(" ", "·")
        # Ersetze Zeilenumbrüche durch ↵
        text = text.replace("\n", "↵\n")
        text = text.replace("\r", "↵")
        return text

    async def search_tag_content(self):
        """Sucht nach Tag-Inhalten basierend auf den Suchkriterien"""
        self.is_searching = True
        self.content_results = []
        self.files_checked = 0
        self.error_message = ""
        self.tag_not_found = False
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_searching = False
            return

        # Tags bestimmen
        is_single_tag_mode = False
        if self.search_mode == "Einzelner Tag":
            if not self.single_tag_input.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_searching = False
                return
            tags_to_search = [self.single_tag_input.strip()]
            is_single_tag_mode = True
        else:  # Mehrere Tags
            if not self.included_tags:
                self.error_message = "Keine Tags zum Durchsuchen ausgewählt."
                self.is_searching = False
                return
            tags_to_search = self.included_tags

        base_path = Path(self.directory_path).expanduser()
        results = []
        tag_found_in_documents = False  # Tracker für einzelnen Tag

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

                # Für jeden zu durchsuchenden Tag
                for tag_name in tags_to_search:
                    xpath = f"//*[local-name()='{tag_name}']"
                    elements = doc.xpath(xpath)

                    # Im Einzeltag-Modus: Prüfen ob Tag überhaupt existiert
                    if is_single_tag_mode and len(elements) > 0:
                        tag_found_in_documents = True

                    for elem in elements:
                        # Text des Elements (ohne Child-Element-Text)
                        elem_text = self._get_element_text(
                            elem, self.include_whitespace
                        )

                        # Ignoriere Formatierungs-Whitespace (Einrückung nach Zeilenumbrüchen)
                        # aber behalte echten Whitespace-Inhalt (ohne Newlines)
                        if self.include_whitespace and elem_text:
                            # Wenn Text mit Newline beginnt und nur Whitespace enthält → Formatierung
                            if elem_text.startswith("\n") and not elem_text.strip():
                                continue

                        # Prüfen ob Kriterien erfüllt sind
                        match = False

                        if self.search_text:  # Nicht .strip() verwenden!
                            # Suche nach bestimmtem Text
                            search_term = self.search_text

                            if not self.include_whitespace:
                                # Normalisiere Suchterm und Element-Text
                                search_term_normalized = " ".join(search_term.split())
                                if (
                                    search_term_normalized
                                    and search_term_normalized in elem_text
                                ):
                                    match = True
                            else:
                                # Exakte Suche mit Whitespace
                                if search_term in elem_text:
                                    match = True
                        else:
                            # Suche nach nicht-leeren Tags
                            if elem_text:
                                match = True

                        if match:
                            # Text für Anzeige vorbereiten
                            display_text = elem_text
                            if len(display_text) > 200:
                                display_text = display_text[:200] + "..."

                            # Whitespace sichtbar machen
                            display_text = self._format_text_with_visible_whitespace(
                                display_text
                            )

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
                print(f"Fehler beim Durchsuchen von {filename}: {e}")
                continue

            # UI alle 10 Dateien aktualisieren
            if self.files_checked % 10 == 0:
                self.content_results = results.copy()
                yield

        self.content_results = results

        # Im Einzeltag-Modus: Prüfen ob Tag gar nicht existiert
        if is_single_tag_mode and not tag_found_in_documents:
            self.tag_not_found = True

        self.is_searching = False


def tag_content_input() -> rx.Component:
    """UI für Tag-Inhalts-Suche"""

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
            field="tag",
            header_name="Tag",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="text",
            header_name="Inhalt",
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        # Warnung wenn keine Dateien geladen
        # rx.cond(
        #     ~TagContentState.has_files,
        #     rx.callout(
        #         "Bitte zuerst unter 'Daten' ein Verzeichnis scannen oder Dateien hochladen.",
        #         icon="triangle-alert",
        #         color_scheme="red",
        #     ),
        # ),
        rx.heading("Suchmodus", size="3", color="var(--jade-11)", margin_top="20px"),
        # Modus-Auswahl
        rx.radio_group(
            ["Einzelner Tag", "Mehrere Tags"],
            value=TagContentState.search_mode,
            on_change=TagContentState.set_search_mode,
            direction="row",
            spacing="4",
            color_scheme="jade",
        ),
        # Einzelner Tag Modus
        rx.cond(
            TagContentState.search_mode == "Einzelner Tag",
            rx.vstack(
                rx.text("Geben Sie den Tag-Namen ein (ohne Klammern):", size="2"),
                rx.input(
                    value=TagContentState.single_tag_input,
                    placeholder="z.B. entry oder sense",
                    on_change=TagContentState.set_single_tag_input,
                    width="100%",
                    color_scheme="jade",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        # Mehrere Tags Modus
        rx.cond(
            TagContentState.search_mode == "Mehrere Tags",
            rx.vstack(
                # Button zum Laden der Tags
                rx.cond(
                    (TagContentState.all_tags.length() == 0)
                    & ~TagContentState.is_loading_tags,
                    rx.button(
                        "Tags aus Dokumenten laden",
                        on_click=TagContentState.load_all_tags,
                        variant="solid",
                        color_scheme="jade",
                    ),
                ),
                # Ladeanzeige
                rx.cond(
                    TagContentState.is_loading_tags,
                    rx.hstack(
                        rx.spinner(),
                        rx.callout(
                            "Lade Tags aus allen Dokumenten...",
                            color_scheme="jade",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Durchsuchte Tags
                rx.cond(
                    TagContentState.included_tags.length() > 0,
                    rx.vstack(
                        rx.heading(
                            "Durchsuchte Tags", size="2", color="var(--jade-11)"
                        ),
                        rx.text(
                            "Klicken Sie auf das X, um Tags auszuschließen:",
                            size="1",
                            color="gray",
                        ),
                        rx.box(
                            rx.foreach(
                                TagContentState.included_tags,
                                lambda tag: rx.badge(
                                    rx.hstack(
                                        rx.text(tag),
                                        rx.icon(
                                            "x",
                                            size=14,
                                            cursor="pointer",
                                            on_click=TagContentState.exclude_tag(tag),
                                        ),
                                        spacing="1",
                                    ),
                                    color_scheme="jade",
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
                # Ausgeschlossene Tags
                rx.cond(
                    TagContentState.excluded_tags.length() > 0,
                    rx.vstack(
                        rx.heading(
                            "Ausgeschlossene Tags", size="2", color="var(--red-11)"
                        ),
                        rx.text(
                            "Klicken Sie auf einen Tag, um ihn wieder hinzuzufügen:",
                            size="1",
                            color="gray",
                        ),
                        rx.box(
                            rx.foreach(
                                TagContentState.excluded_tags,
                                lambda tag: rx.badge(
                                    tag,
                                    color_scheme="red",
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
        rx.heading("Suchoptionen", size="3", color="var(--jade-11)", margin_top="20px"),
        # Whitespace-Option
        rx.checkbox(
            "Leerzeichen und Zeilenumbrüche in der Suche berücksichtigen",
            checked=TagContentState.include_whitespace,
            on_change=TagContentState.set_include_whitespace,
            color_scheme="jade",
        ),
        # Text-Suche
        rx.vstack(
            rx.text("Suchtext (optional):", size="2"),
            rx.text(
                "Leer lassen, um alle nicht-leeren Tags zu finden.",
                size="1",
                color="gray",
                font_style="italic",
            ),
            rx.hstack(
                rx.input(
                    value=TagContentState.search_text,
                    placeholder="Text zum Suchen eingeben...",
                    on_change=TagContentState.set_search_text,
                    flex="1",
                    color_scheme="jade",
                    font_family="monospace",
                ),
                rx.button(
                    "·",
                    on_click=TagContentState.insert_space,
                    variant="outline",
                    color_scheme="gray",
                    size="2",
                    title="Leerzeichen einfügen",
                ),
                rx.button(
                    "↵",
                    on_click=TagContentState.insert_linebreak,
                    variant="outline",
                    color_scheme="gray",
                    size="2",
                    title="Zeilenumbruch einfügen",
                ),
                width="100%",
                spacing="2",
            ),
            # Visuelle Darstellung mit sichtbaren Whitespace-Zeichen
            rx.cond(
                TagContentState.search_text != "",
                rx.box(
                    rx.text(
                        "Vorschau: ",
                        TagContentState.search_text.replace(" ", "·")
                        .replace("\n", "↵\n")
                        .replace("\r", "↵"),
                        size="1",
                        font_family="monospace",
                        color="var(--jade-11)",
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
        # Suchen-Button
        rx.button(
            rx.cond(
                TagContentState.is_searching,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Suchen..."),
                    spacing="2",
                ),
                rx.text("Suchen"),
            ),
            on_click=TagContentState.search_tag_content,
            variant="solid",
            color_scheme="jade",
            disabled=TagContentState.is_searching | ~TagContentState.has_files,
            margin_top="10px",
        ),
        # Suchanzeige
        rx.cond(
            TagContentState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.text(
                    "Durchsuche ",
                    TagContentState.files_checked,
                    " / ",
                    TagContentState.file_count,
                    " Dateien...",
                    color="var(--jade-11)",
                ),
                spacing="2",
                align="center",
            ),
        ),
        # Fehleranzeige
        rx.cond(
            TagContentState.error_message != "",
            rx.callout(
                TagContentState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),
        # Ergebnisse
        rx.cond(
            TagContentState.has_results,
            rx.vstack(
                rx.text(
                    TagContentState.results_count,
                    " Treffer gefunden",
                    color="var(--jade-11)",
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="tag_content_grid",
                    row_data=TagContentState.content_results,
                    column_defs=column_defs,
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={
                        "fileName": "tag_content_results.csv",
                        "allColumns": True,
                        "columnSeparator": ";",
                        "exportMode": "csv",
                    },
                    dom_layout="autoHeight",
                    height="None",
                    column_size="sizeToFit",
                    row_selection={"mode": "singleRow"},
                    on_selection_changed=TagContentState.set_selected_rows,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=TagContentState.open_selected_file,
                        variant="outline",
                        color_scheme="jade",
                        disabled=TagContentState.selected_rows.length() == 0,
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
                ~TagContentState.is_searching,
                rx.cond(
                    TagContentState.tag_not_found,
                    rx.callout(
                        [
                            "Der Tag '",
                            TagContentState.single_tag_input,
                            "' wurde in keinem Dokument gefunden.",
                        ],
                        icon="circle-x",
                        color_scheme="red",
                    ),
                    rx.callout(
                        "Keine Treffer gefunden.",
                        icon="info",
                        color_scheme="gray",
                    ),
                ),
            ),
        ),
        # Dateivorschau-Dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            TagContentState.preview_filename,
                        ),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=TagContentState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Treffer in Zeile: ",
                        TagContentState.preview_line,
                    ),
                    rx.box(
                        rx.html(
                            TagContentState.preview_content_with_line_numbers,
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
                            on_click=TagContentState.close_preview,
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
            open=TagContentState.show_preview_dialog,
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def tag_content_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading(
                    "INHALT & LEERE TAGS",
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
                rx.text(
                    "Durchsuchen Sie Tags nach bestimmten Inhalten oder finden Sie nicht-leere Tags."
                ),
                tag_content_input(),
                spacing="4",
            ),
        )
    )
