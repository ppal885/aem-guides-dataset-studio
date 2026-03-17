"""
DITA Subject Scheme Dataset - subject scheme maps and topics for controlled attribute validation.

Generates:
- subject-scheme.ditamap: SubjectScheme with audience-values (beginner, intermediate, advanced)
- root-map.ditamap: References subject-scheme + topics
- topic_valid_01.dita through topic_valid_10.dita: Valid audience values
- topic_invalid_01.dita through topic_invalid_10.dita: Invalid values (expert, invalid, etc.)
- dataset_manifest.json

Used for: AEM Guides QA, subject scheme validation testing.
"""
import json
import xml.etree.ElementTree as ET
from typing import Dict, List

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


VALID_VALUES = ["beginner", "intermediate", "advanced"]
INVALID_VALUES = ["expert", "invalid", "foo", "bar", "unknown", "custom", "test", "x", "y", "z"]


def _topic_xml(config: DatasetConfig, topic_elem: ET.Element, pretty_print: bool = True) -> bytes:
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


def _build_subject_scheme() -> ET.Element:
    scheme = ET.Element("subjectScheme")
    scheme.set("id", "subject-scheme-audience")
    subjectdef = ET.SubElement(scheme, "subjectdef", {"keys": "audience-values"})
    for v in VALID_VALUES:
        ET.SubElement(subjectdef, "subjectdef", {"keys": v})
    enumdef = ET.SubElement(scheme, "enumerationdef")
    ET.SubElement(enumdef, "elementdef", {"name": "topic"})
    ET.SubElement(enumdef, "attributedef", {"name": "audience"})
    ET.SubElement(enumdef, "subjectdef", {"keyref": "audience-values"})
    return scheme


def _build_topic(topic_id: str, title: str, body_audience: str, body_text: str) -> ET.Element:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    body = ET.SubElement(topic, "body", {"audience": body_audience} if body_audience else {})
    p = ET.SubElement(body, "p")
    p.text = body_text
    return topic


def generate_dita_subject_scheme_dataset(
    config: DatasetConfig,
    base_path: str,
    valid_count: int = 10,
    invalid_count: int = 10,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    win_safe = getattr(config, "windows_safe_filenames", True)
    used_ids: set[str] = set()
    root = f"{base_path}/dita_subject_scheme_dataset"

    files: Dict[str, bytes] = {}

    scheme_filename = sanitize_filename("subject-scheme.ditamap", win_safe)
    scheme_path = f"{root}/{scheme_filename}"
    scheme_elem = _build_subject_scheme()
    files[scheme_path] = _map_xml(config, scheme_elem, pretty_print)

    valid_paths = []
    for i in range(1, valid_count + 1):
        topic_id = make_dita_id(f"topic_valid_{i:02d}", id_prefix, used_ids)
        topic_filename = sanitize_filename(f"topic_valid_{i:02d}.dita", win_safe)
        topic_path = f"{root}/{topic_filename}"
        audience = VALID_VALUES[(i - 1) % len(VALID_VALUES)]
        topic_elem = _build_topic(
            topic_id,
            "Valid Audience Topic",
            audience,
            "This topic uses a valid controlled value.",
        )
        files[topic_path] = _topic_xml(config, topic_elem, pretty_print)
        valid_paths.append(topic_filename)

    invalid_paths = []
    for i in range(1, invalid_count + 1):
        topic_id = make_dita_id(f"topic_invalid_{i:02d}", id_prefix, used_ids)
        topic_filename = sanitize_filename(f"topic_invalid_{i:02d}.dita", win_safe)
        topic_path = f"{root}/{topic_filename}"
        audience = INVALID_VALUES[(i - 1) % len(INVALID_VALUES)]
        topic_elem = _build_topic(
            topic_id,
            "Invalid Audience Topic",
            audience,
            "This topic intentionally violates the subject scheme.",
        )
        files[topic_path] = _topic_xml(config, topic_elem, pretty_print)
        invalid_paths.append(topic_filename)

    root_map = ET.Element("map", {"id": make_dita_id("root_map", id_prefix, used_ids)})
    ET.SubElement(root_map, "title").text = "Subject Scheme Root Map"
    tr_scheme = ET.SubElement(root_map, "topicref", {"href": scheme_filename, "type": "subjectScheme"})
    tr_scheme.set("format", "ditamap")
    for fn in valid_paths[:5]:
        ET.SubElement(root_map, "topicref", {"href": fn})
    for fn in invalid_paths[:5]:
        ET.SubElement(root_map, "topicref", {"href": fn})

    root_map_path = f"{root}/root-map.ditamap"
    files[root_map_path] = _map_xml(config, root_map, pretty_print)

    manifest = {
        "dataset_name": "dita_subject_scheme_dataset",
        "valid_topics": valid_count,
        "invalid_topics": invalid_count,
        "dita_feature": "subject_scheme",
        "purpose": "Subject scheme validation testing",
        "recipe_name": "dita_subject_scheme_dataset_recipe",
        "files": list(files.keys()),
        "stats": {"valid_count": valid_count, "invalid_count": invalid_count},
    }
    manifest_path = f"{root}/dataset_manifest.json"
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "dita_subject_scheme_dataset_recipe",
        "mechanism_family": "metadata",
        "title": "Subject Scheme Dataset",
        "description": "Subject scheme maps and topics for controlled attribute validation. Valid and invalid audience topics.",
        "tags": ["subject scheme", "subjectdef", "enumerationdef", "audience", "controlled values"],
        "module": "app.generator.subject_scheme",
        "function": "generate_dita_subject_scheme_dataset",
        "params_schema": {"valid_count": "int", "invalid_count": "int", "id_prefix": "str", "pretty_print": "bool"},
        "default_params": {"valid_count": 10, "invalid_count": 10, "id_prefix": "t", "pretty_print": True},
        "stability": "stable",
        "constructs": ["subjectScheme", "subjectdef", "enumerationdef", "topic", "audience"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["subject scheme", "controlled values", "audience validation"],
        "avoid_when": ["no subject scheme", "generic topics"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "small",
    },
]
