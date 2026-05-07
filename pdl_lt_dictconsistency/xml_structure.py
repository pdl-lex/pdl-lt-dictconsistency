import json
from pathlib import Path
from typing import TypedDict

import reflex as rx

from .state import FileState
from .components import (
    base_layout,
    page_heading,
    section_heading,
    no_files_warning,
    error_callout,
    HEADING_SECTION,
)


# ============ Row type ============


class TreeRow(TypedDict):
    id: str
    depth: int
    kind: str
    label: str
    has_children: bool
    is_collapsed: bool
    is_visible: bool
    has_content: bool
    example_loaded: bool
    example_value: str
    loading: bool
    attr_values: list[str]
    inline_attr_values: list[str]
    extra_attr_count: int
    is_search_match: bool


# ============ State ============


class StructureAnalysisState(rx.State):
    """State for XML structure analysis page."""

    # Analysis results
    tree_rows: list[TreeRow] = []
    collapsed_ids: list[str] = []     # used as set; list for JSON-serializability

    # Loading / progress
    is_analyzing: bool = False
    analysis_done: bool = False
    files_analyzed: int = 0
    error_message: str = ""

    # Backend-only vars (not synced to client)
    _total_files: int = 0
    _file_paths_json: str = ""       # JSON list of absolute file path strings

    # File filter (badge list + pagination)
    file_badges: list[dict] = []     # [{"key": "subdir/file.xml", "display": "file.xml"}]
    active_file_filter: str = ""     # "" = all files
    file_page: int = 0
    FILES_PER_PAGE: int = 20

    # Search
    search_query: str = ""

    # Modal for showing all attribute values
    modal_open: bool = False
    modal_label: str = ""
    modal_values: list[str] = []

    # ---- Computed vars ----

    @rx.var
    def total_files(self) -> int:
        return self._total_files

    @rx.var
    def total_badge_pages(self) -> int:
        n = len(self.file_badges)
        if n == 0:
            return 0
        return (n - 1) // self.FILES_PER_PAGE + 1

    @rx.var
    def paged_file_badges(self) -> list[dict]:
        start = self.file_page * self.FILES_PER_PAGE
        end = start + self.FILES_PER_PAGE
        return self.file_badges[start:end]

    @rx.var
    def has_more_badge_pages(self) -> bool:
        return self.total_badge_pages > 1

    @rx.var
    def visible_rows(self) -> list[TreeRow]:
        """Rows to display, respecting collapse state and search filter."""
        query = self.search_query.lower().strip()

        if not query:
            return [r for r in self.tree_rows if r["is_visible"]]

        # Pass 1: collect IDs of directly matching rows + all their ancestor tag IDs
        direct_match_ids: set[str] = set()
        matching_ids: set[str] = set()
        for row in self.tree_rows:
            label_match = query in row["label"].lower()
            value_match = (
                row["example_loaded"]
                and row["example_value"] not in ("", "—", "...")
                and query in row["example_value"].lower()
            )
            attr_match = any(
                query in v.lower() for v in row.get("inline_attr_values", [])
            )
            if label_match or value_match or attr_match:
                direct_match_ids.add(row["id"])
                matching_ids.add(row["id"])
                # Walk up id path to include ancestor tags
                parts = row["id"].split("/")
                for i in range(1, len(parts)):
                    ancestor_id = "/".join(parts[:i])
                    matching_ids.add(ancestor_id)

        # Pass 2: for every matched tag row, also include its direct attr/text children
        # so that content is visible alongside the matching tag name.
        matched_tag_ids = {
            r["id"] for r in self.tree_rows
            if r["id"] in matching_ids and r["kind"] == "tag"
        }
        for row in self.tree_rows:
            kind = row["kind"]
            if kind == "attr":
                at_idx = row["id"].rfind("/@")
                parent_id = row["id"][:at_idx] if at_idx != -1 else ""
            elif kind == "text_content":
                parent_id = row["id"][:-len("/#text")]
            else:
                continue
            if parent_id in matched_tag_ids:
                matching_ids.add(row["id"])

        return [
            {**r, "is_visible": True, "is_search_match": r["id"] in direct_match_ids}
            for r in self.tree_rows
            if r["id"] in matching_ids
        ]

    # ---- Event handlers ----

    @rx.event
    async def analyze_all(self):
        """Build the merged XML structure tree from all loaded files."""
        self.is_analyzing = True
        self.analysis_done = False
        self.tree_rows = []
        self.collapsed_ids = []
        self.error_message = ""
        self.files_analyzed = 0
        self.file_badges = []
        self.active_file_filter = ""
        self.file_page = 0
        self.search_query = ""
        self.modal_open = False
        yield

        file_state = await self.get_state(FileState)
        if not file_state.directory_path or not file_state.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_analyzing = False
            return

        from .xml_structure_analysis import flatten_to_rows, apply_default_collapse, _traverse

        base_path = Path(file_state.directory_path).expanduser()
        if not base_path.exists():
            self.error_message = f"Verzeichnis nicht gefunden: {base_path}"
            self.is_analyzing = False
            return
        file_paths: list[Path] = []
        badges: list[dict] = []

        for fi in file_state.xml_files_data:
            subdir = fi["subdir"]
            filename = fi["filename"]
            fp = base_path / filename if subdir == "." else base_path / subdir / filename
            file_paths.append(fp)
            key = filename if subdir == "." else f"{subdir}/{filename}"
            badges.append({"key": key, "display": filename})

        self._total_files = len(file_paths)
        self._file_paths_json = json.dumps([str(p) for p in file_paths])

        # Build analysis with progress updates
        analysis: dict = {}
        from lxml import etree
        parser = etree.XMLParser(
            dtd_validation=False,
            load_dtd=False,
            no_network=True,
            resolve_entities=False,
        )

        for i, fp in enumerate(file_paths):
            try:
                with open(fp, "rb") as f:
                    doc = etree.parse(f, parser)
                _traverse(doc.getroot(), analysis, ())
            except Exception as e:
                print(f"xml_structure: analyze_all error in {fp}: {e}")

            self.files_analyzed = i + 1
            if (i + 1) % 5 == 0:
                yield

        # Flatten and apply default collapse (depth >= 1 collapsed)
        rows = flatten_to_rows(analysis)
        rows = apply_default_collapse(rows, max_open_depth=1)

        self.tree_rows = rows
        self.file_badges = badges
        self.is_analyzing = False
        self.analysis_done = True

    @rx.event
    def toggle_node(self, node_id: str):
        """Expand or collapse a tag node."""
        from .xml_structure_analysis import recompute_visibility

        collapsed = list(self.collapsed_ids)
        if node_id in collapsed:
            collapsed.remove(node_id)
        else:
            collapsed.append(node_id)
        self.collapsed_ids = collapsed
        self.tree_rows = recompute_visibility(self.tree_rows, collapsed)

    @rx.event
    def expand_all(self):
        from .xml_structure_analysis import recompute_visibility

        self.collapsed_ids = []
        self.tree_rows = recompute_visibility(self.tree_rows, [])

    @rx.event
    def collapse_all(self):
        from .xml_structure_analysis import recompute_visibility

        all_collapsible = [
            r["id"]
            for r in self.tree_rows
            if r["kind"] == "tag" and r["has_children"]
        ]
        self.collapsed_ids = all_collapsible
        self.tree_rows = recompute_visibility(self.tree_rows, all_collapsible)

    @rx.event
    async def load_example(self, row_id: str):
        """Fetch a text content example for the given #text row. On reload, finds a different value."""
        # Get current value to exclude (for reload → different example)
        current_value = ""
        for r in self.tree_rows:
            if r["id"] == row_id:
                current_value = r.get("example_value", "")
                if current_value == "—":
                    current_value = ""
                break

        # Mark as loading
        rows = list(self.tree_rows)
        for i, r in enumerate(rows):
            if r["id"] == row_id:
                rows[i] = {**r, "loading": True}
                break
        self.tree_rows = rows
        yield

        file_paths = [Path(p) for p in json.loads(self._file_paths_json)]

        from .xml_structure_analysis import find_example
        value = find_example(
            row_id,
            file_paths,
            self.active_file_filter,
            exclude_value=current_value,
        )

        # If no different example found, keep the current one (or mark as not found)
        if not value and current_value:
            value = current_value

        rows = list(self.tree_rows)
        for i, r in enumerate(rows):
            if r["id"] == row_id:
                rows[i] = {
                    **r,
                    "loading": False,
                    "example_loaded": True,
                    "example_value": value if value else "—",
                    "has_content": bool(value),
                }
                break
        self.tree_rows = rows

    @rx.event
    def open_attr_modal(self, row_id: str):
        """Open the modal showing all collected attribute values for a row."""
        for r in self.tree_rows:
            if r["id"] == row_id:
                self.modal_label = r["label"]
                self.modal_values = r.get("attr_values", [])
                break
        self.modal_open = True

    @rx.event
    def close_attr_modal(self):
        self.modal_open = False

    @rx.event
    def set_modal_open(self, value: bool):
        self.modal_open = value

    @rx.event
    async def set_file_filter(self, file_key: str):
        """Switch file filter: populate tree from selected file, or revert to all-files view."""
        self.active_file_filter = file_key
        yield

        from .xml_structure_analysis import load_examples_from_file, restore_all_files_examples

        if not file_key:
            self.tree_rows = restore_all_files_examples(self.tree_rows)
            return

        file_paths = [Path(p) for p in json.loads(self._file_paths_json)]
        matching = [p for p in file_paths if str(p).endswith(file_key)]
        if not matching:
            return

        self.tree_rows = load_examples_from_file(matching[0], self.tree_rows)

    @rx.event
    def set_search(self, query: str):
        self.search_query = query

    @rx.event
    def prev_badge_page(self):
        if self.file_page > 0:
            self.file_page -= 1

    @rx.event
    def next_badge_page(self):
        if self.file_page < self.total_badge_pages - 1:
            self.file_page += 1


