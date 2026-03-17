"""
Evidence-to-DITA fallback recipe.

Generates DITA from Representative Sample XML when no specific recipe matches.
Used when the planner returns {"recipes": []} but content_from_evidence has representative_xml.
Parses XML snippets from Jira, writes valid DITA files with deterministic IDs.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig

RECIPE_SPECS = [
    {
        "id": "evidence_to_dita",
        "title": "Evidence to DITA",
        "description": "Generate DITA from Representative Sample XML when no matching recipe exists. Parses XML snippets from Jira and writes valid DITA files.",
        "tags": ["Representative Sample", "evidence XML", "fallback", "no matching recipe"],
        "module": "app.generator.evidence_to_dita",
        "function": "generate_evidence_to_dita",
        "params_schema": {"representative_xml": "list"},
        "default_params": {},
        "stability": "stable",
        "constructs": ["map", "topic", "topicref", "keydef", "keyref"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["Representative Sample", "evidence XML", "no matching recipe"],
        "avoid_when": ["specific recipe matches"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]


def _minimal_topic_xml(
    config: DatasetConfig,
    topic_id: str,
    title: str = "Placeholder",
    body_text: Optional[str] = None,
) -> bytes:
    """Generate minimal valid topic when XML parse fails.
    If body_text is provided, use it (escaped, truncated to 500 chars); else use default.
    """
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    # ElementTree escapes text on serialization; truncate for safety
    ET.SubElement(topic, "title").text = (title or "Placeholder")[:200]
    body = ET.SubElement(topic, "body")
    if body_text and str(body_text).strip():
        ET.SubElement(body, "p").text = str(body_text).strip()[:500]
    else:
        ET.SubElement(body, "p").text = "Content from Representative Sample (parse fallback)."
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _ensure_root_tag(xml_str: str, default: str = "topic") -> str:
    """Wrap fragment in root element if needed. Detect map vs topic from content."""
    s = (xml_str or "").strip()
    if not s:
        return f"<{default} id=\"placeholder\"><title>Placeholder</title><body><p>Empty</p></body></{default}>"
    s_lower = s.lower()
    if s_lower.startswith("<map"):
        return s
    if s_lower.startswith("<topic"):
        return s
    if "<map " in s_lower or "<map>" in s_lower or "ditamap" in s_lower:
        if not re.search(r"<map[\s>]", s_lower):
            return f"<map id=\"evidence_map\">{s}</map>"
        return s
    if "<topic " in s_lower or "<topic>" in s_lower:
        if not re.search(r"<topic[\s>]", s_lower):
            return f"<topic id=\"evidence_topic\" xml:lang=\"en\">{s}</topic>"
        return s
    return f"<topic id=\"evidence_topic\" xml:lang=\"en\">{s}</topic>"


def _extract_root_tag(root: ET.Element) -> str:
    """Get root tag name (map or topic)."""
    tag = root.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.lower()


def _looks_like_dita(text: str) -> bool:
    """Check if text contains DITA-like tags. Reject HTML, JSON, plain text."""
    t = (text or "").lower()
    if not t.strip():
        return False
    dita_tags = ("<map", "<topic", "<keydef", "<topicref", "<keyref", "<section", "<body", "<p ")
    if any(tag in t for tag in dita_tags):
        return True
    return False


def _is_non_dita(text: str) -> bool:
    """Reject content that is clearly not DITA (HTML, JSON, etc.)."""
    t = (text or "").lower().strip()
    if "<html" in t or "<!doctype html" in t or "<script" in t or "<style" in t:
        return True
    if t.startswith("{") or t.startswith("["):
        return True
    return False


def _validate_representative_xml(snippets: List[str], max_items: int = 6, max_chars: int = 2000) -> List[str]:
    """
    Filter representative_xml: keep only items that parse as XML and contain DITA-like tags.
    Reject HTML, JSON, plain text. Cap items and chars.
    """
    out: List[str] = []
    for s in (snippets or [])[:max_items * 2]:
        if not s or not isinstance(s, str):
            continue
        s = s.strip()[:max_chars]
        if not s or _is_non_dita(s) or not _looks_like_dita(s):
            continue
        try:
            ET.fromstring(_ensure_root_tag(s))
        except ET.ParseError:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


EVIDENCE_TO_DITA_MAX_FILES = 20


def generate_evidence_to_dita(
    config: DatasetConfig,
    base_path: str,
    representative_xml: Optional[List[str]] = None,
    id_prefix: str = "ev",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Parse representative_xml snippets and write valid DITA files.
    On parse failure, writes minimal placeholder topic.
    Input validation: filter to DITA-like XML, reject HTML/JSON. Output cap: max 20 files.
    """
    files: Dict[str, bytes] = {}
    used_ids: set = set()
    raw = representative_xml or []
    snippets = _validate_representative_xml(raw, max_items=6, max_chars=2000)

    if not snippets:
        root = f"{base_path}/evidence_to_dita"
        placeholder_id = make_dita_id("placeholder", id_prefix, used_ids)
        files[f"{root}/topics/placeholder.dita"] = _minimal_topic_xml(
            config, placeholder_id, "No Representative Sample"
        )
        return files

    root_folder = f"{base_path}/evidence_to_dita"
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"
    Path(maps_folder).mkdir(parents=True, exist_ok=True)
    Path(topics_folder).mkdir(parents=True, exist_ok=True)

    map_files: List[str] = []
    topic_files: List[str] = []

    file_count = 0
    for i, snippet in enumerate(snippets):
        if file_count >= EVIDENCE_TO_DITA_MAX_FILES:
            break
        if not snippet or not isinstance(snippet, str):
            continue
        snippet = snippet.strip()
        if not snippet:
            continue

        wrapped = _ensure_root_tag(snippet)
        try:
            root_elem = ET.fromstring(wrapped)
        except ET.ParseError:
            pid = make_dita_id(f"parse_fail_{i}", id_prefix, used_ids)
            files[f"{topics_folder}/parse_fail_{i}.dita"] = _minimal_topic_xml(
                config, pid, f"Parse fallback {i}"
            )
            continue

        tag = _extract_root_tag(root_elem)
        elem_id = root_elem.get("id") or root_elem.get("{http://www.w3.org/XML/1998/namespace}id")
        if not elem_id:
            elem_id = make_dita_id(f"elem_{i}", id_prefix, used_ids)
            root_elem.set("id", elem_id)
        used_ids.add(elem_id)

        if tag == "map":
            fname = f"evidence_map_{i}.ditamap"
            out_path = f"{maps_folder}/{fname}"
            map_files.append(out_path)
        else:
            fname = f"evidence_topic_{i}.dita"
            out_path = f"{topics_folder}/{fname}"
            topic_files.append(out_path)

        xml_bytes = ET.tostring(root_elem, encoding="utf-8", xml_declaration=False)
        if pretty_print:
            try:
                from xml.dom import minidom
                dom = minidom.parseString(xml_bytes)
                xml_bytes = dom.toprettyxml(indent="  ", encoding="utf-8")
                xml_bytes = xml_bytes.split(b"\n", 1)[1] if b"\n" in xml_bytes else xml_bytes
            except Exception:
                pass

        doctype = config.doctype_map if tag == "map" else config.doctype_topic
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}\n'
        files[out_path] = doc.encode("utf-8") + xml_bytes
        file_count += 1

    readme = f"""Evidence-to-DITA Dataset
========================

Generated from Jira Representative Sample XML ({len(snippets)} snippets).
Maps: {len(map_files)}, Topics: {len(topic_files)}
"""
    files[f"{root_folder}/README.txt"] = readme.encode("utf-8")
    return files
