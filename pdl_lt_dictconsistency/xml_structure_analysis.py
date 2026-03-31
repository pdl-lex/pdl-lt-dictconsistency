# Pure Python logic for XML structure analysis.
# No Reflex imports – can be used and tested independently.

from pathlib import Path
from lxml import etree

MAX_EXAMPLES = 5          # max text content examples per tag
MAX_ATTR_EXAMPLES = 20    # max attribute value examples per attribute
MAX_TEXT_LEN = 120        # characters before truncation
INLINE_ATTR_VALUES = 5    # how many attr values shown inline; rest shown in modal


# ============ Tree Building ============

def build_analysis(file_paths: list[Path]) -> dict:
    """
    Parse all files and merge their XML structures into a single analysis dict.

    Key:   "|"-joined path of local tag names, e.g. "TEI|text|body|entry"
    Value: {
        "tag":             str,           local tag name
        "depth":           int,           nesting depth (0 = root)
        "children_order":  list[str],     child tag local-names in first-seen order
        "attrs":           dict[str, list[str]],  attr local-name -> example values
        "text_examples":   list[str],     sample text content values
        "has_text":        bool,          whether any file has text content here
    }
    """
    analysis: dict[str, dict] = {}
    parser = etree.XMLParser(
        dtd_validation=False,
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
    )

    for file_path in file_paths:
        try:
            with open(file_path, "rb") as f:
                doc = etree.parse(f, parser)
            _traverse(doc.getroot(), analysis, ())
        except Exception as e:
            print(f"xml_structure_analysis: error in {file_path}: {e}")
            continue

    return analysis


def _traverse(elem, analysis: dict, parent_path: tuple) -> None:
    """Recursively visit element and merge into analysis dict."""
    if not isinstance(elem.tag, str):
        # Skip comments, processing instructions, etc.
        return

    try:
        tag = etree.QName(elem).localname
    except Exception:
        tag = str(elem.tag)

    current_path = parent_path + (tag,)
    path_key = "|".join(current_path)

    if path_key not in analysis:
        analysis[path_key] = {
            "tag": tag,
            "depth": len(parent_path),
            "children_order": [],
            "attrs": {},
            "text_examples": [],
            "has_text": False,
        }

    node = analysis[path_key]

    # Register this tag as a child of its parent
    if parent_path:
        parent_key = "|".join(parent_path)
        if parent_key in analysis:
            parent_node = analysis[parent_key]
            if tag not in parent_node["children_order"]:
                parent_node["children_order"].append(tag)

    # Collect direct text content
    text = (elem.text or "").strip()
    if text:
        node["has_text"] = True
        if len(node["text_examples"]) < MAX_EXAMPLES:
            truncated = text[:MAX_TEXT_LEN]
            if truncated not in node["text_examples"]:
                node["text_examples"].append(truncated)

    # Collect attributes (up to MAX_ATTR_EXAMPLES distinct values each)
    for attr_qname, attr_val in elem.attrib.items():
        try:
            attr_local = etree.QName(attr_qname).localname
        except Exception:
            attr_local = str(attr_qname)

        if attr_local not in node["attrs"]:
            node["attrs"][attr_local] = []
        if len(node["attrs"][attr_local]) < MAX_ATTR_EXAMPLES:
            if attr_val not in node["attrs"][attr_local]:
                node["attrs"][attr_local].append(attr_val)

    # Recurse into children
    for child in elem:
        _traverse(child, analysis, current_path)


# ============ Flattening ============

def flatten_to_rows(analysis: dict) -> list[dict]:
    """
    Convert analysis dict to a flat ordered list of display rows (DFS order).

    Row order within a tag node:
      1. The tag row itself
      2. Attribute rows (alphabetically sorted)
      3. #text row (if has_text)
      4. Child tag rows (in first-seen order)

    All rows start visible and expanded (is_visible=True, is_collapsed=False).
    Callers should apply apply_default_collapse() afterwards for the default view.
    """
    rows: list[dict] = []

    # Find root nodes (depth == 0), sorted by key for stability
    root_keys = sorted(k for k, v in analysis.items() if v["depth"] == 0)

    for root_key in root_keys:
        _flatten_recursive(root_key, analysis, rows, visible=True)

    return rows


