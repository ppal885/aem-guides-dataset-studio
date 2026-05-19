"""Deterministic bundle for a topic that demonstrates multiple xref forms."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join
from app.jobs.schemas import DatasetConfig


RECIPE_SPECS = [
    {
        "id": "xref_variety_bundle",
        "title": "Xref Variety Bundle",
        "description": "Generate a map plus topics that demonstrate same-topic, cross-topic, fragment, external, local non-DITA, and keyref-based xrefs.",
        "tags": ["xref", "cross-reference", "keyref", "keydef", "map"],
        "module": "app.generator.xref_variety",
        "function": "generate_xref_variety_bundle",
        "params_schema": {
            "subject": "str",
            "topic_title": "str",
            "target_title": "str",
            "map_title": "str",
        },
        "default_params": {
            "subject": "DITA cross references",
            "topic_title": "Cross-reference patterns",
            "target_title": "Cross-reference targets",
            "map_title": "Cross-reference pattern map",
        },
        "stability": "stable",
        "constructs": ["map", "topicref", "keydef", "xref", "keyref", "related-links", "link"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["all xref types", "all types of cross references", "different xref forms"],
        "avoid_when": ["single isolated xref", "conref reuse", "pure explanation"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "small_bundle",
    },
]


def _doctype(config: DatasetConfig, name: str) -> str:
    return getattr(config, f"doctype_{name}", None) or (
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
        if name == "map"
        else '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    )


def _serialize(root: ET.Element, doctype: str) -> bytes:
    xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}\n'.encode("utf-8") + xml_body


def _xref_paragraph(parent: ET.Element, lead: str, attrs: dict[str, str], label: str, tail: str = ".") -> None:
    p = ET.SubElement(parent, "p")
    p.text = lead
    xref = ET.SubElement(p, "xref", attrs)
    xref.text = label
    xref.tail = tail


def _target_table(parent: ET.Element, table_id: str) -> None:
    table = ET.SubElement(parent, "table", {"id": table_id})
    ET.SubElement(table, "title").text = "Target table"
    tgroup = ET.SubElement(table, "tgroup", {"cols": "2"})
    thead = ET.SubElement(tgroup, "thead")
    head = ET.SubElement(thead, "row")
    ET.SubElement(head, "entry").text = "Target"
    ET.SubElement(head, "entry").text = "Purpose"
    tbody = ET.SubElement(tgroup, "tbody")
    row = ET.SubElement(tbody, "row")
    ET.SubElement(row, "entry").text = "table-id"
    ET.SubElement(row, "entry").text = "Table-level xref target"


def generate_xref_variety_bundle(
    config: DatasetConfig,
    base_path: str,
    subject: str = "DITA cross references",
    topic_title: str = "Cross-reference patterns",
    target_title: str = "Cross-reference targets",
    map_title: str = "Cross-reference pattern map",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Generate a construct-true bundle for "all types of xrefs" prompts."""

    del pretty_print
    used_ids: set[str] = set()
    root_folder = safe_join(base_path, "xref_variety")
    maps_folder = safe_join(root_folder, "maps")
    topics_folder = safe_join(root_folder, "topics")
    source_file = "xref_patterns.dita"
    target_file = "xref_targets.dita"
    map_path = safe_join(maps_folder, "xref_patterns.ditamap")
    source_path = safe_join(topics_folder, source_file)
    target_path = safe_join(topics_folder, target_file)

    source_id = stable_id(config.seed, "xref_patterns", "source", used_ids)
    target_id = stable_id(config.seed, "xref_targets", "target", used_ids)
    map_id = stable_id(config.seed, "xref_patterns_map", "map", used_ids)
    source_section_id = stable_id(config.seed, "xref_patterns", "section", used_ids)
    source_fig_id = stable_id(config.seed, "xref_patterns", "figure", used_ids)
    source_table_id = stable_id(config.seed, "xref_patterns", "table", used_ids)
    source_li_id = stable_id(config.seed, "xref_patterns", "list_item", used_ids)
    target_section_id = stable_id(config.seed, "xref_targets", "section", used_ids)
    target_fig_id = stable_id(config.seed, "xref_targets", "figure", used_ids)
    target_table_id = stable_id(config.seed, "xref_targets", "table", used_ids)
    target_li_id = stable_id(config.seed, "xref_targets", "list_item", used_ids)

    source = ET.Element("topic", {"id": source_id, "xml:lang": "en"})
    ET.SubElement(source, "title").text = topic_title
    ET.SubElement(source, "shortdesc").text = f"Examples of DITA xref patterns for {subject}."
    body = ET.SubElement(source, "body")
    overview = ET.SubElement(body, "section", {"id": source_section_id})
    ET.SubElement(overview, "title").text = "Local targets in this topic"
    ET.SubElement(overview, "p").text = "This section is a same-topic section target."

    _xref_paragraph(body, "Same-topic section reference: ", {"href": f"#{source_id}/{source_section_id}", "type": "section"}, "local section")
    _xref_paragraph(body, "Same-topic figure reference: ", {"href": f"#{source_id}/{source_fig_id}", "type": "fig"}, "local figure")
    _xref_paragraph(body, "Same-topic table reference: ", {"href": f"#{source_id}/{source_table_id}", "type": "table"}, "local table")
    _xref_paragraph(body, "Same-topic list-item reference: ", {"href": f"#{source_id}/{source_li_id}", "type": "li"}, "local list item")
    _xref_paragraph(body, "Cross-topic topic reference: ", {"href": target_file}, "target topic")
    _xref_paragraph(body, "Cross-topic section reference: ", {"href": f"{target_file}#{target_id}/{target_section_id}", "type": "section"}, "target section")
    _xref_paragraph(body, "Cross-topic figure reference: ", {"href": f"{target_file}#{target_id}/{target_fig_id}", "type": "fig"}, "target figure")
    _xref_paragraph(body, "Cross-topic table reference: ", {"href": f"{target_file}#{target_id}/{target_table_id}", "type": "table"}, "target table")
    _xref_paragraph(body, "Cross-topic list-item reference: ", {"href": f"{target_file}#{target_id}/{target_li_id}", "type": "li"}, "target list item")
    _xref_paragraph(body, "External HTML reference: ", {"href": "https://example.com/guide.html", "scope": "external", "format": "html"}, "external guide")
    _xref_paragraph(body, "Local PDF reference: ", {"href": "resources/runbook.pdf", "scope": "local", "format": "pdf"}, "local runbook PDF")
    _xref_paragraph(body, "External DOC reference: ", {"href": "https://example.com/spec.docx", "scope": "external", "format": "doc"}, "external specification")
    _xref_paragraph(body, "Map-keyed external reference: ", {"keyref": "external-docs"}, "external documentation")

    fig = ET.SubElement(body, "fig", {"id": source_fig_id})
    ET.SubElement(fig, "title").text = "Local figure"
    ET.SubElement(fig, "desc").text = "A figure target for same-topic xrefs."
    _target_table(body, source_table_id)
    ul = ET.SubElement(body, "ul")
    li = ET.SubElement(ul, "li", {"id": source_li_id})
    li.text = "A list item target for same-topic xrefs."
    related_links = ET.SubElement(source, "related-links")
    linklist = ET.SubElement(related_links, "linklist")
    ET.SubElement(linklist, "title").text = "Related cross-reference targets"
    link = ET.SubElement(linklist, "link", {"href": target_file})
    ET.SubElement(link, "linktext").text = "Target topic through related-links"

    target = ET.Element("topic", {"id": target_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = target_title
    ET.SubElement(target, "shortdesc").text = "This topic provides cross-topic targets for the xref pattern topic."
    target_body = ET.SubElement(target, "body")
    _xref_paragraph(target_body, "Return to the source topic: ", {"href": source_file}, "cross-reference patterns")
    target_section = ET.SubElement(target_body, "section", {"id": target_section_id})
    ET.SubElement(target_section, "title").text = "Target section"
    ET.SubElement(target_section, "p").text = "A section target in another topic."
    target_fig = ET.SubElement(target_body, "fig", {"id": target_fig_id})
    ET.SubElement(target_fig, "title").text = "Target figure"
    ET.SubElement(target_fig, "desc").text = "A figure target in another topic."
    _target_table(target_body, target_table_id)
    target_ol = ET.SubElement(target_body, "ol")
    target_li = ET.SubElement(target_ol, "li", {"id": target_li_id})
    target_li.text = "A list item target in another topic."

    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = map_title
    keydef = ET.SubElement(
        map_elem,
        "keydef",
        {
            "keys": "external-docs",
            "href": "https://example.com/docs",
            "scope": "external",
            "format": "html",
        },
    )
    topicmeta = ET.SubElement(keydef, "topicmeta")
    ET.SubElement(topicmeta, "linktext").text = "External documentation"
    ET.SubElement(map_elem, "topicref", {"href": f"../topics/{source_file}"})
    ET.SubElement(map_elem, "topicref", {"href": f"../topics/{target_file}"})

    return {
        source_path: _serialize(source, _doctype(config, "topic")),
        target_path: _serialize(target, _doctype(config, "topic")),
        map_path: _serialize(map_elem, _doctype(config, "map")),
    }
