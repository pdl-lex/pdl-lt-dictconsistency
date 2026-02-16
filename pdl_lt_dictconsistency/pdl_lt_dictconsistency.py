# This main app file only defines the structure and start page.
# Page rendering is done in base_layout, to be found in components.py
# Every further consistency checks has its own page and file, to be found in the same directory as this file.
# To add a new check/page, create a new file with the check name, add the page function and add it to the app with app.add_page().

import reflex as rx

from .components import base_layout
from .data import data_page
from .validator import validator_page
from .pathfinder import pathfinder_page
from .tag_content import tag_content_page
from .uniqueness import uniqueness_page


# ============ Pages ============


def index() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("START", size="4", color="var(--jade-12)", weight="light"),
                rx.text(
                    "Dieses Werkzeug bietet verschiedene Möglichkeiten zur Konsistenzprüfung von Wörterbüchern auf XML-Basis. Es funktioniert mit beliebigen XML-Schemata, aber am besten mit TEI-Lex 0.",
                ),
                rx.text(
                    "Schritte:",
                ),
                rx.list(
                    rx.list.item(
                        rx.icon(
                            "arrow_up_narrow_wide",
                            color="var(--jade-11)",
                            margin_right="10px",
                        ),
                        "Datenimport: Verzeichnis angeben oder XML-Dateien/ZIP-Archive hochladen.",
                        margin_top="0px",
                    ),
                    rx.list.item(
                        rx.icon(
                            "check_line", color="var(--jade-11)", margin_right="10px"
                        ),
                        "Verschiedene Konsistenzprüfungen durchführen",
                        margin_top="20px",
                    ),
                    rx.list.item(
                        rx.icon("expand", color="var(--jade-11)", margin_right="10px"),
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


# ============ App ============

app = rx.App()
app.add_page(index)
app.add_page(data_page, route="/data")
app.add_page(validator_page, route="/validator")
app.add_page(pathfinder_page, route="/pathfinder")
app.add_page(tag_content_page, route="/tag-content")
app.add_page(uniqueness_page, route="/uniqueness")
