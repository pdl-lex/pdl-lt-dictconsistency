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
    TEXT_RESULT,
)


VALIDATOR_COLUMN_DEFS = [
    {"field": "filename", "headerName": "Dateiname", "sortable": True, "filter": True},
    {"field": "subdir", "headerName": "Unterverzeichnis", "sortable": True, "filter": True},
    {"field": "line", "headerName": "Zeile", "sortable": True, "filter": True},
    {"field": "column", "headerName": "Spalte", "sortable": True, "filter": True},
    {"field": "error", "headerName": "Fehler", "sortable": True, "filter": True},
]


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

    validation_type: str = "Wohlgeformtheit (Well-formed XML)"
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

    def download_wellformed_csv(self) -> rx.event.EventSpec | None:
        """Download well-formedness errors as CSV."""
        from .components import make_csv_download
        return make_csv_download(self.wellformed_errors, "xml_wellformed_errors.csv")

    def download_schema_csv(self) -> rx.event.EventSpec | None:
        """Download schema errors as CSV."""
        from .components import make_csv_download
        return make_csv_download(self.schema_errors, "xml_schema_errors.csv")

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

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_validating = False
            return

        self._total_files = len(file_state.xml_files_data)
        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_validating = False
            return
        from .processing import CHUNK_SIZE, append, load, clear
        token = self.router.session.client_token
        clear(token, "wellformed")
        clear(token, "schema")

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

        all_files = list(file_state.xml_files_data)

        for chunk_start in range(0, len(all_files), CHUNK_SIZE):
            chunk = all_files[chunk_start : chunk_start + CHUNK_SIZE]
            chunk_wf: list[dict] = []
            chunk_sc: list[dict] = []

            for file_info in chunk:
                subdir = file_info["subdir"]
                filename = file_info["filename"]
                file_path = base_path / filename if subdir == "." else base_path / subdir / filename
                self.files_checked += 1
                has_wellformed_error = False
                has_schema_error = False

                try:
                    with open(file_path, "rb") as f:
                        doc = etree.parse(f)
                    if rng_schema is not None:
                        if not rng_schema.validate(doc):
                            has_schema_error = True
                            for error in rng_schema.error_log:
                                chunk_sc.append({
                                    "subdir": subdir, "filename": filename,
                                    "line": error.line if error.line else 0,
                                    "column": error.column if error.column else 0,
                                    "error": error.message,
                                })
                except etree.XMLSyntaxError as e:
                    has_wellformed_error = True
                    chunk_wf.append({
                        "subdir": subdir, "filename": filename,
                        "line": e.lineno if e.lineno else 0,
                        "column": e.offset if e.offset else 0,
                        "error": str(e.msg) if e.msg else str(e),
                    })
                except Exception as e:
                    has_wellformed_error = True
                    chunk_wf.append({
                        "subdir": subdir, "filename": filename,
                        "line": 0, "column": 0, "error": str(e),
                    })

                if has_wellformed_error:
                    self.files_with_wellformed_errors += 1
                if has_schema_error:
                    self.files_with_schema_errors += 1

            append(token, "wellformed", chunk_wf)
            append(token, "schema", chunk_sc)
            yield

        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_errors = load(token, "wellformed")
            self.wellformed_validation_complete = True
        else:
            self.schema_errors = load(token, "schema")
            self.schema_validation_complete = True

        self.is_validating = False


# ============ UI Components ============


