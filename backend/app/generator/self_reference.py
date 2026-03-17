"""
Self-Reference Dataset Generator.

Generates a DITA dataset for testing self-reference in AEM Guides:
- Topic with keyref pointing to itself (keydef in map points to same topic)
- Reproduces "self reference showing as forward reference (outgoing links) is showing empty in right panel"
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig

RECIPE_SPECS = [
    {
        "id": "self_reference",
        "title": "Self Reference",
        "description": "Generate topic with keyref pointing to itself for testing self-reference in outgoing links panel",
        "tags": ["keyref", "keydef", "self", "forward reference", "outgoing links"],
        "module": "app.generator.self_reference",
        "function": "generate_self_reference_dataset",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["keyref", "keydef", "topicref"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["self reference", "keyref to self", "outgoing links panel", "forward reference"],
        "avoid_when": ["cross-topic keyref", "no key usage"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_content: str, pretty_print: bool = True) -> bytes:
    """Generate topic XML."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})

    title_elem = ET.SubElement(topic, "title")
    title_elem.text = title

    body = ET.SubElement(topic, "body")
    try:
        body_elem = ET.fromstring(f"<body>{body_content}</body>")
        for child in body_elem:
            body.append(child)
    except ET.ParseError:
        p_elem = ET.SubElement(body, "p")
        p_elem.text = body_content

    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)

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


def _map_xml(
    config: DatasetConfig,
    map_id: str,
    title: str,
    keydefs: list,
    topicrefs: list,
    pretty_print: bool = True,
) -> bytes:
    """Generate map XML."""
    map_elem = ET.Element("map", {"id": map_id})

    title_elem = ET.SubElement(map_elem, "title")
    title_elem.text = title

    for keydef in keydefs:
        keydef_elem = ET.SubElement(map_elem, "keydef")
        for key, value in keydef.items():
            if key == "keys":
                keydef_elem.set("keys", value)
            elif key == "href":
                keydef_elem.set("href", value)

    for topicref in topicrefs:
        topicref_elem = ET.SubElement(map_elem, "topicref")
        for key, value in topicref.items():
            topicref_elem.set(key, value)

    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)

    if pretty_print:
        try:
            from xml.dom import minidom

            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass

    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    return doc.encode("utf-8") + xml_body


def generate_self_reference_dataset(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate self-reference dataset.

    Creates a topic that references itself via keyref. The keydef in the map
    points to the same topic. Used for testing AEM Guides right panel
    (outgoing links / forward reference) when self-reference is present.

    Args:
        config: Dataset configuration
        base_path: Base path for dataset files
        id_prefix: Prefix for generated IDs
        pretty_print: Pretty print XML output

    Returns:
        Dictionary of file paths to file contents (bytes)
    """
    files = {}
    used_ids = set()

    root_folder = f"{base_path}/aem_guides_self_reference"
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"

    map_id = make_dita_id("map_self_ref", id_prefix, used_ids)
    topic_id = make_dita_id("t_self_ref", id_prefix, used_ids)

    topic_path = f"{topics_folder}/self_ref_topic.dita"
    map_path = f"{maps_folder}/self_ref_map.ditamap"

    body_content = (
        '<p>This topic references itself: <xref keyref="self"/>. '
        "The key \"self\" in the map points to this same topic. "
        "In AEM Guides, the right panel (outgoing links / forward reference) "
        "should show this self-reference.</p>"
    )

    files[topic_path] = _topic_xml(
        config,
        topic_id,
        "Self-Reference Topic",
        body_content,
        pretty_print,
    )

    keydefs = [
        {"keys": "self", "href": "../topics/self_ref_topic.dita"},
    ]
    topicrefs = [
        {"href": "../topics/self_ref_topic.dita", "navtitle": "Self-Reference Topic", "type": "topic"},
    ]

    files[map_path] = _map_xml(
        config,
        map_id,
        "Self-Reference Map",
        keydefs,
        topicrefs,
        pretty_print,
    )

    readme_content = """Self-Reference Dataset
====================

This dataset demonstrates a topic that references itself via keyref.

Structure:
- Map defines key "self" -> self_ref_topic.dita
- Topic self_ref_topic.dita contains <xref keyref="self"/> (points to itself)

Use case: Testing AEM Guides right panel (outgoing links / forward reference)
when displaying self-reference. Bug GUIDES-42286: self reference may show
empty in right panel.
"""
    files[f"{root_folder}/README.txt"] = readme_content.encode("utf-8")

    return files
