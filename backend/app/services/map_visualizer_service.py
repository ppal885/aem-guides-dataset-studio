"""Parse DITA maps (ditamap, bookmap) and return a graph data structure for visualization."""

import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# Elements that represent structural containers in DITA maps
_TOPICREF_TAGS = {"topicref", "topicgroup", "topichead", "chapter", "appendix", "mapref"}

# Map from element tag to node type
_TAG_TO_TYPE = {
    "map": "map",
    "bookmap": "map",
    "topicref": "topic",
    "topicgroup": "topicgroup",
    "topichead": "topichead",
    "chapter": "chapter",
    "appendix": "appendix",
    "mapref": "map",
}


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from a tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _node_label(elem: ET.Element, local_tag: str) -> str:
    """Derive a display label for a node from navtitle or href."""
    navtitle = elem.get("navtitle")
    if navtitle:
        return navtitle
    href = elem.get("href")
    if href:
        return os.path.splitext(os.path.basename(href))[0]
    # Fall back to tag name
    return local_tag


def _node_metadata(elem: ET.Element) -> dict:
    """Extract metadata attributes from an element."""
    toc_val = elem.get("toc", "yes")
    return {
        "format": elem.get("format", "dita"),
        "scope": elem.get("scope", "local"),
        "toc": toc_val.lower() != "no",
        "processing_role": elem.get("processing-role", "normal"),
    }


def _walk(
    elem: ET.Element,
    level: int,
    parent_id: Optional[str],
    nodes: List[dict],
    edges: List[dict],
    counter: List[int],
    sibling_counts: Dict[str, int],
):
    """Recursively walk a DITA map element tree and populate nodes/edges."""
    local_tag = _strip_ns(elem.tag)

    # Only process recognised structural elements
    if local_tag not in _TAG_TO_TYPE:
        # Still recurse into children (e.g. frontmatter, backmatter wrappers)
        for child in elem:
            _walk(child, level, parent_id, nodes, edges, counter, sibling_counts)
        return

    node_id = f"n{counter[0]}"
    counter[0] += 1

    node = {
        "id": node_id,
        "label": _node_label(elem, local_tag),
        "type": _TAG_TO_TYPE.get(local_tag, "topic"),
        "href": elem.get("href"),
        "level": level,
        "metadata": _node_metadata(elem),
    }
    nodes.append(node)

    if parent_id is not None:
        edges.append({"source": parent_id, "target": node_id, "type": "contains"})

    # Track sibling counts for the AI suggestion about grouping
    if parent_id is not None:
        sibling_counts[parent_id] = sibling_counts.get(parent_id, 0) + 1

    # Recurse into children (skip reltable — handled separately)
    for child in elem:
        child_tag = _strip_ns(child.tag)
        if child_tag == "reltable":
            continue
        _walk(child, level + 1, node_id, nodes, edges, counter, sibling_counts)


def _parse_reltables(root: ET.Element, nodes: List[dict], edges: List[dict]):
    """Parse <reltable> entries and add 'related' edges between topics."""
    # Build a lookup from href to node id for quick matching
    href_to_id: Dict[str, str] = {}
    for node in nodes:
        if node.get("href"):
            href_to_id[node["href"]] = node["id"]

    for reltable in root.iter("reltable"):
        for relrow in reltable.iter("relrow"):
            # Collect all hrefs in this row
            row_ids: List[str] = []
            for relcell in relrow.iter("relcell"):
                for topicref in relcell.iter("topicref"):
                    href = topicref.get("href")
                    if href and href in href_to_id:
                        row_ids.append(href_to_id[href])
            # Create pairwise related edges
            for i in range(len(row_ids)):
                for j in range(i + 1, len(row_ids)):
                    edges.append({
                        "source": row_ids[i],
                        "target": row_ids[j],
                        "type": "related",
                    })


