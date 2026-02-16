import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout


class ValidatorState(FileState):
    """State für XML-Validierung - erbt von FileState um Zugriff auf xml_files_data zu haben"""

    wellformed_errors: list[dict] = []
    schema_errors: list[dict] = []
    is_validating: bool = False
    wellformed_validation_complete: bool = False
    schema_validation_complete: bool = False
    files_checked: int = 0
    files_with_wellformed_errors: int = 0
    files_with_schema_errors: int = 0

    # Validierungstyp
    validation_type: str = "Wohlgeformtheit (Well-formed XML)"

    # Schema-Fehler
    schema_error: str = ""

    @rx.var
    def wellformed_error_count(self) -> int:
        return len(self.wellformed_errors)

    @rx.var
    def schema_error_count(self) -> int:
        return len(self.schema_errors)

    @rx.var
    def has_wellformed_errors(self) -> bool:
        return len(self.wellformed_errors) > 0

    @rx.var
    def has_schema_errors(self) -> bool:
        return len(self.schema_errors) > 0

    @rx.var
    def can_validate(self) -> bool:
        """Prüft ob Dateien zum Validieren vorhanden sind"""
        return len(self.xml_files_data) > 0

    @rx.var
    def can_start_validation(self) -> bool:
        """Prüft ob Validierung gestartet werden kann"""
        return self.can_validate

    @rx.var
    def validation_type_label(self) -> str:
        """Gibt den Namen des Validierungstyps zurück"""
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            return "Wohlgeformtheit"
        return "TEI-Lex 0 Schema"

    @rx.var
    def wellformed_errors_df(self) -> pd.DataFrame:
        """DataFrame für Wohlgeformtheits-Fehler"""
        if not self.wellformed_errors:
            return pd.DataFrame()

        df = pd.DataFrame(self.wellformed_errors)
        df = df.rename(
            columns={
                "subdir": "Unterverzeichnis",
                "filename": "Dateiname",
                "line": "Zeile",
                "column": "Spalte",
                "error": "Fehler",
            }
        )
        return df

    @rx.var
    def schema_errors_df(self) -> pd.DataFrame:
        """DataFrame für Schema-Fehler"""
        if not self.schema_errors:
            return pd.DataFrame()

        df = pd.DataFrame(self.schema_errors)
        df = df.rename(
            columns={
                "subdir": "Unterverzeichnis",
                "filename": "Dateiname",
                "line": "Zeile",
                "column": "Spalte",
                "error": "Fehler",
            }
        )
        return df

    def set_validation_type(self, value: str):
        self.validation_type = value
        self.schema_error = ""

    def _get_schema_path(self) -> Path:
        """Gibt den Pfad zur Schema-Datei im App-Verzeichnis zurück"""
        return Path(__file__).parent / "teilex0.rng"

    def _load_rng_schema(self, schema_path: Path):
        """Lädt ein RelaxNG Schema"""
        with open(schema_path, "rb") as f:
            schema_doc = etree.parse(f)
        return etree.RelaxNG(schema_doc)

    def _reset_validation_results(self):
        """Setzt Validierungsergebnisse zurück wenn neue Daten geladen werden"""
        self.wellformed_errors = []
        self.schema_errors = []
        self.wellformed_validation_complete = False
        self.schema_validation_complete = False
        self.files_checked = 0
        self.files_with_wellformed_errors = 0
        self.files_with_schema_errors = 0
        self.schema_error = ""

    def reset_validation(self):
        """Setzt alle Validierungsergebnisse zurück"""
        self._reset_validation_results()

    async def validate_all_xml(self):
        """Validiert alle XML-Dateien"""
        self.is_validating = True

        # Nur die AKTUELL gewählte Validierung zurücksetzen
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_validation_complete = False
            self.wellformed_errors = []
            self.files_with_wellformed_errors = 0
        else:
            self.schema_validation_complete = False
            self.schema_errors = []
            self.files_with_schema_errors = 0

        self.files_checked = 0
        self.schema_error = ""

        yield

        if not self.directory_path or not self.xml_files_data:
            self.is_validating = False
            return

        base_path = Path(self.directory_path).expanduser()
        wellformed_errors = []
        schema_errors = []

        # Schema laden falls TEI-Lex 0 Validierung
        rng_schema = None
        if self.validation_type == "TEI-Lex 0 Schema (RelaxNG)":
            try:
                schema_file = self._get_schema_path()
                if not schema_file.exists():
                    self.schema_error = f"Schema-Datei nicht gefunden: {schema_file}. Bitte 'teilex0.rng' im App-Verzeichnis ablegen."
                    self.is_validating = False
                    return
                rng_schema = self._load_rng_schema(schema_file)
            except Exception as e:
                self.schema_error = f"Fehler beim Laden des Schemas: {str(e)}"
                self.is_validating = False
                return

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1
            has_wellformed_error = False
            has_schema_error = False

            try:
                # Versuche XML zu parsen (Wohlgeformtheit)
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Schema-Validierung falls aktiviert
                if rng_schema is not None:
                    if not rng_schema.validate(doc):
                        has_schema_error = True
                        for error in rng_schema.error_log:
                            schema_errors.append(
                                {
                                    "subdir": subdir,
                                    "filename": filename,
                                    "line": error.line if error.line else 0,
                                    "column": error.column if error.column else 0,
                                    "error": error.message,
                                }
                            )

            except etree.XMLSyntaxError as e:
                has_wellformed_error = True
                wellformed_errors.append(
                    {
                        "subdir": subdir,
                        "filename": filename,
                        "line": e.lineno if e.lineno else 0,
                        "column": e.offset if e.offset else 0,
                        "error": str(e.msg) if e.msg else str(e),
                    }
                )
            except Exception as e:
                has_wellformed_error = True
                wellformed_errors.append(
                    {
                        "subdir": subdir,
                        "filename": filename,
                        "line": 0,
                        "column": 0,
                        "error": str(e),
                    }
                )

            if has_wellformed_error:
                self.files_with_wellformed_errors += 1
            if has_schema_error:
                self.files_with_schema_errors += 1

            # Alle 100 Dateien UI aktualisieren
            if self.files_checked % 100 == 0:
                if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
                    self.wellformed_errors = wellformed_errors.copy()
                else:
                    self.schema_errors = schema_errors.copy()
                yield

        # Ergebnisse speichern
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_errors = wellformed_errors
            self.wellformed_validation_complete = True
        else:
            self.schema_errors = schema_errors
            self.schema_validation_complete = True

        self.is_validating = False

    def download_wellformed_errors_csv(self):
        """Erstellt CSV-Download der Wohlgeformtheits-Fehler"""
        if not self.wellformed_errors:
            return

        df = pd.DataFrame(self.wellformed_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_wellformed_errors.csv",
        )

    def download_schema_errors_csv(self):
        """Erstellt CSV-Download der Schema-Fehler"""
        if not self.schema_errors:
            return

        df = pd.DataFrame(self.schema_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_schema_errors.csv",
        )


