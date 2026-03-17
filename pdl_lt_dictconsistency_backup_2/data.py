import reflex as rx
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState, MAX_FILE_SIZE
from .components import base_layout, page_heading, section_heading, COLOR_DANGER, HEADING_SECTION


def select_data_input_method() -> rx.Component:
    """Main data input component with mode selection."""

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
            field="size_kb",
            header_name="Dateigröße (KB)",
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        rx.vstack(
            section_heading("Modus", margin_top="0px"),
            rx.text("Wie möchten Sie XML-Dateien bereitstellen?"),
            rx.spacer(height="30px"),
            rx.text(
                "Die Option 'Verzeichnispfad' durchsucht ein Verzeichnis und eignet sich besonders bei lokaler Installation. Die Option 'Datei-Upload' ermöglicht das Hochladen von XML-Dateien oder ZIP-Archiven.",
                color="gray",
                style={"font_style": "italic"},
            ),
            rx.text(
                "Bei der 'Datei-Upload'-Methode werden die Dateien in einem temporären Verzeichnis gespeichert und verarbeitet. Dieses Verzeichnis wird automatisch bereinigt, wenn die Session endet.",
                color="gray",
                style={"font_style": "italic"},
            ),
            rx.text(
                "Aus Sicherheitsgründen bestehen diverse Beschränkungen beim Hochladen von Dateien (max. Dateigröße, max. Anzahl Dateien, keine ausführbaren Dateien etc.).",
                color="gray",
                style={"font_style": "italic"},
            ),
            rx.spacer(height="30px"),
            rx.radio_group(
                ["Verzeichnispfad", "Datei-Upload"],
                value=FileState.upload_mode,
                on_change=FileState.set_upload_mode,
                direction="row",
                spacing="4",
            ),
            align_items="start",
            spacing="2",
        ),
        rx.cond(
            FileState.upload_mode == "Verzeichnispfad",
            path_input_section(column_defs),
        ),
        rx.cond(
            FileState.upload_mode == "Datei-Upload",
            upload_section(column_defs),
        ),
        spacing="4",
        width="100%",
    )


def path_input_section(column_defs: list) -> rx.Component:
    """Directory path input with scan button and results grid."""

    return rx.vstack(
        section_heading("Verzeichnispfad"),
        rx.text(
            "Bitte geben Sie den vollständigen Pfad zu Ihrem XML-Verzeichnis ein:",
        ),
        rx.text(
            "Beispiel: /home/user/dokumente/xml oder C:\\Users\\Name\\Documents\\XML",
            size="2",
            color=HEADING_SECTION,
            font_family="monospace",
        ),
        rx.text(
            "Tip: Pfad aus der Adresszeile des Explorers/Finders etc. kopieren und hier einfügen.",
            size="2",
            color=HEADING_SECTION,
            font_family="monospace",
        ),
        rx.hstack(
            rx.input(
                value=FileState.directory_path,
                placeholder="Pfad zum XML-Verzeichnis eingeben...",
                on_change=FileState.set_directory_path,
                on_key_down=FileState.handle_key_down,
                disabled=FileState.is_loading,
                width="100%",
            ),
            rx.button(
                rx.cond(
                    FileState.is_loading,
                    rx.hstack(
                        rx.spinner(size="3"),
                        rx.text("Durchsuche..."),
                        spacing="2",
                    ),
                    rx.text("Durchsuchen"),
                ),
                on_click=FileState.scan_xml_files,
                variant="solid",
                disabled=FileState.is_loading,
            ),
            width="100%",
        ),
        rx.cond(
            FileState.is_loading,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Durchsuche Verzeichnis rekursiv nach XML-Dateien...",
                ),
                spacing="2",
                align="center",
            ),
        ),
        section_heading("Ergebnisse"),
        rx.cond(
            FileState.error_message != "",
            rx.callout(
                FileState.error_message,
                icon="message-circle-warning",
                color_scheme=COLOR_DANGER,
            ),
        ),
        rx.cond(
            FileState.has_files,
            rx.vstack(
                rx.text(
                    FileState.file_count,
                    " XML-Dateien gefunden",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="path_input_grid",
                    row_data=FileState.xml_files_data,
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
                ),
                rx.spacer(height="30px"),
                spacing="3",
                width="100%",
            ),
        ),
        spacing="4",
        width="100%",
    )


def upload_section(column_defs: list) -> rx.Component:
    """File upload area with drag-and-drop and results grid."""

    return rx.vstack(
        rx.text(
            "Laden Sie eine oder mehrere XML-Dateien oder ein ZIP-Archiv hoch:",
            size="2",
            color="gray",
        ),
        rx.upload(
            rx.vstack(
                rx.button(
                    "Dateien auswählen",
                    variant="outline",
                ),
                rx.text(
                    "Oder Dateien hier hinziehen",
                    size="1",
                    color="gray",
                ),
                rx.cond(
                    rx.selected_files("file_upload"),
                    rx.vstack(
                        rx.text(
                            "Bereit zum Hochladen.",
                            weight="bold",
                            size="2",
                        ),
                    ),
                    rx.text("Keine Dateien ausgewählt", size="1", color="gray"),
                ),
                align="center",
            ),
            id="file_upload",
            accept={
                "application/xml": [".xml"],
                "application/zip": [".zip"],
            },
            multiple=True,
            max_files=100,
            max_size=MAX_FILE_SIZE,
            border="1px dotted var(--gray-6)",
            padding="60px",
            background_color="var(--gray-3)",
            border_radius="6px",
            width="100%",
            disabled=FileState.is_loading,
        ),
        rx.button(
            "Hochladen & Verarbeiten",
            on_click=FileState.handle_upload(
                rx.upload_files(upload_id="file_upload")
            ),
            variant="solid",
            disabled=FileState.is_loading,
        ),
        rx.cond(
            FileState.is_loading,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Lade Dateien hoch und verarbeite...",
                ),
                spacing="2",
                align="center",
            ),
        ),
        section_heading("Ergebnisse"),
        rx.cond(
            FileState.error_message != "",
            rx.callout(
                FileState.error_message,
                icon="message-circle-warning",
                color_scheme=COLOR_DANGER,
            ),
        ),
        rx.cond(
            FileState.has_files,
            rx.vstack(
                rx.text(
                    FileState.file_count,
                    " XML-Dateien gefunden",
                    color=HEADING_SECTION,
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="upload_grid",
                    row_data=FileState.xml_files_data,
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
                ),
                rx.spacer(height="30px"),
                rx.text(
                    "Tipp: Klicken Sie auf das Download-Symbol oben rechts in der Tabelle, um die Dateiliste als CSV-Datei herunterzuladen.",
                    color="gray",
                    size="2",
                ),
                spacing="3",
                width="100%",
                padding_bottom="20px",
            ),
        ),
        spacing="3",
        width="100%",
    )


def data_page() -> rx.Component:
    """Page layout for data import."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("DATEN"),
                select_data_input_method(),
                spacing="4",
            ),
        )
    )
