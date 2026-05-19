from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import textwrap
import xml.etree.ElementTree as ET
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_XML_DECLARATION_RE = re.compile(r"<\?xml[^>]*\?>", re.IGNORECASE)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_SVG_NS = "http://www.w3.org/2000/svg"
_LOCAL_IMAGE_MODEL = "local-svg-fallback"
_OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1"
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
_FLOWCHART_LARGE_XML_CHARS = 45_000
_FLOWCHART_LARGE_ELEMENT_COUNT = 90
_FLOWCHART_MAX_VISIBLE_NODES = 30
_FLOWCHART_MAX_VISIBLE_EDGES = 42


def _strip_xml_wrappers(xml: str) -> str:
    cleaned = _XML_DECLARATION_RE.sub("", xml or "")
    cleaned = _DOCTYPE_RE.sub("", cleaned)
    return cleaned.strip()


def _short_label(value: str, *, max_len: int = 44) -> str:
    compact = " ".join((value or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def _wrap_text(value: str, *, width: int = 26, max_lines: int = 4) -> list[str]:
    wrapped = textwrap.wrap(_short_label(value, max_len=width * max_lines), width=width) or [value[:width]]
    return wrapped[:max_lines]


def _data_url(mime_type: str, payload: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload.encode('utf-8')).decode('ascii')}"


def _bytes_to_data_url(mime_type: str, payload: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload).decode('ascii')}"


def _parse_xml_root(xml: str) -> ET.Element:
    cleaned = _strip_xml_wrappers(xml)
    if not cleaned:
        raise ValueError("XML content is required")
    return ET.fromstring(cleaned)


def _safe_tag(tag: str) -> str:
    if "}" in tag:
        tag = tag.rsplit("}", 1)[-1]
    return tag


def _find_text(elem: ET.Element, tag_name: str) -> str:
    for child in list(elem):
        if _safe_tag(child.tag) == tag_name:
            return " ".join("".join(child.itertext()).split())
    return ""


def _structure_profile(root: ET.Element, xml: str) -> dict[str, Any]:
    tag_counts: dict[str, int] = {}
    reference_counts = {"href": 0, "keyref": 0, "conref": 0, "conkeyref": 0}
    max_depth = 0

    def visit(elem: ET.Element, depth: int) -> int:
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        tag = _safe_tag(elem.tag)
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for attr in reference_counts:
            if elem.get(attr):
                reference_counts[attr] += 1
        count = 1
        for child in list(elem):
            count += visit(child, depth + 1)
        return count

    element_count = visit(root, 1)
    top_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    return {
        "root_element": _safe_tag(root.tag),
        "xml_char_count": len(xml or ""),
        "line_count": len((xml or "").splitlines()) or 1,
        "element_count": element_count,
        "max_depth": max_depth,
        "tag_counts": tag_counts,
        "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
        "reference_counts": reference_counts,
    }


