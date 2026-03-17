"""
Cross-reference recipe family - internal, self, external, negative.

Covers xref behaviour for Jira-driven dataset generation.
Follows Oxygen DITA style guide for links.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.generator.self_ref_utils import self_xref_href
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


def _spec(id_: str, title: str, desc: str, fn: str, constructs: list, tags: list,
          use_when: list, avoid_when: list, positive_negative: str = "positive",
          scenario_types: list = None) -> dict:
    scenario_types = scenario_types or ["MIN_REPRO"]
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": constructs,
        "scenario_types": scenario_types,
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive_negative,
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.xrefs",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


# --- Internal references (cross-topic) ---

def generate_xref_topic_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Link to another topic."""
    used = set()
    t1_id = stable_id("xref_topic", id_prefix, "source", used)
    t2_id = stable_id("xref_topic", id_prefix, "target", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source Topic"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita")
    x.text = "target topic"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target Topic"
    b2 = ET.SubElement(target, "body")
    ET.SubElement(b2, "p").text = "Target content."
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


def generate_xref_section_target(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                                 pretty_print: bool = True) -> Dict[str, bytes]:
    """Link to a section inside another topic."""
    used = set()
    t1_id = stable_id("xref_sec", id_prefix, "src", used)
    t2_id = stable_id("xref_sec", id_prefix, "tgt", used)
    sec_id = stable_id("xref_sec", id_prefix, "sec", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita#" + t2_id + "/" + sec_id)
    x.set("type", "section")
    x.text = "target section"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target"
    b2 = ET.SubElement(target, "body")
    sec = ET.SubElement(b2, "section", {"id": sec_id})
    ET.SubElement(sec, "title").text = "Target Section"
    ET.SubElement(sec, "p").text = "Section content."
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


def generate_xref_list_item_target(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                                   pretty_print: bool = True) -> Dict[str, bytes]:
    """Link to an li target in another topic."""
    used = set()
    t1_id = stable_id("xref_li", id_prefix, "src", used)
    t2_id = stable_id("xref_li", id_prefix, "tgt", used)
    li_id = stable_id("xref_li", id_prefix, "li", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See item "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita#" + t2_id + "/" + li_id)
    x.set("type", "li")
    x.text = "item"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target"
    b2 = ET.SubElement(target, "body")
    ol = ET.SubElement(b2, "ol")
    li = ET.SubElement(ol, "li", {"id": li_id})
    li.text = "Target item."
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


def generate_xref_figure_target(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                               pretty_print: bool = True) -> Dict[str, bytes]:
    """Link to a figure in another topic."""
    used = set()
    t1_id = stable_id("xref_fig", id_prefix, "src", used)
    t2_id = stable_id("xref_fig", id_prefix, "tgt", used)
    fig_id = stable_id("xref_fig", id_prefix, "fig", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita#" + t2_id + "/" + fig_id)
    x.set("type", "fig")
    x.text = "figure"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target"
    b2 = ET.SubElement(target, "body")
    fig = ET.SubElement(b2, "fig", {"id": fig_id})
    ET.SubElement(fig, "title").text = "Figure"
    ET.SubElement(fig, "desc").text = "Desc."
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


def generate_xref_table_target(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Link to a table in another topic."""
    used = set()
    t1_id = stable_id("xref_tbl", id_prefix, "src", used)
    t2_id = stable_id("xref_tbl", id_prefix, "tgt", used)
    tbl_id = stable_id("xref_tbl", id_prefix, "tbl", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita#" + t2_id + "/" + tbl_id)
    x.set("type", "table")
    x.text = "table"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target"
    b2 = ET.SubElement(target, "body")
    tbl = ET.SubElement(b2, "table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Table"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "2"})
    thead = ET.SubElement(tg, "thead")
    r1 = ET.SubElement(thead, "row")
    ET.SubElement(r1, "entry").text = "A"
    ET.SubElement(r1, "entry").text = "B"
    tbody = ET.SubElement(tg, "tbody")
    r2 = ET.SubElement(tbody, "row")
    ET.SubElement(r2, "entry").text = "1"
    ET.SubElement(r2, "entry").text = "2"
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


# --- Self references ---

def generate_xref_self_section(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                               pretty_print: bool = True) -> Dict[str, bytes]:
    """Same-file xref to section."""
    used = set()
    tid = stable_id("xref_self_sec", id_prefix, "topic", used)
    sid = stable_id("xref_self_sec", id_prefix, "section", used)
    fn = "xref_self_section.dita"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Section"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", self_xref_href(sid, tid, fn, False))
    x.set("type", "section")
    x.tail = " for details."
    sec = ET.SubElement(body, "section", {"id": sid})
    ET.SubElement(sec, "title").text = "Target Section"
    ET.SubElement(sec, "p").text = "Content."
    return {"topics/" + fn: _topic_xml(config, topic, pretty_print)}


def generate_xref_self_figure(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Same-file xref to figure."""
    used = set()
    tid = stable_id("xref_self_fig", id_prefix, "topic", used)
    fid = stable_id("xref_self_fig", id_prefix, "fig", used)
    fn = "xref_self_figure.dita"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Figure"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", self_xref_href(fid, tid, fn, False))
    x.set("type", "fig")
    x.tail = "."
    fig = ET.SubElement(body, "fig", {"id": fid})
    ET.SubElement(fig, "title").text = "Figure"
    ET.SubElement(fig, "desc").text = "Desc."
    return {"topics/" + fn: _topic_xml(config, topic, pretty_print)}


def generate_xref_self_table(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                            pretty_print: bool = True) -> Dict[str, bytes]:
    """Same-file xref to table."""
    used = set()
    tid = stable_id("xref_self_tbl", id_prefix, "topic", used)
    tbl_id = stable_id("xref_self_tbl", id_prefix, "tbl", used)
    fn = "xref_self_table.dita"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Self Xref Table"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", self_xref_href(tbl_id, tid, fn, False))
    x.set("type", "table")
    x.tail = "."
    tbl = ET.SubElement(body, "table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Table"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "2"})
    thead = ET.SubElement(tg, "thead")
    r1 = ET.SubElement(thead, "row")
    ET.SubElement(r1, "entry").text = "A"
    ET.SubElement(r1, "entry").text = "B"
    tbody = ET.SubElement(tg, "tbody")
    r2 = ET.SubElement(tbody, "row")
    ET.SubElement(r2, "entry").text = "1"
    ET.SubElement(r2, "entry").text = "2"
    return {"topics/" + fn: _topic_xml(config, topic, pretty_print)}


