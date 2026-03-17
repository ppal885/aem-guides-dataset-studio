"""
Nested Keydef (Map → Map → Topic) Dataset Generator.

Generates a DITA dataset matching GUIDES-42533: nested keydef chains where
Map A has keydef pointing to Map B (ditamap), Map B has keydefs (inline + href to Topic C),
Topic C has keywords with id, and Topic D uses keyrefs. Tests recursive key resolution
in AEM Guides Author/Preview (keys must resolve when Map A is context without opening Map B).

Structure:
- Map A: keydef keys="staticKeyMap" href="keymap.ditamap" format="ditamap" + topicref to consumer
- Map B (keymap.ditamap): keydef productName (inline topicmeta), keydef keywordFile href to Topic C
- Topic C (static_content.dita): prolog/keywords/keyword id="versionString"
- Topic D (consumer): uses keyword keyref="productName" and keyword keyref="versionString"
"""
import xml.etree.ElementTree as ET
from typing import Dict, List
from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig

RECIPE_SPECS = [
    {
        "id": "nested_keydef_map_map_topic",
        "mechanism_family": "keyref",
        "title": "Nested Keydef Map Map Topic",
        "description": "Generate nested keydef chain: Map A keydef→Map B keydef→Topic C (keywords). Consumer topic uses keyrefs. Reproduces GUIDES-42533: recursive key resolution when outermost map is context.",
        "tags": ["nested keydef", "keydef", "keyref", "keyscope", "recursive key resolution", "Map Map Topic", "keyword"],
        "module": "app.generator.nested_keydef",
        "function": "generate_nested_keydef_dataset",
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "constructs": ["keydef", "keyref", "keywords", "topicmeta", "keyword", "map", "topicref"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "nested keydef",
            "nested keydefs",
            "Map Map Topic",
            "Map → Map → Topic",
            "keydef pointing to ditamap",
            "recursive key resolution",
            "key resolution through nested maps",
            "keydef chain",
            "Author mode key resolution",
            "keys not resolved in editor",
        ],
        "avoid_when": ["single map", "no key usage", "xref/conref only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "minimal",
        "aem_guides_features": ["key-resolution", "author-mode", "web-editor"],
    },
]


def _topic_xml(
    config: DatasetConfig,
    topic_id: str,
    title: str,
    body_content: str,
    keywords_with_id: List[Dict[str, str]] = None,
    pretty_print: bool = True,
) -> bytes:
    """Generate topic XML. keywords_with_id: [{"id": "versionString", "text": "v6.1"}]."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})

    title_elem = ET.SubElement(topic, "title")
    title_elem.text = title

    if keywords_with_id:
        prolog = ET.SubElement(topic, "prolog")
        metadata = ET.SubElement(prolog, "metadata")
        keywords_elem = ET.SubElement(metadata, "keywords")
        for kw in keywords_with_id:
            kw_elem = ET.SubElement(keywords_elem, "keyword", {"id": kw["id"]})
            kw_elem.text = kw.get("text", kw["id"])

    body = ET.SubElement(topic, "body")
    try:
        body_elem = ET.fromstring(f"<body>{body_content}</body>")
        for child in body_elem:
            body.append(child)
    except ET.ParseError:
        p_elem = ET.SubElement(body, "p")
        p_elem.text = body_content

    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass

    doc = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n{config.doctype_topic}\n"
    return doc.encode("utf-8") + xml_body


def _map_xml(
    config: DatasetConfig,
    map_id: str,
    title: str,
    keydefs: List[Dict],
    topicrefs: List[Dict] = None,
    pretty_print: bool = True,
) -> bytes:
    """Generate map XML. keydefs can have keys, href, format, or inline topicmeta."""
    map_elem = ET.Element("map", {"id": map_id})
    title_elem = ET.SubElement(map_elem, "title")
    title_elem.text = title

    for kd in keydefs:
        keydef_elem = ET.SubElement(map_elem, "keydef")
        for key, value in kd.items():
            if key == "topicmeta":
                # Inline topicmeta: {"topicmeta": {"keyword": "IBM Security Guardium"}}
                tm = value
                if isinstance(tm, dict) and "keyword" in tm:
                    tm_elem = ET.SubElement(keydef_elem, "topicmeta")
                    kw = ET.SubElement(tm_elem, "keyword")
                    kw.text = tm["keyword"]
                continue
            if key in ("keys", "keyscope", "href", "format", "processing-role"):
                keydef_elem.set(key, str(value))

    if topicrefs:
        for tr in topicrefs:
            tr_elem = ET.SubElement(map_elem, "topicref")
            for key, value in tr.items():
                tr_elem.set(key, str(value))

    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass

    doc = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n{config.doctype_map}\n"
    return doc.encode("utf-8") + xml_body


def generate_nested_keydef_dataset(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate nested keydef dataset matching GUIDES-42533.

    Map A: keydef staticKeyMap -> Map B; topicref -> consumer topic
    Map B: keydef productName (inline); keydef keywordFile -> Topic C
    Topic C: keywords with id versionString
    Topic D: uses keyword keyref productName, versionString
    """
    files = {}
    used_ids = set()

    root_folder = f"{base_path}/nested_keydef_map_map_topic"
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"

    map_a_id = make_dita_id("map_a", id_prefix, used_ids)
    map_b_id = make_dita_id("map_b_keymap", id_prefix, used_ids)
    topic_c_id = make_dita_id("static_content", id_prefix, used_ids)
    topic_d_id = make_dita_id("consumer_overview", id_prefix, used_ids)

    topic_c_path = f"{topics_folder}/static_content.dita"
    topic_d_path = f"{topics_folder}/consumer_overview.dita"
    map_a_path = f"{maps_folder}/map_a.ditamap"
    map_b_path = f"{maps_folder}/keymap.ditamap"

    # Topic C: keywords file with id="versionString"
    topic_c_body = "<p>Static content with version and product metadata.</p>"
    files[topic_c_path] = _topic_xml(
        config,
        topic_c_id,
        "Static Content (Keywords)",
        topic_c_body,
        keywords_with_id=[{"id": "versionString", "text": "v6.1"}],
        pretty_print=pretty_print,
    )

    # Topic D: consumer using keyref="productName" and keyref="versionString"
    topic_d_body = (
        '<p>Welcome to <keyword keyref="productName"/> release <keyword keyref="versionString"/>.</p>'
    )
    files[topic_d_path] = _topic_xml(
        config,
        topic_d_id,
        "Consumer Overview",
        topic_d_body,
        pretty_print=pretty_print,
    )

    # Map B (keymap.ditamap): keydef productName (inline), keydef keywordFile -> Topic C
    map_b_keydefs = [
        {"keys": "productName", "topicmeta": {"keyword": "IBM Security Guardium"}},
        {"keys": "keywordFile", "href": "../topics/static_content.dita", "format": "dita"},
    ]
    files[map_b_path] = _map_xml(
        config,
        map_b_id,
        "Key Map (Map B)",
        map_b_keydefs,
        pretty_print=pretty_print,
    )

    # Map A: keydef staticKeyMap -> Map B; topicref -> Topic D
    map_a_keydefs = [
        {"keys": "staticKeyMap", "href": "keymap.ditamap", "format": "ditamap"},
    ]
    map_a_topicrefs = [
        {"href": "../topics/consumer_overview.dita", "navtitle": "Consumer Overview", "type": "topic"},
    ]
    files[map_a_path] = _map_xml(
        config,
        map_a_id,
        "Map A (Root Context)",
        map_a_keydefs,
        topicrefs=map_a_topicrefs,
        pretty_print=pretty_print,
    )

    readme = """Nested Keydef (Map → Map → Topic) Dataset
============================================

Reproduces GUIDES-42533: nested keydef chains not resolved in AEM Guides Author mode.

Structure:
- Map A (map_a.ditamap): keydef staticKeyMap -> keymap.ditamap; topicref -> consumer_overview.dita
- Map B (keymap.ditamap): keydef productName (inline); keydef keywordFile -> static_content.dita
- Topic C (static_content.dita): keywords with id="versionString"
- Topic D (consumer_overview.dita): uses keyword keyref="productName", keyref="versionString"

Expected: When Map A is opened as context, keys productName and versionString should resolve.
Bug: Keys only resolve when Map B is opened as root context. DITA-OT publishes correctly.
"""
    files[f"{root_folder}/README.txt"] = readme.encode("utf-8")
    return files