def validator_page() -> rx.Component:
    """Page layout for XML validation."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("XML-Validator"),
                no_files_warning(),
                rx.text("Prüft XML-Dateien auf Wohlgeformtheit oder gegen ein TEI-Lex 0 Schema."),
                rx.text("Wenn beide Validierungstypen durchgeführt werden sollen, muss die Validierung zweimal gestartet werden (jeweils für einen Typ). Es werden dann beide Ergebnisse untereinander angezeigt."),
                section_heading("Validierungstyp"),
                # Validation options
                rx.cond(
                    FileState.has_files,
                    rx.vstack(
                        rx.radio_group(
                            ["Wohlgeformtheit (Well-formed XML)", "TEI-Lex 0 Schema (RelaxNG)"],
                            value=ValidatorState.validation_type,
                            on_change=ValidatorState.set_validation_type,
                            direction="row",
                        ),
                        rx.hstack(
                            rx.button(
                                rx.cond(
                                    ValidatorState.is_validating,
                                    rx.hstack(rx.spinner(size="3"), rx.text("Validiere..."), spacing="2"),
                                    rx.hstack(rx.icon("play", size=16), rx.text("Validierung starten"), spacing="2"),
                                ),
                                on_click=ValidatorState.validate_all_xml,
                                variant="solid",
                                disabled=ValidatorState.is_validating,
                            ),
                        ),
                    ),
                ),
                rx.cond(
                    ValidatorState.is_validating
                    | ValidatorState.wellformed_validation_complete
                    | ValidatorState.schema_validation_complete,
                    section_heading("Ergebnisse"),
                ),
                # Schema file error
                rx.cond(
                    ValidatorState.schema_error != "",
                    rx.callout(ValidatorState.schema_error, icon="circle-alert", color_scheme=COLOR_DANGER),
                ),
                # Progress during validation
                rx.cond(
                    ValidatorState.is_validating,
                    rx.hstack(
                        rx.spinner(),
                        rx.text(
                            "Geprüft: ", ValidatorState.files_checked, " / ", ValidatorState.total_files,
                            " Dateien (", ValidatorState.validation_type_label, ")",
                            color=HEADING_SECTION,
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Result summary - well-formedness
                rx.cond(
                    ValidatorState.wellformed_validation_complete,
                    rx.cond(
                        ValidatorState.has_wellformed_errors,
                        rx.callout(
                            [ValidatorState.files_with_wellformed_errors, " von ", ValidatorState.files_checked,
                             " Dateien haben Wohlgeformtheits-Fehler (", ValidatorState.wellformed_error_count, " Fehler insgesamt)"],
                            icon="circle-alert", color_scheme=COLOR_DANGER, margin_top="20px",
                        ),
                        rx.callout(
                            ["Alle ", ValidatorState.files_checked, " Dateien sind wohlgeformt."],
                            icon="check-check", margin_top="20px",
                        ),
                    ),
                ),
                # Result summary - schema
                rx.cond(
                    ValidatorState.schema_validation_complete,
                    rx.cond(
                        ValidatorState.has_schema_errors,
                        rx.callout(
                            [ValidatorState.files_with_schema_errors, " von ", ValidatorState.files_checked,
                             " Dateien haben Schema-Fehler (", ValidatorState.schema_error_count, " Fehler insgesamt)."],
                            icon="circle-alert", color_scheme=COLOR_DANGER, margin_top="20px",
                        ),
                        rx.callout(
                            ["Alle ", ValidatorState.files_checked, " Dateien sind schema-valide."],
                            icon="check-check", margin_top="20px",
                        ),
                    ),
                ),
                # Error table - well-formedness
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.vstack(
                        rx.heading("Fehler Wohlgeformtheit", size="2", color=TEXT_RESULT, margin_top="30px"),
                        results_grid(
                            grid_id="xml_error_grid",
                            row_data=ValidatorState.wellformed_errors,
                            column_defs=VALIDATOR_COLUMN_DEFS,
                            csv_filename="xml_wellformed_errors.csv",
                            download_handler=ValidatorState.download_wellformed_csv,
                            show_preview=True,
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                # Error table - schema
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.vstack(
                        rx.heading("Fehler Schema", size="2", color=TEXT_RESULT, margin_top="30px"),
                        results_grid(
                            grid_id="schema_error_grid",
                            row_data=ValidatorState.schema_errors,
                            column_defs=VALIDATOR_COLUMN_DEFS,
                            csv_filename="xml_schema_errors.csv",
                            download_handler=ValidatorState.download_schema_csv,
                            show_preview=True,
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
