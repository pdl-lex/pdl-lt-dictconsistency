# Main app file. Defines the start page and registers all pages.
# Page rendering is handled by base_layout in components.py.
# Each check has its own module with page function and state.
# To add a new check: create a new module, import its page function, add it to PAGES.

import reflex as rx

from .components import base_layout, page_container, page_heading


# ============ Start Page ============


def index() -> rx.Component:
    """Landing page with app description and usage steps."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("START"),
                rx.text(
                    "Dieses Werkzeug bietet verschiedene Möglichkeiten zur Konsistenzprüfung von Wörterbüchern auf XML-Basis. Es funktioniert mit beliebigen XML-Schemata, aber am besten mit TEI-Lex 0.",
                ),


                rx.card(
                    rx.data_list.root(
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Daten",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Daten aus Verzeichnis laden, XML/ZIP-Dateien hochladen, oder ausgewählte Wörterbücher laden."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "XML/TL0 Validator",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Prüfung auf XML-Wohlgeformtheit und TEI-Lex 0 Konformität."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Strukturanalyse",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Analysiert den XML-Baum aller hochgeladenen Dateien, zeigt Attribute und Werte an, und erlaubt die Projektion einzelner Dateien in den gesamten Baum."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Tag- und Pfadsuche",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Suche nach bestimmten Tags oder Pfaden im XML-Baum, inklusive Wildcards."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Inhalt / Leere Tags",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Suche nach Textinhalten, leeren Tags und Umbrüchen."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Einmaligkeit",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Prüft, ob Tags oder Attribute mehrfach vorkommen."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Einmaligkeit",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Analyisert Verschachtelung und Verschachtelungstiefe."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "Anzahl und Länge",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Bedeutungsangaben können hinsichtlich ihrer Anzahl, sowie minimaler und maximaler Länge ausgewertet werden."

                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label(
                                rx.badge(
                                    "LLM-Anfrage",
                                    variant="soft",
                                )
                                ),
                            rx.data_list.value("Einzelne oder mehrere XML-Dateien können an ein lokales oder Cloud-LLM gesendet werden. Per Chat-Funktion können Fragen gestellt und Analysen vorgenommen werden."

                            ),
                        ),
                    ),
                ),

            ),
        )
    )


# ============ Page Registry ============

# Map routes to (page_function, page_title)
PAGES: dict[str, tuple[callable, str]] = {}


def _register_pages() -> None:
    """Import and register all page modules. Keeps imports local to avoid circular deps."""
    from .data import data_page
    from .validator import validator_page
    from .pathfinder import pathfinder_page
    from .tag_content import tag_content_page
    from .uniqueness import uniqueness_page
    from .nesting import nesting_page
    from .senses_stats import senses_stats_page
    from .settings import settings_page
    from .llm_query import llm_query_page
    from .ocr_query import ocr_query_page
    from .xml_structure import xml_structure_page
    from .spelling import spelling_page

    PAGES["/data"] = (data_page, "Daten")
    PAGES["/validator"] = (validator_page, "XML-Validator")
    PAGES["/pathfinder"] = (pathfinder_page, "Tag- und Pfadsuche")
    PAGES["/tag-content"] = (tag_content_page, "Inhalt / Leere Tags")
    PAGES["/uniqueness"] = (uniqueness_page, "Einmaligkeit")
    PAGES["/nesting"] = (nesting_page, "Verschachtelung")
    PAGES["/senses-stats"] = (senses_stats_page, "Anzahl und Länge")
    PAGES["/settings"] = (settings_page, "LLM-Einstellungen")
    PAGES["/llm-query"] = (llm_query_page, "LLM-Anfrage")
    PAGES["/ocr-query"] = (ocr_query_page, "Texterkennung (OCR)")
    PAGES["/xml-structure"] = (xml_structure_page, "Strukturanalyse")
    PAGES["/spelling"] = (spelling_page, "Rechtschreibung")


_register_pages()

_APP_TITLE = "LT Wörterbuch-Konsistenzprüfung"

# ============ App ============

app = rx.App(
    theme=rx.theme(
    accent_color="jade",
    # gray_color="sand",
    has_background=True,
    radius="large",
    appearance="light",
    )
)
app.add_page(index, title=f"Start | {_APP_TITLE}")
for route, (page_fn, page_title) in PAGES.items():
    app.add_page(page_fn, route=route, title=f"{page_title} | {_APP_TITLE}")
