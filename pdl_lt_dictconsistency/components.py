import reflex as rx
from .state import FileState


def sidebar_item(text: str, url: str, icon: str = "chevron-right"):
    return rx.link(
        rx.hstack(
            rx.icon(tag=icon, size=16, color="var(--jade-12)"),
            rx.text(text, color="var(--gray-12)"),
            spacing="2",
            vertical_align="bottom",
        ),
        href=url,
        width="100%",
    )


def sidebar_left() -> rx.Component:
    return rx.vstack(
        rx.heading("MENÜ", size="4", color="var(--jade-12)", weight="light"),
        # https://reflex.dev/docs/library/data-display/icon/#icons-list
        sidebar_item("Start", "/", "home"),
        sidebar_item("Daten", "/data", "files"),
        sidebar_item("XML/TL0 Validator", "/validator", "file-check"),
        sidebar_item("Tag- und Pfadsuche", "/pathfinder", "search-code"),
        sidebar_item("Inhalt / Leere Tags", "/tag-content", "text-search"),
        sidebar_item("Einmaligkeit", "/uniqueness", "shield-check"),
        rx.spacer(),
        rx.text("Version 0.1", size="1", color="gray"),
        width="250px",
        padding="20px",
        spacing="3",
        background_color=rx.color("sand", 1, False),
        border_radius="5px",
        border="1px solid var(--gray-8)",
        margin_left="20px",
        margin_bottom="40px",
        left="0",
        top="100",
    )


def sidebar_right() -> rx.Component:
    return rx.vstack(
        rx.heading("ÜBERSICHT", size="4", color="var(--jade-12)", weight="light"),
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
        width="250px",
        padding="20px",
        background_color=rx.color("sand", 1, False),
        border_radius="5px",
        border="1px solid var(--gray-8)",
        margin_right="20px",
        margin_bottom="40px",
        left="0",
        top="100",
    )


def base_layout(content: rx.Component) -> rx.Component:
    return rx.vstack(  # container for header and main content
        rx.box(  # outer box for padding
            rx.box(  # inner box for header styling
                rx.hstack(  # header content, with the color mode button
                    rx.text(
                        "LexoTerm Wörterbuch-Konsistenzprüfung",
                        size="4",
                        weight="light",
                    ),
                    rx.spacer(),  # moves the button to the right
                    rx.color_mode.button(),
                    width="100%",
                    align_items="center",
                ),
                padding="10px",
                background_color="#003835",
                color="white",
                width="100%",
                border_radius="4px",
            ),
            padding="20px",  # padding around the header box (white margin)
            padding_bottom="5px",
            width="100%",
        ),
        rx.hstack(
            sidebar_left(),
            rx.box(
                content,
                width="60%",
                background_color=rx.color("sand", 1, False),
                border_radius="5px",
                border="1px solid var(--gray-8)",
            ),
            sidebar_right(),
            width="100%",
        ),
        max_width="1400px",
        background_color="var(--jade-2)",
        padding_bottom="40px",
    )
