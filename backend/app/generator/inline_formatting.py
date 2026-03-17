"""
Inline formatting recipe - topics with nested <b>, <i>, <u> for RTE/cursor reproduction.

Used when Jira describes cursor navigation, arrow keys, Rich Text Editor behavior,
or issues requiring topics with inline formatting tags (bold, italic, underline).
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id, stable_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml
from app.jobs.schemas import DatasetConfig
from app.utils.xml_escape import xml_escape_text, xml_escape_attr


def _topic_xml(config: DatasetConfig, topic_elem: ET.Element, pretty_print: bool = True) -> bytes:
    """Serialize topic to bytes."""
    xml_body = ET.tostring(topic_elem, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def generate_inline_formatting_nested(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    """
    Generate a topic with nested <b>, <i>, <u> inline formatting for RTE/cursor reproduction.

    Reproduces scenarios like: "cursor jumps when navigating past opening italic tag"
    or "arrow key behavior with nested bold/italic/underline".
    """
    used_ids = set()
    topic_id = make_dita_id("inline_formatting", id_prefix, used_ids)
    filename = "inline_formatting_nested.dita"
    topic_rel = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Inline Formatting Nested Tags"
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = "Topic with nested bold, italic, and underline for RTE cursor navigation reproduction."

    body = ET.SubElement(topic, "body")

    # Paragraph with nested <b><i><u> - for reproducing cursor/arrow key behavior
    p = ET.SubElement(body, "p")
    p.text = "Place cursor before the tag and use arrow keys: "
    b = ET.SubElement(p, "b")
    b.text = "bold "
    i = ET.SubElement(b, "i")
    i.text = "italic "
    u = ET.SubElement(i, "u")
    u.text = "underline"
    u.tail = ""
    i.tail = ""
    b.tail = " and navigate back."

    # Second paragraph with different nesting order
    p2 = ET.SubElement(body, "p")
    p2.text = "Alternate nesting: "
    u2 = ET.SubElement(p2, "u")
    u2.text = "underline "
    i2 = ET.SubElement(u2, "i")
    i2.text = "italic "
    b2 = ET.SubElement(i2, "b")
    b2.text = "bold"
    b2.tail = ""
    i2.tail = ""
    u2.tail = " text."

    topic_path = safe_join(base_path, topic_rel)
    topic_bytes = _topic_xml(config, topic, pretty_print)

    # Map
    map_id = stable_id(config.seed, "inline_formatting_map", "", used_ids)
    win_safe = getattr(config, "windows_safe_filenames", True)
    map_filename = sanitize_filename("inline_formatting.ditamap", win_safe)
    map_path = safe_join(base_path, map_filename)
    from app.generator.generate import _rel_href
    href = _rel_href(map_path, topic_path)
    map_xml = _map_xml(
        config,
        map_id=map_id,
        title="Inline Formatting Map",
        topicref_hrefs=[href],
        keydef_entries=[],
        scoped_blocks=[],
    )

    return {
        topic_path: topic_bytes,
        map_path: map_xml,
    }


RECIPE_SPECS = [
    {
        "id": "inline_formatting_nested",
        "title": "Inline Formatting Nested Tags",
        "description": "Topic with nested <b>, <i>, <u> for RTE cursor navigation, arrow key behavior, or inline formatting reproduction.",
        "tags": ["inline", "b", "i", "u", "RTE", "cursor", "arrow key", "rich text editor"],
        "module": "app.generator.inline_formatting",
        "function": "generate_inline_formatting_nested",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["topic", "p", "b", "i", "u", "body"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["cursor navigation", "arrow key", "RTE", "inline tag", "italic tag", "bold tag", "nested b i u"],
        "avoid_when": ["images", "media", "keyref", "conref"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