# --- External resources ---

def _add_xref_ext(body: ET.Element, href: str, fmt: str, scope: str, text: str) -> None:
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", href)
    x.set("format", fmt)
    x.set("scope", scope)
    x.text = text
    x.tail = "."


def generate_xref_external_html(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                               pretty_print: bool = True) -> Dict[str, bytes]:
    """Xref to external HTML. format=html, scope=external."""
    used = set()
    tid = stable_id("xref_ext_html", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref External HTML"
    body = ET.SubElement(topic, "body")
    _add_xref_ext(body, "https://example.com/guide.html", "html", "external", "external HTML")
    return {"topics/xref_external_html.dita": _topic_xml(config, topic, pretty_print)}


def generate_xref_external_pdf(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                               pretty_print: bool = True) -> Dict[str, bytes]:
    """Xref to local PDF. format=pdf, scope=local."""
    used = set()
    tid = stable_id("xref_ext_pdf", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref External PDF"
    body = ET.SubElement(topic, "body")
    _add_xref_ext(body, "manual.pdf", "pdf", "local", "user manual")
    return {"topics/xref_external_pdf.dita": _topic_xml(config, topic, pretty_print)}


def generate_xref_external_doc(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Xref to external DOC. format=doc, scope=external."""
    used = set()
    tid = stable_id("xref_ext_doc", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref External DOC"
    body = ET.SubElement(topic, "body")
    _add_xref_ext(body, "https://example.com/spec.doc", "doc", "external", "spec document")
    return {"topics/xref_external_doc.dita": _topic_xml(config, topic, pretty_print)}


def generate_xref_external_url(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Xref to web URL. format=html, scope=external."""
    used = set()
    tid = stable_id("xref_ext_url", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Xref External URL"
    body = ET.SubElement(topic, "body")
    _add_xref_ext(body, "https://example.com", "html", "external", "example site")
    return {"topics/xref_external_url.dita": _topic_xml(config, topic, pretty_print)}


# --- Negative ---

def generate_xref_broken_href(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                              pretty_print: bool = True) -> Dict[str, bytes]:
    """Negative: xref with broken href (non-existent target)."""
    used = set()
    tid = stable_id("xref_broken", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Broken Xref"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "Broken: "
    x = ET.SubElement(p, "xref")
    x.set("href", "nonexistent_topic.dita")
    x.text = "missing"
    x.tail = "."
    return {"topics/xref_broken_href.dita": _topic_xml(config, topic, pretty_print)}


def generate_xref_invalid_scope_format(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                                       pretty_print: bool = True) -> Dict[str, bytes]:
    """Negative: xref with invalid scope/format for external resource."""
    used = set()
    tid = stable_id("xref_inv", id_prefix, "topic", used)
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Invalid Scope Format"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "Invalid: "
    x = ET.SubElement(p, "xref")
    x.set("href", "https://example.com/doc.pdf")
    x.set("format", "dita")
    x.set("scope", "peer")
    x.text = "wrong format/scope"
    x.tail = "."
    return {"topics/xref_invalid_scope_format.dita": _topic_xml(config, topic, pretty_print)}


def generate_xref_fragment_only(config: DatasetConfig, base_path: str, id_prefix: str = "t",
                                pretty_print: bool = True) -> Dict[str, bytes]:
    """Xref with fragment-only href (#topicId/elementId)."""
    used = set()
    t1_id = stable_id("xref_frag", id_prefix, "src", used)
    t2_id = stable_id("xref_frag", id_prefix, "tgt", used)
    sec_id = stable_id("xref_frag", id_prefix, "sec", used)
    topic = ET.Element("topic", {"id": t1_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Source"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    x = ET.SubElement(p, "xref")
    x.set("href", "target.dita#" + t2_id + "/" + sec_id)
    x.text = "fragment"
    x.tail = "."
    target = ET.Element("topic", {"id": t2_id, "xml:lang": "en"})
    ET.SubElement(target, "title").text = "Target"
    b2 = ET.SubElement(target, "body")
    sec = ET.SubElement(b2, "section", {"id": sec_id})
    ET.SubElement(sec, "title").text = "Section"
    ET.SubElement(sec, "p").text = "Content."
    return {
        "topics/source.dita": _topic_xml(config, topic, pretty_print),
        "topics/target.dita": _topic_xml(config, target, pretty_print),
    }


# --- RECIPE_SPECS ---

RECIPE_SPECS = [
    _spec("xref_topic_basic", "Xref Topic Basic", "Link to another topic.",
          "generate_xref_topic_basic", ["topic", "body", "p", "xref"], ["XREF", "INTERNAL", "TOPIC"],
          ["jira mentions link to topic", "cross-topic reference"], ["same-file", "external resource"], "positive"),
    _spec("xref_section_target", "Xref Section Target", "Link to a section inside another topic.",
          "generate_xref_section_target", ["topic", "body", "xref", "section"], ["XREF", "INTERNAL", "SECTION"],
          ["jira mentions section link", "link to section in topic"], ["topic-level only", "external"], "positive"),
    _spec("xref_list_item_target", "Xref List Item Target", "Link to an li target in another topic.",
          "generate_xref_list_item_target", ["topic", "body", "xref", "li", "ol"], ["XREF", "INTERNAL", "LI"],
          ["jira mentions list item link", "link to list item"], ["section link", "external"], "positive"),
    _spec("xref_figure_target", "Xref Figure Target", "Link to a figure in another topic.",
          "generate_xref_figure_target", ["topic", "body", "xref", "fig"], ["XREF", "INTERNAL", "FIGURE"],
          ["jira mentions figure link", "link to figure"], ["table link", "external"], "positive"),
    _spec("xref_table_target", "Xref Table Target", "Link to a table in another topic.",
          "generate_xref_table_target", ["topic", "body", "xref", "table"], ["XREF", "INTERNAL", "TABLE"],
          ["jira mentions table link", "link to table"], ["figure link", "external"], "positive"),
    _spec("xref_self_section", "Xref Self Section", "Same-file xref to section.",
          "generate_xref_self_section", ["topic", "body", "xref", "section"], ["XREF", "SELF", "SECTION"],
          ["jira mentions same-file xref", "right panel link to section"], ["cross-topic", "external"], "positive"),
    _spec("xref_self_figure", "Xref Self Figure", "Same-file xref to figure.",
          "generate_xref_self_figure", ["topic", "body", "xref", "fig"], ["XREF", "SELF", "FIGURE"],
          ["same-file figure link"], ["cross-topic", "external"], "positive"),
    _spec("xref_self_table", "Xref Self Table", "Same-file xref to table.",
          "generate_xref_self_table", ["topic", "body", "xref", "table"], ["XREF", "SELF", "TABLE"],
          ["same-file table link"], ["cross-topic", "external"], "positive"),
    _spec("xref_external_html", "Xref External HTML", "Topic with xref to external HTML. format=html, scope=external.",
          "generate_xref_external_html", ["topic", "body", "xref", "external_resource", "html"],
          ["XREF", "EXTERNAL_RESOURCE", "HTML"],
          ["jira mentions pdf reference", "jira mentions link to pdf", "jira mentions non-dita resource"],
          ["link to another topic", "conref reuse"], "positive"),
    _spec("xref_external_pdf", "Xref External PDF", "Topic with xref to local PDF. format=pdf, scope=local.",
          "generate_xref_external_pdf", ["topic", "body", "xref", "external_resource", "pdf"],
          ["XREF", "EXTERNAL_RESOURCE", "PDF"],
          ["jira mentions pdf reference", "jira mentions link to pdf", "jira mentions non-dita resource"],
          ["link to another topic", "conref reuse"], "positive"),
    _spec("xref_external_doc", "Xref External DOC", "Topic with xref to external DOC. format=doc, scope=external.",
          "generate_xref_external_doc", ["topic", "body", "xref", "external_resource", "doc"],
          ["XREF", "EXTERNAL_RESOURCE", "DOC"],
          ["jira mentions doc reference", "link to word document"], ["link to topic", "conref"], "positive"),
    _spec("xref_external_url", "Xref External URL", "Topic with xref to web URL. format=html, scope=external.",
          "generate_xref_external_url", ["topic", "body", "xref", "external_resource", "url"],
          ["XREF", "EXTERNAL_RESOURCE", "URL"],
          ["jira mentions web link", "url reference", "external link"], ["link to topic", "conref"], "positive"),
    _spec("xref_broken_href", "Xref Broken Href", "Negative: xref with broken href (non-existent target).",
          "generate_xref_broken_href", ["topic", "body", "xref"], ["XREF", "NEGATIVE", "BROKEN"],
          ["testing validator catches broken xref", "negative validation"], ["valid datasets", "production"],
          "negative", ["NEGATIVE"]),
    _spec("xref_invalid_scope_format", "Xref Invalid Scope Format", "Negative: xref with invalid scope/format.",
          "generate_xref_invalid_scope_format", ["topic", "body", "xref"], ["XREF", "NEGATIVE", "INVALID"],
          ["testing invalid format/scope", "negative validation"], ["valid datasets", "production"],
          "negative", ["NEGATIVE"]),
    _spec("xref.fragment_only", "Xref Fragment Only", "Xref with fragment-only href (#topicId/elementId).",
          "generate_xref_fragment_only", ["XREF", "FRAGMENT"], ["fragment xref", "section link"], ["full href"], "positive"),
    _spec("xref.invalid_fragment_negative", "Xref Invalid Fragment Negative", "Negative: xref with invalid fragment.",
          "generate_xref_broken_href", ["XREF", "NEGATIVE"], ["validation", "broken fragment"], ["valid xref"], "negative", ["NEGATIVE"]),
    _spec("xref.invalid_scope_format_negative", "Xref Invalid Scope Format Negative", "Negative: invalid scope/format.",
          "generate_xref_invalid_scope_format", ["XREF", "NEGATIVE"], ["validation", "invalid format"], ["valid xref"], "negative", ["NEGATIVE"]),
    # Dot-notation aliases for existing recipes
    _spec("xref.topic_basic", "Xref Topic Basic", "Link to another topic.", "generate_xref_topic_basic",
          ["XREF", "TOPIC"], ["link to topic", "cross-topic reference"], ["same-file", "external"], "positive"),
    _spec("xref.section_target", "Xref Section Target", "Link to section in another topic.", "generate_xref_section_target",
          ["XREF", "SECTION"], ["section link"], ["topic-level only"], "positive"),
    _spec("xref.figure_target", "Xref Figure Target", "Link to figure in another topic.", "generate_xref_figure_target",
          ["XREF", "FIGURE"], ["figure link"], ["table link"], "positive"),
    _spec("xref.table_target", "Xref Table Target", "Link to table in another topic.", "generate_xref_table_target",
          ["XREF", "TABLE"], ["table link"], ["figure link"], "positive"),
    _spec("xref.list_item_target", "Xref List Item Target", "Link to list item in another topic.", "generate_xref_list_item_target",
          ["XREF", "LI"], ["list item link"], ["section link"], "positive"),
    _spec("xref.self_section", "Xref Self Section", "Same-file xref to section.", "generate_xref_self_section",
          ["XREF", "SELF", "SECTION"], ["same-file xref", "section"], ["cross-topic"], "positive"),
    _spec("xref.self_figure", "Xref Self Figure", "Same-file xref to figure.", "generate_xref_self_figure",
          ["XREF", "SELF", "FIGURE"], ["same-file figure"], ["cross-topic"], "positive"),
    _spec("xref.self_table", "Xref Self Table", "Same-file xref to table.", "generate_xref_self_table",
          ["XREF", "SELF", "TABLE"], ["same-file table"], ["cross-topic"], "positive"),
    _spec("xref.external_html", "Xref External HTML", "Xref to external HTML.", "generate_xref_external_html",
          ["XREF", "EXTERNAL", "HTML"], ["html link", "external resource"], ["dita link"], "positive"),
    _spec("xref.external_pdf", "Xref External PDF", "Xref to PDF. format=pdf, scope=local.", "generate_xref_external_pdf",
          ["XREF", "EXTERNAL", "PDF"], ["pdf link", "non-dita resource"], ["dita link"], "positive"),
    _spec("xref.external_doc", "Xref External DOC", "Xref to DOC. format=doc, scope=external.", "generate_xref_external_doc",
          ["XREF", "EXTERNAL", "DOC"], ["doc link", "word document"], ["dita link"], "positive"),
    _spec("xref.external_url", "Xref External URL", "Xref to external web URL. format=html, scope=external.", "generate_xref_external_url",
          ["XREF", "EXTERNAL", "URL"], ["web link", "url"], ["dita link"], "positive"),
]
