import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from pdl_lt_reflex_aggrid_wrapper import ag_grid

from .state import FileState
from .components import base_layout, page_heading, section_heading, no_files_warning, COLOR_DANGER, HEADING_SECTION, TEXT_RESULT


class ValidatorState(rx.State):
    """State for XML validation. Independent from FileState, loads file data on demand."""

    wellformed_errors: list[dict] = []
    schema_errors: list[dict] = []
    is_validating: bool = False
    wellformed_validation_complete: bool = False
    schema_validation_complete: bool = False
    files_checked: int = 0
    files_with_wellformed_errors: int = 0
    files_with_schema_errors: int = 0
    error_message: str = ""

    # Validation type selector
    validation_type: str = "Wohlgeformtheit (Well-formed XML)"

    # Schema loading error
    schema_error: str = ""

    # Total file count, cached from FileState for progress display
    _total_files: int = 0

    @rx.var
    def total_files(self) -> int:
        """Return total file count for progress display."""
        return self._total_files

    @rx.var
    def wellformed_error_count(self) -> int:
        """Return number of well-formedness errors."""
        return len(self.wellformed_errors)

    @rx.var
    def schema_error_count(self) -> int:
        """Return number of schema errors."""
        return len(self.schema_errors)

    @rx.var
    def has_wellformed_errors(self) -> bool:
        """Check if any well-formedness errors exist."""
        return len(self.wellformed_errors) > 0

    @rx.var
    def has_schema_errors(self) -> bool:
        """Check if any schema errors exist."""
        return len(self.schema_errors) > 0

    @rx.var
    def validation_type_label(self) -> str:
        """Return short label for the current validation type."""
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            return "Wohlgeformtheit"
        return "TEI-Lex 0 Schema"

    def set_validation_type(self, value: str) -> None:
        """Switch validation type and clear schema error."""
        self.validation_type = value
        self.schema_error = ""

    def _get_schema_path(self) -> Path:
        """Return path to the RelaxNG schema file."""
        return Path(__file__).parent / "teilex0.rng"

    def _load_rng_schema(self, schema_path: Path) -> etree.RelaxNG:
        """Load and return a RelaxNG schema."""
        with open(schema_path, "rb") as f:
            schema_doc = etree.parse(f)
        return etree.RelaxNG(schema_doc)

    async def validate_all_xml(self):
        """Validate all XML files for well-formedness or schema conformance."""
        self.is_validating = True

        # Only reset the currently selected validation type
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
        self.error_message = ""
        yield

        # Load file data from FileState on demand
        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_validating = False
            return

        self._total_files = len(file_state.xml_files_data)
        base_path = Path(file_state.directory_path).expanduser()
        wellformed_errors: list[dict] = []
        schema_errors: list[dict] = []

        # Load schema if TEI-Lex 0 validation
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

        for file_info in file_state.xml_files_data:
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
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Schema validation if enabled
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

            # Update UI every 100 files
            if self.files_checked % 100 == 0:
                if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
                    self.wellformed_errors = wellformed_errors.copy()
                else:
                    self.schema_errors = schema_errors.copy()
                yield

        # Store final results
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_errors = wellformed_errors
            self.wellformed_validation_complete = True
        else:
            self.schema_errors = schema_errors
            self.schema_validation_complete = True

        self.is_validating = False

    def download_wellformed_errors_csv(self) -> rx.event.EventSpec:
        """Generate CSV download for well-formedness errors."""
        if not self.wellformed_errors:
            return

        df = pd.DataFrame(self.wellformed_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_wellformed_errors.csv",
        )

    def download_schema_errors_csv(self) -> rx.event.EventSpec:
        """Generate CSV download for schema errors."""
        if not self.schema_errors:
            return

        df = pd.DataFrame(self.schema_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_schema_errors.csv",
        )


# ============ UI Components ============


def validator_page() -> rx.Component:
    """Page layout for XML validation."""

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
                page_heading("XML-Validator"),
                no_files_warning(),
                rx.text(
                    "Prüft XML-Dateien auf Wohlgeformtheit oder gegen ein TEI-Lex 0 Schema."
                ),
                rx.text(
                    "Wenn beide Validierungstypen durchgeführt werden sollen, muss die Validierung zweimal gestartet werden (jeweils für einen Typ). Es werden dann beide Ergebnisse untereinander angezeigt."
                ),
                section_heading("Validierungstyp"),
                # Validation options
                rx.cond(
                    FileState.has_files,
                    rx.vstack(
                        rx.radio_group(
                            [
                                "Wohlgeformtheit (Well-formed XML)",
                                "TEI-Lex 0 Schema (RelaxNG)",
                            ],
                            value=ValidatorState.validation_type,
                            on_change=ValidatorState.set_validation_type,
                            direction="row",
                        ),
                        rx.hstack(
                            rx.button(
                                rx.cond(
                                    ValidatorState.is_validating,
                                    rx.hstack(
                                        rx.spinner(size="3"),
                                        rx.text("Validiere..."),
                                        spacing="2",
                                    ),
                                    rx.hstack(
                                        rx.icon("play", size=16),
                                        rx.text("Validierung starten"),
                                        spacing="2",
                                    ),
                                ),
                                on_click=ValidatorState.validate_all_xml,
                                variant="solid",
                                disabled=ValidatorState.is_validating,
                            ),
                        ),
                    ),
                ),
                section_heading("Ergebnisse"),
                # Schema file error
                rx.cond(
                    ValidatorState.schema_error != "",
                    rx.callout(
                        ValidatorState.schema_error,
                        icon="circle-alert",
                        color_scheme=COLOR_DANGER,
                    ),
                ),
                # CSV download - well-formedness
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
                    ),
                ),
                # CSV download - schema
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
                    ),
                ),
                # Progress during validation
                rx.cond(
                    ValidatorState.is_validating,
                    rx.hstack(
                        rx.spinner(),
                        rx.text(
                            "Geprüft: ",
                            ValidatorState.files_checked,
                            " / ",
                            ValidatorState.total_files,
                            " Dateien (",
                            ValidatorState.validation_type_label,
                            ")",
                            color=HEADING_SECTION,
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Result after validation - well-formedness
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
                            color_scheme=COLOR_DANGER,
                            margin_top="20px",
                        ),
                        rx.callout(
                            [
                                "Alle ",
                                ValidatorState.files_checked,
                                " Dateien sind wohlgeformt.",
                            ],
                            icon="check-check",
                            margin_top="20px",
                        ),
                    ),
                ),
                # Result after validation - schema
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
                            color_scheme=COLOR_DANGER,
                            margin_top="20px",
                        ),
                        rx.callout(
                            [
                                "Alle ",
                                ValidatorState.files_checked,
                                " Dateien sind schema-valide.",
                            ],
                            icon="check-check",
                            margin_top="20px",
                        ),
                    ),
                ),
                # Error table - well-formedness
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.vstack(
                        rx.heading(
                            "Fehler Wohlgeformtheit",
                            size="2",
                            color=TEXT_RESULT,
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
                # Error table - schema
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.vstack(
                        rx.heading(
                            "Fehler Schema",
                            size="2",
                            color=TEXT_RESULT,
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