def validator_page() -> rx.Component:

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
            field="column",
            header_name="Spalte",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="error",
            header_name="Fehler",
            sortable=True,
            filter=True,
        ),
    ]

    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading(
                    "XML-Validator", size="4", color="var(--jade-12)", weight="light"
                ),
                # Warnung wenn keine Dateien geladen
                rx.cond(
                    ~ValidatorState.can_validate,
                    rx.callout(
                        "Bitte zuerst unter 'Daten' Dateien laden.",
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                ),
                rx.text(
                    "Prüft XML-Dateien auf Wohlgeformtheit oder gegen ein TEI-Lex 0 Schema."
                ),
                rx.text(
                    "Wenn beide Validierungstypen durchgeführt werden sollen, muss die Validierung zweimal gestartet werden (jeweils für einen Typ). Es werden dann beide Ergebnisse untereinander angezeigt."
                ),
                rx.heading(
                    "Validierungstyp",
                    size="3",
                    color="var(--jade-11)",
                    margin_top="30px",
                ),
                # Validierungsoptionen
                rx.cond(
                    ValidatorState.can_validate,
                    rx.vstack(
                        # Validierungstyp auswählen
                        rx.radio_group(
                            [
                                "Wohlgeformtheit (Well-formed XML)",
                                "TEI-Lex 0 Schema (RelaxNG)",
                            ],
                            value=ValidatorState.validation_type,
                            on_change=ValidatorState.set_validation_type,
                            direction="row",
                            color_scheme="jade",
                        ),
                        # Buttons
                        rx.hstack(
                            rx.button(
                                rx.cond(
                                    ValidatorState.is_validating,
                                    rx.hstack(
                                        rx.spinner(size="3"),
                                        rx.text("Validiere..."),
                                        spacing="2",
                                        color_scheme="jade",
                                    ),
                                    rx.hstack(
                                        rx.icon("play", size=16),
                                        rx.text("Validierung starten"),
                                        spacing="2",
                                        color_scheme="jade",
                                    ),
                                ),
                                on_click=ValidatorState.validate_all_xml,
                                variant="solid",
                                color_scheme="jade",
                                disabled=~ValidatorState.can_start_validation
                                | ValidatorState.is_validating,
                            ),
                        ),
                    ),
                ),
                rx.heading(
                    "Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"
                ),
                # Schema-Datei-Fehler anzeigen
                rx.cond(
                    ValidatorState.schema_error != "",
                    rx.callout(
                        ValidatorState.schema_error,
                        icon="circle-alert",
                        color_scheme="red",
                    ),
                ),
                # CSV Download - Wohlgeformtheit
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.button(
                        rx.hstack(
                            rx.icon("download", size=16),
                            rx.text("CSV Wohlgeformtheit"),
                            spacing="2",
                        ),
                        on_click=ValidatorState.download_wellformed_errors_csv,
                        variant="outline",
                        color_scheme="jade",
                    ),
                ),
                # CSV Download - Schema
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.button(
                        rx.hstack(
                            rx.icon("download", size=16),
                            rx.text("CSV Schema"),
                            spacing="2",
                        ),
                        on_click=ValidatorState.download_schema_errors_csv,
                        variant="outline",
                        color_scheme="jade",
                    ),
                ),
                # Fortschritt während Validierung
                rx.cond(
                    ValidatorState.is_validating,
                    rx.hstack(
                        rx.spinner(),
                        rx.text(
                            "Geprüft: ",
                            ValidatorState.files_checked,
                            " / ",
                            ValidatorState.file_count,
                            " Dateien (",
                            ValidatorState.validation_type_label,
                            ")",
                            color="var(--jade-11)",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Ergebnis nach Validierung - Wohlgeformtheit
                rx.cond(
                    ValidatorState.wellformed_validation_complete,
                    rx.cond(
                        ValidatorState.has_wellformed_errors,
                        rx.callout(
                            [
                                ValidatorState.files_with_wellformed_errors,
                                " von ",
                                ValidatorState.files_checked,
                                " Dateien haben Wohlgeformtheits-Fehler (",
                                ValidatorState.wellformed_error_count,
                                " Fehler insgesamt)",
                            ],
                            icon="circle-alert",
                            color_scheme="red",
                            margin_top="20px",
                        ),
                        rx.callout(
                            [
                                "Alle ",
                                ValidatorState.files_checked,
                                " Dateien sind wohlgeformt.",
                            ],
                            icon="check-check",
                            color_scheme="jade",
                            margin_top="20px",
                        ),
                    ),
                ),
                # Ergebnis nach Validierung - Schema
                rx.cond(
                    ValidatorState.schema_validation_complete,
                    rx.cond(
                        ValidatorState.has_schema_errors,
                        rx.callout(
                            [
                                ValidatorState.files_with_schema_errors,
                                " von ",
                                ValidatorState.files_checked,
                                " Dateien haben Schema-Fehler (",
                                ValidatorState.schema_error_count,
                                " Fehler insgesamt).",
                            ],
                            icon="circle-alert",
                            color_scheme="red",
                            margin_top="20px",
                        ),
                        rx.callout(
                            [
                                "Alle ",
                                ValidatorState.files_checked,
                                " Dateien sind schema-valide.",
                            ],
                            icon="check-check",
                            color_scheme="jade",
                            margin_top="20px",
                        ),
                    ),
                ),
                # Fehler-Tabelle Wohlgeformtheit
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.vstack(
                        rx.heading(
                            "Fehler Wohlgeformtheit",
                            size="2",
                            color="var(--jade-12)",
                            margin_top="30px",
                        ),
                        ag_grid(
                            id="xml_error_grid",
                            row_data=ValidatorState.wellformed_errors,
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
                        spacing="2",
                        width="100%",
                    ),
                ),
                # Fehler-Tabelle Schema
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.vstack(
                        rx.heading(
                            "Fehler Schema",
                            size="2",
                            color="var(--jade-12)",
                            margin_top="30px",
                        ),
                        ag_grid(
                            id="schema_error_grid",
                            row_data=ValidatorState.schema_errors,
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
                        spacing="2",
                        width="100%",
                    ),
                ),
                rx.spacer(height="30px"),
                spacing="4",
                width="100%",
            ),
        )
    )
