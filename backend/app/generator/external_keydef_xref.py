"""External keydef/xref DITA bundle generator."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join
from app.jobs.schemas import DatasetConfig
from app.utils.xml_escape import xml_escape_attr, xml_escape_href, xml_escape_text


RECIPE_SPECS = [
    {
        "id": "external_keydef_xref_bundle",
        "title": "External Keydef Xref Bundle",
        "description": "Generate a map-defined external keydef consumed by a topic xref keyref.",
        "tags": ["keydef", "keyref", "xref", "external", "map"],
        "module": "app.generator.external_keydef_xref",
        "function": "generate_external_keydef_xref_bundle",
        "params_schema": {
            "key_name": "str",
            "href": "str",
            "format": "str",
            "scope": "str",
            "link_text": "str",
            "topic_title": "str",
            "map_title": "str",
        },
        "default_params": {
            "key_name": "external-docs",
            "href": "https://example.com/docs",
            "format": "html",
            "scope": "external",
            "link_text": "External documentation",
            "topic_title": "Using external keyed references",
            "map_title": "External keyed references map",
        },
        "stability": "stable",
        "constructs": ["map", "keydef", "topicref", "xref", "keyref"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["external links as keydefs", "keydef external xref", "cross-reference through keyref"],
        "avoid_when": ["direct external xref href", "no map"],
        "positive_negative": "positive",
        "complexity": "low",
        "output_scale": "minimal",
    },
]


def _normalize_key_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip().lower()).strip("-")
    return clean or "external-docs"


def _doctype(config: DatasetConfig, name: str) -> str:
    return getattr(config, f"doctype_{name}", None) or (
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
        if name == "map"
        else '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    )


def _serialize(root: ET.Element, doctype: str) -> bytes:
    xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}\n'.encode("utf-8") + xml_body


def generate_external_keydef_xref_bundle(
    config: DatasetConfig,
    base_path: str,
    key_name: str = "external-docs",
    href: str = "https://example.com/docs",
    format: str = "html",
    scope: str = "external",
    link_text: str = "External documentation",
    topic_title: str = "Using external keyed references",
    map_title: str = "External keyed references map",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """Generate a minimal, construct-true external keydef/xref bundle."""

    del pretty_print
    files: Dict[str, bytes] = {}
    used_ids: set[str] = set()
    root_folder = safe_join(base_path, "external_keydef_xref")
    maps_folder = safe_join(root_folder, "maps")
    topics_folder = safe_join(root_folder, "topics")
    key = _normalize_key_name(key_name)
    clean_href = str(href or "").strip() or "https://example.com/docs"
    clean_format = str(format or "").strip().lower() or "html"
    clean_scope = str(scope or "").strip().lower() or "external"
    clean_link_text = str(link_text or "").strip() or "External documentation"

    topic_path = safe_join(topics_folder, "external_reference.dita")
    map_path = safe_join(maps_folder, "external_links.ditamap")
    topic_id = stable_id(config.seed, "external_reference", key, used_ids)
    map_id = stable_id(config.seed, "external_links_map", key, used_ids)

    topic = ET.Element("topic", {"id": xml_escape_attr(topic_id), "xml:lang": "en"})
    title = ET.SubElement(topic, "title")
    title.text = xml_escape_text(topic_title)
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = xml_escape_text("This topic consumes an external resource through a map-defined key.")
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    xref = ET.SubElement(p, "xref", {"keyref": xml_escape_attr(key)})
    xref.text = xml_escape_text(clean_link_text)
    xref.tail = "."
    files[topic_path] = _serialize(topic, _doctype(config, "topic"))

    map_elem = ET.Element("map", {"id": xml_escape_attr(map_id)})
    map_title_elem = ET.SubElement(map_elem, "title")
    map_title_elem.text = xml_escape_text(map_title)
    keydef = ET.SubElement(
        map_elem,
        "keydef",
        {
            "keys": xml_escape_attr(key),
            "href": xml_escape_href(clean_href),
            "scope": xml_escape_attr(clean_scope),
            "format": xml_escape_attr(clean_format),
        },
    )
    topicmeta = ET.SubElement(keydef, "topicmeta")
    linktext = ET.SubElement(topicmeta, "linktext")
    linktext.text = xml_escape_text(clean_link_text)
    ET.SubElement(map_elem, "topicref", {"href": xml_escape_href("../topics/external_reference.dita")})
    files[map_path] = _serialize(map_elem, _doctype(config, "map"))

    return files
