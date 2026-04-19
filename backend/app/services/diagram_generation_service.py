"""Diagram Generation service - generate Mermaid.js diagrams from DITA XML content.

Supports task flowcharts, concept mind maps, ditamap structure diagrams,
and process flow diagrams from ordered lists.
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


# ---------------------------------------------------------------------------
# Mermaid label helpers
# ---------------------------------------------------------------------------

def _escape_label(text: str) -> str:
    """Escape special Mermaid characters in a node label."""
    if not text:
        return ""
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove characters that break Mermaid syntax
    text = text.replace('"', "'")
    text = text.replace("|", "/")
    text = text.replace("[", "(")
    text = text.replace("]", ")")
    text = text.replace("{", "(")
    text = text.replace("}", ")")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("#", "Nr")
    text = text.replace("&", "and")
    # Truncate very long labels
    if len(text) > 80:
        text = text[:77] + "..."
    return text


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from a tag name."""
    return tag.split("}")[-1] if "}" in tag else tag


def _get_title(root: ET.Element, fallback: str = "Untitled") -> str:
    """Safely extract title text from a DITA element."""
    title_el = root.find("title")
    if title_el is not None:
        text = _text_content(title_el).strip()
        if text:
            return text
    return fallback


def _text_content(el: ET.Element) -> str:
    """Get all text content of an element (including children)."""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(_text_content(child))
        if child.tail:
            parts.append(child.tail)
    return " ".join(parts)


def _find_all_recursive(root: ET.Element, tag: str) -> list:
    """Find all descendants matching a local tag name (namespace-agnostic)."""
    results = []
    for el in root.iter():
        if _strip_ns(el.tag) == tag:
            results.append(el)
    return results


def _detect_root_type(root: ET.Element) -> str:
    """Detect the DITA document type from the root element."""
    tag = _strip_ns(root.tag)
    return tag.lower()


