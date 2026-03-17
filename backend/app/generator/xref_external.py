"""
Xref to non-DITA resources - HTML, PDF, DOC, web URLs.

Follows Oxygen DITA style guide for links to non-DITA resources:
https://www.oxygenxml.com/dita/styleguide/Cross_Referencing/c_Links_to_non-DITA_Resources.html
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
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


def _add_xref_para(body: ET.Element, href: str, format_val: str, scope_val: str, link_text: str = None) -> ET.Element:
    """Add paragraph with xref to non-DITA resource."""
    p = ET.SubElement(body, "p")
    if link_text:
        p.text = f"See "
    xref = ET.SubElement(p, "xref")
    xref.set("href", href)
    xref.set("format", format_val)
    xref.set("scope", scope_val)
    if link_text:
        xref.text = link_text
        xref.tail = "."
    return p


def generate_xref_html_external(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to external HTML resource. format=html, scope=external."""
    used_ids = set()
    topic_id = stable_id("xref_html_ext", id_prefix, "topic", used_ids)
    rel_path = "topics/xref_html_external.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref HTML External"
    body = ET.SubElement(topic, "body")
    _add_xref_para(body, "https://example.com/guide.html", "html", "external", "external HTML guide")

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_xref_pdf_local(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to local PDF. format=pdf, scope=local."""
    used_ids = set()
    topic_id = stable_id("xref_pdf_local", id_prefix, "topic", used_ids)
    rel_path = "topics/xref_pdf_local.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref PDF Local"
    body = ET.SubElement(topic, "body")
    _add_xref_para(body, "manual.pdf", "pdf", "local", "user manual")

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_xref_doc_external(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to external DOC. format=doc, scope=external."""
    used_ids = set()
    topic_id = stable_id("xref_doc_ext", id_prefix, "topic", used_ids)
    rel_path = "topics/xref_doc_external.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref DOC External"
    body = ET.SubElement(topic, "body")
    _add_xref_para(body, "https://example.com/spec.doc", "doc", "external", "specification document")

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_xref_web_external(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with xref to web URL. format=html, scope=external."""
    used_ids = set()
    topic_id = stable_id("xref_web_ext", id_prefix, "topic", used_ids)
    rel_path = "topics/xref_web_external.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref Web External"
    body = ET.SubElement(topic, "body")
    _add_xref_para(body, "https://example.com", "html", "external", "example website")

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def generate_related_links_external_resources(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Topic with related-links section containing xrefs to external resources."""
    used_ids = set()
    topic_id = stable_id("related_links_ext", id_prefix, "topic", used_ids)
    rel_path = "topics/related_links_external_resources.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Related Links External Resources"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See related external resources below."

    related = ET.SubElement(topic, "related-links")
    linkgroup = ET.SubElement(related, "linkgroup")
    for href, fmt, scope, text in [
        ("https://example.com/faq.html", "html", "external", "FAQ"),
        ("docs.pdf", "pdf", "local", "Documentation"),
    ]:
        link = ET.SubElement(linkgroup, "link")
        xref = ET.SubElement(link, "xref")
        xref.set("href", href)
        xref.set("format", fmt)
        xref.set("scope", scope)
        xref.text = text

    return {rel_path: _topic_xml(config, topic, pretty_print)}


def _recipe_spec_base() -> dict:
    return {
        "constructs": ["xref"],
        "tags": ["XREF", "NON_DITA", "EXTERNAL_LINK"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["linking to non-DITA resources", "external files", "web URLs"],
        "avoid_when": ["DITA-to-DITA links only", "same-file xref"],
        "examples": [{"prompt": "Generate xref to non-DITA resource with format and scope"}],
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
    }


# Consolidated into app.generator.xrefs (xref_external_html, xref_external_pdf, xref_external_doc, xref_external_url)
RECIPE_SPECS = [
    {
        "id": "related_links_external_resources",
        "title": "Related Links External Resources",
        "description": "Topic with related-links section containing xrefs to external resources.",
        "module": "app.generator.xref_external",
        "function": "generate_related_links_external_resources",
        **_recipe_spec_base(),
    },
]