def _compute_stats(nodes: List[dict]) -> dict:
    """Compute summary statistics from the node list."""
    topic_count = sum(1 for n in nodes if n["type"] == "topic")
    map_count = sum(1 for n in nodes if n["type"] == "map")
    topicgroup_count = sum(1 for n in nodes if n["type"] == "topicgroup")
    max_depth = max((n["level"] for n in nodes), default=0)
    return {
        "total_nodes": len(nodes),
        "max_depth": max_depth,
        "topic_count": topic_count,
        "map_count": map_count,
        "topicgroup_count": topicgroup_count,
    }


def _generate_suggestions(
    nodes: List[dict],
    edges: List[dict],
    stats: dict,
    sibling_counts: Dict[str, int],
    has_reltable: bool,
) -> List[str]:
    """Generate rule-based AI suggestions for map improvement."""
    suggestions: List[str] = []

    # Deep nesting
    if stats["max_depth"] > 4:
        suggestions.append(
            f"Map has {stats['max_depth']} levels of nesting — consider flattening for readability"
        )

    # Missing navtitles
    missing_navtitle = sum(
        1 for n in nodes
        if n["type"] in ("topic", "chapter", "appendix") and n.get("href") and n["label"] == os.path.splitext(os.path.basename(n["href"]))[0]
    )
    if missing_navtitle > 0:
        suggestions.append(
            f"{missing_navtitle} topics have no navtitle — add titles for better navigation"
        )

    # Too many siblings
    for parent_id, count in sibling_counts.items():
        if count > 10:
            suggestions.append(
                "Consider grouping related topics with <topicgroup>"
            )
            break

    # No reltable
    if not has_reltable:
        suggestions.append(
            "No relationship table found — add <reltable> for cross-linking"
        )

    return suggestions


def _get_map_title(root: ET.Element) -> str:
    """Extract the map title from <title> child or @title attribute."""
    title_elem = root.find("title")
    if title_elem is not None and title_elem.text:
        return title_elem.text.strip()
    # Try booktitle/mainbooktitle for bookmaps
    booktitle = root.find("booktitle")
    if booktitle is not None:
        main = booktitle.find("mainbooktitle")
        if main is not None and main.text:
            return main.text.strip()
    return root.get("title", "Untitled Map")


def parse_map_to_graph(xml_str: str) -> dict:
    """Parse a ditamap/bookmap XML string and return a visualization graph.

    Returns a dict with keys: nodes, edges, stats, title, ai_suggestions.
    Raises ValueError for malformed XML.
    """
    logger.info("Parsing DITA map for visualization")

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        logger.info("Failed to parse DITA map XML")
        raise ValueError(f"Malformed XML: {exc}") from exc

    nodes: List[dict] = []
    edges: List[dict] = []
    counter = [0]  # mutable counter for node IDs
    sibling_counts: Dict[str, int] = {}

    _walk(root, 0, None, nodes, edges, counter, sibling_counts)

    # Check for reltable presence before parsing
    has_reltable = any(_strip_ns(child.tag) == "reltable" for child in root)
    _parse_reltables(root, nodes, edges)

    stats = _compute_stats(nodes)
    title = _get_map_title(root)
    suggestions = _generate_suggestions(nodes, edges, stats, sibling_counts, has_reltable)

    logger.info("DITA map parsed successfully")

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "title": title,
        "ai_suggestions": suggestions,
    }


def graph_to_mermaid(graph: dict) -> str:
    """Convert a graph dict (from parse_map_to_graph) to Mermaid.js diagram code."""
    lines = ["graph TD"]

    # Shape by type
    _shape = {
        "map": ("{{", "}}"),
        "topic": ("[", "]"),
        "topicgroup": ("([", "])"),
        "topichead": ("[[", "]]"),
        "chapter": ("[/", "/]"),
        "appendix": ("[\\", "\\]"),
    }

    for node in graph["nodes"]:
        left, right = _shape.get(node["type"], ("[", "]"))
        safe_label = node["label"].replace('"', "'")
        lines.append(f'    {node["id"]}{left}"{safe_label}"{right}')

    for edge in graph["edges"]:
        if edge["type"] == "related":
            lines.append(f'    {edge["source"]} -.- {edge["target"]}')
        else:
            lines.append(f'    {edge["source"]} --> {edge["target"]}')

    return "\n".join(lines)
