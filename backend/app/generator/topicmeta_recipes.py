"""
Topicmeta recipe family - DITA map metadata (keywords, indexterm, cascade).

Generates datasets demonstrating topicmeta in maps:
- topicmeta with keywords
- topicmeta with keywords + indexterm
- topicmeta metadata cascade via nested topicref
- broken/invalid topicmeta placement (negative)
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.jobs.schemas import DatasetConfig


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_content: str, pretty_print: bool = True) -> bytes:
    """Generate topic XML."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = body_content
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
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
    """Serialize map element to bytes."""
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


def generate_topicmeta_keywords(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Map with topicref + topicmeta > keywords. Minimal valid topicmeta."""
    used_ids = set()
    map_id = stable_id("topicmeta_kw", id_prefix, "map", used_ids)
    topic_id = stable_id("topicmeta_kw", id_prefix, "topic", used_ids)
    topics_rel = "../topics"
    topic_href = f"{topics_rel}/topicmeta_topic.dita"
    map_rel = "maps/topicmeta_keywords.ditamap"

    topic_content = _topic_xml(config, topic_id, "Topicmeta Keywords Topic", "Content.", pretty_print)

    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicmeta Keywords"
    tr = ET.SubElement(map_elem, "topicref", {"href": topic_href})
    tm = ET.SubElement(tr, "topicmeta")
    kw = ET.SubElement(tm, "keywords")
    ET.SubElement(kw, "keyword").text = "metadata"
    ET.SubElement(kw, "keyword").text = "search"

    files = {
        "topics/topicmeta_topic.dita": topic_content,
        map_rel: _map_xml(config, map_elem, pretty_print),
    }
    return files


def generate_topicmeta_keywords_indexterm(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Map with topicref + topicmeta > keywords > keyword + indexterm."""
    used_ids = set()
    map_id = stable_id("topicmeta_kw_idx", id_prefix, "map", used_ids)
    topic_id = stable_id("topicmeta_kw_idx", id_prefix, "topic", used_ids)
    topics_rel = "../topics"
    topic_href = f"{topics_rel}/topicmeta_indexterm_topic.dita"
    map_rel = "maps/topicmeta_keywords_indexterm.ditamap"

    topic_content = _topic_xml(config, topic_id, "Topicmeta Indexterm Topic", "Content.", pretty_print)

    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicmeta Keywords Indexterm"
    tr = ET.SubElement(map_elem, "topicref", {"href": topic_href})
    tm = ET.SubElement(tr, "topicmeta")
    kw = ET.SubElement(tm, "keywords")
    ET.SubElement(kw, "keyword").text = "indexing"
    idx = ET.SubElement(kw, "indexterm")
    idx.text = "topicmeta indexterm"

    files = {
        "topics/topicmeta_indexterm_topic.dita": topic_content,
        map_rel: _map_xml(config, map_elem, pretty_print),
    }
    return files


def generate_topicmeta_cascade(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Map with nested topicrefs; parent topicmeta cascades to children."""
    used_ids = set()
    map_id = stable_id("topicmeta_cascade", id_prefix, "map", used_ids)
    t1_id = stable_id("topicmeta_cascade", id_prefix, "t1", used_ids)
    t2_id = stable_id("topicmeta_cascade", id_prefix, "t2", used_ids)
    topics_rel = "../topics"
    parent_href = f"{topics_rel}/topicmeta_parent.dita"
    child_href = f"{topics_rel}/topicmeta_child.dita"
    map_rel = "maps/topicmeta_cascade.ditamap"

    t1 = _topic_xml(config, t1_id, "Parent Topic", "Parent content.", pretty_print)
    t2 = _topic_xml(config, t2_id, "Child Topic", "Child content.", pretty_print)

    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicmeta Cascade"
    parent_tr = ET.SubElement(map_elem, "topicref", {"href": parent_href})
    tm = ET.SubElement(parent_tr, "topicmeta")
    auth = ET.SubElement(tm, "author")
    auth.text = "Map Author"
    ET.SubElement(parent_tr, "topicref", {"href": child_href})

    files = {
        "topics/topicmeta_parent.dita": t1,
        "topics/topicmeta_child.dita": t2,
        map_rel: _map_xml(config, map_elem, pretty_print),
    }
    return files


def generate_topicmeta_negative(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Negative: topic with topicmeta inside body (invalid placement)."""
    used_ids = set()
    topic_id = stable_id("topicmeta_neg", id_prefix, "topic", used_ids)
    topics_rel = "topics"
    rel_path = f"{topics_rel}/topicmeta_negative.dita"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Invalid Topicmeta"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "Content. "
    tm = ET.SubElement(body, "topicmeta")
    kw = ET.SubElement(tm, "keywords")
    ET.SubElement(kw, "keyword").text = "invalid"

    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    content = doc.encode("utf-8") + xml_body

    return {rel_path: content}


RECIPE_SPECS = [
    {
        "id": "topicmeta_keywords",
        "title": "Topicmeta Keywords",
        "description": "Map with topicref and topicmeta containing keywords. Minimal valid topicmeta.",
        "tags": ["topicmeta", "keywords", "map", "metadata", "topicref"],
        "constructs": ["topicmeta", "keywords", "keyword", "topicref", "map"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["testing topicmeta keywords", "map-level metadata", "search indexing from map"],
        "avoid_when": ["topic-level prolog only", "indexterm needed", "metadata cascade test"],
        "examples": [{"prompt": "Generate map with topicmeta keywords on topicref"}],
        "positive_negative": "positive",
        "module": "app.generator.topicmeta_recipes",
        "function": "generate_topicmeta_keywords",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
    },
    {
        "id": "topicmeta_keywords_indexterm",
        "title": "Topicmeta Keywords Indexterm",
        "description": "Map with topicref and topicmeta containing keywords and indexterm.",
        "tags": ["topicmeta", "keywords", "indexterm", "map", "metadata"],
        "constructs": ["topicmeta", "keywords", "keyword", "indexterm", "topicref", "map"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["testing topicmeta with indexterm", "index generation from map", "keywords plus index"],
        "avoid_when": ["keywords only", "cascade test", "invalid placement test"],
        "examples": [{"prompt": "Generate map with topicmeta keywords and indexterm"}],
        "positive_negative": "positive",
        "module": "app.generator.topicmeta_recipes",
        "function": "generate_topicmeta_keywords_indexterm",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
    },
    {
        "id": "topicmeta_cascade",
        "title": "Topicmeta Cascade",
        "description": "Map with nested topicrefs; parent topicmeta (author) cascades to child topicref.",
        "tags": ["topicmeta", "cascade", "author", "topicref", "map", "metadata"],
        "constructs": ["topicmeta", "author", "topicref", "map", "cascade"],
        "scenario_types": ["BOUNDARY", "INTEGRATION"],
        "use_when": ["testing metadata cascade", "nested topicref metadata", "author inheritance"],
        "avoid_when": ["flat map", "keywords only", "single topicref"],
        "examples": [{"prompt": "Generate map with topicmeta cascade to child topicrefs"}],
        "positive_negative": "positive",
        "module": "app.generator.topicmeta_recipes",
        "function": "generate_topicmeta_cascade",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
    },
    {
        "id": "topicmeta_negative",
        "title": "Topicmeta Negative",
        "description": "Invalid: topic with topicmeta inside body. For validation testing.",
        "tags": ["topicmeta", "negative", "validation", "invalid"],
        "constructs": ["topic", "body", "topicmeta"],
        "scenario_types": ["NEGATIVE"],
        "use_when": ["testing validator catches invalid topicmeta placement", "negative validation scenario"],
        "avoid_when": ["generating valid datasets", "production content", "map context"],
        "examples": [{"prompt": "Generate invalid topicmeta placement for validation test"}],
        "positive_negative": "negative",
        "module": "app.generator.topicmeta_recipes",
        "function": "generate_topicmeta_negative",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
    },
]
