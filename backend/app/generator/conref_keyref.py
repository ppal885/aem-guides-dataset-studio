"""
DITA Conref + Keyref Dataset - topics demonstrating conref and keyref combinations.

Generates:
- keydef-map.ditamap: Map with keydefs pointing to variables.dita ph elements
- variables.dita: Topic with ph elements (product_name, release_name)
- topic_conref_keyref_01.dita through topic_conref_keyref_15.dita: Variants (conref only, keyref only, conref+keyref, nested)
- dataset_manifest.json

Used for: AEM Guides QA, conref/keyref resolution testing, LLM training, Jira reproduction.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


DEFAULT_VARIABLES = [
    ("product_name", "AEM Guides"),
    ("release_name", "Build-2026"),
]

# Topic variant: 0=conref only, 1=keyref only, 2=conref+keyref, 3=nested
VARIANT_CONREF_ONLY = 0
VARIANT_KEYREF_ONLY = 1
VARIANT_CONREF_KEYREF = 2
VARIANT_NESTED = 3


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


def _build_variables_topic(config: DatasetConfig, vars_id: str, variables: List[Tuple[str, str]]) -> ET.Element:
    topic = ET.Element("topic", {"id": vars_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Variables"
    body = ET.SubElement(topic, "body")
    for ph_id, content in variables:
        p = ET.SubElement(body, "p")
        ph = ET.SubElement(p, "ph", {"id": ph_id})
        ph.text = content
    return topic


def _build_topic_variant(
    topic_id: str,
    variant: int,
    variables_filename: str,
    vars_id: str,
    key_product: str,
    key_release: str,
) -> ET.Element:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Conref + Keyref Example"
    body = ET.SubElement(topic, "body")

    if variant == VARIANT_CONREF_ONLY:
        p = ET.SubElement(body, "p")
        p.set("conref", f"{variables_filename}#{vars_id}/product_name")
    elif variant == VARIANT_KEYREF_ONLY:
        p = ET.SubElement(body, "p")
        p.text = "The current release is "
        ph = ET.SubElement(p, "ph", {"keyref": key_release})
        ph.tail = "."
    elif variant == VARIANT_CONREF_KEYREF:
        p1 = ET.SubElement(body, "p")
        p1.set("conref", f"{variables_filename}#{vars_id}/product_name")
        p2 = ET.SubElement(body, "p")
        p2.text = "The current release is "
        ph = ET.SubElement(p2, "ph", {"keyref": key_release})
        ph.tail = "."
    else:  # VARIANT_NESTED
        p = ET.SubElement(body, "p")
        p.text = "Product: "
        ph = ET.SubElement(p, "ph", {"keyref": key_product})
        ph.tail = " | Release: "
        ph2 = ET.SubElement(p, "ph", {"keyref": key_release})
        ph2.tail = "."
        p2 = ET.SubElement(body, "p")
        p2.set("conref", f"{variables_filename}#{vars_id}/release_name")

    return topic


def validate_dita_structure(files: Dict[str, bytes]) -> List[str]:
    errors: List[str] = []
    all_ids: Dict[str, str] = {}
    parsed: Dict[str, ET.Element] = {}

    for path, content in files.items():
        if not path.endswith((".dita", ".ditamap")):
            continue
        try:
            root = ET.fromstring(content)
            parsed[path] = root
        except ET.ParseError as e:
            errors.append(f"{path}: XML parse error - {e}")
            continue

    for path, root in parsed.items():
        for elem in root.iter():
            eid = elem.get("id")
            if eid:
                if eid in all_ids and all_ids[eid] != path:
                    errors.append(f"Duplicate ID '{eid}' in {path}")
                all_ids[eid] = path

    conref_re = re.compile(r"^([^#]+)#([^/]+)/(.+)$")
    for path, root in parsed.items():
        for elem in root.iter():
            conref = elem.get("conref")
            if conref:
                m = conref_re.match(conref)
                if not m:
                    errors.append(f"{path}: Invalid conref syntax '{conref}'")
    return errors


def generate_dita_conref_keyref_dataset(
    config: DatasetConfig,
    base_path: str,
    topic_count: int = 15,
    id_prefix: str = "t",
    pretty_print: bool = True,
    variables: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, bytes]:
    win_safe = getattr(config, "windows_safe_filenames", True)
    used_ids: set[str] = set()
    root = f"{base_path}/dita_conref_keyref_dataset"
    vars_list = variables or DEFAULT_VARIABLES

    vars_id = make_dita_id("vars", id_prefix, used_ids)
    variables_filename = sanitize_filename("variables.dita", win_safe)
    variables_path = f"{root}/{variables_filename}"

    files: Dict[str, bytes] = {}
    vars_topic = _build_variables_topic(config, vars_id, vars_list)
    files[variables_path] = _topic_xml(config, vars_topic, pretty_print)

    key_product = "product"
    key_release = "release"
    ph_product, _ = vars_list[0]
    ph_release, _ = vars_list[1]

    map_elem = ET.Element("map", {"id": make_dita_id("keydef_map", id_prefix, used_ids)})
    ET.SubElement(map_elem, "title").text = "Conref Keyref Map"
    ET.SubElement(map_elem, "keydef", {"keys": key_product, "href": f"{variables_filename}#{vars_id}/{ph_product}"})
    ET.SubElement(map_elem, "keydef", {"keys": key_release, "href": f"{variables_filename}#{vars_id}/{ph_release}"})

    topic_paths = []
    for i in range(1, topic_count + 1):
        topic_id = make_dita_id(f"topic_conref_keyref_{i:02d}", id_prefix, used_ids)
        topic_filename = sanitize_filename(f"topic_conref_keyref_{i:02d}.dita", win_safe)
        topic_path = f"{root}/{topic_filename}"
        variant = (i - 1) % 4
        topic_elem = _build_topic_variant(
            topic_id, variant, variables_filename, vars_id, key_product, key_release
        )
        files[topic_path] = _topic_xml(config, topic_elem, pretty_print)
        topic_paths.append(topic_filename)
        tr = ET.SubElement(map_elem, "topicref", {"href": topic_filename})
        tr.set("type", "topic")

    map_path = f"{root}/keydef-map.ditamap"
    files[map_path] = _map_xml(config, map_elem, pretty_print)

    validation_errors = validate_dita_structure(files)
    if validation_errors:
        raise ValueError(f"DITA validation failed: {'; '.join(validation_errors[:5])}")

    manifest = {
        "dataset_name": "dita_conref_keyref_dataset",
        "generated_topics": topic_count,
        "dita_feature": "conref_keyref",
        "purpose": "AEM Guides conref/keyref resolution testing",
        "recipe_name": "dita_conref_keyref_dataset_recipe",
        "files": list(files.keys()),
        "stats": {"topic_count": topic_count, "variable_count": len(vars_list)},
    }
    manifest_path = f"{root}/dataset_manifest.json"
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "dita_conref_keyref_dataset_recipe",
        "mechanism_family": "conref",
        "title": "Conref + Keyref Dataset",
        "description": "Topics demonstrating conref and keyref combinations. Variables topic, keydef map, target topics for AEM Guides QA.",
        "tags": ["conref", "keyref", "content reuse", "keydef"],
        "module": "app.generator.conref_keyref",
        "function": "generate_dita_conref_keyref_dataset",
        "params_schema": {"topic_count": "int", "id_prefix": "str", "pretty_print": "bool"},
        "default_params": {"topic_count": 15, "id_prefix": "t", "pretty_print": True},
        "stability": "stable",
        "constructs": ["conref", "keyref", "keydef", "ph", "topic"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["conref keyref", "conref and keyref", "content reuse keys"],
        "avoid_when": ["conrefend only", "keyref only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "small",
    },
]