def _safe_parse(xml: str) -> Optional[ET.Element]:
    """Parse XML, returning None on failure."""
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        logger.warning("Failed to parse XML: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 1. Task Flowchart
# ---------------------------------------------------------------------------

def _generate_task_flowchart(root: ET.Element) -> dict:
    """Generate a Mermaid flowchart from a DITA task's <steps>."""
    title_text = _escape_label(_get_title(root, "Task"))

    steps_el = _find_all_recursive(root, "steps")
    if not steps_el:
        # Minimal diagram when no steps found
        code = "flowchart TD\n    Start([Start]) --> End([Done])"
        return {
            "mermaid_code": code,
            "diagram_type": "flowchart",
            "node_count": 2,
            "title": title_text,
            "svg_placeholder": f"[Flowchart: {title_text} — 2 nodes]",
        }

    lines = ["flowchart TD"]
    node_id = 0
    edges = []

    def _next_id():
        nonlocal node_id
        node_id += 1
        return f"S{node_id}"

    start_id = "Start"
    lines.append(f"    {start_id}([Start])")
    prev_ids = [start_id]

    for steps in steps_el:
        for child in steps:
            child_tag = _strip_ns(child.tag)

            if child_tag == "stepsection":
                note_text = _escape_label(_text_content(child))
                if note_text and prev_ids:
                    nid = _next_id()
                    lines.append(f"    {nid}[/{note_text}/]")
                    for pid in prev_ids:
                        edges.append(f"    {pid} --> {nid}")
                    prev_ids = [nid]
                continue

            if child_tag != "step":
                continue

            # Check for <choices> inside the step
            choices_el = _find_all_recursive(child, "choices")
            substeps_el = _find_all_recursive(child, "substeps")

            cmd_el = child.find("cmd") if child.find("cmd") is not None else None
            if cmd_el is None:
                # Namespace-agnostic search
                for c in child:
                    if _strip_ns(c.tag) == "cmd":
                        cmd_el = c
                        break

            cmd_text = _escape_label(_text_content(cmd_el)) if cmd_el is not None else "Step"

            if choices_el:
                # Decision diamond
                dec_id = _next_id()
                lines.append(f"    {dec_id}{{{{{cmd_text}}}}}")
                for pid in prev_ids:
                    edges.append(f"    {pid} --> {dec_id}")

                choice_end_ids = []
                for choices in choices_el:
                    for choice in choices:
                        if _strip_ns(choice.tag) != "choice":
                            continue
                        choice_text = _escape_label(_text_content(choice))
                        cid = _next_id()
                        lines.append(f"    {cid}[{choice_text}]")
                        edges.append(f"    {dec_id} -->|{choice_text[:20]}| {cid}")
                        choice_end_ids.append(cid)

                prev_ids = choice_end_ids if choice_end_ids else [dec_id]

            elif substeps_el:
                # Main step node
                sid = _next_id()
                lines.append(f"    {sid}[{cmd_text}]")
                for pid in prev_ids:
                    edges.append(f"    {pid} --> {sid}")
                prev_ids = [sid]

                # Sub-step nodes
                for substeps in substeps_el:
                    for substep in substeps:
                        if _strip_ns(substep.tag) != "substep":
                            continue
                        sub_cmd = None
                        for sc in substep:
                            if _strip_ns(sc.tag) == "cmd":
                                sub_cmd = sc
                                break
                        sub_text = _escape_label(_text_content(sub_cmd)) if sub_cmd is not None else "Sub-step"
                        sub_id = _next_id()
                        lines.append(f"    {sub_id}[{sub_text}]")
                        for pid in prev_ids:
                            edges.append(f"    {pid} --> {sub_id}")
                        prev_ids = [sub_id]
            else:
                sid = _next_id()
                lines.append(f"    {sid}[{cmd_text}]")
                for pid in prev_ids:
                    edges.append(f"    {pid} --> {sid}")
                prev_ids = [sid]

    end_id = "End"
    lines.append(f"    {end_id}([Done])")
    for pid in prev_ids:
        edges.append(f"    {pid} --> {end_id}")

    code = "\n".join(lines + edges)
    total_nodes = node_id + 2  # +2 for Start and End
    return {
        "mermaid_code": code,
        "diagram_type": "flowchart",
        "node_count": total_nodes,
        "title": title_text,
        "svg_placeholder": f"[Flowchart: {title_text} — {total_nodes} nodes]",
    }


# ---------------------------------------------------------------------------
# 2. Concept Mind Map
# ---------------------------------------------------------------------------

def _generate_concept_map(root: ET.Element) -> dict:
    """Generate a Mermaid mindmap from a DITA concept topic."""
    title_text = _escape_label(_get_title(root, "Concept"))

    lines = ["mindmap"]
    lines.append(f"    root(({title_text}))")
    node_count = 1

    # Find body element
    body = None
    for child in root:
        if _strip_ns(child.tag) in ("conbody", "body"):
            body = child
            break

    if body is None:
        return {
            "mermaid_code": "\n".join(lines),
            "diagram_type": "mindmap",
            "node_count": node_count,
            "title": title_text,
            "svg_placeholder": f"[Mindmap: {title_text} — {node_count} nodes]",
        }

    for child in body:
        child_tag = _strip_ns(child.tag)

        if child_tag == "section":
            sec_title_el = child.find("title") if child.find("title") is not None else None
            if sec_title_el is None:
                for sc in child:
                    if _strip_ns(sc.tag) == "title":
                        sec_title_el = sc
                        break
            sec_title = _escape_label(_text_content(sec_title_el)) if sec_title_el is not None else "Section"
            lines.append(f"        {sec_title}")
            node_count += 1

            # Look for definition lists within section
            for dl in _find_all_recursive(child, "dl"):
                for dlentry in _find_all_recursive(dl, "dlentry"):
                    dt_el = None
                    for de_child in dlentry:
                        if _strip_ns(de_child.tag) == "dt":
                            dt_el = de_child
                            break
                    if dt_el is not None:
                        term = _escape_label(_text_content(dt_el))
                        if term:
                            lines.append(f"            {term}")
                            node_count += 1

            # Look for paragraphs as leaf nodes if no dl found
            dls = _find_all_recursive(child, "dl")
            if not dls:
                for p in child:
                    if _strip_ns(p.tag) == "p":
                        p_text = _escape_label(_text_content(p))
                        if p_text:
                            # Truncate paragraph to first sentence
                            first_sent = p_text.split(".")[0].strip()
                            if first_sent:
                                lines.append(f"            {first_sent}")
                                node_count += 1

        elif child_tag == "p" and not _find_all_recursive(body, "section"):
            # If no sections, treat top-level paragraphs as branches
            p_text = _escape_label(_text_content(child))
            if p_text:
                first_sent = p_text.split(".")[0].strip()
                if first_sent:
                    lines.append(f"        {first_sent}")
                    node_count += 1

    code = "\n".join(lines)
    return {
        "mermaid_code": code,
        "diagram_type": "mindmap",
        "node_count": node_count,
        "title": title_text,
        "svg_placeholder": f"[Mindmap: {title_text} — {node_count} nodes]",
    }


# ---------------------------------------------------------------------------
# 3. Map Structure Diagram
# ---------------------------------------------------------------------------

def _generate_map_diagram(root: ET.Element) -> dict:
    """Generate a Mermaid flowchart showing ditamap structure."""
    title_el = root.find("title")
    if title_el is None:
        for child in root:
            if _strip_ns(child.tag) == "title":
                title_el = child
                break
    title_text = _escape_label(_text_content(title_el)) if title_el is not None else "Map"

    lines = ["flowchart TD"]
    edges = []
    node_counter = [0]

    def _next_id():
        node_counter[0] += 1
        return f"M{node_counter[0]}"

    root_id = _next_id()
    lines.append(f"    {root_id}[({title_text})]")

    def _process_topicrefs(parent: ET.Element, parent_id: str):
        for child in parent:
            if _strip_ns(child.tag) != "topicref":
                continue
            href = child.get("href", "")
            navtitle = child.get("navtitle", "")
            # Also check for <topicmeta>/<navtitle>
            if not navtitle:
                meta = None
                for mc in child:
                    if _strip_ns(mc.tag) == "topicmeta":
                        meta = mc
                        break
                if meta is not None:
                    for mc in meta:
                        if _strip_ns(mc.tag) == "navtitle":
                            navtitle = _text_content(mc)
                            break
            label = _escape_label(navtitle or href or "topic")
            nid = _next_id()
            lines.append(f"    {nid}[{label}]")
            edges.append(f"    {parent_id} --> {nid}")
            # Recurse into nested topicrefs
            _process_topicrefs(child, nid)

    _process_topicrefs(root, root_id)

    code = "\n".join(lines + edges)
    total_nodes = node_counter[0]
    return {
        "mermaid_code": code,
        "diagram_type": "map_structure",
        "node_count": total_nodes,
        "title": title_text,
        "svg_placeholder": f"[Map Structure: {title_text} — {total_nodes} nodes]",
    }


# ---------------------------------------------------------------------------
# 4. Process Flow
# ---------------------------------------------------------------------------

def _generate_process_flow(root: ET.Element) -> dict:
    """Generate a Mermaid flowchart from ordered lists in DITA content."""
    title_text = _escape_label(_get_title(root, "Process"))

    ol_elements = _find_all_recursive(root, "ol")
    if not ol_elements:
        code = "flowchart TD\n    Start([Start]) --> End([Done])"
        return {
            "mermaid_code": code,
            "diagram_type": "process_flow",
            "node_count": 2,
            "title": title_text,
            "svg_placeholder": f"[Process Flow: {title_text} — 2 nodes]",
        }

    lines = ["flowchart TD"]
    edges = []
    node_counter = [0]

    def _next_id():
        node_counter[0] += 1
        return f"P{node_counter[0]}"

    start_id = "Start"
    lines.append(f"    {start_id}([Start])")
    prev_id = start_id

    for ol in ol_elements:
        for li in ol:
            if _strip_ns(li.tag) != "li":
                continue
            li_text = _escape_label(_text_content(li))
            if not li_text:
                continue
            nid = _next_id()
            lines.append(f"    {nid}[{li_text}]")
            edges.append(f"    {prev_id} --> {nid}")
            prev_id = nid

    end_id = "End"
    lines.append(f"    {end_id}([Done])")
    edges.append(f"    {prev_id} --> {end_id}")

    code = "\n".join(lines + edges)
    total_nodes = node_counter[0] + 2  # +2 for Start and End
    return {
        "mermaid_code": code,
        "diagram_type": "process_flow",
        "node_count": total_nodes,
        "title": title_text,
        "svg_placeholder": f"[Process Flow: {title_text} — {total_nodes} nodes]",
    }


# ---------------------------------------------------------------------------
# Fallback mindmap from sections
# ---------------------------------------------------------------------------

def _generate_fallback_mindmap(root: ET.Element) -> dict:
    """Fallback: build a mindmap from any sections found in the topic."""
    return _generate_concept_map(root)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def _auto_detect_type(root: ET.Element) -> str:
    """Determine the best diagram type for the given DITA XML root."""
    root_tag = _detect_root_type(root)

    if root_tag == "task" and _find_all_recursive(root, "steps"):
        return "flowchart"
    if root_tag == "concept":
        return "mindmap"
    if root_tag in ("map", "bookmap"):
        return "map_structure"
    if _find_all_recursive(root, "ol"):
        return "process_flow"
    return "mindmap"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_diagram(xml: str, diagram_type: str = "auto") -> dict:
    """Generate a Mermaid.js diagram from DITA XML.

    Args:
        xml: The DITA XML content as a string.
        diagram_type: One of "flowchart", "mindmap", "map_structure",
                      "process_flow", or "auto".

    Returns:
        dict with keys: mermaid_code, diagram_type, node_count, title,
        svg_placeholder.  On error returns a dict with an "error" key.
    """
    logger.info("Generating diagram (type=%s)", diagram_type)

    root = _safe_parse(xml)
    if root is None:
        return {
            "error": "Failed to parse XML",
            "mermaid_code": "",
            "diagram_type": diagram_type,
            "node_count": 0,
            "title": "",
            "svg_placeholder": "",
        }

    if diagram_type == "auto":
        diagram_type = _auto_detect_type(root)
        logger.info("Auto-detected diagram type: %s", diagram_type)

    generators = {
        "flowchart": _generate_task_flowchart,
        "mindmap": _generate_concept_map,
        "map_structure": _generate_map_diagram,
        "process_flow": _generate_process_flow,
    }

    generator = generators.get(diagram_type, _generate_fallback_mindmap)
    result = generator(root)
    logger.info("Generated %s diagram with %d nodes", result["diagram_type"], result["node_count"])
    return result


def generate_task_flowchart(xml: str) -> dict:
    """Synchronous helper: generate a task flowchart."""
    root = _safe_parse(xml)
    if root is None:
        return {"error": "Failed to parse XML", "mermaid_code": "", "diagram_type": "flowchart",
                "node_count": 0, "title": "", "svg_placeholder": ""}
    return _generate_task_flowchart(root)


def generate_concept_map(xml: str) -> dict:
    """Synchronous helper: generate a concept mindmap."""
    root = _safe_parse(xml)
    if root is None:
        return {"error": "Failed to parse XML", "mermaid_code": "", "diagram_type": "mindmap",
                "node_count": 0, "title": "", "svg_placeholder": ""}
    return _generate_concept_map(root)


def generate_map_diagram(xml: str) -> dict:
    """Synchronous helper: generate a ditamap structure diagram."""
    root = _safe_parse(xml)
    if root is None:
        return {"error": "Failed to parse XML", "mermaid_code": "", "diagram_type": "map_structure",
                "node_count": 0, "title": "", "svg_placeholder": ""}
    return _generate_map_diagram(root)


def generate_process_flow(xml: str) -> dict:
    """Synchronous helper: generate a process flow from ordered lists."""
    root = _safe_parse(xml)
    if root is None:
        return {"error": "Failed to parse XML", "mermaid_code": "", "diagram_type": "process_flow",
                "node_count": 0, "title": "", "svg_placeholder": ""}
    return _generate_process_flow(root)
