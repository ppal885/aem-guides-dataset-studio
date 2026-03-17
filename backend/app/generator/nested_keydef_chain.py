"""
Nested Keydef Chain (Map A -> Map B -> Topic C) - minimal repro for recursive key resolution.

Reproduces AEM Guides Web Editor bug: nested keys not resolved when Map A is context map,
but resolve when Map B is opened as root. DITA-OT publishes correctly.

Structure:
- Map A: keydef to Map B + optional direct key + topicref to Topic D
- Map B: keydef productName (topicmeta) + keydef keywordFile -> Topic C
- Topic C: keywords with id (e.g. versionString)
- Topic D: uses keyref productName, versionString

Recipe ID: keyref_nested_keydef_chain_map_to_map_to_topic
Recipe family: keyref
Pattern: nested_keydef_chain_map_to_map_to_topic
"""
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


def _topic_xml(
    config: DatasetConfig,
    topic_id: str,
    title: str,
    body_content: str,
    keywords_with_id: Optional[List[Dict[str, str]]] = None,
    pretty_print: bool = True,
) -> bytes:
    """Generate topic XML. keywords_with_id: [{"id": "versionString", "text": "v6.1"}]."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title

    body = ET.SubElement(topic, "body")
    if keywords_with_id:
        keywords_elem = ET.SubElement(body, "keywords")
        for kw in keywords_with_id:
            kw_elem = ET.SubElement(keywords_elem, "keyword", {"id": kw["id"]})
            kw_elem.text = kw.get("text", kw["id"])
    if body_content:
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
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _map_xml(
    config: DatasetConfig,
    map_id: str,
    title: str,
    keydefs: List[Dict],
    topicrefs: Optional[List[Dict]] = None,
    pretty_print: bool = True,
) -> bytes:
    """Generate map XML. keydefs: [{"keys": "x", "href": "...", "format": "..."} or {"keys": "x", "topicmeta": {"keyword": "..."}}]."""
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = title

    for kd in keydefs:
        keydef_elem = ET.SubElement(map_elem, "keydef")
        for key, value in kd.items():
            if key == "topicmeta":
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
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    return doc.encode("utf-8") + xml_body


def _validate_chain_correctness(
    files: Dict[str, bytes],
    map_a_path: str,
    map_b_path: str,
    topic_c_path: str,
    topic_d_path: str,
    root_to_intermediate_key: str,
    map_b_file: str,
    topic_c_file: str,
    consumer_keyrefs: List[str],
    include_nested_keyword_topic: bool,
) -> Dict:
    """
    Validate recursive keydef chain: Map A keydef->Map B keydef->Topic C; Topic D keyrefs.
    Returns {valid: bool, errors: list[str], checks: dict}.
    """
    errors: List[str] = []
    checks: Dict[str, bool] = {}

    def _parse(path: str):
        content = files.get(path)
        if not content:
            return None
        try:
            return ET.fromstring(content)
        except ET.ParseError:
            return None

    map_a = _parse(map_a_path)
    map_b = _parse(map_b_path)
    topic_d = _parse(topic_d_path)
    topic_c = _parse(topic_c_path) if include_nested_keyword_topic else None

    # Map A must have keydef to Map B
    map_a_has_keydef_to_b = False
    if map_a is not None:
        for kd in map_a.findall(".//keydef"):
            href = kd.get("href", "")
            keys_attr = kd.get("keys", "")
            if keys_attr == root_to_intermediate_key and (map_b_file in href or "ditamap" in href):
                map_a_has_keydef_to_b = True
                break
    checks["map_a_keydef_to_map_b"] = map_a_has_keydef_to_b
    if not map_a_has_keydef_to_b and map_a is not None:
        errors.append("Map A must contain keydef to Map B")

    # Map A must have topicref to Topic D
    map_a_has_topicref_to_d = False
    if map_a is not None:
        for tr in map_a.findall(".//topicref"):
            href = tr.get("href", "")
            if href and ("topics/" in href or href.endswith(".dita")):
                map_a_has_topicref_to_d = True
                break
    checks["map_a_topicref_to_topic_d"] = map_a_has_topicref_to_d

    # Map B must have keydef to Topic C (when nested keyword topic included)
    map_b_has_keydef_to_c = True
    if include_nested_keyword_topic and map_b is not None:
        map_b_has_keydef_to_c = False
        for kd in map_b.findall(".//keydef"):
            href = kd.get("href", "")
            if topic_c_file in href or "dita" in href:
                map_b_has_keydef_to_c = True
                break
        checks["map_b_keydef_to_topic_c"] = map_b_has_keydef_to_c
        if not map_b_has_keydef_to_c:
            errors.append("Map B must contain keydef to Topic C")

    # Topic D must have keyref elements
    topic_d_has_keyrefs = False
    if topic_d is not None:
        keyrefs_found = topic_d.findall(".//*[@keyref]")
        keyref_vals = {e.get("keyref") for e in keyrefs_found if e.get("keyref")}
        topic_d_has_keyrefs = all(kr in keyref_vals for kr in consumer_keyrefs)
    checks["topic_d_has_keyrefs"] = topic_d_has_keyrefs
    if not topic_d_has_keyrefs and topic_d is not None:
        errors.append("Topic D must contain keyref elements for consumer keys")

    # Topic C must have keyword with id (when included)
    topic_c_has_keyword = True
    if include_nested_keyword_topic and topic_c is not None:
        topic_c_has_keyword = len(topic_c.findall(".//keyword[@id]")) > 0
        checks["topic_c_has_keyword_id"] = topic_c_has_keyword
        if not topic_c_has_keyword:
            errors.append("Topic C must contain keyword with id attribute")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "checks": checks,
    }


def generate_keyref_nested_keydef_chain_map_to_map_to_topic(
    config: DatasetConfig,
    base_path: str,
    root_map_name: str = "map_a.ditamap",
    intermediate_map_name: str = "map_b.ditamap",
    keyword_topic_name: str = "topic_c_keywords.dita",
    consumer_topic_name: str = "topic_d_consumer.dita",
    root_map_title: str = "Outer Context Map",
    intermediate_map_title: str = "Static Key Map",
    keyword_topic_title: str = "Keyword Source Topic",
    consumer_topic_title: str = "Consumer Topic",
    root_to_intermediate_key: str = "staticKeyMap",
    direct_intermediate_key_name: str = "productName",
    nested_keyword_file_key_name: str = "keywordFile",
    nested_keyword_id: str = "versionString",
    consumer_keyrefs: Optional[List[str]] = None,
    include_direct_key_in_root_map: bool = True,
    include_direct_key_in_intermediate_map: bool = True,
    include_nested_keyword_topic: bool = True,
    include_workaround_notes: bool = True,
    include_expected_rendering_text: bool = True,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    """
    Generate minimal repro for nested keydef chain resolution.

    Map A -> Map B -> Topic C. Topic D consumes keys. Keys resolve when Map B is root
    but may not when Map A is context (Web Editor bug). DITA-OT correct.
    """
    consumer_keyrefs = consumer_keyrefs or ["productName", "versionString"]
    used_ids = set()

    root_folder = f"{base_path}/keyref_nested_keydef_chain"
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"
    meta_folder = f"{root_folder}/meta"

    map_a_id = make_dita_id("map_a", id_prefix, used_ids)
    map_b_id = make_dita_id("map_b", id_prefix, used_ids)
    topic_c_id = make_dita_id("topic_c_keywords", id_prefix, used_ids)
    topic_d_id = make_dita_id("topic_d_consumer", id_prefix, used_ids)

    win_safe = getattr(config, "windows_safe_filenames", True)
    topic_c_file = sanitize_filename(keyword_topic_name.replace(".dita", ".dita"), win_safe)
    topic_d_file = sanitize_filename(consumer_topic_name.replace(".dita", ".dita"), win_safe)
    map_a_file = sanitize_filename(root_map_name.replace(".ditamap", ".ditamap"), win_safe)
    map_b_file = sanitize_filename(intermediate_map_name.replace(".ditamap", ".ditamap"), win_safe)

    topic_c_path = f"{topics_folder}/{topic_c_file}"
    topic_d_path = f"{topics_folder}/{topic_d_file}"
    map_a_path = f"{maps_folder}/{map_a_file}"
    map_b_path = f"{maps_folder}/{map_b_file}"

    files: Dict[str, bytes] = {}

    # Topic C: keyword source
    if include_nested_keyword_topic:
        topic_c_body = "<p>Static content with version and product metadata.</p>"
        files[topic_c_path] = _topic_xml(
            config,
            topic_c_id,
            keyword_topic_title,
            topic_c_body,
            keywords_with_id=[{"id": nested_keyword_id, "text": "v6.1"}],
            pretty_print=pretty_print,
        )

    # Topic D: consumer
    keyref_markup = " ".join(f'<keyword keyref="{kr}"/>' for kr in consumer_keyrefs)
    if include_expected_rendering_text and len(consumer_keyrefs) >= 2:
        topic_d_body = f'<p>Welcome to <keyword keyref="{consumer_keyrefs[0]}"/> release <keyword keyref="{consumer_keyrefs[1]}"/>.</p>'
    else:
        topic_d_body = f"<p>{keyref_markup}</p>"

    files[topic_d_path] = _topic_xml(
        config,
        topic_d_id,
        consumer_topic_title,
        topic_d_body,
        pretty_print=pretty_print,
    )

    # Map B: keydef productName (inline), keydef keywordFile -> Topic C
    map_b_keydefs: List[Dict] = []
    if include_direct_key_in_intermediate_map:
        map_b_keydefs.append({
            "keys": direct_intermediate_key_name,
            "topicmeta": {"keyword": "IBM Security Guardium"},
        })
    if include_nested_keyword_topic:
        map_b_keydefs.append({
            "keys": nested_keyword_file_key_name,
            "href": f"../topics/{topic_c_file}",
            "format": "dita",
        })

    files[map_b_path] = _map_xml(
        config,
        map_b_id,
        intermediate_map_title,
        map_b_keydefs,
        pretty_print=pretty_print,
    )

    # Map A: keydef staticKeyMap -> Map B; optional direct key; topicref -> Topic D
    map_a_keydefs: List[Dict] = []
    if include_direct_key_in_root_map:
        map_a_keydefs.append({
            "keys": "rootVisibleKey",
            "topicmeta": {"keyword": "Outer Root Value"},
        })
    map_a_keydefs.append({
        "keys": root_to_intermediate_key,
        "href": map_b_file,
        "format": "ditamap",
    })

    map_a_topicrefs = [
        {"href": f"../topics/{topic_d_file}", "navtitle": consumer_topic_title, "type": "topic"},
    ]

    files[map_a_path] = _map_xml(
        config,
        map_a_id,
        root_map_title,
        map_a_keydefs,
        topicrefs=map_a_topicrefs,
        pretty_print=pretty_print,
    )

    # Stats
    keydef_count = len(map_a_keydefs) + len(map_b_keydefs)
    direct_key_count = (1 if include_direct_key_in_root_map else 0) + (1 if include_direct_key_in_intermediate_map else 0)
    nested_key_count = 1 if include_nested_keyword_topic else 0

    readme_lines = [
        "Nested Keydef Chain (Map A -> Map B -> Topic C)",
        "==============================================",
        "",
        "Reproduces AEM Guides Web Editor: nested keys not resolved when Map A is context.",
        "",
        "Structure:",
        f"- Map A ({map_a_file}): keydef {root_to_intermediate_key} -> {map_b_file}; topicref -> {topic_d_file}",
        f"- Map B ({map_b_file}): keydef {direct_intermediate_key_name} (inline); keydef {nested_keyword_file_key_name} -> {topic_c_file}",
        f"- Topic C ({topic_c_file}): keywords with id={nested_keyword_id}",
        f"- Topic D ({topic_d_file}): uses keyref {consumer_keyrefs}",
        "",
        "Expected: When Map A is opened as context, keys should resolve.",
        "Bug: Keys only resolve when Map B is opened as root. DITA-OT publishes correctly.",
    ]
    if include_workaround_notes:
        readme_lines.extend([
            "",
            "Workaround: Open Map B as root context map to verify keys resolve.",
        ])

    files[f"{root_folder}/README.txt"] = "\n".join(readme_lines).encode("utf-8")

    # Manifest
    stats = {
        "map_count": 2,
        "topic_count": 2,
        "keydef_count": keydef_count,
        "keyref_count": len(consumer_keyrefs),
        "keyword_count": 1 if include_nested_keyword_topic else 0,
        "direct_key_count": direct_key_count,
        "nested_key_count": nested_key_count,
        "variant_count": 1,
        "generated_files": list(files.keys()),
    }

    manifest_path = f"{meta_folder}/manifest.json"
    stats["generated_files"] = list(files.keys()) + [manifest_path]
    warnings: List[str] = []

    # Validate XML well-formedness
    for path, content in list(files.items()):
        if path.endswith((".dita", ".ditamap")):
            try:
                ET.fromstring(content)
            except ET.ParseError as e:
                warnings.append(f"XML validation failed for {path}: {e}")

    # Validate chain correctness: Map A -> Map B -> Topic C; Topic D consumer
    chain_validation = _validate_chain_correctness(
        files=files,
        map_a_path=map_a_path,
        map_b_path=map_b_path,
        topic_c_path=topic_c_path,
        topic_d_path=topic_d_path,
        root_to_intermediate_key=root_to_intermediate_key,
        map_b_file=map_b_file,
        topic_c_file=topic_c_file,
        consumer_keyrefs=consumer_keyrefs,
        include_nested_keyword_topic=include_nested_keyword_topic,
    )
    if not chain_validation["valid"]:
        warnings.extend(chain_validation["errors"])
    stats["chain_validation"] = chain_validation

    manifest = {
        "recipe_name": "keyref_nested_keydef_chain_map_to_map_to_topic",
        "files": stats["generated_files"],
        "stats": stats,
        "assumptions": [],
        "warnings": warnings,
    }
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "keyref_nested_keydef_chain_map_to_map_to_topic",
        "mechanism_family": "keyref",
        "title": "Nested Keydef Chain (Map A -> Map B -> Topic C)",
        "description": "Minimal repro for nested keydef chain resolution across outer map -> intermediate keymap -> keyword/topic source. Especially when DITA-OT resolves correctly but Web Editor author/preview does not.",
        "tags": ["nested keydef", "keydef chain", "keyref", "recursive key resolution", "Map A Map B Topic C", "keyword", "web editor", "author mode", "DITA-OT parity"],
        "module": "app.generator.nested_keydef_chain",
        "function": "generate_keyref_nested_keydef_chain_map_to_map_to_topic",
        "params_schema": {
            "root_map_name": "str",
            "intermediate_map_name": "str",
            "keyword_topic_name": "str",
            "consumer_topic_name": "str",
            "root_map_title": "str",
            "intermediate_map_title": "str",
            "keyword_topic_title": "str",
            "consumer_topic_title": "str",
            "root_to_intermediate_key": "str",
            "direct_intermediate_key_name": "str",
            "nested_keyword_file_key_name": "str",
            "nested_keyword_id": "str",
            "consumer_keyrefs": "list",
            "include_direct_key_in_root_map": "bool",
            "include_direct_key_in_intermediate_map": "bool",
            "include_nested_keyword_topic": "bool",
            "include_workaround_notes": "bool",
            "generation_mode": "str",
            "add_negative_variant": "bool",
            "add_workaround_variant": "bool",
            "id_prefix": "str",
            "pretty_print": "bool",
        },
        "default_params": {
            "root_map_name": "map_a.ditamap",
            "intermediate_map_name": "map_b.ditamap",
            "keyword_topic_name": "topic_c_keywords.dita",
            "consumer_topic_name": "topic_d_consumer.dita",
            "root_map_title": "Outer Context Map",
            "intermediate_map_title": "Static Key Map",
            "keyword_topic_title": "Keyword Source Topic",
            "consumer_topic_title": "Consumer Topic",
            "root_to_intermediate_key": "staticKeyMap",
            "direct_intermediate_key_name": "productName",
            "nested_keyword_file_key_name": "keywordFile",
            "nested_keyword_id": "versionString",
            "consumer_keyrefs": ["productName", "versionString"],
            "include_direct_key_in_root_map": True,
            "include_direct_key_in_intermediate_map": True,
            "include_nested_keyword_topic": True,
            "include_workaround_notes": True,
            "generation_mode": "minimal_repro",
            "add_negative_variant": False,
            "add_workaround_variant": False,
            "id_prefix": "t",
            "pretty_print": True,
        },
        "stability": "stable",
        "constructs": ["keydef", "keyref", "keywords", "topicmeta", "keyword", "map", "topicref"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "nested keydef chain resolution across outer map intermediate keymap keyword topic source",
            "DITA-OT resolves correctly but Web Editor author preview does not",
            "nested key resolution",
            "keydef chain",
            "keydef points to keymap",
            "keydef points to topic with keywords",
            "map A map B topic C",
            "keys resolve only when intermediate keymap is opened",
            "web editor does not resolve nested keys",
            "author preview unresolved keyref but dita-ot output correct",
            "recursive key loading missing",
            "parity issue between editor and DITA-OT",
            "intermediate map as root is a workaround",
        ],
        "avoid_when": [
            "xref href resolution",
            "conref conkeyref reuse",
            "ditaval profiling",
            "glossary display only",
            "duplicate keys same scope without recursive chain",
            "reltable navigation",
            "publishing-only issue",
            "broken external links",
            "map hierarchy without nested keydefs",
            "heavy performance topic generation",
        ],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
