"""
DITA Glossary Abbreviation Dataset - glossary entries with term and abbreviated-form.

Generates:
- glossary-map.ditamap: Map with keydefs to glossentry files
- api.glossentry, aem.glossentry, ... (15 entries): glossentry with glossterm, glossdef, glossAlt/glossAbbreviation
- topic_glossary_usage_01.dita through topic_glossary_usage_10.dita: Topics with term keyref, abbreviated-form keyref
- dataset_manifest.json

Used for: AEM Guides QA, glossary resolution testing, term/abbreviation keyref.
"""
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


DEFAULT_ENTRIES: List[Tuple[str, str, str, str]] = [
    ("api", "Application Programming Interface", "A mechanism for software communication.", "API"),
    ("aem", "Adobe Experience Manager", "Enterprise content management platform.", "AEM"),
    ("dita", "Darwin Information Typing Architecture", "XML-based architecture for technical documentation.", "DITA"),
    ("cms", "Content Management System", "Software for managing digital content.", "CMS"),
    ("crm", "Customer Relationship Management", "System for managing customer interactions.", "CRM"),
    ("sdk", "Software Development Kit", "Set of development tools.", "SDK"),
    ("ui", "User Interface", "Visual elements for user interaction.", "UI"),
    ("ux", "User Experience", "Overall experience of using a product.", "UX"),
    ("html", "HyperText Markup Language", "Markup language for web pages.", "HTML"),
    ("xml", "eXtensible Markup Language", "Markup language for structured data.", "XML"),
    ("json", "JavaScript Object Notation", "Lightweight data interchange format.", "JSON"),
    ("rest", "Representational State Transfer", "Architectural style for web services.", "REST"),
    ("url", "Uniform Resource Locator", "Address of a resource on the web.", "URL"),
    ("id", "Identifier", "Unique reference to an entity.", "ID"),
    ("pdf", "Portable Document Format", "Document format for sharing.", "PDF"),
]


def _glossentry_xml(config: DatasetConfig, gloss_elem: ET.Element, pretty_print: bool = True) -> bytes:
    xml_body = ET.tostring(gloss_elem, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_glossentry}\n'
    return doc.encode("utf-8") + xml_body


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


def _build_glossentry(entry_id: str, term: str, definition: str, abbreviation: str) -> ET.Element:
    gloss = ET.Element("glossentry", {"id": f"{entry_id}-entry", "xml:lang": "en"})
    ET.SubElement(gloss, "glossterm").text = term
    glossdef = ET.SubElement(gloss, "glossdef")
    p = ET.SubElement(glossdef, "p")
    p.text = definition
    glossalt = ET.SubElement(gloss, "glossAlt")
    ET.SubElement(glossalt, "glossAbbreviation").text = abbreviation
    return gloss


def generate_dita_glossary_abbrev_dataset(
    config: DatasetConfig,
    base_path: str,
    entry_count: int = 15,
    usage_topic_count: int = 10,
    id_prefix: str = "t",
    pretty_print: bool = True,
    entries: Optional[List[Tuple[str, str, str, str]]] = None,
) -> Dict[str, bytes]:
    win_safe = getattr(config, "windows_safe_filenames", True)
    used_ids: set[str] = set()
    root = f"{base_path}/dita_glossary_dataset"
    entries_list = (entries or DEFAULT_ENTRIES)[:entry_count]

    files: Dict[str, bytes] = {}
    key_to_file: Dict[str, str] = {}

    for i, (key, term, definition, abbrev) in enumerate(entries_list):
        entry_id = make_dita_id(f"gloss_{key}", id_prefix, used_ids)
        filename = sanitize_filename(f"{key}.dita", win_safe)
        filepath = f"{root}/{filename}"
        gloss_elem = _build_glossentry(entry_id, term, definition, abbrev)
        files[filepath] = _glossentry_xml(config, gloss_elem, pretty_print)
        key_to_file[key] = filename

    map_elem = ET.Element("map", {"id": make_dita_id("glossary_map", id_prefix, used_ids)})
    ET.SubElement(map_elem, "title").text = "Glossary Map"
    for key, filename in key_to_file.items():
        tr = ET.SubElement(map_elem, "topicref", {"href": filename, "keys": key})
        tr.set("type", "glossentry")
    map_path = f"{root}/glossary-map.ditamap"
    files[map_path] = _map_xml(config, map_elem, pretty_print)

    keys_available = list(key_to_file.keys())
    for i in range(1, usage_topic_count + 1):
        topic_id = make_dita_id(f"topic_glossary_usage_{i:02d}", id_prefix, used_ids)
        topic_filename = sanitize_filename(f"topic_glossary_usage_{i:02d}.dita", win_safe)
        topic_path = f"{root}/{topic_filename}"
        key1 = keys_available[(i - 1) % len(keys_available)]
        key2 = keys_available[(i) % len(keys_available)] if len(keys_available) > 1 else key1

        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        ET.SubElement(topic, "title").text = "Glossary Usage"
        body = ET.SubElement(topic, "body")
        p1 = ET.SubElement(body, "p")
        p1.text = "The "
        t1 = ET.SubElement(p1, "term", {"keyref": key1})
        t1.tail = " enables integration."
        p2 = ET.SubElement(body, "p")
        p2.text = "The abbreviation "
        af = ET.SubElement(p2, "abbreviated-form", {"keyref": key1})
        af.tail = " is widely used."
        p3 = ET.SubElement(body, "p")
        p3.text = "Content platforms such as "
        t2 = ET.SubElement(p3, "term", {"keyref": key2})
        t2.tail = " manage documentation."

        files[topic_path] = _topic_xml(config, topic, pretty_print)

    manifest = {
        "dataset_name": "dita_glossary_dataset",
        "entry_count": len(key_to_file),
        "usage_topic_count": usage_topic_count,
        "dita_feature": "glossary_abbrev",
        "purpose": "Glossary term and abbreviated-form keyref testing",
        "recipe_name": "dita_glossary_abbrev_dataset_recipe",
        "files": list(files.keys()),
        "stats": {"entry_count": len(key_to_file), "usage_topic_count": usage_topic_count},
    }
    manifest_path = f"{root}/dataset_manifest.json"
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "dita_glossary_abbrev_dataset_recipe",
        "mechanism_family": "glossary",
        "title": "Glossary Abbreviation Dataset",
        "description": "Glossary entries with term and abbreviated-form. Usage topics with term keyref and abbreviated-form keyref.",
        "tags": ["glossary", "glossentry", "term", "abbreviated-form", "glossAbbreviation"],
        "module": "app.generator.glossary_abbrev",
        "function": "generate_dita_glossary_abbrev_dataset",
        "params_schema": {"entry_count": "int", "usage_topic_count": "int", "id_prefix": "str", "pretty_print": "bool"},
        "default_params": {"entry_count": 15, "usage_topic_count": 10, "id_prefix": "t", "pretty_print": True},
        "stability": "stable",
        "constructs": ["glossentry", "glossterm", "glossdef", "glossAbbreviation", "term", "abbreviated-form"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["glossary", "term keyref", "abbreviated-form", "glossentry"],
        "avoid_when": ["no glossary", "concept only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "small",
    },
]
