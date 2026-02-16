import reflex as rx
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState, MAX_FILE_SIZE
from .components import base_layout


def select_data_input_method() -> rx.Component:

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
            rx.heading("Modus", size="3", color="var(--jade-11)"),
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
                color_scheme="jade",
            ),
            align_items="start",
            spacing="2",
        ),
        # Bedingte Anzeige: Pfad-Input ODER Upload
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


def path_input_section(column_defs) -> rx.Component:
    # Lazy import to avoid circular dependency
    from .validator import ValidatorState

    return rx.vstack(
        rx.heading(
            "Verzeichnispfad", size="3", color="var(--jade-11)", margin_top="30px"
        ),
        rx.text(
            "Bitte geben Sie den vollständigen Pfad zu Ihrem XML-Verzeichnis ein:",
        ),
        rx.text(
            "Beispiel: /home/user/dokumente/xml oder C:\\Users\\Name\\Documents\\XML",
            size="2",
            color="var(--jade-11)",
            font_family="monospace",
        ),
        rx.text(
            "Tip: Pfad aus der Adresszeile des Explorers/Finders etc. kopieren und hier einfügen.",
            size="2",
            color="var(--jade-11)",
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
                color_scheme="jade",
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
                on_click=[ValidatorState.reset_validation, FileState.scan_xml_files],
                variant="solid",
                color_scheme="jade",
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
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),
        rx.cond(
            FileState.error_message != "",
            rx.callout(
                FileState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        rx.cond(
            FileState.has_files,
            rx.vstack(
                rx.text(
                    FileState.file_count,
                    " XML-Dateien gefunden",
                    color="var(--jade-11)",
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


def upload_section(column_defs) -> rx.Component:
    # Lazy import to avoid circular dependency
    from .validator import ValidatorState

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
                    color_scheme="jade",
                    variant="outline",
                ),
                rx.text(
                    "Oder Dateien hier hinziehen",
                    size="1",
                    color="gray",
                ),
                # Status-Anzeige
                rx.cond(
                    rx.selected_files("file_upload"),
                    rx.vstack(
                        rx.text(
                            "Bereit zum Hochladen.",
                            weight="bold",
                            size="2",
                            color_scheme="jade",
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
            color_scheme="jade",
        ),
        # Upload-Button
        rx.button(
            "Hochladen & Verarbeiten",
            on_click=[
                ValidatorState.reset_validation,
                FileState.handle_upload(rx.upload_files(upload_id="file_upload")),
            ],
            variant="solid",
            color_scheme="jade",
            disabled=FileState.is_loading,
        ),
        rx.cond(
            FileState.is_loading,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Lade Dateien hoch und verarbeite...",
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),
        rx.cond(
            FileState.error_message != "",
            rx.callout(
                FileState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        rx.cond(
            FileState.has_files,
            rx.vstack(
                rx.text(
                    FileState.file_count,
                    " XML-Dateien gefunden",
                    color="var(--jade-11)",
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
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("DATEN", size="4", color="var(--jade-12)", weight="light"),
                select_data_input_method(),
                spacing="4",
            ),
        )
    )
