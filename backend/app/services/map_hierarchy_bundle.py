"""
DITA map bundle from diagram / hierarchy outlines (vision → nested topicrefs + topic stubs).

Map relationships are expressed only in the .ditamap (nested topicref); topic bodies are
validation-safe stubs. Paths are relative to the map file (e.g. tasks/foo.dita).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from app.core.schemas_chat_authoring import ChatMapHierarchyNodeType, ChatMapOutlineNode

_MAX_DEPTH = 8
_MAX_NODES = 48

_FOLDER_FOR: dict[str, str] = {
    "concept": "concepts",
    "task": "tasks",
    "reference": "references",
    "topic": "topics",
}


def _slug(text: str, fallback: str = "topic") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (text or "").strip().lower()).strip(".-")
    return (cleaned[:56] if cleaned else fallback) or fallback


def _parse_child(raw: object, depth: int, counter: list[int], warnings: list[str]) -> ChatMapOutlineNode | None:
    if not isinstance(raw, dict):
        return None
    if depth > _MAX_DEPTH:
        warnings.append(f"Truncated hierarchy beyond depth {_MAX_DEPTH}.")
        return None
    if counter[0] >= _MAX_NODES:
        warnings.append(f"Truncated hierarchy beyond {_MAX_NODES} nodes.")
        return None
    counter[0] += 1
    title = str(raw.get("title") or "").strip()[:280]
    dt = str(raw.get("dita_type") or "topic").strip().lower()
    if dt not in {"map_root", "concept", "task", "reference", "topic"}:
        dt = "topic"
    children_raw = raw.get("children")
    child_list = children_raw if isinstance(children_raw, list) else []
    children: list[ChatMapOutlineNode] = []
    for c in child_list:
        node = _parse_child(c, depth + 1, counter, warnings)
        if node is not None:
            children.append(node)
    if not title and dt != "map_root":
        title = f"topic-{counter[0]}"
    conf = raw.get("confidence")
    try:
        cval = float(conf) if conf is not None else 0.75
    except (TypeError, ValueError):
        cval = 0.75
    cval = max(0.0, min(1.0, cval))
    return ChatMapOutlineNode(title=title or "Map", dita_type=dt, children=children, confidence=cval)


def parse_map_outline_payload(raw: dict[str, object]) -> tuple[ChatMapOutlineNode | None, str, float, list[str]]:
    """
    Parse vision JSON into a single root :class:`ChatMapOutlineNode`.

    Accepts ``root`` (object) or ``roots`` (array) — multiple top-level nodes are wrapped
    in a synthetic ``map_root``.
    """
    warnings: list[str] = []
    map_title = str(raw.get("map_title") or "").strip()[:280] or "Generated map"
    try:
        conf = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    for w in raw.get("warnings") or []:
        if str(w).strip():
            warnings.append(str(w).strip()[:500])
    counter = [0]
    root_raw = raw.get("root")
    roots_arr = raw.get("roots")
    tree: ChatMapOutlineNode | None = None
    if isinstance(root_raw, dict):
        tree = _parse_child(root_raw, 0, counter, warnings)
    elif isinstance(roots_arr, list) and roots_arr:
        children: list[ChatMapOutlineNode] = []
        for item in roots_arr:
            n = _parse_child(item, 1, counter, warnings)
            if n is not None:
                children.append(n)
        tree = ChatMapOutlineNode(title="DITA map", dita_type="map_root", children=children, confidence=conf)
    else:
        warnings.append("Model returned no root or roots for the map hierarchy.")
        return None, map_title, conf, warnings

    if tree is None:
        warnings.append("Outline parsing produced an empty tree.")
        return None, map_title, conf, warnings
    if tree.dita_type == "map_root" and not tree.children:
        warnings.append("Map root had no child topics.")
        return None, map_title, conf, warnings
    return tree, map_title, conf, warnings[:24]


@dataclass
class _EnrichedNode:
    title: str
    dita_type: ChatMapHierarchyNodeType
    href: str | None
    children: list[_EnrichedNode]


def _enrich(node: ChatMapOutlineNode, used: set[str]) -> _EnrichedNode:
    if node.dita_type == "map_root":
        return _EnrichedNode(
            title=node.title,
            dita_type="map_root",
            href=None,
            children=[_enrich(c, used) for c in node.children],
        )
    folder = _FOLDER_FOR.get(node.dita_type, "topics")
    base = _slug(node.title)
    rel = f"{folder}/{base}.dita"
    n = 1
    while rel in used:
        n += 1
        rel = f"{folder}/{base}-{n}.dita"
    used.add(rel)
    return _EnrichedNode(
        title=node.title,
        dita_type=node.dita_type,
        href=rel,
        children=[_enrich(c, used) for c in node.children],
    )


def _ensure_map_root_top(en: _EnrichedNode) -> _EnrichedNode:
    if en.dita_type == "map_root":
        return en
    return _EnrichedNode(title="DITA map", dita_type="map_root", href=None, children=[en])


def _render_topicrefs(en: _EnrichedNode, indent: int) -> str:
    pad = " " * indent
    if en.dita_type == "map_root":
        lines = [_render_topicrefs(c, indent) for c in en.children]
        return "\n".join(line for line in lines if line.strip())
    if not en.href:
        return ""
    esc = escape(en.href, {"'": "&apos;", '"': "&quot;"})
    if not en.children:
        return f'{pad}<topicref href="{esc}" type="{en.dita_type}"/>'
    inner = "\n".join(_render_topicrefs(c, indent + 2) for c in en.children)
    return f'{pad}<topicref href="{esc}" type="{en.dita_type}">\n{inner}\n{pad}</topicref>'


def _topic_id_from_href(href: str) -> str:
    stem = Path(href).stem
    return _slug(stem, "topic")


def _stub_topic_xml(en: _EnrichedNode) -> str:
    assert en.href and en.dita_type != "map_root"
    tid = _topic_id_from_href(en.href)
    title = escape(en.title, {"'": "&apos;", '"': "&quot;"})
    short = escape(
        f"Stub topic generated from diagram hierarchy. Replace with product content for «{en.title}».",
        {"'": "&apos;", '"': "&quot;"},
    )
    dt = en.dita_type
    if dt == "task":
        body = (
            f'<task id="{tid}" xml:lang="en-US">\n'
            f"  <title>{title}</title>\n"
            f"  <shortdesc>{short}</shortdesc>\n"
            "  <taskbody>\n"
            "    <context>\n"
            "      <p>Add context from your product documentation.</p>\n"
            "    </context>\n"
            "    <steps>\n"
            "      <step><cmd>Add procedural steps.</cmd></step>\n"
            "    </steps>\n"
            "  </taskbody>\n"
            "</task>\n"
        )
        hdr = '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">\n'
    elif dt == "concept":
        body = (
            f'<concept id="{tid}" xml:lang="en-US">\n'
            f"  <title>{title}</title>\n"
            f"  <shortdesc>{short}</shortdesc>\n"
            "  <conbody>\n"
            "    <p>Add explanatory content.</p>\n"
            "  </conbody>\n"
            "</concept>\n"
        )
        hdr = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">\n'
    elif dt == "reference":
        body = (
            f'<reference id="{tid}" xml:lang="en-US">\n'
            f"  <title>{title}</title>\n"
            f"  <shortdesc>{short}</shortdesc>\n"
            "  <refbody>\n"
            "    <section>\n"
            "      <title>Details</title>\n"
            "      <p>Add parameters, tables, or API details.</p>\n"
            "    </section>\n"
            "  </refbody>\n"
            "</reference>\n"
        )
        hdr = '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">\n'
    else:
        body = (
            f'<topic id="{tid}" xml:lang="en-US">\n'
            f"  <title>{title}</title>\n"
            f"  <shortdesc>{short}</shortdesc>\n"
            "  <body>\n"
            "    <p>Add body content.</p>\n"
            "  </body>\n"
            "</topic>\n"
        )
        hdr = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">\n'
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{hdr}{body}'


def _iter_topic_nodes(en: _EnrichedNode) -> list[_EnrichedNode]:
    out: list[_EnrichedNode] = []
    if en.dita_type != "map_root" and en.href:
        out.append(en)
    for c in en.children:
        out.extend(_iter_topic_nodes(c))
    return out


def _well_formed_xml(xml: str) -> bool:
    try:
        ET.fromstring(xml)
        return True
    except ET.ParseError:
        return False


def build_map_bundle_files(
    root: ChatMapOutlineNode,
    *,
    map_title: str,
    map_basename: str = "generated_map.ditamap",
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Return (files as (relative_path, full_xml)), structural_warnings.

    First file is always the map; remaining entries are topic paths aligned with topicref hrefs.
    """
    warnings: list[str] = []
    used: set[str] = set()
    enriched = _ensure_map_root_top(_enrich(root, used))
    map_id = _slug(map_title, "map")
    inner = _render_topicrefs(enriched, 2)
    if not inner.strip():
        return [], ["No topicref entries to serialize."]
    esc_title = escape(map_title, {"'": "&apos;", '"': "&quot;"})
    map_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">\n'
        f'<map id="{map_id}" xml:lang="en-US">\n'
        f"  <title>{esc_title}</title>\n"
        f"{inner}\n"
        "</map>\n"
    )
    if not _well_formed_xml(map_xml):
        return [], ["Generated map XML failed well-formedness check."]
    files: list[tuple[str, str]] = [(map_basename, map_xml)]
    for node in _iter_topic_nodes(enriched):
        assert node.href
        tx = _stub_topic_xml(node)
        if not _well_formed_xml(tx):
            warnings.append(f"Skipping malformed stub for {node.href}")
            continue
        files.append((node.href.replace("\\", "/"), tx))
    if len(files) < 2:
        warnings.append("Map has no serializable topic files.")
    return files, warnings
