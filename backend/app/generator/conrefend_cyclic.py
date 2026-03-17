"""
Conrefend + Cyclic References - minimal repro for false "Duplicate ID" warnings.

Reproduces: False "Duplicate ID" Warnings in Guides Web Editor when conrefend + Cyclic References
(IBM / AEM Guides scenario).

Structure:
- Topic A: conref+conrefend range pulling from Topic B
- Topic B: conref+conrefend range pulling from Topic A (cycle)
- When the editor resolves conrefend ranges, the same element IDs can appear multiple times
  in the resolved DOM, triggering false duplicate ID warnings.
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


def generate_conrefend_cyclic_duplicate_id(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate minimal repro: conrefend + cyclic references causing false duplicate ID warnings.

    Topic A conrefs (range) to Topic B; Topic B conrefs (range) back to Topic A.
    Both use conref+conrefend. When resolved in Guides Web Editor, duplicate ID warnings may appear.
    """
    used_ids = set()
    root = f"{base_path}/conrefend_cyclic"
    topics_dir = f"{root}/topics"
    maps_dir = f"{root}/maps"

    topic_a_id = make_dita_id("conrefend_cyclic_a", id_prefix, used_ids)
    topic_b_id = make_dita_id("conrefend_cyclic_b", id_prefix, used_ids)
    range_start_a = make_dita_id("range_start", id_prefix, used_ids)
    range_mid_a = make_dita_id("range_mid", id_prefix, used_ids)
    range_end_a = make_dita_id("range_end", id_prefix, used_ids)
    range_start_b = make_dita_id("range_start_b", id_prefix, used_ids)
    range_mid_b = make_dita_id("range_mid_b", id_prefix, used_ids)
    range_end_b = make_dita_id("range_end_b", id_prefix, used_ids)

    topic_a_path = f"{topics_dir}/topic_a.dita"
    topic_b_path = f"{topics_dir}/topic_b.dita"

    # --- Topic A: has reusable range + conrefend to Topic B ---
    topic_a = ET.Element("topic", {"id": topic_a_id, "xml:lang": "en"})
    ET.SubElement(topic_a, "title").text = "Topic A (conrefend to B)"
    body_a = ET.SubElement(topic_a, "body")

    p1_a = ET.SubElement(body_a, "p")
    p1_a.set("id", range_start_a)
    p1_a.text = "Topic A range start."
    p2_a = ET.SubElement(body_a, "p")
    p2_a.set("id", range_mid_a)
    p2_a.text = "Topic A middle."
    p3_a = ET.SubElement(body_a, "p")
    p3_a.set("id", range_end_a)
    p3_a.text = "Topic A range end."

    # p conref/conrefend: must match referenced element type (p)
    p_conref_a = ET.SubElement(body_a, "p")
    p_conref_a.set("conref", f"topic_b.dita#{topic_b_id}/{range_start_b}")
    p_conref_a.set("conrefend", f"topic_b.dita#{topic_b_id}/{range_end_b}")

    # --- Topic B: has reusable range + conrefend to Topic A (cycle) ---
    topic_b = ET.Element("topic", {"id": topic_b_id, "xml:lang": "en"})
    ET.SubElement(topic_b, "title").text = "Topic B (conrefend to A)"
    body_b = ET.SubElement(topic_b, "body")

    p1_b = ET.SubElement(body_b, "p")
    p1_b.set("id", range_start_b)
    p1_b.text = "Topic B range start."
    p2_b = ET.SubElement(body_b, "p")
    p2_b.set("id", range_mid_b)
    p2_b.text = "Topic B middle."
    p3_b = ET.SubElement(body_b, "p")
    p3_b.set("id", range_end_b)
    p3_b.text = "Topic B range end."

    # p conref/conrefend: must match referenced element type (p)
    p_conref_b = ET.SubElement(body_b, "p")
    p_conref_b.set("conref", f"topic_a.dita#{topic_a_id}/{range_start_a}")
    p_conref_b.set("conrefend", f"topic_a.dita#{topic_a_id}/{range_end_a}")

    # --- Map ---
    map_elem = ET.Element("map", {"id": make_dita_id("conrefend_cyclic_map", id_prefix, used_ids)})
    ET.SubElement(map_elem, "title").text = "Conrefend Cyclic Duplicate ID Repro"
    tr_a = ET.SubElement(map_elem, "topicref")
    tr_a.set("href", "../topics/topic_a.dita")
    tr_a.set("type", "topic")
    tr_b = ET.SubElement(map_elem, "topicref")
    tr_b.set("href", "../topics/topic_b.dita")
    tr_b.set("type", "topic")

    readme = """Conrefend + Cyclic References - False Duplicate ID Warnings
============================================================

Reproduces: False "Duplicate ID" Warnings in Guides Web Editor when conrefend + Cyclic References.

Structure:
- topic_a.dita: conref+conrefend range pulls from topic_b.dita (range_start_b to range_end_b)
- topic_b.dita: conref+conrefend range pulls from topic_a.dita (range_start_a to range_end_a)

Cycle: A -> B -> A. When the editor resolves conrefend, the same element IDs can appear
multiple times in the resolved DOM, triggering false duplicate ID warnings.

Expected: Open in AEM Guides Web Editor; may see duplicate ID warnings in Source view
even though the content is valid and publishes correctly.
"""

    return {
        topic_a_path: _topic_xml(config, topic_a, pretty_print),
        topic_b_path: _topic_xml(config, topic_b, pretty_print),
        f"{maps_dir}/main.ditamap": _map_xml(config, map_elem, pretty_print),
        f"{root}/README.txt": readme.encode("utf-8"),
    }


RECIPE_SPECS = [
    {
        "id": "conrefend_cyclic_duplicate_id",
        "mechanism_family": "conref",
        "title": "Conrefend Cyclic Duplicate ID",
        "description": "Minimal repro: conrefend + cyclic references causing false duplicate ID warnings in Guides Web Editor. Topic A conrefs (range) to B; B conrefs (range) back to A.",
        "tags": ["conref", "conrefend", "cyclic", "duplicate id", "range", "IBM", "Guides Web Editor"],
        "module": "app.generator.conrefend_cyclic",
        "function": "generate_conrefend_cyclic_duplicate_id",
        "params_schema": {"id_prefix": "str", "pretty_print": "bool"},
        "default_params": {"id_prefix": "t", "pretty_print": True},
        "stability": "stable",
        "constructs": ["conref", "conrefend", "p", "topic"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "conrefend cyclic",
            "conrefend duplicate id",
            "false duplicate ID warnings",
            "Guides Web Editor duplicate ID",
            "conrefend + cyclic references",
        ],
        "avoid_when": ["single topic", "no conrefend", "no cyclic"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
