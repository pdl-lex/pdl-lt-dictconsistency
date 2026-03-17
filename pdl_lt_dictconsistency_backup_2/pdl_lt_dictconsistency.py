# Main app file. Defines the start page and registers all pages.
# Page rendering is handled by base_layout in components.py.
# Each check has its own module with page function and state.
# To add a new check: create a new module, import its page function, add it to PAGES.

import reflex as rx

from .components import base_layout, page_heading, NAV_ITEMS, HEADING_SECTION


# ============ Start Page ============


def index() -> rx.Component:
    """Landing page with app description and usage steps."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("START"),
                rx.text(
                    "Dieses Werkzeug bietet verschiedene Möglichkeiten zur Konsistenzprüfung von Wörterbüchern auf XML-Basis. Es funktioniert mit beliebigen XML-Schemata, aber am besten mit TEI-Lex 0.",
                ),
                rx.text("Schritte:"),
                rx.list(
                    rx.list.item(
                        rx.icon(
                            "arrow_up_narrow_wide",
                            color=HEADING_SECTION,
                            margin_right="10px",
                        ),
                        "Datenimport: Verzeichnis angeben oder XML-Dateien/ZIP-Archive hochladen.",
                        margin_top="0px",
                    ),
                    rx.list.item(
                        rx.icon(
                            "check_line",
                            color=HEADING_SECTION,
                            margin_right="10px",
                        ),
                        "Verschiedene Konsistenzprüfungen durchführen",
                        margin_top="20px",
                    ),
                    rx.list.item(
                        rx.icon(
                            "expand",
                            color=HEADING_SECTION,
                            margin_right="10px",
                        ),
                        "Ergebnisse exportieren und weiterverarbeiten",
                        margin_top="20px",
                    ),
                    list_style_type="none",
                ),
                spacing="5",
                justify="center",
            ),
        )
    )


# ============ Page Registry ============

# Map routes to page functions (index is registered separately)
PAGES: dict[str, callable] = {}


def _register_pages() -> None:
    """Import and register all page modules. Keeps imports local to avoid circular deps."""
    from .data import data_page
    from .validator import validator_page
    from .pathfinder import pathfinder_page
    from .tag_content import tag_content_page
    from .uniqueness import uniqueness_page

    PAGES["/data"] = data_page
    PAGES["/validator"] = validator_page
    PAGES["/pathfinder"] = pathfinder_page
    PAGES["/tag-content"] = tag_content_page
    PAGES["/uniqueness"] = uniqueness_page


_register_pages()


# ============ App ============

app = rx.App(
    theme=rx.theme(
    accent_color="gray",
    gray_color="sand",
    appearance="light",
    )
)
app.add_page(index)
for route, page_fn in PAGES.items():
    app.add_page(page_fn, route=route)
