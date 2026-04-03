"""
Same-file xref and conref recipe generators.
Generates DITA topics with cross-references and content reuse within the same file.
Follows Oxygen DITA cross-reference sample behavior.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id, stable_id
from app.generator.generate import safe_join
from app.generator.self_ref_utils import self_xref_href, self_conref_value, self_conrefend_value
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


def generate_self_xref_section(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to section in same file. type='section'. Minimal, deterministic IDs."""
    used_ids = set()
    topic_id = stable_id("self_xref_section", id_prefix, "topic", used_ids)
    section_id = stable_id("self_xref_section", id_prefix, "section", used_ids)
    filename = "self_xref_section.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Section"
    body = ET.SubElement(topic, "body")

    p_intro = ET.SubElement(body, "p")
    p_intro.text = "See "
    xref = ET.SubElement(p_intro, "xref")
    xref.set("href", self_xref_href(section_id, topic_id, filename, use_filename=False))
    xref.set("type", "section")
    xref.tail = " for details."

    section = ET.SubElement(body, "section")
    section.set("id", section_id)
    ET.SubElement(section, "title").text = "Target Section"
    ET.SubElement(section, "p").text = "Content in the target section."

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_list_item(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to list item (li) in same file. type='li'."""
    used_ids = set()
    topic_id = make_dita_id("self_xref_li", id_prefix, used_ids)
    li_id = make_dita_id("target_li", id_prefix, used_ids)
    filename = "self_xref_li.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref List Item"
    body = ET.SubElement(topic, "body")

    p_intro = ET.SubElement(body, "p")
    p_intro.text = "See item "
    xref = ET.SubElement(p_intro, "xref")
    xref.set("href", self_xref_href(li_id, topic_id, filename, use_filename=False))
    xref.set("type", "li")
    xref.tail = " below."

    ol = ET.SubElement(body, "ol")
    li = ET.SubElement(ol, "li")
    li.set("id", li_id)
    li.text = "Target list item content."

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_figure(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to figure in same file. type='fig'."""
    used_ids = set()
    topic_id = make_dita_id("self_xref_fig", id_prefix, used_ids)
    fig_id = make_dita_id("target_fig", id_prefix, used_ids)
    filename = "self_xref_fig.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Figure"
    body = ET.SubElement(topic, "body")

    p_intro = ET.SubElement(body, "p")
    p_intro.text = "See "
    xref = ET.SubElement(p_intro, "xref")
    xref.set("href", self_xref_href(fig_id, topic_id, filename, use_filename=False))
    xref.set("type", "fig")
    xref.tail = " for the diagram."

    fig = ET.SubElement(body, "fig")
    fig.set("id", fig_id)
    ET.SubElement(fig, "title").text = "Sample Figure"
    ET.SubElement(fig, "desc").text = "Figure description."

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_table(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to table in same file. type='table'."""
    used_ids = set()
    topic_id = make_dita_id("self_xref_tbl", id_prefix, used_ids)
    table_id = make_dita_id("target_table", id_prefix, used_ids)
    filename = "self_xref_table.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Table"
    body = ET.SubElement(topic, "body")

    p_intro = ET.SubElement(body, "p")
    p_intro.text = "See "
    xref = ET.SubElement(p_intro, "xref")
    xref.set("href", self_xref_href(table_id, topic_id, filename, use_filename=False))
    xref.set("type", "table")
    xref.tail = " for the data."

    table = ET.SubElement(body, "table")
    table.set("id", table_id)
    ET.SubElement(table, "title").text = "Sample Table"
    tgroup = ET.SubElement(table, "tgroup", {"cols": "2"})
    thead = ET.SubElement(tgroup, "thead")
    row = ET.SubElement(thead, "row")
    ET.SubElement(row, "entry").text = "Col1"
    ET.SubElement(row, "entry").text = "Col2"
    tbody = ET.SubElement(tgroup, "tbody")
    row2 = ET.SubElement(tbody, "row")
    ET.SubElement(row2, "entry").text = "A"
    ET.SubElement(row2, "entry").text = "B"

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_conref_basic(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with same-file conref to p/section. Minimal valid dataset."""
    used_ids = set()
    topic_id = make_dita_id("self_conref_basic", id_prefix, used_ids)
    target_id = make_dita_id("reusable_block", id_prefix, used_ids)
    filename = "self_conref_basic.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conref Basic"
    body = ET.SubElement(topic, "body")

    p_target = ET.SubElement(body, "p")
    p_target.set("id", target_id)
    p_target.text = "Reusable paragraph content."

    p_conref = ET.SubElement(body, "p")
    p_conref.set("conref", self_conref_value(topic_id, target_id, filename, use_filename=False))

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_conrefend_range(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with same-file conref+conrefend range. Minimal valid dataset."""
    used_ids = set()
    topic_id = make_dita_id("self_conrefend", id_prefix, used_ids)
    start_id = make_dita_id("range_start", id_prefix, used_ids)
    end_id = make_dita_id("range_end", id_prefix, used_ids)
    filename = "self_conrefend_range.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Conrefend Range"
    body = ET.SubElement(topic, "body")

    p1 = ET.SubElement(body, "p")
    p1.set("id", start_id)
    p1.text = "Start of range."
    p2 = ET.SubElement(body, "p")
    p2.text = "Middle."
    p3 = ET.SubElement(body, "p")
    p3.set("id", end_id)
    p3.text = "End of range."

    sectiondiv = ET.SubElement(body, "sectiondiv")
    sectiondiv.set("conref", self_conref_value(topic_id, start_id, filename, use_filename=False))
    sectiondiv.set("conrefend", self_conrefend_value(topic_id, end_id, filename, use_filename=False))

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_conref_positive_minimal(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Minimal valid topic with one same-file xref and one same-file conref. Positive case."""
    used_ids = set()
    topic_id = stable_id("self_xref_conref_pos", id_prefix, "topic", used_ids)
    section_id = stable_id("self_xref_conref_pos", id_prefix, "section", used_ids)
    block_id = stable_id("self_xref_conref_pos", id_prefix, "block", used_ids)
    filename = "self_xref_conref_positive.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Conref Positive"
    body = ET.SubElement(topic, "body")

    p_intro = ET.SubElement(body, "p")
    p_intro.text = "See "
    xref = ET.SubElement(p_intro, "xref")
    xref.set("href", self_xref_href(section_id, topic_id, filename, use_filename=False))
    xref.set("type", "section")
    xref.tail = "."

    p_target = ET.SubElement(body, "p")
    p_target.set("id", block_id)
    p_target.text = "Reusable block."

    p_conref = ET.SubElement(body, "p")
    p_conref.set("conref", self_conref_value(topic_id, block_id, filename, use_filename=False))

    section = ET.SubElement(body, "section")
    section.set("id", section_id)
    ET.SubElement(section, "title").text = "Target Section"
    ET.SubElement(section, "p").text = "Section content."

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_conref_boundary(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Boundary: topic with multiple xrefs (section, fig) and conref. Edge-case same-file mix."""
    used_ids = set()
    topic_id = stable_id("self_xref_conref_bdry", id_prefix, "topic", used_ids)
    sec_id = stable_id("self_xref_conref_bdry", id_prefix, "section", used_ids)
    fig_id = stable_id("self_xref_conref_bdry", id_prefix, "fig", used_ids)
    block_id = stable_id("self_xref_conref_bdry", id_prefix, "block", used_ids)
    filename = "self_xref_conref_boundary.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Conref Boundary"
    body = ET.SubElement(topic, "body")

    p1 = ET.SubElement(body, "p")
    p1.text = "See "
    x1 = ET.SubElement(p1, "xref")
    x1.set("href", self_xref_href(sec_id, topic_id, filename, use_filename=False))
    x1.set("type", "section")
    x1.tail = " and "
    x2 = ET.SubElement(p1, "xref")
    x2.set("href", self_xref_href(fig_id, topic_id, filename, use_filename=False))
    x2.set("type", "fig")
    x2.tail = "."

    p_target = ET.SubElement(body, "p")
    p_target.set("id", block_id)
    p_target.text = "Reusable content."

    p_conref = ET.SubElement(body, "p")
    p_conref.set("conref", self_conref_value(topic_id, block_id, filename, use_filename=False))

    section = ET.SubElement(body, "section")
    section.set("id", sec_id)
    ET.SubElement(section, "title").text = "Section"
    ET.SubElement(section, "p").text = "Content."

    fig = ET.SubElement(body, "fig")
    fig.set("id", fig_id)
    ET.SubElement(fig, "title").text = "Figure"
    ET.SubElement(fig, "desc").text = "Desc."

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


def generate_self_xref_conref_negative(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Negative: topic with broken xref (href to non-existent id). For validation testing."""
    used_ids = set()
    topic_id = stable_id("self_xref_conref_neg", id_prefix, "topic", used_ids)
    filename = "self_xref_conref_negative.dita"
    rel_path = f"topics/{filename}"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Conref Negative"
    body = ET.SubElement(topic, "body")

    p = ET.SubElement(body, "p")
    p.text = "Broken xref: "
    xref = ET.SubElement(p, "xref")
    xref.set("href", "#nonexistent_id")
    xref.set("type", "section")
    xref.tail = "."

    p_conref = ET.SubElement(body, "p")
    p_conref.set("conref", "#nonexistent_block")

    return {safe_join(base_path, rel_path): _topic_xml(config, topic, pretty_print)}


RECIPE_SPECS = [
    {
        "id": "self_xref_list_item",
        "title": "Self Xref List Item",
        "description": "Topic with xref to li in same file (type=li)",
        "tags": ["xref", "self", "same-file", "li", "list"],
        "module": "app.generator.self_xref",
        "function": "generate_self_xref_list_item",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["xref", "li", "ol", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file list item link", "xref to li", "list item reference"],
        "avoid_when": ["cross-topic xref", "section link"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_xref_figure",
        "title": "Self Xref Figure",
        "description": "Topic with xref to fig in same file (type=fig)",
        "tags": ["xref", "self", "same-file", "fig", "figure"],
        "module": "app.generator.self_xref",
        "function": "generate_self_xref_figure",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["xref", "fig", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file figure link", "xref to fig", "figure reference"],
        "avoid_when": ["cross-topic xref", "table link"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_xref_table",
        "title": "Self Xref Table",
        "description": "Topic with xref to table in same file (type=table)",
        "tags": ["xref", "self", "same-file", "table"],
        "module": "app.generator.self_xref",
        "function": "generate_self_xref_table",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["xref", "table", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file table link", "xref to table", "table reference"],
        "avoid_when": ["cross-topic xref", "figure link"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_conref_basic",
        "title": "Self Conref Basic",
        "description": "Topic with same-file conref to p/section",
        "tags": ["conref", "self", "same-file", "paragraph"],
        "module": "app.generator.self_xref",
        "function": "generate_self_conref_basic",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "paragraph", "section", "topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["same-file conref", "self conref", "paragraph section reuse"],
        "avoid_when": ["cross-topic conref", "xref only"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "self_conrefend_range",
        "title": "Self Conrefend Range",
        "description": "Topic with same-file conref+conrefend range",
        "tags": ["conref", "conrefend", "self", "same-file", "range"],
        "module": "app.generator.self_xref",
        "function": "generate_self_conrefend_range",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["conref", "conrefend", "topic"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["conrefend range", "range conref", "same-file range reuse"],
        "avoid_when": ["single element conref", "cross-topic"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
