import reflex as rx
from pathlib import Path
from .state import FileState


# ============ Design Tokens ============

# Colors - these follow the theme's accent_color automatically
COLOR_DANGER = "red"
COLOR_NEUTRAL = "gray"

HEADING_PRIMARY = "var(--accent-12)"
HEADING_SECTION = "var(--accent-11)"
TEXT_MUTED = "gray"
TEXT_RESULT = "var(--accent-11)"
COLOR_ACCENT = "var(--accent-9)"

PANEL_BG = rx.color("sand", 1, False)
PANEL_BORDER = "1px solid var(--gray-8)"
PAGE_BG = "var(--accent-2)"

# Layout
MAX_PAGE_WIDTH = "1400px"
SIDEBAR_WIDTH = ["100%", "100%", "250px"]  # mobile, tablet, desktop
CONTENT_WIDTH = ["100%", "100%", "60%"]

# Spacing
SECTION_GAP = "30px"
PANEL_PADDING = "20px"
PANEL_RADIUS = "5px"

# Version
APP_VERSION = "0.2"


# ============ Navigation ============

# Structured navigation: list of (section_heading, [(label, route), ...])
NAV_STRUCTURE: list[tuple[str, list[tuple[str, str]]]] = [
    ("Start", [
        ("Einführung", "/"),
        ("Daten", "/data"),
    ]),
    ("XML", [
        ("XML/TL0 Validator", "/validator"),
        ("Strukturanalyse", "/xml-structure"),
        ("Tag- und Pfadsuche", "/pathfinder"),
        ("Inhalt / Leere Tags", "/tag-content"),
        ("Einmaligkeit", "/uniqueness"),
        ("Verschachtelung", "/nesting"),

    ]),
    ("Bedeutungen", [
        ("Anzahl und Länge", "/senses-stats"),
    ]),
    ("LLM", [
        ("Chat", "/llm-query"),
        ("Texterkennung (OCR)", "/ocr-query"),
        ("LLM-Einstellungen", "/settings"),
    ]),
]


# ============ XML Preview (shared across all result pages) ============


class XmlPreviewState(rx.State):
    """Shared state for XML file preview dialog. Used by results_grid when show_preview=True."""

    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []
    preview_error: str = ""

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Format preview content with line numbers, highlighting the target line."""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        num_width = len(str(len(lines)))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            escaped = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            num_span = f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
            if i == self.preview_line:
                html_lines.append(
                    f'<div id="preview-highlight" style="background-color: var(--yellow-3); border-left: 3px solid var(--yellow-9);">'
                    f"{num_span}<span>{escaped}</span></div>"
                )
            else:
                html_lines.append(f"<div>{num_span}<span>{escaped}</span></div>")

        return "\n".join(html_lines)

    def set_selected_rows(self, rows: list[dict]) -> None:
        """Store selected grid rows."""
        self.selected_rows = rows if rows else []

    def _open_file_preview(self, row_data: dict, directory_path: str) -> None:
        """Read file and populate preview state."""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            base_path = Path(directory_path).expanduser()
            file_path = (
                base_path / filename if subdir == "." else base_path / subdir / filename
            )

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.preview_error = ""
            self.show_preview_dialog = True

        except Exception as e:
            self.preview_error = f"Fehler beim Öffnen der Datei: {str(e)}"

    async def open_selected_file(self):
        """Open preview for the currently selected grid row."""
        if not self.selected_rows:
            return
        file_state = await self.get_state(FileState)
        self._open_file_preview(self.selected_rows[0], file_state.directory_path)
        # After state update, scroll the highlighted line into view
        yield rx.call_script(
            "setTimeout(() => {"
            "  const el = document.getElementById('preview-highlight');"
            "  if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });"
            "}, 120);"
        )

    def close_preview(self) -> None:
        """Close the file preview dialog."""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0


def xml_preview_dialog() -> rx.Component:
    """Global XML preview dialog. Included once in base_layout."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.dialog.title(XmlPreviewState.preview_filename),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon("x"),
                            variant="ghost",
                            on_click=XmlPreviewState.close_preview,
                        ),
                    ),
                    width="100%",
                    align_items="center",
                ),
                rx.dialog.description("Treffer in Zeile: ", XmlPreviewState.preview_line),
                rx.cond(
                    XmlPreviewState.preview_error != "",
                    rx.callout(
                        XmlPreviewState.preview_error,
                        icon="message-circle-warning",
                        color_scheme=COLOR_DANGER,
                    ),
                ),
                rx.box(
                    rx.html(XmlPreviewState.preview_content_with_line_numbers),
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
                        on_click=XmlPreviewState.close_preview,
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
        open=XmlPreviewState.show_preview_dialog,
    )