def _flatten_recursive(
    path_key: str,
    analysis: dict,
    rows: list[dict],
    visible: bool,
) -> None:
    node = analysis[path_key]
    tag = node["tag"]
    depth = node["depth"]

    has_children = (
        bool(node["children_order"])
        or node["has_text"]
        or bool(node["attrs"])
    )

    tag_row_id = path_key.replace("|", "/")

    # Tag rows have no attr value fields (set to empty for consistent dict shape)
    rows.append({
        "id": tag_row_id,
        "depth": depth,
        "kind": "tag",
        "label": tag,
        "has_children": has_children,
        "is_collapsed": False,
        "is_visible": visible,
        "has_content": False,
        "example_loaded": False,
        "example_value": "",
        "loading": False,
        "attr_values": [],
        "inline_attr_values": [],
        "extra_attr_count": 0,
        "is_search_match": False,
    })

    # Children are visible when parent is not collapsed (starts expanded)
    children_visible = visible

    # Attribute rows (alphabetical) – values pre-loaded from analysis
    for attr_name in sorted(node["attrs"].keys()):
        attr_id = f"{tag_row_id}/@{attr_name}"
        all_values = node["attrs"][attr_name]
        inline = all_values[:INLINE_ATTR_VALUES]
        extra_count = max(0, len(all_values) - INLINE_ATTR_VALUES)
        rows.append({
            "id": attr_id,
            "depth": depth + 1,
            "kind": "attr",
            "label": f"@{attr_name}",
            "has_children": False,
            "is_collapsed": False,
            "is_visible": children_visible,
            "has_content": bool(all_values),
            "example_loaded": False,
            "example_value": "",
            "loading": False,
            "attr_values": all_values,
            "inline_attr_values": inline,
            "extra_attr_count": extra_count,
            "is_search_match": False,
        })

    # Text content row (lazy-loaded on demand)
    if node["has_text"]:
        text_id = f"{tag_row_id}/#text"
        rows.append({
            "id": text_id,
            "depth": depth + 1,
            "kind": "text_content",
            "label": "#text",
            "has_children": False,
            "is_collapsed": False,
            "is_visible": children_visible,
            "has_content": True,
            "example_loaded": False,
            "example_value": "",
            "loading": False,
            "attr_values": [],
            "inline_attr_values": [],
            "extra_attr_count": 0,
            "is_search_match": False,
        })

    # Child tag rows (first-seen order)
    for child_tag in node["children_order"]:
        child_key = f"{path_key}|{child_tag}"
        if child_key in analysis:
            _flatten_recursive(child_key, analysis, rows, visible=children_visible)


def apply_default_collapse(rows: list[dict], max_open_depth: int = 1) -> list[dict]:
    """
    Collapse all tag rows whose depth >= max_open_depth and recompute visibility.
    Returns updated row list.
    """
    collapsed_ids = [
        r["id"]
        for r in rows
        if r["kind"] == "tag" and r["has_children"] and r["depth"] >= max_open_depth
    ]
    return recompute_visibility(rows, collapsed_ids)


def recompute_visibility(rows: list[dict], collapsed_ids: list[str]) -> list[dict]:
    """
    Walk rows in order, tracking which ancestor tag rows are collapsed.
    A row is visible iff no ancestor tag row is collapsed.

    Uses a stack of (depth, id, is_collapsed) tuples representing the
    ancestor chain for the current position in the DFS.
    """
    collapsed_set = set(collapsed_ids)
    result: list[dict] = []
    # Stack entries: (depth, row_id, is_collapsed)
    stack: list[tuple[int, str, bool]] = []

    for row in rows:
        d = row["depth"]
        kind = row["kind"]

        # Trim stack to ancestors: keep entries with depth < d
        while stack and stack[-1][0] >= d:
            stack.pop()

        # Visible if no ancestor in stack is collapsed
        is_visible = all(not is_col for (_, _, is_col) in stack)

        is_collapsed = (row["id"] in collapsed_set) if kind == "tag" else False

        result.append({**row, "is_visible": is_visible, "is_collapsed": is_collapsed})

        # Push this tag row for its children
        if kind == "tag":
            stack.append((d, row["id"], is_collapsed))

    return result


# ============ File-filter helpers ============

