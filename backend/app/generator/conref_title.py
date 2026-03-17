"""
DITA Conref in Title Dataset - topics with conref in title referencing variable ph elements.

Generates:
- variables.dita: Reusable variable topic with ph elements (build_version, release_name, product_name)
- topic_1.dita through topic_N.dita: Target topics whose <title> uses conref to reference variables
- dataset_manifest.json: Metadata for QA automation and LLM training

Pipeline functions: generate_variable_topic, generate_conref_topic, validate_dita_structure, write_dataset_files

Used for: AEM Guides QA automation, DITA conref resolution testing, LLM training, Jira issue reproduction.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


# Default variable ph elements: (id, content)
DEFAULT_VARIABLES = [
    ("build_version", "Build-2026"),
    ("release_name", "Release-A"),
    ("product_name", "AEM-Guides"),
]

# Phrase-level elements valid for title conref (DITA 1.3)
PHRASE_LEVEL_ELEMENTS = frozenset({"ph", "keyword", "term", "abbreviated-form", "tm"})


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


def generate_variable_topic(
    config: DatasetConfig,
    variables_topic_id: str,
    variables: List[Tuple[str, str]],
    pretty_print: bool = True,
) -> ET.Element:
    """
    Generate a reusable variable topic containing ph elements.
    Returns the topic element (caller serializes).
    """
    topic = ET.Element("topic", {"id": variables_topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "variables"
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = ""
    body = ET.SubElement(topic, "body")
    for ph_id, content in variables:
        p = ET.SubElement(body, "p")
        ph = ET.SubElement(p, "ph", {"id": ph_id})
        ph.text = content
    return topic


def generate_conref_topic(
    config: DatasetConfig,
    topic_id: str,
    ph_id: str,
    variables_filename: str,
    variables_topic_id: str,
    pretty_print: bool = True,
) -> ET.Element:
    """
    Generate a target topic whose title uses conref to reference a variable.
    Returns the topic element.
    """
    conref_value = f"{variables_filename}#{variables_topic_id}/{ph_id}"
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    title_elem = ET.SubElement(topic, "title")
    title_elem.set("conref", conref_value)
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = "Topic demonstrating title conref resolution."
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "This topic resolves its title from a reusable variable."
    return topic


def validate_dita_structure(files: Dict[str, bytes]) -> List[str]:
    """
    Validate generated DITA structure.
    Returns list of error messages. Empty list means valid.
    Checks: unique IDs, referenced IDs exist, conref syntax, well-formed XML,
    titles only reference phrase-level elements.
    """
    errors: List[str] = []
    all_ids: Dict[str, str] = {}  # id -> file path
    id_to_tag: Dict[str, str] = {}  # id -> element tag (for phrase-level check)

    # Parse all DITA files
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

    # Collect IDs and check uniqueness
    for path, root in parsed.items():
        for elem in root.iter():
            eid = elem.get("id")
            if eid:
                if eid in all_ids and all_ids[eid] != path:
                    errors.append(f"Duplicate ID '{eid}' in {path} (also in {all_ids[eid]})")
                all_ids[eid] = path
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                id_to_tag[eid] = tag

    # Build file -> ids map for conref resolution
    file_ids: Dict[str, set[str]] = {}
    for path, root in parsed.items():
        ids_in_file = set()
        for elem in root.iter():
            eid = elem.get("id")
            if eid:
                ids_in_file.add(eid)
        file_ids[path] = ids_in_file

    # Validate conrefs (format: file#topicId/elementId)
    conref_re = re.compile(r"^([^#]+)#([^/]+)/(.+)$")
    for path, root in parsed.items():
        for elem in root.iter():
            conref = elem.get("conref")
            if not conref:
                continue
            m = conref_re.match(conref)
            if not m:
                errors.append(f"{path}: Invalid conref syntax '{conref}' (expected file#topicId/elementId)")
                continue
            ref_file, ref_topic_id, ref_elem_id = m.groups()
            ref_path = next((p for p in file_ids if p.endswith(ref_file) or ref_file in p), None)
            if ref_path and ref_path in file_ids:
                ids_in_ref = file_ids[ref_path]
                if ref_topic_id not in ids_in_ref or ref_elem_id not in ids_in_ref:
                    errors.append(f"{path}: conref '{conref}' - topic id or element id not found in {ref_path}")
                elif ref_elem_id in id_to_tag:
                    tag = id_to_tag[ref_elem_id]
                    if tag not in PHRASE_LEVEL_ELEMENTS:
                        errors.append(f"{path}: Title conref targets '{tag}' (id={ref_elem_id}), not a phrase-level element")
            else:
                errors.append(f"{path}: conref '{conref}' - referenced file not in dataset")

    return errors


def write_dataset_files(files: Dict[str, bytes], output_dir: str) -> None:
    """Write generated files dict to output directory."""
    base = Path(output_dir)
    for rel_path, content in files.items():
        out_path = base / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(content)


def generate_dita_conref_title_dataset(
    config: DatasetConfig,
    base_path: str,
    topic_count: int = 10,
    id_prefix: str = "t",
    pretty_print: bool = True,
    variables: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, bytes]:
    """
    Generate DITA dataset with conref in titles.

    - variables.dita: Topic with reusable ph elements
    - topic_1.dita through topic_N.dita: Topics whose title conrefs to variables
    - dataset_manifest.json: Metadata
    """
    win_safe = getattr(config, "windows_safe_filenames", True)
    used_ids: set[str] = set()
    root = f"{base_path}/dita_conref_titles"
    vars_list = variables or DEFAULT_VARIABLES

    variables_topic_id = make_dita_id("variables_topic", id_prefix, used_ids)
    variables_filename = sanitize_filename("variables.dita", win_safe)
    variables_path = f"{root}/{variables_filename}"

    # Generate variable topic
    vars_topic = generate_variable_topic(config, variables_topic_id, vars_list, pretty_print)
    files: Dict[str, bytes] = {}
    files[variables_path] = _topic_xml(config, vars_topic, pretty_print)

    # Generate target topics with title conref
    for i in range(1, topic_count + 1):
        topic_id = make_dita_id(f"topic_{i:03d}", id_prefix, used_ids)
        topic_filename = sanitize_filename(f"topic_{i}.dita", win_safe)
        topic_path = f"{root}/{topic_filename}"
        ph_id, _ = vars_list[(i - 1) % len(vars_list)]
        topic_elem = generate_conref_topic(
            config, topic_id, ph_id, variables_filename, variables_topic_id, pretty_print
        )
        files[topic_path] = _topic_xml(config, topic_elem, pretty_print)

    # Validate
    validation_errors = validate_dita_structure(files)
    if validation_errors:
        raise ValueError(f"DITA validation failed: {'; '.join(validation_errors[:5])}")

    # Dataset manifest
    generated_files = list(files.keys())
    manifest = {
        "dataset_name": "dita_conref_title_dataset",
        "generated_topics": topic_count,
        "dita_feature": "conref_title",
        "purpose": "AEM Guides conref resolution testing",
        "recipe_name": "dita_conref_title_dataset_recipe",
        "files": generated_files,
        "stats": {
            "topic_count": topic_count,
            "variable_count": len(vars_list),
            "generated_files": generated_files,
        },
        "assumptions": [],
        "warnings": [],
    }
    manifest_path = f"{root}/dataset_manifest.json"
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "dita_conref_title_dataset_recipe",
        "mechanism_family": "conref",
        "title": "Conref in Title Dataset",
        "description": "Topics with conref in title referencing variable ph elements. Variables topic + target topics for AEM Guides QA, conref resolution testing, LLM training.",
        "tags": ["conref", "title", "content reuse", "ph", "variables"],
        "module": "app.generator.conref_title",
        "function": "generate_dita_conref_title_dataset",
        "params_schema": {
            "topic_count": "int",
            "id_prefix": "str",
            "pretty_print": "bool",
            "variables": "list[tuple[str, str]] | None",
        },
        "default_params": {
            "topic_count": 10,
            "id_prefix": "t",
            "pretty_print": True,
            "variables": None,
        },
        "stability": "stable",
        "constructs": ["conref", "title", "ph", "topic"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "conref in title",
            "title conref",
            "content reuse in title",
            "reusable title",
            "variable title",
        ],
        "avoid_when": ["conrefend", "range conref", "body conref only"],
        "positive_negative": "positive",
        "complexity": "low",
        "output_scale": "small",
    },
]
