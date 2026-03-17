"""
Same-file conref and conrefend recipe generators.
Generates DITA topics with content reuse within the same file.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id, stable_id
from app.generator.self_ref_utils import self_conref_value, self_conrefend_value
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


def generate_self_conref_basic_paragraph(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with paragraph conref to another paragraph in same file."""
    used_ids = set()
    topic_id = make_dita_id("self_conref_p", id_prefix, used_ids)
    target_id = make_dita_id("reusable_p", id_prefix, used_ids)
    filename = "self_conref_para.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conref Paragraph"
    body = ET.SubElement(topic, "body")

    p_target = ET.SubElement(body, "p")
    p_target.set("id", target_id)
    p_target.text = "This is the reusable paragraph content."

    p_conref = ET.SubElement(body, "p")
    p_conref.set("conref", self_conref_value(topic_id, target_id, filename, use_filename=False))

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_self_conref_section(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with section conref to another section in same file."""
    used_ids = set()
    topic_id = make_dita_id("self_conref_sec", id_prefix, used_ids)
    target_id = make_dita_id("reusable_section", id_prefix, used_ids)
    filename = "self_conref_section.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conref Section"
    body = ET.SubElement(topic, "body")

    section_target = ET.SubElement(body, "section")
    section_target.set("id", target_id)
    ET.SubElement(section_target, "title").text = "Reusable Section"
    p_in_sec = ET.SubElement(section_target, "p")
    p_in_sec.text = "Content inside the reusable section."

    section_conref = ET.SubElement(body, "section")
    section_conref.set("conref", self_conref_value(topic_id, target_id, filename, use_filename=False))

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_self_conrefend_range_paragraphs(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with conref+conrefend range of paragraphs in same file."""
    used_ids = set()
    topic_id = make_dita_id("self_conrefend_p", id_prefix, used_ids)
    start_id = make_dita_id("range_start", id_prefix, used_ids)
    mid_id = make_dita_id("range_mid", id_prefix, used_ids)
    end_id = make_dita_id("range_end", id_prefix, used_ids)
    filename = "self_conrefend_paras.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conrefend Range Paragraphs"
    body = ET.SubElement(topic, "body")

    p1 = ET.SubElement(body, "p")
    p1.set("id", start_id)
    p1.text = "Start of range."
    p2 = ET.SubElement(body, "p")
    p2.set("id", mid_id)
    p2.text = "Middle content."
    p3 = ET.SubElement(body, "p")
    p3.set("id", end_id)
    p3.text = "End of range."

    sectiondiv = ET.SubElement(body, "sectiondiv")
    sectiondiv.set("conref", self_conref_value(topic_id, start_id, filename, use_filename=False))
    sectiondiv.set("conrefend", self_conrefend_value(topic_id, end_id, filename, use_filename=False))

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_self_conrefend_range_section_content(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with conref+conrefend range of section content (sectiondiv) in same file."""
    used_ids = set()
    topic_id = make_dita_id("self_conrefend_sec", id_prefix, used_ids)
    start_id = make_dita_id("sec_range_start", id_prefix, used_ids)
    end_id = make_dita_id("sec_range_end", id_prefix, used_ids)
    filename = "self_conrefend_section.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conrefend Range Section"
    body = ET.SubElement(topic, "body")

    section = ET.SubElement(body, "section")
    ET.SubElement(section, "title").text = "Content Section"
    sectiondiv_start = ET.SubElement(section, "sectiondiv")
    sectiondiv_start.set("id", start_id)
    p1 = ET.SubElement(sectiondiv_start, "p")
    p1.text = "First block."
    sectiondiv_mid = ET.SubElement(section, "sectiondiv")
    p2 = ET.SubElement(sectiondiv_mid, "p")
    p2.text = "Second block."
    sectiondiv_end = ET.SubElement(section, "sectiondiv")
    sectiondiv_end.set("id", end_id)
    p3 = ET.SubElement(sectiondiv_end, "p")
    p3.text = "Third block."

    bodydiv = ET.SubElement(body, "bodydiv")
    bodydiv.set("conref", self_conref_value(topic_id, start_id, filename, use_filename=False))
    bodydiv.set("conrefend", self_conrefend_value(topic_id, end_id, filename, use_filename=False))

    return {rel_path: _topic_xml(config, topic, pretty_print)}


RECIPE_SPECS = [
    {
        "id": "self_conref_basic_paragraph",
        "title": "Self Conref Basic Paragraph",
        "description": "Topic with same-file conref to a paragraph",
        "tags": ["conref", "self", "same-file", "paragraph"],
        "module": "app.generator.self_conref",
        "function": "generate_self_conref_basic_paragraph",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "paragraph", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file conref", "paragraph reuse", "conref within topic"],
        "avoid_when": ["cross-topic conref", "xref only"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_conref_section",
        "title": "Self Conref Section",
        "description": "Topic with same-file conref to a section",
        "tags": ["conref", "self", "same-file", "section"],
        "module": "app.generator.self_conref",
        "function": "generate_self_conref_section",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "section", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file section conref", "section reuse"],
        "avoid_when": ["cross-topic conref", "paragraph only"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_conrefend_range_paragraphs",
        "title": "Self Conrefend Range Paragraphs",
        "description": "Topic with same-file conref+conrefend range of paragraphs",
        "tags": ["conref", "conrefend", "self", "same-file", "range"],
        "module": "app.generator.self_conref",
        "function": "generate_self_conrefend_range_paragraphs",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "conrefend", "paragraph", "sectiondiv"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["conrefend range", "range conref", "multiple paragraphs reuse"],
        "avoid_when": ["single element conref", "cross-topic"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_conrefend_range_section_content",
        "title": "Self Conrefend Range Section Content",
        "description": "Topic with same-file conref+conrefend range of section content",
        "tags": ["conref", "conrefend", "self", "same-file", "section", "range"],
        "module": "app.generator.self_conref",
        "function": "generate_self_conrefend_range_section_content",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "conrefend", "section", "bodydiv"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["conrefend section range", "range conref section"],
        "avoid_when": ["single section conref", "cross-topic"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
