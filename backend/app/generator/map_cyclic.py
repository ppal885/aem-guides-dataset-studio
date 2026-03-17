"""
Map Cyclic References - minimal repro for mapref cycle.

Structure:
- map_a.ditamap: topicref to topic_a.dita, mapref to map_b.ditamap
- map_b.ditamap: topicref to topic_b.dita, mapref to map_a.ditamap

Cycle: map_a -> map_b -> map_a
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig


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


def _map_xml(config: DatasetConfig, map_elem: ET.Element, pretty_print: bool = True) -> bytes:
    """Serialize map to bytes."""
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


def generate_map_cyclic(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate minimal repro: mapref cycle (map_a -> map_b -> map_a).

    map_a.ditamap has mapref to map_b.ditamap
    map_b.ditamap has mapref to map_a.ditamap
    """
    used_ids = set()
    root = f"{base_path}/map_cyclic"
    topics_dir = f"{root}/topics"
    maps_dir = f"{root}/maps"

    topic_a_id = make_dita_id("map_cyclic_a", id_prefix, used_ids)
    topic_b_id = make_dita_id("map_cyclic_b", id_prefix, used_ids)
    map_a_id = make_dita_id("map_cyclic_map_a", id_prefix, used_ids)
    map_b_id = make_dita_id("map_cyclic_map_b", id_prefix, used_ids)

    # --- Topic A ---
    topic_a = ET.Element("topic", {"id": topic_a_id, "xml:lang": "en"})
    ET.SubElement(topic_a, "title").text = "Topic A"
    body_a = ET.SubElement(topic_a, "body")
    ET.SubElement(body_a, "p").text = "Content in Topic A."

    # --- Topic B ---
    topic_b = ET.Element("topic", {"id": topic_b_id, "xml:lang": "en"})
    ET.SubElement(topic_b, "title").text = "Topic B"
    body_b = ET.SubElement(topic_b, "body")
    ET.SubElement(body_b, "p").text = "Content in Topic B."

    # --- Map A: topicref to A, mapref to map_b (cycle) ---
    map_a = ET.Element("map", {"id": map_a_id})
    ET.SubElement(map_a, "title").text = "Map A (references Map B)"
    ET.SubElement(map_a, "topicref", {"href": "../topics/topic_a.dita", "type": "topic"})
    ET.SubElement(map_a, "mapref", {"href": "map_b.ditamap"})

    # --- Map B: topicref to B, mapref to map_a (cycle) ---
    map_b = ET.Element("map", {"id": map_b_id})
    ET.SubElement(map_b, "title").text = "Map B (references Map A)"
    ET.SubElement(map_b, "topicref", {"href": "../topics/topic_b.dita", "type": "topic"})
    ET.SubElement(map_b, "mapref", {"href": "map_a.ditamap"})

    readme = """Map Cyclic References
====================

Structure:
- map_a.ditamap: topicref to topic_a.dita, mapref to map_b.ditamap
- map_b.ditamap: topicref to topic_b.dita, mapref to map_a.ditamap

Cycle: map_a -> map_b -> map_a

Open map_a.ditamap as the root. Processors may warn about or reject the cyclic mapref.
"""

    return {
        f"{topics_dir}/topic_a.dita": _topic_xml(config, topic_a, pretty_print),
        f"{topics_dir}/topic_b.dita": _topic_xml(config, topic_b, pretty_print),
        f"{maps_dir}/map_a.ditamap": _map_xml(config, map_a, pretty_print),
        f"{maps_dir}/map_b.ditamap": _map_xml(config, map_b, pretty_print),
        f"{root}/README.txt": readme.encode("utf-8"),
    }


RECIPE_SPECS = [
    {
        "id": "map_cyclic",
        "mechanism_family": "map_hierarchy",
        "title": "Map Cyclic References",
        "description": "Minimal repro: mapref cycle. map_a references map_b, map_b references map_a.",
        "tags": ["map", "mapref", "cyclic", "map cycle", "circular reference"],
        "module": "app.generator.map_cyclic",
        "function": "generate_map_cyclic",
        "params_schema": {"id_prefix": "str", "pretty_print": "bool"},
        "default_params": {"id_prefix": "t", "pretty_print": True},
        "stability": "stable",
        "constructs": ["mapref", "topicref", "map", "topic"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["map cyclic", "mapref cycle", "circular map reference"],
        "avoid_when": ["single map", "no mapref"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
