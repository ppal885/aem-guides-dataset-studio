"""
Metadata recipe family - topicmeta, keywords, indexterm, cascade, audience, platform.

Extends topicmeta_recipes and keyword_metadata with dot-notation recipe IDs.
"""
from typing import Dict

from app.generator.topicmeta_recipes import (
    generate_topicmeta_keywords,
    generate_topicmeta_keywords_indexterm,
    generate_topicmeta_cascade,
    generate_topicmeta_negative,
)
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.jobs.schemas import DatasetConfig


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body: str, pretty: bool = True) -> bytes:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    b = ET.SubElement(topic, "body")
    p = ET.SubElement(b, "p")
    p.text = body
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    if pretty:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'.encode("utf-8") + xml_body


def generate_metadata_topicmeta_keywords_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicmeta with keywords. Wrapper over topicmeta_recipes."""
    return generate_topicmeta_keywords(config, base_path, id_prefix, **kwargs)


def generate_metadata_topicmeta_indexterm(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicmeta with indexterm. Thin wrapper - use keywords_indexterm as base."""
    return generate_topicmeta_keywords_indexterm(config, base_path, id_prefix, **kwargs)


def generate_metadata_topicmeta_keywords_indexterm(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicmeta with keywords and indexterm."""
    return generate_topicmeta_keywords_indexterm(config, base_path, id_prefix, **kwargs)


def generate_metadata_cascade_map_to_topicref(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicmeta metadata cascade via topicref. Uses topicmeta_cascade."""
    return generate_topicmeta_cascade(config, base_path, id_prefix, **kwargs)


def generate_metadata_override_topicref_over_topic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicref metadata overrides topic metadata. Uses cascade variant."""
    return generate_topicmeta_cascade(config, base_path, id_prefix, **kwargs)


def generate_metadata_audience_platform_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with audience and platform attributes."""
    import random
    rand = kwargs.get("rand") or __import__("random").Random(config.seed)
    used = set()
    tid = stable_id("meta_ap", id_prefix, "topic", used)
    root = f"{base_path}/metadata_audience_platform"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Audience Platform"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p", {"audience": "admin", "platform": "windows"})
    p.text = "Admin Windows content."
    p2 = ET.SubElement(body, "p", {"audience": "user", "platform": "linux"})
    p2.text = "User Linux content."
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return {f"{root}/topics/main.dita": doc.encode("utf-8") + xml_body}


def generate_metadata_props_otherprops_combo(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with product and otherprops attributes."""
    used = set()
    tid = stable_id("meta_props", id_prefix, "topic", used)
    root = f"{base_path}/metadata_props_otherprops"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Props Otherprops"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p", {"product": "acme", "otherprops": "beta"})
    p.text = "Acme beta content."
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return {f"{root}/topics/main.dita": doc.encode("utf-8") + xml_body}


def generate_metadata_invalid_attribute_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: invalid topicmeta placement."""
    return generate_topicmeta_negative(config, base_path, id_prefix, **kwargs)


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["topicmeta", "keywords", "indexterm", "audience", "platform", "product", "otherprops"],
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.metadata",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("metadata.topicmeta_keywords_basic", "Topicmeta Keywords Basic", "Map with topicmeta keywords.", "generate_metadata_topicmeta_keywords_basic",
          ["TOPICMETA", "KEYWORDS"], ["topicmeta", "keywords in map"], ["prolog only"], "positive"),
    _spec("metadata.topicmeta_indexterm", "Topicmeta Indexterm", "Topicmeta with indexterm.", "generate_metadata_topicmeta_indexterm",
          ["TOPICMETA", "INDEXTERM"], ["indexterm", "index entry"], ["keywords only"], "positive"),
    _spec("metadata.topicmeta_keywords_indexterm", "Topicmeta Keywords Indexterm", "Topicmeta with keywords and indexterm.", "generate_metadata_topicmeta_keywords_indexterm",
          ["TOPICMETA", "KEYWORDS", "INDEXTERM"], ["keywords indexterm", "metadata cascade"], ["minimal metadata"], "positive"),
    _spec("metadata.cascade_map_to_topicref", "Cascade Map to Topicref", "Topicmeta cascade via topicref.", "generate_metadata_cascade_map_to_topicref",
          ["TOPICMETA", "CASCADE"], ["metadata cascade", "topicref metadata"], ["single topic"], "positive"),
    _spec("metadata.override_topicref_over_topic", "Override Topicref Over Topic", "Topicref metadata overrides topic.", "generate_metadata_override_topicref_over_topic",
          ["TOPICMETA", "OVERRIDE"], ["metadata override", "topicref over topic"], ["no override"], "positive"),
    _spec("metadata.audience_platform_basic", "Audience Platform Basic", "Topic with audience and platform.", "generate_metadata_audience_platform_basic",
          ["AUDIENCE", "PLATFORM"], ["audience", "platform filter"], ["unconditional"], "positive"),
    _spec("metadata.props_otherprops_combo", "Props Otherprops Combo", "Topic with product and otherprops.", "generate_metadata_props_otherprops_combo",
          ["PRODUCT", "OTHERPROPS"], ["product", "otherprops"], ["no conditions"], "positive"),
    _spec("metadata.invalid_attribute_negative", "Invalid Attribute Negative", "Negative: invalid topicmeta placement.", "generate_metadata_invalid_attribute_negative",
          ["TOPICMETA", "NEGATIVE"], ["validation", "invalid topicmeta"], ["valid metadata"], "negative", ["NEGATIVE"]),
]
