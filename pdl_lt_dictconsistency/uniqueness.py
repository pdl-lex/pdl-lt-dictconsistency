import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout


class UniquenessState(FileState):
    """State für Einmaligkeitsprüfungen - prüft ob Tags, Inhalte oder Attribute innerhalb von Dokumenten einmalig sind"""

    check_mode: str = "Tag"  # "Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"
    tag_name: str = ""
    tag_content: str = ""
    attribute_name: str = ""

    uniqueness_results: list[dict] = []
    files_checked: int = 0
    is_checking: bool = False

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.uniqueness_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.uniqueness_results)

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

    def set_check_mode(self, value: str):
        self.check_mode = value

    def set_tag_name(self, value: str):
        self.tag_name = value

    def set_tag_content(self, value: str):
        self.tag_content = value

    def set_attribute_name(self, value: str):
        self.attribute_name = value

    def _reset_validation_results(self):
        """Setzt Ergebnisse zurück wenn neue Daten geladen werden"""
        self.uniqueness_results = []
        self.files_checked = 0
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

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

    def _get_attribute_value(self, elem, attr_name: str):
        """Holt Attributwert, unterstützt auch Namespace-Attribute wie xml:id"""

        # Durchsuche alle Attribute des Elements
        for attr_key, attr_value in elem.attrib.items():
            # Fall 1: Direkter Match (z.B. "type" == "type")
            if attr_key == attr_name:
                return attr_value

            # Fall 2: Namespace-Match (z.B. "{http://...}id" == "xml:id")
            if "}" in attr_key and ":" in attr_name:
                # Extrahiere Namespace und lokalen Namen aus dem Schlüssel
                namespace_uri = attr_key.split("}", 1)[0] + "}"
                local_name = attr_key.split("}", 1)[1]

                # Extrahiere Präfix und lokalen Namen aus der Eingabe
                prefix, local_input = attr_name.split(":", 1)

                # Prüfe ob lokale Namen übereinstimmen
                if local_name == local_input:
                    # Prüfe bekannte Namespace-Präfixe
                    if prefix == "xml" and "XML/1998/namespace" in namespace_uri:
                        return attr_value

        return None

    async def check_uniqueness(self):
        """Führt Einmaligkeitsprüfung basierend auf dem gewählten Modus durch"""
        self.is_checking = True
        self.uniqueness_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_checking = False
            return

        # Validierung der Eingaben
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
                # Parser ohne DTD/ID-Validierung, damit auch Dokumente mit ID-Duplikaten geparst werden können
                parser = etree.XMLParser(
                    dtd_validation=False,
                    load_dtd=False,
                    no_network=True,
                    resolve_entities=False,
                )
                with open(file_path, "rb") as f:
                    doc = etree.parse(f, parser)

                # Je nach Modus unterschiedliche Prüfung
                if self.check_mode == "Tag":
                    # Prüfe ob Tag mehrfach vorkommt
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    if len(elements) > 1:
                        # Tag kommt mehrfach vor - Fehler!
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
                    # Prüfe ob Tag-Inhalte einmalig sind
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    # Sammle alle Inhalte
                    content_map = {}  # content -> [line_numbers]
                    for elem in elements:
                        content = (elem.text or "").strip()
                        if content:
                            line = elem.sourceline or 0
                            if content not in content_map:
                                content_map[content] = []
                            content_map[content].append(line)

                    # Prüfe auf Duplikate
                    for content, lines in content_map.items():
                        if len(lines) > 1:
                            # Inhalt kommt mehrfach vor
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
                    # Prüfe ob Attributwerte im Tag einmalig sind
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    # Sammle alle Attributwerte
                    attr_map = {}  # attr_value -> [line_numbers]
                    for elem in elements:
                        attr_value = self._get_attribute_value(
                            elem, self.attribute_name.strip()
                        )
                        if attr_value:
                            line = elem.sourceline or 0
                            if attr_value not in attr_map:
                                attr_map[attr_value] = []
                            attr_map[attr_value].append(line)

                    # Prüfe auf Duplikate
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
                    # Prüfe ob Attributwerte über alle Tags einmalig sind
                    # Hole alle Elemente (wegen Namespace-Attributen kann XPath nicht verwendet werden)
                    all_elements = doc.xpath("//*")

                    # Sammle alle Attributwerte
                    attr_map = {}  # attr_value -> [(tag_name, line_number)]
                    for elem in all_elements:
                        attr_value = self._get_attribute_value(
                            elem, self.attribute_name.strip()
                        )
                        if attr_value:
                            line = elem.sourceline or 0
                            tag_name = etree.QName(elem).localname
                            if attr_value not in attr_map:
                                attr_map[attr_value] = []
                            attr_map[attr_value].append((tag_name, line))

                    # Prüfe auf Duplikate
                    for attr_value, occurrences in attr_map.items():
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
                print(f"Fehler in {filename}: {e}")
                continue

            # UI alle 10 Dateien aktualisieren
            if self.files_checked % 10 == 0:
                self.uniqueness_results = results.copy()
                yield

        self.uniqueness_results = results
        self.is_checking = False


def uniqueness_check() -> rx.Component:
    """UI für Einmaligkeitsprüfung"""

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
        rx.heading("Einmaligkeitsprüfung", size="4", color="var(--jade-11)"),
        rx.text(
            "Prüft, ob Tags, Inhalte oder Attribute innerhalb eines Dokuments einmalig sind.",
            size="2",
            color="var(--gray-11)",
        ),
        rx.spacer(height="20px"),
        # Modus-Auswahl
        rx.heading("Prüfmodus", size="3", color="var(--jade-11)"),
        rx.radio(
            ["Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"],
            value=UniquenessState.check_mode,
            on_change=UniquenessState.set_check_mode,
            direction="column",
            spacing="2",
        ),
        rx.spacer(height="20px"),
        # Eingabefelder basierend auf Modus
        rx.cond(
            UniquenessState.check_mode == "Tag",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. title",
                    on_change=UniquenessState.set_tag_name,
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
                    width="100%",
                ),
                rx.text("Attribut-Name:", weight="bold", size="2", margin_top="10px"),
                rx.input(
                    value=UniquenessState.attribute_name,
                    placeholder="z.B. xml:id",
                    on_change=UniquenessState.set_attribute_name,
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
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),
        rx.spacer(height="20px"),
        # Prüfen-Button
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
            color_scheme="jade",
            disabled=UniquenessState.is_checking,
        ),
        rx.cond(
            UniquenessState.is_checking,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    f"Durchsuche Dokumente... ({UniquenessState.files_checked} geprüft)",
                    color_scheme="jade",
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
                color_scheme="red",
            ),
        ),
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),
        rx.cond(
            UniquenessState.has_results,
            rx.vstack(
                rx.text(
                    UniquenessState.results_count,
                    " Fehler gefunden",
                    color="var(--red-11)",
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
                        color_scheme="jade",
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
                    color_scheme="jade",
                ),
            ),
        ),
        # Dateivorschau-Dialog
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
            open=UniquenessState.show_preview_dialog,
        ),
        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def uniqueness_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading(
                    "EINMALIGKEIT", size="4", color="var(--jade-12)", weight="light"
                ),
                rx.cond(
                    ~FileState.has_files,
                    rx.callout(
                        "Bitte zuerst unter 'Daten' Dateien laden.",
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                ),
                uniqueness_check(),
                spacing="4",
            ),
        )
    )
