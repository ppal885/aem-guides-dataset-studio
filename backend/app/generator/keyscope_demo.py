"""
Keyscope Demo Dataset Generator.

Generates a DITA dataset demonstrating keyscope resolution with:
- Root map defining key "prod" to ROOT target
- Submap S1 defining key "prod" to S1 target inside keyscope="s1"
- Submap S2 defining key "prod" to S2 target inside keyscope="s2"
- Consumer topics using keyref="prod" (and optionally s1.prod, s2.prod)
"""
import xml.etree.ElementTree as ET
from typing import Dict
from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig

RECIPE_SPECS = [
    {
        "id": "keyscope_demo",
        "title": "Keyscope Demo",
        "description": "Generate keyscope resolution demo with scoped keydefs and keyrefs",
        "tags": ["keyscope", "keyref", "keydef"],
        "module": "app.generator.keyscope_demo",
        "function": "generate_keyscope_demo_dataset",
        "params_schema": {"id_prefix": "str", "include_qualified_keyrefs": "bool", "demo_shape": "str"},
        "default_params": {"id_prefix": "t", "include_qualified_keyrefs": True, "demo_shape": "full_demo"},
        "stability": "stable",
        "constructs": ["keyscope", "keydef", "keyref", "mapref", "topicref"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "EDGE"],
        "use_when": ["key resolution testing", "scoped keys", "multi-map key conflicts"],
        "avoid_when": ["single map", "no key usage"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "minimal",
        "aem_guides_features": ["key-resolution", "keyscope", "outgoing-links"],
    },
]


def sanitize_filename(filename: str, windows_safe: bool = False) -> str:
    """Sanitize filename."""
    if windows_safe:
        filename = filename.replace(":", "-").replace("<", "").replace(">", "")
    return filename


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_content: str, pretty_print: bool = True) -> bytes:
    """Generate topic XML."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    
    title_elem = ET.SubElement(topic, "title")
    title_elem.text = title
    
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
            xml_body = xml_body.split(b'\n', 1)[1] if b'\n' in xml_body else xml_body
        except Exception:
            pass
    
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _map_xml(config: DatasetConfig, map_id: str, title: str, keydefs: list, topicrefs: list, maprefs: list = None, pretty_print: bool = True) -> bytes:
    """Generate map XML."""
    map_elem = ET.Element("map", {"id": map_id})
    
    title_elem = ET.SubElement(map_elem, "title")
    title_elem.text = title
    
    for keydef in keydefs:
        keydef_elem = ET.SubElement(map_elem, "keydef")
        for key, value in keydef.items():
            if key == "keyscope":
                keydef_elem.set("keyscope", value)
            elif key == "keys":
                keydef_elem.set("keys", value)
            elif key == "href":
                keydef_elem.set("href", value)
    
    for topicref in topicrefs:
        topicref_elem = ET.SubElement(map_elem, "topicref")
        for key, value in topicref.items():
            topicref_elem.set(key, value)
    
    if maprefs:
        for mapref in maprefs:
            mapref_elem = ET.SubElement(map_elem, "mapref")
            for key, value in mapref.items():
                mapref_elem.set(key, value)
    
    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b'\n', 1)[1] if b'\n' in xml_body else xml_body
        except Exception:
            pass
    
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    return doc.encode("utf-8") + xml_body


def generate_keyscope_demo_dataset(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    include_qualified_keyrefs: bool = True,
    demo_shape: str = "full_demo",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate keyscope demo dataset.
    
    Args:
        config: Dataset configuration
        base_path: Base path for dataset files
        id_prefix: Prefix for generated IDs (default: "t")
        include_qualified_keyrefs: Include explicit qualified keyrefs (s1.prod, s2.prod) for diagnostics
        pretty_print: Pretty print XML output
    
    Returns:
        Dictionary of file paths to file contents (bytes)
    """
    files = {}
    used_ids = set()
    
    shape = str(demo_shape or "full_demo").strip().lower()
    minimal_demo = shape == "minimal_demo"

    root_folder = (
        f"{base_path}/aem_guides_keyscope_demo_minimal"
        if minimal_demo
        else f"{base_path}/aem_guides_keyscope_demo"
    )
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"
    
    map_root_id = make_dita_id("map_root", id_prefix, used_ids)
    map_s1_id = make_dita_id("map_s1", id_prefix, used_ids)
    map_s2_id = make_dita_id("map_s2", id_prefix, used_ids) if not minimal_demo else None
    
    topic_root_target_id = make_dita_id("t_root_target", id_prefix, used_ids)
    topic_s1_target_id = make_dita_id("t_s1_target", id_prefix, used_ids)
    topic_s2_target_id = make_dita_id("t_s2_target", id_prefix, used_ids) if not minimal_demo else None
    topic_consumer_root_id = make_dita_id("t_consumer_root", id_prefix, used_ids)
    topic_consumer_s1_id = make_dita_id("t_consumer_s1", id_prefix, used_ids)
    topic_consumer_s2_id = make_dita_id("t_consumer_s2", id_prefix, used_ids) if not minimal_demo else None
    
    root_target_path = f"{topics_folder}/root_target.dita"
    s1_target_path = f"{topics_folder}/s1_target.dita"
    s2_target_path = f"{topics_folder}/s2_target.dita" if not minimal_demo else None
    consumer_root_path = f"{topics_folder}/consumer_root.dita"
    consumer_s1_path = f"{topics_folder}/consumer_s1.dita"
    consumer_s2_path = f"{topics_folder}/consumer_s2.dita" if not minimal_demo else None
    
    root_map_path = f"{maps_folder}/root_map.ditamap"
    submap_s1_path = f"{maps_folder}/submap_s1.ditamap"
    submap_s2_path = f"{maps_folder}/submap_s2.ditamap" if not minimal_demo else None
    
    root_target_body = '<p>This is ROOT target (key=prod).</p>'
    s1_target_body = '<p>This is S1 target (key=prod, keyscope=s1).</p>'
    s2_target_body = '<p>This is S2 target (key=prod, keyscope=s2).</p>'
    
    consumer_root_body = '<p>Keyref should resolve to: <xref keyref="prod"/></p>'
    
    if include_qualified_keyrefs:
        consumer_s1_body = '''<p>Keyref should resolve to: <xref keyref="prod"/> (implicit s1 scope)</p>
<p>Explicit qualified keyref: <xref keyref="s1.prod"/></p>'''
        consumer_s2_body = '''<p>Keyref should resolve to: <xref keyref="prod"/> (implicit s2 scope)</p>
<p>Explicit qualified keyref: <xref keyref="s2.prod"/></p>'''
    else:
        consumer_s1_body = '<p>Keyref should resolve to: <xref keyref="prod"/> (should resolve to S1 target)</p>'
        consumer_s2_body = '<p>Keyref should resolve to: <xref keyref="prod"/> (should resolve to S2 target)</p>'
    
    files[root_target_path] = _topic_xml(config, topic_root_target_id, "ROOT target (key=prod)", root_target_body, pretty_print)
    files[s1_target_path] = _topic_xml(config, topic_s1_target_id, "S1 target (key=prod)", s1_target_body, pretty_print)
    if not minimal_demo and s2_target_path and topic_s2_target_id:
        files[s2_target_path] = _topic_xml(config, topic_s2_target_id, "S2 target (key=prod)", s2_target_body, pretty_print)
    files[consumer_root_path] = _topic_xml(config, topic_consumer_root_id, "Consumer (root context)", consumer_root_body, pretty_print)
    files[consumer_s1_path] = _topic_xml(config, topic_consumer_s1_id, "Consumer (inside keyscope s1)", consumer_s1_body, pretty_print)
    if not minimal_demo and consumer_s2_path and topic_consumer_s2_id:
        files[consumer_s2_path] = _topic_xml(config, topic_consumer_s2_id, "Consumer (inside keyscope s2)", consumer_s2_body, pretty_print)
    
    root_map_keydefs = [
        {"keys": "prod", "href": "../topics/root_target.dita"}
    ]
    
    root_map_topicrefs = [
        {"href": "../topics/consumer_root.dita", "navtitle": "Consumer Root", "type": "topic"}
    ]
    
    root_map_maprefs = [
        {"href": "submap_s1.ditamap", "keyscope": "s1", "navtitle": "Submap S1 (defines prod)"},
    ]
    if not minimal_demo:
        root_map_maprefs.append(
            {"href": "submap_s2.ditamap", "keyscope": "s2", "navtitle": "Submap S2 (defines prod)"}
        )
    
    files[root_map_path] = _map_xml(
        config,
        map_root_id,
        "ROOT MAP (prod at root + scoped overrides)",
        root_map_keydefs,
        root_map_topicrefs,
        root_map_maprefs,
        pretty_print
    )
    
    submap_s1_keydefs = [
        {"keys": "prod", "href": "../topics/s1_target.dita"}
    ]
    
    submap_s1_topicrefs = [
        {"href": "../topics/consumer_s1.dita", "navtitle": "Consumer S1", "type": "topic"}
    ]
    
    files[submap_s1_path] = _map_xml(
        config,
        map_s1_id,
        "Submap S1",
        submap_s1_keydefs,
        submap_s1_topicrefs,
        None,
        pretty_print
    )
    
    if not minimal_demo and submap_s2_path and map_s2_id:
        submap_s2_keydefs = [
            {"keys": "prod", "href": "../topics/s2_target.dita"}
        ]

        submap_s2_topicrefs = [
            {"href": "../topics/consumer_s2.dita", "navtitle": "Consumer S2", "type": "topic"}
        ]

        files[submap_s2_path] = _map_xml(
            config,
            map_s2_id,
            "Submap S2",
            submap_s2_keydefs,
            submap_s2_topicrefs,
            None,
            pretty_print
        )
    
    readme_content = f"""Keyscope Demo Dataset
====================

This dataset demonstrates DITA keyscope resolution.

Structure:
- Root map defines key "prod" -> root_target.dita
- Submap S1 defines key "prod" -> s1_target.dita (keyscope="s1")
"""
    if not minimal_demo:
        readme_content += """- Submap S2 defines key "prod" -> s2_target.dita (keyscope="s2")

Consumer topics:
- consumer_root.dita uses keyref="prod" (resolves to ROOT target)
- consumer_s1.dita uses keyref="prod" (resolves to S1 target when in S1 context)
- consumer_s2.dita uses keyref="prod" (resolves to S2 target when in S2 context)
"""
    else:
        readme_content += """

Consumer topics:
- consumer_root.dita uses keyref="prod" (resolves to ROOT target)
- consumer_s1.dita uses keyref="prod" (resolves to S1 target when in S1 context)
"""
    readme_content += """

All IDs are DITA-compliant (start with letter/underscore, no leading digits).

Validation:
- All href references are relative and valid
- All IDs match DITA ID pattern: ^[A-Za-z_][A-Za-z0-9_.-]*$
- XML is well-formed
"""
    
    files[f"{root_folder}/README.txt"] = readme_content.encode("utf-8")
    
    return files
