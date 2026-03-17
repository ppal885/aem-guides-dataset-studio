"""
Asset / Media recipe family - image, alt text, external reference.

Deterministic generators for image and media scenarios.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.jobs.schemas import DatasetConfig


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_elem: ET.Element, pretty: bool = True) -> bytes:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    body = ET.SubElement(topic, "body")
    body.append(body_elem)
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


def generate_assets_image_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with basic image reference."""
    used = set()
    tid = stable_id("assets_img", id_prefix, "topic", used)
    root = f"{base_path}/assets_image_basic"
    body = ET.Element("body")
    p = ET.SubElement(body, "p")
    p.text = "See image: "
    img = ET.SubElement(p, "image", {"href": "images/fig1.png", "alt": "Figure 1"})
    img.tail = "."
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Image Basic", body)}


def generate_assets_image_with_alt(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with image and proper alt text."""
    return generate_assets_image_basic(config, base_path, id_prefix, **kwargs)


def generate_assets_image_external_reference(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with image referencing external URL."""
    used = set()
    tid = stable_id("assets_ext", id_prefix, "topic", used)
    root = f"{base_path}/assets_image_external"
    body = ET.Element("body")
    p = ET.SubElement(body, "p")
    p.text = "External: "
    img = ET.SubElement(p, "image", {"href": "https://example.com/image.png", "alt": "External image", "scope": "external"})
    img.tail = "."
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Image External", body)}


def generate_assets_image_missing_alt_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: image without alt (accessibility)."""
    used = set()
    tid = stable_id("assets_neg", id_prefix, "topic", used)
    root = f"{base_path}/assets_image_missing_alt_negative"
    body = ET.Element("body")
    p = ET.SubElement(body, "p")
    p.text = "Image: "
    img = ET.SubElement(p, "image", {"href": "images/fig1.png"})  # no alt
    img.tail = "."
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Image Missing Alt Negative", body)}


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["image", "alt", "figure", "media"],
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.assets",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("assets.image_basic", "Image Basic", "Topic with basic image reference.", "generate_assets_image_basic",
          ["IMAGE", "MEDIA"], ["image", "figure", "media"], ["text only"], "positive"),
    _spec("assets.image_with_alt", "Image With Alt", "Topic with image and proper alt text.", "generate_assets_image_with_alt",
          ["IMAGE", "ALT"], ["image alt", "accessibility"], ["image without alt"], "positive"),
    _spec("assets.image_external_reference", "Image External Reference", "Image referencing external URL.", "generate_assets_image_external_reference",
          ["IMAGE", "EXTERNAL"], ["external image", "url image"], ["local image"], "positive"),
    _spec("assets.image_missing_alt_negative", "Image Missing Alt Negative", "Negative: image without alt.", "generate_assets_image_missing_alt_negative",
          ["IMAGE", "NEGATIVE", "ALT"], ["validation", "accessibility", "missing alt"], ["valid image"], "negative", ["NEGATIVE"]),
]