def _diagram_id(prefix: str, value: str, seen: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or prefix
    candidate = f"{prefix}_{base}"
    suffix = 2
    while candidate in seen:
        candidate = f"{prefix}_{base}_{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _topic_diagram(root: ET.Element) -> dict[str, Any]:
    title = _find_text(root, "title") or root.get("id") or "DITA topic"
    topic_id = root.get("id") or "topic"
    seen: set[str] = set()
    nodes = [
        {
            "id": _diagram_id("topic", topic_id, seen),
            "label": f"{_safe_tag(root.tag)}: {title}",
            "kind": "root",
        }
    ]
    edges: list[dict[str, str]] = []
    root_node_id = nodes[0]["id"]

    shortdesc = _find_text(root, "shortdesc")
    if shortdesc:
        shortdesc_id = _diagram_id("shortdesc", topic_id, seen)
        nodes.append({"id": shortdesc_id, "label": f"shortdesc: {_short_label(shortdesc, max_len=70)}", "kind": "shortdesc"})
        edges.append({"from": root_node_id, "to": shortdesc_id, "label": "contains"})

    for section in root.findall(".//*"):
        tag = _safe_tag(section.tag)
        if tag not in {"section", "steps", "related-links", "body", "xref", "p", "topic", "taskbody", "conbody", "refbody"}:
            continue
        if section is root:
            continue
        if tag in {"body", "taskbody", "conbody", "refbody"}:
            body_id = _diagram_id("body", tag, seen)
            nodes.append({"id": body_id, "label": tag, "kind": "container"})
            edges.append({"from": root_node_id, "to": body_id, "label": "body"})
            parent_for_children = body_id
            for child in list(section):
                child_tag = _safe_tag(child.tag)
                if child_tag not in {"section", "steps", "p", "related-links"}:
                    continue
                child_text = _find_text(child, "title") or " ".join("".join(child.itertext()).split()) or child_tag
                node_id = _diagram_id(child_tag, child_text[:20], seen)
                nodes.append({"id": node_id, "label": f"{child_tag}: {_short_label(child_text)}", "kind": child_tag})
                edges.append({"from": parent_for_children, "to": node_id, "label": "contains"})
            break

    for ref_elem in root.findall(".//*[@href]") + root.findall(".//*[@keyref]") + root.findall(".//*[@conref]") + root.findall(".//*[@conkeyref]"):
        attr_name = next((name for name in ("href", "keyref", "conref", "conkeyref") if ref_elem.get(name)), "")
        attr_value = ref_elem.get(attr_name)
        if not attr_name or not attr_value:
            continue
        node_id = _diagram_id(attr_name, attr_value, seen)
        nodes.append({"id": node_id, "label": f"{attr_name}: {_short_label(attr_value)}", "kind": "reference"})
        edges.append({"from": root_node_id, "to": node_id, "label": attr_name})

    return {
        "title": title,
        "kind": "topic",
        "nodes": nodes,
        "edges": edges,
    }


def _map_diagram(root: ET.Element) -> dict[str, Any]:
    title = _find_text(root, "title") or root.get("id") or "DITA map"
    map_id = root.get("id") or "map"
    seen: set[str] = set()
    root_id = _diagram_id("map", map_id, seen)
    nodes = [{"id": root_id, "label": f"{_safe_tag(root.tag)}: {title}", "kind": "root"}]
    edges: list[dict[str, str]] = []

    for keydef in root.findall(".//keydef"):
        keys = (keydef.get("keys") or "").strip()
        href = (keydef.get("href") or "").strip()
        label = f"keydef: {keys or '(inline)'}"
        if href:
            label += f" -> {href}"
        node_id = _diagram_id("keydef", keys or href or "inline", seen)
        nodes.append({"id": node_id, "label": _short_label(label), "kind": "keydef"})
        edges.append({"from": root_id, "to": node_id, "label": "keydef"})

    for topicref in root.findall(".//topicref"):
        label = topicref.get("navtitle") or topicref.get("keyref") or topicref.get("href") or "topicref"
        node_id = _diagram_id("topicref", label, seen)
        nodes.append({"id": node_id, "label": f"topicref: {_short_label(label)}", "kind": "topicref"})
        edges.append({"from": root_id, "to": node_id, "label": "topicref"})

    for mapref in root.findall(".//mapref") + root.findall(".//navref"):
        href = mapref.get("href") or mapref.get("navtitle") or "submap"
        label = f"{_safe_tag(mapref.tag)}: {_short_label(href)}"
        node_id = _diagram_id("mapref", href, seen)
        nodes.append({"id": node_id, "label": label, "kind": "mapref"})
        edges.append({"from": root_id, "to": node_id, "label": _safe_tag(mapref.tag)})

    return {
        "title": title,
        "kind": "map",
        "nodes": nodes,
        "edges": edges,
    }


def _flowchart_legend(diagram: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "root": "Root topic or map",
        "container": "Body/container",
        "section": "Section",
        "steps": "Procedure steps",
        "p": "Paragraph",
        "reference": "Link/reuse reference",
        "keydef": "Key definition",
        "topicref": "Topic reference",
        "mapref": "Map reference",
    }
    seen: set[str] = set()
    legend: list[dict[str, str]] = []
    for node in diagram.get("nodes") or []:
        kind = str(node.get("kind") or "").strip()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        legend.append({"kind": kind, "label": labels.get(kind, kind.replace("_", " "))})
    return legend[:8]


def _apply_flowchart_display_policy(diagram: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    all_nodes = list(diagram.get("nodes") or [])
    all_edges = list(diagram.get("edges") or [])
    large_document = (
        int(profile.get("xml_char_count") or 0) > _FLOWCHART_LARGE_XML_CHARS
        or int(profile.get("element_count") or 0) > _FLOWCHART_LARGE_ELEMENT_COUNT
        or len(all_nodes) > _FLOWCHART_MAX_VISIBLE_NODES
    )

    visible_nodes = all_nodes[:_FLOWCHART_MAX_VISIBLE_NODES]
    visible_ids = {str(node.get("id")) for node in visible_nodes}
    visible_edges = [
        edge for edge in all_edges
        if str(edge.get("from")) in visible_ids and str(edge.get("to")) in visible_ids
    ][:_FLOWCHART_MAX_VISIBLE_EDGES]

    omitted_nodes = max(0, len(all_nodes) - len(visible_nodes))
    omitted_edges = max(0, len(all_edges) - len(visible_edges))
    is_simplified = large_document or omitted_nodes > 0 or omitted_edges > 0
    focus = (
        "First-level structure, map branches, keys, and major references"
        if str(diagram.get("kind") or "") == "map"
        else "Root topic, body containers, major sections, and link/reuse references"
    )
    summary = (
        f"Showing {len(visible_nodes)} of {len(all_nodes)} structural node"
        f"{'s' if len(all_nodes) != 1 else ''}"
    )
    if omitted_nodes:
        summary += f"; {omitted_nodes} lower-priority node{'s' if omitted_nodes != 1 else ''} omitted from the preview"
    summary += "."

    warnings: list[str] = []
    if is_simplified:
        warnings.append(
            "Large or dense XML is rendered as a scoped structure overview, not exhaustive node-by-node output."
        )
    if omitted_nodes:
        warnings.append(
            f"{omitted_nodes} structural node{'s' if omitted_nodes != 1 else ''} were omitted from the SVG to keep the preview readable."
        )

    return {
        **diagram,
        "nodes": visible_nodes,
        "edges": visible_edges,
        "xml_profile": profile,
        "total_node_count": len(all_nodes),
        "total_edge_count": len(all_edges),
        "visible_node_count": len(visible_nodes),
        "visible_edge_count": len(visible_edges),
        "omitted_node_count": omitted_nodes,
        "omitted_edge_count": omitted_edges,
        "max_visible_nodes": _FLOWCHART_MAX_VISIBLE_NODES,
        "max_visible_edges": _FLOWCHART_MAX_VISIBLE_EDGES,
        "is_simplified": is_simplified,
        "large_document": large_document,
        "display_mode": "structure_overview" if is_simplified else "complete_diagram",
        "preview_focus": focus,
        "structure_summary": summary,
        "legend": _flowchart_legend({"nodes": visible_nodes}),
        "warnings": warnings,
    }


def _diagram_from_xml(xml: str, xml_kind: str = "auto") -> dict[str, Any]:
    root = _parse_xml_root(xml)
    profile = _structure_profile(root, xml)
    tag = _safe_tag(root.tag).lower()
    kind = (xml_kind or "auto").strip().lower()
    if kind == "auto":
        if tag in {"map", "bookmap"}:
            kind = "map"
        elif tag in {"topic", "task", "concept", "reference", "glossentry"}:
            kind = "topic"
        else:
            raise ValueError(f"Unsupported XML root element '{tag}'. Paste a DITA topic or map XML snippet.")
    if kind == "map":
        return _apply_flowchart_display_policy(_map_diagram(root), profile)
    if kind == "topic":
        return _apply_flowchart_display_policy(_topic_diagram(root), profile)
    raise ValueError("xml_kind must be one of: auto, map, topic")


def _mermaid_escape(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return escaped.replace("\n", " ")


def diagram_to_mermaid(diagram: dict[str, Any]) -> str:
    lines = ["flowchart TD"]
    for node in diagram.get("nodes") or []:
        lines.append(f'  {node["id"]}["{_mermaid_escape(str(node["label"]))}"]')
    for edge in diagram.get("edges") or []:
        label = str(edge.get("label") or "").strip()
        if label:
            lines.append(f'  {edge["from"]} -->|"{_mermaid_escape(label)}"| {edge["to"]}')
        else:
            lines.append(f'  {edge["from"]} --> {edge["to"]}')
    return "\n".join(lines)


def diagram_to_svg(diagram: dict[str, Any]) -> str:
    nodes = diagram.get("nodes") or []
    edges = diagram.get("edges") or []
    if not nodes:
        raise ValueError("Cannot render an empty diagram")

    columns = 3 if len(nodes) > 6 else 2
    box_w = 250
    box_h = 72
    gap_x = 36
    gap_y = 28
    margin = 28
    positions: dict[str, tuple[int, int]] = {}

    for index, node in enumerate(nodes):
        row = index // columns
        col = index % columns
        x = margin + col * (box_w + gap_x)
        y = margin + row * (box_h + gap_y)
        positions[str(node["id"])] = (x, y)

    max_row = (len(nodes) - 1) // columns
    width = margin * 2 + columns * box_w + (columns - 1) * gap_x
    height = margin * 2 + (max_row + 1) * box_h + max_row * gap_y + 40

    parts = [
        f'<svg xmlns="{_SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(str(diagram.get("title") or "DITA diagram"))}">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 z" fill="#64748b" /></marker></defs>',
        '<rect width="100%" height="100%" rx="22" fill="#f8fafc" />',
    ]

    for edge in edges:
        start = positions.get(str(edge["from"]))
        end = positions.get(str(edge["to"]))
        if not start or not end:
            continue
        x1 = start[0] + box_w / 2
        y1 = start[1] + box_h
        x2 = end[0] + box_w / 2
        y2 = end[1]
        mid_y = (y1 + y2) / 2
        path = f"M{x1},{y1} C{x1},{mid_y} {x2},{mid_y} {x2},{y2 - 8}"
        parts.append(f'<path d="{path}" fill="none" stroke="#94a3b8" stroke-width="2" marker-end="url(#arrow)" />')
        label = str(edge.get("label") or "").strip()
        if label:
            label_x = (x1 + x2) / 2
            label_y = mid_y - 6
            parts.append(
                f'<text x="{label_x}" y="{label_y}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="#475569">{html.escape(label)}</text>'
            )

    color_map = {
        "root": ("#1d4ed8", "#dbeafe"),
        "keydef": ("#7c3aed", "#ede9fe"),
        "topicref": ("#0f766e", "#ccfbf1"),
        "mapref": ("#b45309", "#fef3c7"),
        "shortdesc": ("#2563eb", "#eff6ff"),
        "reference": ("#dc2626", "#fee2e2"),
        "container": ("#475569", "#e2e8f0"),
        "section": ("#0f766e", "#ecfeff"),
        "steps": ("#0369a1", "#e0f2fe"),
        "p": ("#334155", "#f8fafc"),
    }

    for node in nodes:
        x, y = positions[str(node["id"])]
        border, fill = color_map.get(str(node.get("kind") or ""), ("#334155", "#ffffff"))
        parts.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="16" fill="{fill}" stroke="{border}" stroke-width="2" />')
        for line_index, line in enumerate(_wrap_text(str(node.get("label") or ""), width=28, max_lines=3)):
            text_y = y + 24 + line_index * 16
            parts.append(
                f'<text x="{x + 16}" y="{text_y}" font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="{700 if line_index == 0 else 500}" fill="#0f172a">{html.escape(line)}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


async def generate_xml_flowchart(
    xml: str,
    *,
    xml_kind: str = "auto",
    render_mode: str = "both",
) -> dict[str, Any]:
    diagram = _diagram_from_xml(xml, xml_kind=xml_kind)
    mermaid = diagram_to_mermaid(diagram)
    svg = diagram_to_svg(diagram) if render_mode in {"both", "svg", "preview"} else ""
    simplified = bool(diagram.get("is_simplified"))
    message = (
        "Generated a scoped structural overview for this DITA XML with Mermaid source and an SVG preview."
        if simplified and svg
        else "Generated a scoped structural overview for this DITA XML with Mermaid source only."
        if simplified
        else "Generated a structural DITA flowchart with Mermaid source and an SVG preview."
        if svg
        else "Generated a structural DITA flowchart with Mermaid source only."
    )
    return {
        "diagram_kind": diagram.get("kind"),
        "title": diagram.get("title"),
        "node_count": len(diagram.get("nodes") or []),
        "edge_count": len(diagram.get("edges") or []),
        "visible_node_count": diagram.get("visible_node_count"),
        "visible_edge_count": diagram.get("visible_edge_count"),
        "total_node_count": diagram.get("total_node_count"),
        "total_edge_count": diagram.get("total_edge_count"),
        "omitted_node_count": diagram.get("omitted_node_count"),
        "omitted_edge_count": diagram.get("omitted_edge_count"),
        "max_visible_nodes": diagram.get("max_visible_nodes"),
        "max_visible_edges": diagram.get("max_visible_edges"),
        "is_simplified": simplified,
        "large_document": bool(diagram.get("large_document")),
        "display_mode": diagram.get("display_mode"),
        "preview_focus": diagram.get("preview_focus"),
        "structure_summary": diagram.get("structure_summary"),
        "xml_profile": diagram.get("xml_profile"),
        "legend": diagram.get("legend") or [],
        "warnings": diagram.get("warnings") or [],
        "mermaid": mermaid,
        "mermaid_data_url": _data_url("text/plain;charset=utf-8", mermaid),
        "preview_svg": svg,
        "preview_svg_data_url": _data_url("image/svg+xml", svg) if svg else "",
        "message": message,
        "summary": diagram.get("structure_summary") or message,
    }


def _seeded_palette(prompt: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    hues = [int(digest[idx: idx + 2], 16) for idx in (0, 2, 4)]
    colors = []
    for hue in hues:
        degrees = int((hue / 255) * 360)
        colors.append(f"hsl({degrees} 78% 58%)")
    return colors[0], colors[1], colors[2]


def _local_svg_image(prompt: str, *, size: str = "1024x1024", style: str | None = None) -> dict[str, Any]:
    safe_prompt = prompt.strip() or "Abstract enterprise illustration"
    try:
        width_str, height_str = (size or "1024x1024").lower().split("x", 1)
        width = max(256, min(2048, int(width_str)))
        height = max(256, min(2048, int(height_str)))
    except Exception:
        width, height = 1024, 1024
    primary, secondary, accent = _seeded_palette(safe_prompt + (style or ""))
    digest = hashlib.sha256(f"{safe_prompt}|{style or ''}|{width}x{height}".encode("utf-8")).hexdigest()
    circles = []
    for offset in (0, 8, 16, 24):
        x = 80 + (int(digest[offset: offset + 2], 16) / 255) * (width - 160)
        y = 100 + (int(digest[offset + 2: offset + 4], 16) / 255) * (height - 200)
        radius = 90 + (int(digest[offset + 4: offset + 6], 16) / 255) * 120
        color = [primary, secondary, accent, "#ffffff"][offset // 8]
        opacity = 0.18 if offset < 24 else 0.12
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" opacity="{opacity}" />'
        )

    prompt_lines = _wrap_text(safe_prompt, width=28, max_lines=4)
    style_line = _short_label(style or "prompt to image", max_len=28)
    svg = [
        f'<svg xmlns="{_SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(safe_prompt)}">',
        "<defs>",
        f'<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="{primary}" /><stop offset="50%" stop-color="{secondary}" /><stop offset="100%" stop-color="{accent}" /></linearGradient>',
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="40" fill="url(#bg)" />',
        f'<rect x="36" y="36" width="{max(0, width - 72)}" height="{max(0, height - 72)}" rx="32" fill="#0f172a" fill-opacity="0.18" stroke="#ffffff" stroke-opacity="0.25" />',
        *circles,
        f'<text x="72" y="{height - 150}" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="600" fill="#ffffff" fill-opacity="0.9">{html.escape(style_line)}</text>',
    ]
    for index, line in enumerate(prompt_lines):
        svg.append(
            f'<text x="72" y="{height - 108 + index * 28}" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="{700 if index == 0 else 500}" fill="#ffffff">{html.escape(line)}</text>'
        )
    svg.append("</svg>")
    svg_text = "".join(svg)
    return {
        "provider": "local",
        "model": _LOCAL_IMAGE_MODEL,
        "artifacts": [
            {
                "id": hashlib.md5(svg_text.encode("utf-8")).hexdigest()[:12],
                "mime_type": "image/svg+xml",
                "data_url": _data_url("image/svg+xml", svg_text),
                "inline_svg": svg_text,
                "download_name": "chat-image.svg",
                "width": width,
                "height": height,
                "title": _short_label(safe_prompt, max_len=56),
            }
        ],
        "warning": "Rendered with the built-in SVG fallback because no external image generation provider was used.",
    }


async def _openai_image(prompt: str, *, size: str, style: str | None, count: int) -> dict[str, Any]:
    if not _OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key is not configured for image generation.")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=_OPENAI_API_KEY)
    result = await client.images.generate(
        model=_OPENAI_IMAGE_MODEL,
        prompt=prompt,
        size=size,
        n=max(1, min(count, 4)),
    )
    artifacts = []
    for index, item in enumerate(getattr(result, "data", []) or [], start=1):
        b64_json = getattr(item, "b64_json", None)
        if not b64_json:
            continue
        png_bytes = base64.b64decode(b64_json)
        artifacts.append(
            {
                "id": f"openai-{index}",
                "mime_type": "image/png",
                "data_url": _bytes_to_data_url("image/png", png_bytes),
                "download_name": f"chat-image-{index}.png",
                "title": _short_label(prompt, max_len=56),
            }
        )
    if not artifacts:
        raise RuntimeError("The image provider returned no image artifacts.")
    return {
        "provider": "openai",
        "model": _OPENAI_IMAGE_MODEL,
        "artifacts": artifacts,
        "style": style or "",
    }


async def generate_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    style: str | None = None,
    count: int = 1,
) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "prompt is required"}
    provider = os.getenv("CHAT_IMAGE_PROVIDER", "").strip().lower()
    if provider in {"openai", ""} and _OPENAI_API_KEY:
        try:
            result = await _openai_image(prompt, size=size, style=style, count=count)
            result["message"] = "Generated image artifacts for this prompt."
            return result
        except Exception as exc:
            logger.warning_structured(
                "OpenAI image generation failed; falling back to local SVG",
                extra_fields={"error": str(exc)},
            )
            fallback = _local_svg_image(prompt, size=size, style=style)
            fallback["warning"] = f"OpenAI image generation was unavailable, so the built-in SVG fallback was used instead. ({exc})"
            fallback["message"] = "Generated an image-style SVG fallback for this prompt."
            return fallback

    fallback = _local_svg_image(prompt, size=size, style=style)
    fallback["message"] = "Generated an image-style SVG artifact for this prompt."
    return fallback