# ============ UI Components ============


def _structure_controls() -> rx.Component:
    return rx.hstack(
        rx.button(
            rx.cond(
                StructureAnalysisState.is_analyzing,
                rx.hstack(rx.spinner(size="3"), rx.text("Analysiere..."), spacing="2"),
                rx.cond(
                    StructureAnalysisState.analysis_done,
                    rx.text("Neu analysieren"),
                    rx.text("Strukturanalyse starten"),
                ),
            ),
            on_click=StructureAnalysisState.analyze_all,
            variant="solid",
            disabled=StructureAnalysisState.is_analyzing | ~FileState.has_files,
        ),
        error_callout(StructureAnalysisState.error_message),
        spacing="3",
        align="center",
        width="100%",
    )


def _analysis_progress() -> rx.Component:
    return rx.hstack(
        rx.spinner(),
        rx.text(
            "Analysiere ",
            StructureAnalysisState.files_analyzed,
            " / ",
            StructureAnalysisState.total_files,
            " Dateien...",
            color=HEADING_SECTION,
        ),
        spacing="2",
        align="center",
    )


def _file_filter_section() -> rx.Component:
    return rx.cond(
        StructureAnalysisState.file_badges.length() > 0,
        rx.vstack(
            section_heading("Datei-Filter", margin_top="0px"),
            rx.box(
                rx.badge(
                    "Alle Dateien",
                    color_scheme=rx.cond(
                        StructureAnalysisState.active_file_filter == "",
                        "blue",
                        "gray",
                    ),
                    variant=rx.cond(
                        StructureAnalysisState.active_file_filter == "",
                        "solid",
                        "soft",
                    ),
                    cursor="pointer",
                    on_click=StructureAnalysisState.set_file_filter(""),
                    margin="2px",
                ),
                rx.foreach(
                    StructureAnalysisState.paged_file_badges,
                    lambda badge: rx.badge(
                        badge["display"],
                        color_scheme=rx.cond(
                            StructureAnalysisState.active_file_filter == badge["key"],
                            "blue",
                            "gray",
                        ),
                        variant=rx.cond(
                            StructureAnalysisState.active_file_filter == badge["key"],
                            "solid",
                            "soft",
                        ),
                        cursor="pointer",
                        on_click=StructureAnalysisState.set_file_filter(badge["key"]),
                        margin="2px",
                    ),
                ),
                display="flex",
                flex_wrap="wrap",
                gap="4px",
                padding="10px",
                border="1px solid var(--gray-6)",
                border_radius="4px",
            ),
            rx.cond(
                StructureAnalysisState.has_more_badge_pages,
                rx.hstack(
                    rx.button(
                        rx.icon("chevron-left", size=16),
                        on_click=StructureAnalysisState.prev_badge_page,
                        variant="ghost",
                        size="1",
                        disabled=StructureAnalysisState.file_page == 0,
                    ),
                    rx.text(
                        StructureAnalysisState.file_page + 1,
                        " / ",
                        StructureAnalysisState.total_badge_pages,
                        size="1",
                        color="gray",
                    ),
                    rx.button(
                        rx.icon("chevron-right", size=16),
                        on_click=StructureAnalysisState.next_badge_page,
                        variant="ghost",
                        size="1",
                        disabled=StructureAnalysisState.file_page >= StructureAnalysisState.total_badge_pages - 1,
                    ),
                    spacing="2",
                    align="center",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def _search_section() -> rx.Component:
    return rx.hstack(
        rx.icon("search", size=16, color="gray"),
        rx.input(
            value=StructureAnalysisState.search_query,
            placeholder="Tags oder Attribute filtern...",
            on_change=StructureAnalysisState.set_search,
            width="300px",
        ),
        rx.cond(
            StructureAnalysisState.search_query != "",
            rx.icon_button(
                rx.icon("x", size=14),
                on_click=StructureAnalysisState.set_search(""),
                variant="ghost",
                size="1",
            ),
        ),
        spacing="2",
        align="center",
    )


def _tree_toolbar() -> rx.Component:
    return rx.hstack(
        rx.button(
            rx.hstack(
                rx.icon("chevrons-down-up", size=14),
                rx.text("Alles einklappen"),
                spacing="1",
            ),
            on_click=StructureAnalysisState.collapse_all,
            variant="outline",
            size="1",
        ),
        rx.button(
            rx.hstack(
                rx.icon("chevrons-up-down", size=14),
                rx.text("Alles ausklappen"),
                spacing="1",
            ),
            on_click=StructureAnalysisState.expand_all,
            variant="outline",
            size="1",
        ),
        spacing="2",
    )


def _attr_example_area(row: dict) -> rx.Component:
    """Attribute values shown directly as badges (pre-loaded from analysis)."""
    return rx.hstack(
        rx.text(
            "=",
            color="var(--gray-7)",
            font_family="monospace",
            font_size="12px",
        ),
        rx.cond(
            row["has_content"],
            rx.hstack(
                rx.foreach(
                    row["inline_attr_values"],
                    lambda v: rx.badge(
                        v,
                        variant="soft",
                        color_scheme="blue",
                        size="1",
                        font_family="monospace",
                    ),
                ),
                rx.cond(
                    row["extra_attr_count"] > 0,
                    rx.badge(
                        "+",
                        row["extra_attr_count"],
                        " weitere",
                        variant="outline",
                        color_scheme="gray",
                        size="1",
                        cursor="pointer",
                        on_click=StructureAnalysisState.open_attr_modal(row["id"]),
                        title="Alle Werte anzeigen",
                    ),
                ),
                flex_wrap="wrap",
                spacing="1",
                align="center",
            ),
            rx.text(
                "...",
                color="var(--gray-7)",
                font_size="12px",
                font_family="monospace",
            ),
        ),
        spacing="2",
        align="center",
        flex_shrink="0",
    )


def _text_example_area(row: dict) -> rx.Component:
    """Text content shown lazily via 'Beispiel' badge; reload finds a different value."""
    return rx.hstack(
        rx.text(
            "=",
            color="var(--gray-7)",
            font_family="monospace",
            font_size="12px",
        ),
        rx.cond(
            row["loading"],
            rx.spinner(size="1"),
            rx.cond(
                row["example_loaded"],
                # Show loaded value + reload icon
                rx.hstack(
                    rx.text(
                        row["example_value"],
                        font_family="monospace",
                        font_size="12px",
                        color="var(--gray-12)",
                        max_width="350px",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                    ),
                    rx.icon_button(
                        rx.icon("refresh-cw", size=10),
                        on_click=StructureAnalysisState.load_example(row["id"]),
                        variant="ghost",
                        size="1",
                        color="var(--gray-9)",
                        title="Anderes Beispiel laden",
                    ),
                    spacing="1",
                    align="center",
                ),
                # Not yet loaded
                rx.cond(
                    row["has_content"],
                    rx.badge(
                        "Beispiel",
                        cursor="pointer",
                        variant="soft",
                        color_scheme="gray",
                        size="1",
                        on_click=StructureAnalysisState.load_example(row["id"]),
                    ),
                    rx.text(
                        "...",
                        color="var(--gray-7)",
                        font_size="12px",
                        font_family="monospace",
                    ),
                ),
            ),
        ),
        spacing="2",
        align="center",
        flex_shrink="0",
    )


def _tree_row(row: dict) -> rx.Component:
    """Render a single tree row with indentation, label and optional example area."""

    # Collapse toggle (only for tag rows with children)
    toggle = rx.cond(
        (row["kind"] == "tag") & row["has_children"],
        rx.icon_button(
            rx.cond(
                row["is_collapsed"],
                rx.icon("chevron-right", size=12),
                rx.icon("chevron-down", size=12),
            ),
            on_click=StructureAnalysisState.toggle_node(row["id"]),
            variant="ghost",
            size="1",
            color="var(--gray-10)",
            flex_shrink="0",
        ),
        rx.box(width="22px", flex_shrink="0"),
    )

    # Label, color-coded by kind
    label = rx.text(
        row["label"],
        font_family="monospace",
        font_size="13px",
        color=rx.cond(
            row["kind"] == "tag",
            "var(--accent-11)",
            rx.cond(
                row["kind"] == "attr",
                "var(--green-11)",
                "var(--gray-10)",
            ),
        ),
        font_weight=rx.cond(row["kind"] == "tag", "bold", "normal"),
        white_space="nowrap",
    )

    # Example area: attr rows show badges, text_content rows use lazy loading
    example_area = rx.cond(
        row["kind"] == "attr",
        _attr_example_area(row),
        rx.cond(
            row["kind"] == "text_content",
            _text_example_area(row),
            rx.fragment(),
        ),
    )

    indent_px = row["depth"].to(int) * 20

    return rx.box(
        rx.hstack(
            toggle,
            label,
            example_area,
            spacing="1",
            align="center",
            padding_y="2px",
            overflow="hidden",
        ),
        padding_left=indent_px.to_string() + "px",
        width="100%",
        background_color=rx.cond(
            row["is_search_match"],
            "var(--yellow-3)",
            "transparent",
        ),
        border_left=rx.cond(
            row["is_search_match"],
            "2px solid var(--yellow-9)",
            "2px solid transparent",
        ),
        _hover={"background_color": "var(--gray-2)"},
        border_radius="3px",
    )


def _tree_display() -> rx.Component:
    return rx.box(
        rx.cond(
            StructureAnalysisState.visible_rows.length() > 0,
            rx.foreach(
                StructureAnalysisState.visible_rows,
                _tree_row,
            ),
            rx.text(
                "Keine passenden Einträge gefunden.",
                color="var(--gray-9)",
                font_size="13px",
                padding="10px",
            ),
        ),
        width="100%",
        overflow_x="auto",
        border="1px solid var(--gray-6)",
        border_radius="4px",
        padding="10px",
        background_color="var(--gray-1)",
    )


def _attr_values_modal() -> rx.Component:
    """Modal showing all collected attribute values for an attribute row."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("tag", size=16, color="var(--green-11)"),
                    rx.text(
                        StructureAnalysisState.modal_label,
                        font_family="monospace",
                        color="var(--green-11)",
                    ),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.dialog.description(
                "Alle gefundenen Attributwerte in den geladenen Dateien:",
                size="2",
                color="var(--gray-10)",
            ),
            rx.box(
                rx.foreach(
                    StructureAnalysisState.modal_values,
                    lambda v: rx.badge(
                        v,
                        variant="soft",
                        color_scheme="blue",
                        size="2",
                        font_family="monospace",
                        margin="3px",
                    ),
                ),
                display="flex",
                flex_wrap="wrap",
                gap="4px",
                padding="12px",
                border="1px solid var(--gray-5)",
                border_radius="6px",
                background_color="var(--gray-1)",
                min_height="60px",
                margin_y="12px",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        "Schließen",
                        on_click=StructureAnalysisState.close_attr_modal,
                        variant="soft",
                        color_scheme="gray",
                    ),
                ),
                justify="end",
            ),
            max_width="600px",
        ),
        open=StructureAnalysisState.modal_open,
        on_open_change=StructureAnalysisState.set_modal_open,
    )


# ============ Page ============


def xml_structure_page() -> rx.Component:
    """Page layout for XML structure analysis."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("STRUKTURANALYSE"),
                no_files_warning(),
                rx.text(
                    "Zeigt die vollständige Tag- und Attributstruktur aller geladenen XML-Dateien als einheitlichen Baum. "
                    "Attributwerte werden direkt angezeigt; Textinhalte können per 'Beispiel' geladen werden."
                ),
                _structure_controls(),
                rx.cond(
                    StructureAnalysisState.is_analyzing,
                    _analysis_progress(),
                ),
                rx.cond(
                    StructureAnalysisState.analysis_done,
                    rx.vstack(
                        _file_filter_section(),
                        _search_section(),
                        _tree_toolbar(),
                        _tree_display(),
                        spacing="3",
                        width="100%",
                    ),
                ),
                rx.spacer(height="30px"),
                spacing="4",
                width="100%",
            ),
            _attr_values_modal(),
        )
    )
