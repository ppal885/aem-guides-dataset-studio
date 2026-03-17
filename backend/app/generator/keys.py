"""
Keys / Keyscope recipe family - keydef, keyref, keyscope resolution.

Provides deterministic generators for key-related DITA scenarios.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.generator.keyscope_demo import generate_keyscope_demo_dataset
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


def _map_xml(config: DatasetConfig, map_elem: ET.Element, pretty: bool = True) -> bytes:
    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    if pretty:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'.encode("utf-8") + xml_body


def generate_keys_keydef_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Minimal map with keydef and topicref."""
    used = set()
    map_id = stable_id("keys_keydef", id_prefix, "map", used)
    topic_id = stable_id("keys_keydef", id_prefix, "topic", used)
    root = f"{base_path}/keys_keydef_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Keydef Basic"
    ET.SubElement(map_elem, "keydef", {"keys": "prod", "href": "../topics/target.dita"})
    ET.SubElement(map_elem, "topicref", {"href": "../topics/source.dita", "keyref": "prod"})
    topic_body = '<p>Keyref: <xref keyref="prod"/> resolves to this topic.</p>'
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/target.dita": _topic_xml(config, topic_id, "Target", "Target content."),
        f"{root}/topics/source.dita": _topic_xml(config, stable_id("keys_keydef", id_prefix, "src", used), "Source", topic_body),
    }


def generate_keys_keyref_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with keyref to keydef. Thin wrapper over keydef_basic."""
    return generate_keys_keydef_basic(config, base_path, id_prefix, **kwargs)


def generate_keys_keyscope_shadow_2level(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Two-level keyscope shadow (root + one scope)."""
    return generate_keyscope_demo_dataset(config, base_path, id_prefix, include_qualified_keyrefs=False, **kwargs)


