import reflex as rx
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

NAV_ITEMS: list[tuple[str, str, str]] = [
    ("Start", "/", "home"),
    ("Daten", "/data", "files"),
    ("XML/TL0 Validator", "/validator", "file-check"),
    ("Tag- und Pfadsuche", "/pathfinder", "search-code"),
    ("Inhalt / Leere Tags", "/tag-content", "text-search"),
    ("Einmaligkeit", "/uniqueness", "shield-check"),
    ("LLM-Anfrage", "/llm-query", "bot-message-square"),
]

# Settings navigation (displayed separately at bottom of sidebar)
SETTINGS_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("Einstellungen", "/settings", "settings"),
]


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
) -> rx.Component:
    """Standard AG Grid with pagination, sorting, filtering, and optional CSV download.

    Args:
        grid_id: Unique DOM id for the grid.
        row_data: State var containing the row data.
        column_defs: Column definitions for the grid.
        csv_filename: Filename for CSV export (used as button label hint).
        row_selection_handler: Optional event handler for row selection (enables single-row mode).
        download_handler: Optional event handler for CSV download button.
    """
    from pdl_lt_reflex_aggrid_wrapper import ag_grid

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

    if download_handler is None:
        return grid

    return rx.vstack(
        grid,
        rx.button(
            rx.hstack(
                rx.icon("download", size=16),
                rx.text("CSV herunterladen"),
                spacing="2",
            ),
            on_click=download_handler,
            variant="outline",
            size="1",
        ),
        spacing="2",
        width="100%",
    )


# ============ Sidebar ============


def sidebar_item(text: str, url: str, icon: str = "chevron-right") -> rx.Component:
    """Single navigation item in the sidebar."""
    return rx.link(
        rx.hstack(
            rx.icon(tag=icon, size=16, color=HEADING_PRIMARY),
            rx.text(text, color="var(--gray-12)"),
            spacing="2",
            vertical_align="bottom",
        ),
        href=url,
        width="100%",
    )


def sidebar_left() -> rx.Component:
    """Left navigation sidebar, built from NAV_ITEMS with settings separated at bottom."""
    return rx.vstack(
        rx.heading("MENÜ", size="4", color=HEADING_PRIMARY, weight="light"),
        *[sidebar_item(name, route, icon) for name, route, icon in NAV_ITEMS],
        rx.spacer(),
        rx.divider(color="var(--gray-6)"),
        *[sidebar_item(name, route, icon) for name, route, icon in SETTINGS_NAV_ITEMS],
        rx.text(f"Version {APP_VERSION}", size="1", color=TEXT_MUTED),
        width=SIDEBAR_WIDTH,
        min_width=["auto", "auto", "250px"],
        padding=PANEL_PADDING,
        spacing="3",
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
        rx.divider(color="var(--gray-6)"),
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
                    max_width="100px",
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


def mobile_nav_drawer() -> rx.Component:
    """Slide-out navigation drawer for small screens."""
    return rx.drawer.root(
        rx.drawer.overlay(),
        rx.drawer.content(
            rx.vstack(
                rx.hstack(
                    rx.heading("MENÜ", size="4", color=HEADING_PRIMARY, weight="light"),
                    rx.spacer(),
                    rx.icon_button(
                        rx.icon("x"),
                        variant="ghost",
                        color=HEADING_PRIMARY,
                        on_click=MobileNavState.close,
                    ),
                    width="100%",
                    align_items="center",
                ),
                *[
                    rx.link(
                        rx.hstack(
                            rx.icon(tag=icon, size=16, color=HEADING_PRIMARY),
                            rx.text(name, color="var(--gray-12)"),
                            spacing="2",
                        ),
                        href=route,
                        on_click=MobileNavState.close,
                        width="100%",
                    )
                    for name, route, icon in NAV_ITEMS
                ],
                rx.divider(color="var(--gray-6)"),
                *[
                    rx.link(
                        rx.hstack(
                            rx.icon(tag=icon, size=16, color=HEADING_PRIMARY),
                            rx.text(name, color="var(--gray-12)"),
                            spacing="2",
                        ),
                        href=route,
                        on_click=MobileNavState.close,
                        width="100%",
                    )
                    for name, route, icon in SETTINGS_NAV_ITEMS
                ],
                spacing="3",
                padding=PANEL_PADDING,
                width="100%",
            ),
            background_color=PANEL_BG,
            width="280px",
        ),
        open=MobileNavState.is_open,
        on_open_change=MobileNavState.set_is_open,
        direction="left",
    )


# ============ Layout ============


def base_layout(content: rx.Component) -> rx.Component:
    """Main app layout with header, sidebars, and content area."""
    return rx.box(
        # Mobile drawer (rendered once, hidden until opened)
        mobile_nav_drawer(),
        # Full-width background
        rx.vstack(
            # Header
            rx.box(
                rx.hstack(
                    # Burger menu icon (mobile only)
                    rx.icon_button(
                        rx.icon("menu", size=20),
                        variant="ghost",
                        color="white",
                        on_click=MobileNavState.toggle,
                        display=["flex", "flex", "none"],
                    ),
                    rx.text(
                        "LexoTerm Wörterbuch-Konsistenzprüfung",
                        size="4",
                        weight="light",
                    ),
                    rx.spacer(),
                    rx.color_mode.button(),
                    width="100%",
                    align_items="center",
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
