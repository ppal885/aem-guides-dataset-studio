"""
Validation / Negative recipe family - duplicate ID, invalid structure, missing required.

Generates intentionally invalid DITA for validation testing.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.jobs.schemas import DatasetConfig


def _topic_xml(config: DatasetConfig, topic_elem: ET.Element, pretty: bool = True) -> bytes:
    xml_body = ET.tostring(topic_elem, encoding="utf-8", xml_declaration=False)
    if pretty:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'.encode("utf-8") + xml_body


def _map_xml(config: DatasetConfig, map_elem: ET.Element, pretty: bool = True) -> bytes:
    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    if pretty:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'.encode("utf-8") + xml_body


def generate_validation_duplicate_id_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: duplicate ID in same document."""
    used = set()
    tid = stable_id("val_dup", id_prefix, "topic", used)
    root = f"{base_path}/validation_duplicate_id_negative"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Duplicate ID Negative"
    body = ET.SubElement(topic, "body")
    sec1 = ET.SubElement(body, "section", {"id": "dup_id"})
    ET.SubElement(sec1, "title").text = "Section 1"
    ET.SubElement(sec1, "p").text = "Content."
    sec2 = ET.SubElement(body, "section", {"id": "dup_id"})  # duplicate
    ET.SubElement(sec2, "title").text = "Section 2"
    ET.SubElement(sec2, "p").text = "Content."
    return {f"{root}/topics/main.dita": _topic_xml(config, topic)}


def generate_validation_invalid_child_structure(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: invalid child structure (e.g. body inside body)."""
    used = set()
    tid = stable_id("val_inv", id_prefix, "topic", used)
    root = f"{base_path}/validation_invalid_child_structure"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Invalid Child"
    body = ET.SubElement(topic, "body")
    inner_body = ET.SubElement(body, "body")  # invalid: body inside body
    ET.SubElement(inner_body, "p").text = "Invalid."
    return {f"{root}/topics/main.dita": _topic_xml(config, topic)}


def generate_validation_missing_required_element(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: topic without required body."""
    used = set()
    tid = stable_id("val_miss", id_prefix, "topic", used)
    root = f"{base_path}/validation_missing_required_element"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Missing Body"
    # No body - invalid
    return {f"{root}/topics/main.dita": _topic_xml(config, topic)}


def generate_validation_invalid_map_structure(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: map with invalid structure (e.g. topicref without href)."""
    used = set()
    map_id = stable_id("val_map", id_prefix, "map", used)
    root = f"{base_path}/validation_invalid_map_structure"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Invalid Map"
    ET.SubElement(map_elem, "topicref")  # no href - invalid
    return {f"{root}/maps/main.ditamap": _map_xml(config, map_elem)}


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["topic", "map", "section", "body"],
        "scenario_types": ["NEGATIVE"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": "negative",
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.validation_negative",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("validation.duplicate_id_negative", "Duplicate ID Negative", "Negative: duplicate ID in document.", "generate_validation_duplicate_id_negative",
          ["VALIDATION", "NEGATIVE", "DUPLICATE_ID"], ["validation", "duplicate id", "negative test"], ["valid dataset"]),
    _spec("validation.invalid_child_structure", "Invalid Child Structure", "Negative: invalid child structure.", "generate_validation_invalid_child_structure",
          ["VALIDATION", "NEGATIVE", "STRUCTURE"], ["validation", "invalid structure"], ["valid dataset"]),
    _spec("validation.missing_required_element", "Missing Required Element", "Negative: missing required body.", "generate_validation_missing_required_element",
          ["VALIDATION", "NEGATIVE", "REQUIRED"], ["validation", "missing element"], ["valid dataset"]),
    _spec("validation.invalid_map_structure", "Invalid Map Structure", "Negative: invalid map structure.", "generate_validation_invalid_map_structure",
          ["VALIDATION", "NEGATIVE", "MAP"], ["validation", "invalid map"], ["valid dataset"]),
]