# ============ Reusable Components ============


def page_heading(title: str) -> rx.Component:
    """Standard page heading."""
    return rx.heading(title, size="4", color=HEADING_PRIMARY, weight="light")


def section_heading(title: str, margin_top: str = SECTION_GAP) -> rx.Component:
    """Standard section heading with configurable top margin."""
    return rx.heading(
        title, size="3", color=HEADING_SECTION, margin_top=margin_top
    )


def no_files_warning() -> rx.Component:
    """Standard warning when no files are loaded."""
    return rx.cond(
        ~FileState.has_files,
        rx.callout(
            "Bitte zuerst unter 'Daten' Dateien laden.",
            icon="triangle-alert",
            color_scheme=COLOR_DANGER,
        ),
    )


def error_callout(error_message: rx.Var[str]) -> rx.Component:
    """Standard error display callout."""
    return rx.cond(
        error_message != "",
        rx.callout(
            error_message,
            icon="message-circle-warning",
            color_scheme=COLOR_DANGER,
        ),
    )


def make_csv_download(data: list[dict], filename: str) -> rx.event.EventSpec | None:
    """Convert list of dicts to CSV and trigger browser download.

    Call this from a state event handler, e.g.:
        return make_csv_download(self.results, "export.csv")
    """
    import csv
    import io

    if not data:
        return None

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys(), delimiter=";")
    writer.writeheader()
    writer.writerows(data)

    return rx.download(data=output.getvalue(), filename=filename)


def results_grid(
    grid_id: str,
    row_data: rx.Var,
    column_defs: list,
    csv_filename: str = "export.csv",
    row_selection_handler: rx.EventHandler | None = None,
    download_handler: rx.EventHandler | None = None,
    show_preview: bool = False,
) -> rx.Component:
    """Standard AG Grid with pagination, sorting, filtering, optional CSV download and XML preview.

    Args:
        grid_id: Unique DOM id for the grid.
        row_data: State var containing the row data.
        column_defs: Column definitions for the grid.
        csv_filename: Filename for CSV export (used as button label hint).
        row_selection_handler: Optional event handler for row selection (enables single-row mode).
            Ignored when show_preview=True (XmlPreviewState.set_selected_rows is used instead).
        download_handler: Optional event handler for CSV download button.
        show_preview: When True, enables single-row selection and adds an 'Datei öffnen' button
            that opens the XML file in a modal with the matching line highlighted.
            Requires each result row to have 'filename', 'subdir', and 'line' fields.
    """
    from pdl_lt_reflex_aggrid_wrapper import ag_grid

    # Preview takes over row selection
    if show_preview:
        row_selection_handler = XmlPreviewState.set_selected_rows

    grid_props = dict(
        id=grid_id,
        row_data=row_data,
        column_defs=column_defs,
        default_col_def={"flex": 1, "minWidth": 50},
        pagination=True,
        pagination_page_size=25,
        pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
        resizable=True,
        dom_layout="autoHeight",
        height="None",
        column_size="sizeToFit",
    )

    if row_selection_handler is not None:
        grid_props["row_selection"] = {"mode": "singleRow"}
        grid_props["on_selection_changed"] = row_selection_handler

    grid = ag_grid(**grid_props)

    if download_handler is None and not show_preview:
        return grid

    button_row: list[rx.Component] = []

    if download_handler is not None:
        button_row.append(
            rx.button(
                rx.hstack(
                    rx.icon("download", size=16),
                    rx.text("CSV herunterladen"),
                    spacing="2",
                ),
                on_click=download_handler,
                variant="outline",
                size="1",
            )
        )

    if show_preview:
        button_row.append(
            rx.button(
                rx.hstack(
                    rx.icon("file-text", size=16),
                    rx.text("Datei öffnen"),
                    spacing="2",
                ),
                on_click=XmlPreviewState.open_selected_file,
                variant="outline",
                size="1",
                disabled=XmlPreviewState.selected_rows.length() == 0,
            )
        )
        button_row.append(
            rx.text(
                "Zeile auswählen, dann 'Datei öffnen' klicken.",
                size="1",
                color="gray",
                font_style="italic",
            )
        )

    return rx.vstack(
        grid,
        rx.hstack(*button_row, spacing="2", align="center"),
        spacing="2",
        width="100%",
    )