def load_examples_from_file(file_path: Path, rows: list[dict]) -> list[dict]:
    """
    Parse a single file and populate each row with values found in it.

    - attr rows: inline_attr_values and extra_attr_count reflect this file only.
      has_content=False (and inline_attr_values=[]) when the attr is absent.
    - text_content rows: example_value set to first text found, or "..." if absent.
    - tag rows: unchanged.

    attr_values (the full all-files set) is intentionally left intact so the
    modal still shows the complete known value space.
    """
    parser = etree.XMLParser(
        dtd_validation=False,
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
    )
    file_analysis: dict = {}
    try:
        with open(file_path, "rb") as f:
            doc = etree.parse(f, parser)
        _traverse(doc.getroot(), file_analysis, ())
    except Exception as e:
        print(f"xml_structure_analysis: load_examples_from_file error in {file_path}: {e}")
        return rows

    result: list[dict] = []

    for row in rows:
        kind = row["kind"]

        if kind == "tag":
            result.append(row)
            continue

        if kind == "attr":
            row_id = row["id"]
            at_idx = row_id.rfind("/@")
            if at_idx == -1:
                result.append(row)
                continue
            tag_path_str = row_id[:at_idx]
            attr_name = row_id[at_idx + 2:]
            path_key = tag_path_str.replace("/", "|")

            file_node = file_analysis.get(path_key)
            if file_node and attr_name in file_node["attrs"]:
                file_vals = file_node["attrs"][attr_name]
                inline = file_vals[:INLINE_ATTR_VALUES]
                extra = max(0, len(file_vals) - INLINE_ATTR_VALUES)
                result.append({
                    **row,
                    "inline_attr_values": inline,
                    "extra_attr_count": extra,
                    "has_content": bool(file_vals),
                })
            else:
                result.append({
                    **row,
                    "inline_attr_values": [],
                    "extra_attr_count": 0,
                    "has_content": False,
                })
            continue

        if kind == "text_content":
            row_id = row["id"]
            tag_path_str = row_id[:-len("/#text")]
            path_key = tag_path_str.replace("/", "|")

            file_node = file_analysis.get(path_key)
            if file_node and file_node["has_text"] and file_node["text_examples"]:
                result.append({
                    **row,
                    "example_loaded": True,
                    "example_value": file_node["text_examples"][0],
                    "has_content": True,
                    "loading": False,
                })
            else:
                result.append({
                    **row,
                    "example_loaded": True,
                    "example_value": "...",
                    "has_content": False,
                    "loading": False,
                })
            continue

        result.append(row)

    return result


def restore_all_files_examples(rows: list[dict]) -> list[dict]:
    """
    Revert rows to the all-files view:
    - attr rows: restore inline_attr_values from the baked-in attr_values.
    - text_content rows: clear loaded example so the user can re-request one.
    """
    result: list[dict] = []
    for row in rows:
        if row["kind"] == "attr":
            all_vals = row["attr_values"]
            result.append({
                **row,
                "inline_attr_values": all_vals[:INLINE_ATTR_VALUES],
                "extra_attr_count": max(0, len(all_vals) - INLINE_ATTR_VALUES),
                "has_content": bool(all_vals),
            })
        elif row["kind"] == "text_content":
            result.append({
                **row,
                "example_loaded": False,
                "example_value": "",
                "has_content": True,
                "loading": False,
            })
        else:
            result.append(row)
    return result


# ============ Example Loading (text content only) ============

def find_example(
    row_id: str,
    file_paths: list[Path],
    file_filter: str = "",
    exclude_value: str = "",
) -> str:
    """
    Search XML files for a text content example for the given #text row_id.

    row_id format: "tag1/tag2/tag3/#text"

    file_filter:    "" = all files; otherwise matched as suffix of str(file_path).
    exclude_value:  skip this value (used for reload to find a different example).

    Returns the first found value != exclude_value (truncated to MAX_TEXT_LEN), or "".
    """
    parts = row_id.split("/")
    if not parts:
        return ""

    last = parts[-1]
    if last != "#text":
        return ""

    tag_path = parts[:-1]
    if not tag_path:
        return ""

    # Build XPath using local-name() to avoid namespace issues
    xpath_parts = [f"*[local-name()='{t}']" for t in tag_path]
    xpath = "//" + "/".join(xpath_parts)

    # Filter files
    if file_filter:
        search_paths = [p for p in file_paths if str(p).endswith(file_filter)]
    else:
        search_paths = file_paths

    parser = etree.XMLParser(
        dtd_validation=False,
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
    )

    for file_path in search_paths:
        try:
            with open(file_path, "rb") as f:
                doc = etree.parse(f, parser)

            for elem in doc.xpath(xpath):
                text = (elem.text or "").strip()
                if text:
                    truncated = text[:MAX_TEXT_LEN]
                    if truncated != exclude_value:
                        return truncated
        except Exception as e:
            print(f"xml_structure_analysis: find_example error in {file_path}: {e}")
            continue

    return ""