def generate_keys_keyscope_nested_resolution(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Nested keyscope resolution. Uses keyscope_demo."""
    return generate_keyscope_demo_dataset(config, base_path, id_prefix, include_qualified_keyrefs=True, **kwargs)


def generate_keys_duplicate_key_same_scope_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: duplicate key in same scope (invalid)."""
    used = set()
    map_id = stable_id("keys_dup", id_prefix, "map", used)
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Duplicate Key Negative"
    ET.SubElement(map_elem, "keydef", {"keys": "k1", "href": "../topics/a.dita"})
    ET.SubElement(map_elem, "keydef", {"keys": "k1", "href": "../topics/b.dita"})  # duplicate
    root = f"{base_path}/keys_duplicate_negative"
    return {f"{root}/maps/main.ditamap": _map_xml(config, map_elem)}


def generate_keys_duplicate_key_different_scope(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Same key in different keyscopes (valid)."""
    return generate_keyscope_demo_dataset(config, base_path, id_prefix, include_qualified_keyrefs=True, **kwargs)


def generate_keys_external_resource_keydef(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Keydef pointing to external resource (PDF)."""
    used = set()
    map_id = stable_id("keys_ext", id_prefix, "map", used)
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "External Keydef"
    ET.SubElement(map_elem, "keydef", {"keys": "manual", "href": "docs/manual.pdf", "format": "pdf", "scope": "local"})
    root = f"{base_path}/keys_external_keydef"
    return {f"{root}/maps/main.ditamap": _map_xml(config, map_elem)}


def generate_keys_keyref_image(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Keydef for image, keyref in topic."""
    used = set()
    map_id = stable_id("keys_img", id_prefix, "map", used)
    topic_id = stable_id("keys_img", id_prefix, "topic", used)
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Keyref Image"
    ET.SubElement(map_elem, "keydef", {"keys": "hero", "href": "../images/hero.png", "format": "png", "scope": "local"})
    ET.SubElement(map_elem, "topicref", {"href": "../topics/main.dita"})
    body = '<p>Image: <image keyref="hero" alt="Hero image"/></p>'
    root = f"{base_path}/keys_keyref_image"
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/main.dita": _topic_xml(config, topic_id, "Main", body),
    }


def generate_keys_keyref_external_pdf(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Keyref to external PDF. Thin wrapper over external_resource_keydef + topic."""
    used = set()
    map_id = stable_id("keys_pdf", id_prefix, "map", used)
    topic_id = stable_id("keys_pdf", id_prefix, "topic", used)
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Keyref External PDF"
    ET.SubElement(map_elem, "keydef", {"keys": "doc", "href": "../docs/guide.pdf", "format": "pdf", "scope": "local"})
    ET.SubElement(map_elem, "topicref", {"href": "../topics/main.dita"})
    body = '<p>See <xref keyref="doc"/> for the guide.</p>'
    root = f"{base_path}/keys_keyref_external_pdf"
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/main.dita": _topic_xml(config, topic_id, "Main", body),
    }


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None, complexity: str = "minimal") -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "mechanism_family": "keyref",
        "constructs": ["keydef", "keyref", "keyscope", "map", "topicref"],
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": complexity,
        "output_scale": "minimal",
        "module": "app.generator.keys",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("keys.keydef_basic", "Keydef Basic", "Minimal map with keydef and topicref.", "generate_keys_keydef_basic",
          ["KEYDEF", "KEYREF", "KEYS"], ["key definition", "keydef in map"], ["conref", "conditional"], "positive"),
    _spec("keys.keyref_basic", "Keyref Basic", "Topic with keyref to keydef.", "generate_keys_keyref_basic",
          ["KEYREF", "KEYDEF"], ["keyref resolution", "key reference"], ["conref", "xref only"], "positive"),
    _spec("keys.keyscope_shadow_2level", "Keyscope Shadow 2-Level", "Two-level keyscope shadow.", "generate_keys_keyscope_shadow_2level",
          ["KEYSCOPE", "KEYDEF", "KEYREF"], ["keyscope", "scoped keys", "key shadow"], ["single map", "no keys"], "positive", ["BOUNDARY"]),
    _spec("keys.keyscope_nested_resolution", "Keyscope Nested Resolution", "Nested keyscope resolution.", "generate_keys_keyscope_nested_resolution",
          ["KEYSCOPE", "NESTED", "KEYREF"], ["nested keydef", "Map A Map B Topic", "keyscope resolution"], ["single map"], "positive", ["MIN_REPRO", "BOUNDARY"]),
    _spec("keys.duplicate_key_same_scope_negative", "Duplicate Key Same Scope Negative", "Negative: duplicate key in same scope.", "generate_keys_duplicate_key_same_scope_negative",
          ["KEYDEF", "NEGATIVE", "DUPLICATE"], ["validation testing", "duplicate key"], ["valid datasets"], "negative", ["NEGATIVE"]),
    _spec("keys.duplicate_key_different_scope", "Duplicate Key Different Scope", "Same key in different keyscopes (valid).", "generate_keys_duplicate_key_different_scope",
          ["KEYSCOPE", "KEYDEF"], ["scoped keys", "same key different scope"], ["single scope"], "positive"),
    _spec("keys.external_resource_keydef", "External Resource Keydef", "Keydef pointing to external PDF.", "generate_keys_external_resource_keydef",
          ["KEYDEF", "EXTERNAL", "PDF"], ["external resource keydef", "pdf keydef"], ["dita topic only"], "positive"),
    _spec("keys.keyref_image", "Keyref Image", "Keydef for image, keyref in topic.", "generate_keys_keyref_image",
          ["KEYREF", "IMAGE", "KEYDEF"], ["keyref image", "image keydef"], ["direct href image"], "positive"),
    _spec("keys.keyref_external_pdf", "Keyref External PDF", "Keyref to external PDF.", "generate_keys_keyref_external_pdf",
          ["KEYREF", "PDF", "EXTERNAL"], ["keyref pdf", "external pdf link"], ["dita link only"], "positive"),
]