# ============ Sidebar ============


def sidebar_subitem(text: str, url: str) -> rx.Component:
    """Single navigation sub-item (no icon, slightly indented)."""
    return rx.link(
        rx.text(text, size="2", color="var(--gray-12)"),
        href=url,
        width="100%",
        padding_left="8px",
    )


def sidebar_left() -> rx.Component:
    """Left navigation sidebar with section headings and sub-items."""
    nav_items: list[rx.Component] = []
    for i, (section, subitems) in enumerate(NAV_STRUCTURE):
        nav_items.append(
            rx.text(
                section,
                size="2",
                weight="bold",
                color=HEADING_PRIMARY,
                margin_top="0px" if i == 0 else "10px",
            )
        )
        for name, route in subitems:
            nav_items.append(sidebar_subitem(name, route))

    return rx.vstack(
        rx.heading("MENÜ", size="4", color=HEADING_PRIMARY, weight="light"),
        *nav_items,
        rx.spacer(),
        rx.text(f"Version {APP_VERSION}", size="1", color=TEXT_MUTED),
        width=SIDEBAR_WIDTH,
        min_width=["auto", "auto", "250px"],
        padding=PANEL_PADDING,
        spacing="2",
        background_color=PANEL_BG,
        border_radius=PANEL_RADIUS,
        border=PANEL_BORDER,
        display=["none", "none", "flex"],
    )


def sidebar_right() -> rx.Component:
    """Right info sidebar showing current file state and LLM status."""
    from .settings import LLMSettingsState

    return rx.vstack(
        rx.heading("ÜBERSICHT", size="4", color=HEADING_PRIMARY, weight="light"),
        rx.spacer(),
        rx.text("Daten-Modus", size="2", weight="bold"),
        rx.text(FileState.upload_mode, size="2"),
        rx.text("Daten-Verzeichnis", size="2", weight="bold"),
        rx.tooltip(
            rx.text(
                FileState.directory_path,
                size="2",
                max_width="100px",
                overflow="hidden",
                text_overflow="ellipsis",
                white_space="nowrap",
            ),
            content=FileState.directory_path,
        ),
        rx.text("Anzahl XML-Dateien", size="2", weight="bold"),
        rx.text(FileState.file_count, size="2"),
        rx.text("LLM", size="2", weight="bold"),
        rx.hstack(
            rx.cond(
                LLMSettingsState.has_active_llm,
                rx.icon("circle-check", size=14, color="green"),
                rx.icon("circle-minus", size=14, color="var(--gray-8)"),
            ),
            rx.tooltip(
                rx.text(
                    LLMSettingsState.active_model_display,
                    size="2",
                    max_width="200px",
                    overflow="hidden",
                    text_overflow="ellipsis",
                    white_space="nowrap",
                ),
                content=LLMSettingsState.active_model_display,
            ),
            spacing="2",
            align="center",
        ),
        width=SIDEBAR_WIDTH,
        min_width=["auto", "auto", "250px"],
        padding=PANEL_PADDING,
        background_color=PANEL_BG,
        border_radius=PANEL_RADIUS,
        border=PANEL_BORDER,
        display=["none", "none", "flex"],
    )


class MobileNavState(rx.State):
    """Minimal state for mobile navigation drawer."""

    is_open: bool = False

    def toggle(self) -> None:
        """Toggle drawer open/closed."""
        self.is_open = not self.is_open

    def close(self) -> None:
        """Close the drawer."""
        self.is_open = False


# def mobile_nav_drawer() -> rx.Component:
#     """Slide-out navigation drawer for small screens."""
#     nav_items: list[rx.Component] = []
#     for i, (section, subitems) in enumerate(NAV_STRUCTURE):
#         nav_items.append(
#             rx.text(
#                 section,
#                 size="2",
#                 weight="bold",
#                 color=HEADING_PRIMARY,
#                 margin_top="0px" if i == 0 else "8px",
#             )
#         )
#         for name, route in subitems:
#             nav_items.append(
#                 rx.link(
#                     rx.text(name, size="2", color="var(--gray-12)"),
#                     href=route,
#                     on_click=MobileNavState.close,
#                     width="100%",
#                     padding_left="8px",
#                 )
#             )

#     return rx.drawer.root(
#         rx.drawer.overlay(),
#         rx.drawer.content(
#             rx.vstack(
#                 rx.hstack(
#                     rx.heading("MENÜ", size="4", color=HEADING_PRIMARY, weight="light"),
#                     rx.spacer(),
#                     rx.icon_button(
#                         rx.icon("x"),
#                         variant="ghost",
#                         color=HEADING_PRIMARY,
#                         on_click=MobileNavState.close,
#                     ),
#                     width="100%",
#                     align_items="center",
#                 ),
#                 *nav_items,
#                 spacing="2",
#                 padding=PANEL_PADDING,
#                 width="100%",
#             ),
#             background_color=PANEL_BG,
#             width="280px",
#         ),
#         open=MobileNavState.is_open,
#         on_open_change=MobileNavState.set_is_open,
#         direction="left",
#     )

def mobile_nav_drawer() -> rx.Component:
    """Slide-out navigation drawer for small screens."""
    nav_items: list[rx.Component] = []
    for i, (section, subitems) in enumerate(NAV_STRUCTURE):
        nav_items.append(
            rx.text(
                section,
                size="2",
                weight="bold",
                color=HEADING_PRIMARY,
                margin_top="0px" if i == 0 else "8px",
            )
        )
        for name, route in subitems:
            nav_items.append(
                rx.link(
                    rx.text(name, size="2", color="var(--gray-12)"),
                    href=route,
                    on_click=MobileNavState.close,
                    width="100%",
                    padding_left="8px",
                )
            )
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.heading("MENÜ", size="4", color=HEADING_PRIMARY, weight="light"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(
                            rx.icon("x"),
                            variant="ghost",
                            color=HEADING_PRIMARY,
                            on_click=MobileNavState.close,
                        ),
                    ),
                    width="100%",
                    align_items="center",
                ),
                *nav_items,
                spacing="2",
                padding=PANEL_PADDING,
                width="100%",
            ),
            background_color=PANEL_BG,
            max_width="280px",
        ),
        open=MobileNavState.is_open,
        on_open_change=MobileNavState.set_is_open,
    )

# ============ Layout ============


def base_layout(content: rx.Component) -> rx.Component:
    """Main app layout with header, sidebars, and content area."""
    return rx.box(
        # Mobile drawer (rendered once, hidden until opened)
        mobile_nav_drawer(),
        # XML preview dialog (rendered once globally, controlled by XmlPreviewState)
        xml_preview_dialog(),
        # Full-width background
        rx.vstack(
            # Header
            rx.box(
                rx.hstack(
                    rx.image(
                        src="/lexoterm_logo.svg",
                        height="32px",
                        width="32px",
                        alt="LexoTerm Logo",
                    ),
                    rx.text(
                        "LexoTerm Wörterbuch-Konsistenzprüfung",
                        size="4",
                        weight="light",
                    ),
                    rx.spacer(),
                    rx.color_mode.button(),
                    # Burger menu icon (mobile only, right of dark-mode button)
                    rx.icon_button(
                        rx.icon("menu", size=20),
                        variant="ghost",
                        color="white",
                        on_click=MobileNavState.toggle,
                        display=["flex", "flex", "none"],
                    ),
                    width="100%",
                    align_items="center",
                    spacing="3",
                ),
                padding="10px",
                background_color=COLOR_ACCENT,
                color="white",
                width="100%",
                border_radius="4px",
            ),
            # Main content area
            rx.hstack(
                sidebar_left(),
                rx.box(
                    content,
                    flex="1",
                    min_width="0",
                    background_color=PANEL_BG,
                    border_radius=PANEL_RADIUS,
                    border=PANEL_BORDER,
                ),
                sidebar_right(),
                width="100%",
                align_items="start",
            ),
            max_width=MAX_PAGE_WIDTH,
            width="100%",
            margin_x="auto",
            padding=PANEL_PADDING,
            padding_top="20px",
            spacing="3",
        ),
        background_color=PAGE_BG,
        min_height="100vh",
        width="100%",
    )
