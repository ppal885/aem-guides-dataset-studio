"""
Map / Hierarchy recipe family - topicref, topicgroup, mapref, reltable.

Deterministic generators for map structure scenarios.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.generator.map_stress import generate_map_parse_stress_dataset
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


def generate_maps_topicref_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with basic topicrefs."""
    used = set()
    map_id = stable_id("maps_tr", id_prefix, "map", used)
    t1 = stable_id("maps_tr", id_prefix, "t1", used)
    t2 = stable_id("maps_tr", id_prefix, "t2", used)
    root = f"{base_path}/maps_topicref_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicref Basic"
    ET.SubElement(map_elem, "topicref", {"href": "../topics/a.dita", "navtitle": "Topic A"})
    ET.SubElement(map_elem, "topicref", {"href": "../topics/b.dita", "navtitle": "Topic B"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/a.dita": _topic_xml(config, t1, "Topic A", "Content A."),
        f"{root}/topics/b.dita": _topic_xml(config, t2, "Topic B", "Content B."),
    }


def generate_maps_nested_topicrefs(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with nested topicref hierarchy."""
    used = set()
    map_id = stable_id("maps_nest", id_prefix, "map", used)
    t1 = stable_id("maps_nest", id_prefix, "t1", used)
    t2 = stable_id("maps_nest", id_prefix, "t2", used)
    t3 = stable_id("maps_nest", id_prefix, "t3", used)
    root = f"{base_path}/maps_nested_topicrefs"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Nested Topicrefs"
    tr1 = ET.SubElement(map_elem, "topicref", {"href": "../topics/parent.dita", "navtitle": "Parent"})
    ET.SubElement(tr1, "topicref", {"href": "../topics/child1.dita", "navtitle": "Child 1"})
    ET.SubElement(tr1, "topicref", {"href": "../topics/child2.dita", "navtitle": "Child 2"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/parent.dita": _topic_xml(config, t1, "Parent", "Parent content."),
        f"{root}/topics/child1.dita": _topic_xml(config, t2, "Child 1", "Child 1 content."),
        f"{root}/topics/child2.dita": _topic_xml(config, t3, "Child 2", "Child 2 content."),
    }


def generate_maps_topicgroup_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with topicgroup."""
    used = set()
    map_id = stable_id("maps_tg", id_prefix, "map", used)
    t1 = stable_id("maps_tg", id_prefix, "t1", used)
    t2 = stable_id("maps_tg", id_prefix, "t2", used)
    root = f"{base_path}/maps_topicgroup_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicgroup Basic"
    tg = ET.SubElement(map_elem, "topicgroup")
    ET.SubElement(tg, "topicref", {"href": "../topics/a.dita", "navtitle": "A"})
    ET.SubElement(tg, "topicref", {"href": "../topics/b.dita", "navtitle": "B"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/a.dita": _topic_xml(config, t1, "A", "Content A."),
        f"{root}/topics/b.dita": _topic_xml(config, t2, "B", "Content B."),
    }


def generate_maps_topicgroup_nested(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Nested topicgroups."""
    used = set()
    map_id = stable_id("maps_tgn", id_prefix, "map", used)
    t1 = stable_id("maps_tgn", id_prefix, "t1", used)
    root = f"{base_path}/maps_topicgroup_nested"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicgroup Nested"
    tg1 = ET.SubElement(map_elem, "topicgroup")
    ET.SubElement(tg1, "topicref", {"href": "../topics/a.dita", "navtitle": "A"})
    tg2 = ET.SubElement(tg1, "topicgroup")
    ET.SubElement(tg2, "topicref", {"href": "../topics/b.dita", "navtitle": "B"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/a.dita": _topic_xml(config, t1, "A", "Content A."),
        f"{root}/topics/b.dita": _topic_xml(config, stable_id("maps_tgn", id_prefix, "t2", used), "B", "Content B."),
    }


def generate_maps_mapref_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with mapref to submap."""
    used = set()
    map_id = stable_id("maps_mr", id_prefix, "map", used)
    sub_id = stable_id("maps_mr", id_prefix, "sub", used)
    t1 = stable_id("maps_mr", id_prefix, "t1", used)
    root = f"{base_path}/maps_mapref_basic"
    main_map = ET.Element("map", {"id": map_id})
    ET.SubElement(main_map, "title").text = "Main Map"
    ET.SubElement(main_map, "topicref", {"href": "../topics/root.dita", "navtitle": "Root"})
    ET.SubElement(main_map, "mapref", {"href": "submap.ditamap", "navtitle": "Submap"})
    sub_map = ET.Element("map", {"id": sub_id})
    ET.SubElement(sub_map, "title").text = "Submap"
    ET.SubElement(sub_map, "topicref", {"href": "../topics/child.dita", "navtitle": "Child"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, main_map),
        f"{root}/maps/submap.ditamap": _map_xml(config, sub_map),
        f"{root}/topics/root.dita": _topic_xml(config, t1, "Root", "Root content."),
        f"{root}/topics/child.dita": _topic_xml(config, stable_id("maps_mr", id_prefix, "t2", used), "Child", "Child content."),
    }


def generate_maps_reltable_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with reltable for relationship definitions."""
    used = set()
    map_id = stable_id("maps_rel", id_prefix, "map", used)
    t1 = stable_id("maps_rel", id_prefix, "t1", used)
    t2 = stable_id("maps_rel", id_prefix, "t2", used)
    root = f"{base_path}/maps_reltable_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Reltable Basic"
    ET.SubElement(map_elem, "topicref", {"href": "../topics/a.dita", "navtitle": "A"})
    ET.SubElement(map_elem, "topicref", {"href": "../topics/b.dita", "navtitle": "B"})
    rel = ET.SubElement(map_elem, "reltable")
    relrow = ET.SubElement(rel, "relrow")
    ET.SubElement(relrow, "relcell", {"href": "../topics/a.dita"})
    ET.SubElement(relrow, "relcell", {"href": "../topics/b.dita", "type": "next"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/a.dita": _topic_xml(config, t1, "A", "Content A."),
        f"{root}/topics/b.dita": _topic_xml(config, t2, "B", "Content B."),
    }


def generate_maps_topichead_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with topichead elements - section headings without href. Topicrefs under topichead for output/TOC under heading."""
    used = set()
    map_id = stable_id("maps_th", id_prefix, "map", used)
    t1 = stable_id("maps_th", id_prefix, "t1", used)
    t2 = stable_id("maps_th", id_prefix, "t2", used)
    t3 = stable_id("maps_th", id_prefix, "t3", used)
    root = f"{base_path}/maps_topichead_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topichead Basic"
    th1 = ET.SubElement(map_elem, "topichead", {"navtitle": "Getting Started"})
    ET.SubElement(th1, "topicref", {"href": "../topics/intro.dita", "navtitle": "Introduction"})
    ET.SubElement(th1, "topicref", {"href": "../topics/install.dita", "navtitle": "Installation"})
    th2 = ET.SubElement(map_elem, "topichead", {"navtitle": "Advanced"})
    ET.SubElement(th2, "topicref", {"href": "../topics/advanced.dita", "navtitle": "Advanced Topics"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/intro.dita": _topic_xml(config, t1, "Introduction", "Introduction content."),
        f"{root}/topics/install.dita": _topic_xml(config, t2, "Installation", "Installation content."),
        f"{root}/topics/advanced.dita": _topic_xml(config, t3, "Advanced Topics", "Advanced content."),
    }


def generate_maps_navtitle_override(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topicref with navtitle overriding topic title."""
    used = set()
    map_id = stable_id("maps_nav", id_prefix, "map", used)
    t1 = stable_id("maps_nav", id_prefix, "t1", used)
    root = f"{base_path}/maps_navtitle_override"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Navtitle Override"
    ET.SubElement(map_elem, "topicref", {"href": "../topics/topic.dita", "navtitle": "Custom Nav Title"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/topic.dita": _topic_xml(config, t1, "Original Title", "Content."),
    }


def generate_maps_deep_hierarchy_stress(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Stress: deep map hierarchy. Uses map_parse_stress with small params."""
    return generate_map_parse_stress_dataset(config, base_path, map_count=3, topicrefs_per_map=5, **kwargs)


def generate_maps_topicset_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with topicset - groups topics for navigation without affecting output order (DITA 1.3)."""
    used = set()
    map_id = stable_id("maps_ts", id_prefix, "map", used)
    t1 = stable_id("maps_ts", id_prefix, "t1", used)
    t2 = stable_id("maps_ts", id_prefix, "t2", used)
    t3 = stable_id("maps_ts", id_prefix, "t3", used)
    root = f"{base_path}/maps_topicset_basic"
    map_elem = ET.Element("map", {"id": map_id})
    ET.SubElement(map_elem, "title").text = "Topicset Basic"
    topicset = ET.SubElement(map_elem, "topicset")
    topicset.set("navtitle", "Related Topics")
    ET.SubElement(topicset, "topicref", {"href": "../topics/a.dita", "navtitle": "Topic A"})
    ET.SubElement(topicset, "topicref", {"href": "../topics/b.dita", "navtitle": "Topic B"})
    ET.SubElement(topicset, "topicref", {"href": "../topics/c.dita", "navtitle": "Topic C"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, map_elem),
        f"{root}/topics/a.dita": _topic_xml(config, t1, "Topic A", "Content A."),
        f"{root}/topics/b.dita": _topic_xml(config, t2, "Topic B", "Content B."),
        f"{root}/topics/c.dita": _topic_xml(config, t3, "Topic C", "Content C."),
    }


def generate_maps_navref_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Map with navref - references another map for navigation."""
    used = set()
    map_id = stable_id("maps_nr", id_prefix, "map", used)
    sub_id = stable_id("maps_nr", id_prefix, "sub", used)
    t1 = stable_id("maps_nr", id_prefix, "t1", used)
    t2 = stable_id("maps_nr", id_prefix, "t2", used)
    root = f"{base_path}/maps_navref_basic"
    main_map = ET.Element("map", {"id": map_id})
    ET.SubElement(main_map, "title").text = "Main Map with Navref"
    ET.SubElement(main_map, "topicref", {"href": "../topics/intro.dita", "navtitle": "Introduction"})
    ET.SubElement(main_map, "navref", {"href": "submap.ditamap", "navtitle": "Additional Topics"})
    sub_map = ET.Element("map", {"id": sub_id})
    ET.SubElement(sub_map, "title").text = "Submap"
    ET.SubElement(sub_map, "topicref", {"href": "../topics/extra.dita", "navtitle": "Extra Topic"})
    return {
        f"{root}/maps/main.ditamap": _map_xml(config, main_map),
        f"{root}/maps/submap.ditamap": _map_xml(config, sub_map),
        f"{root}/topics/intro.dita": _topic_xml(config, t1, "Introduction", "Introduction content."),
        f"{root}/topics/extra.dita": _topic_xml(config, t2, "Extra Topic", "Extra topic content."),
    }


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None, complexity: str = "minimal",
          constructs: list = None) -> dict:
    default_constructs = ["map", "topicref", "topicgroup", "mapref", "reltable"]
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": constructs if constructs is not None else default_constructs,
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": complexity,
        "output_scale": "minimal" if complexity != "stress" else "stress",
        "module": "app.generator.maps",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("maps.topicref_basic", "Topicref Basic", "Map with basic topicrefs.", "generate_maps_topicref_basic",
          ["MAP", "TOPICREF"], ["topicref in map", "map structure"], ["conref", "keys"], "positive"),
    _spec("maps.nested_topicrefs", "Nested Topicrefs", "Map with nested topicref hierarchy.", "generate_maps_nested_topicrefs",
          ["MAP", "TOPICREF", "NESTED"], ["nested topicref", "hierarchy"], ["flat map"], "positive"),
    _spec("maps.topicgroup_basic", "Topicgroup Basic", "Map with topicgroup.", "generate_maps_topicgroup_basic",
          ["MAP", "TOPICGROUP"], ["topicgroup", "grouping topicrefs"], ["flat topicrefs"], "positive"),
    _spec("maps.topicgroup_nested", "Topicgroup Nested", "Map with nested topicgroup elements for hierarchical grouping.", "generate_maps_topicgroup_nested",
          ["MAP", "TOPICGROUP", "NESTED"], ["nested topicgroup"], ["flat structure"], "positive"),
    _spec("maps.mapref_basic", "Mapref Basic", "Map with mapref to submap.", "generate_maps_mapref_basic",
          ["MAP", "MAPREF"], ["mapref", "submap", "nested map"], ["single map"], "positive"),
    _spec("maps.reltable_basic", "Reltable Basic", "Map with reltable for next/previous/related relationship definitions.", "generate_maps_reltable_basic",
          ["MAP", "RELTABLE"], ["reltable", "relationship table"], ["simple map"], "positive"),
    _spec("maps.navtitle_override", "Navtitle Override", "Topicref with navtitle override.", "generate_maps_navtitle_override",
          ["MAP", "NAVTITLE"], ["navtitle", "override title"], ["default title"], "positive"),
    _spec("maps.topichead_basic", "Topichead Basic", "Map with topichead elements - section headings without href. Topicrefs under topichead for output/TOC under heading.", "generate_maps_topichead_basic",
          ["MAP", "TOPICHEAD"], ["topichead", "output pages under topichead", "TOC under topichead", "map structure"], ["ditaval", "conditionals"], "positive"),
    _spec("maps.topicset_basic", "Topicset Basic", "Map with topicset - groups topics for navigation without affecting output order (DITA 1.3).", "generate_maps_topicset_basic",
          ["MAP", "TOPICSET"], ["topicset", "topic grouping", "navigation group"], ["flat topicrefs"], "positive",
          constructs=["map", "topicref", "topicset"]),
    _spec("maps.navref_basic", "Navref Basic", "Map with navref - references another map for navigation.", "generate_maps_navref_basic",
          ["MAP", "NAVREF"], ["navref", "map reference", "navigation map"], ["single map"], "positive",
          constructs=["map", "topicref", "mapref", "navref"]),
    _spec("maps.deep_hierarchy_stress", "Deep Hierarchy Stress", "Stress: deep map hierarchy.", "generate_maps_deep_hierarchy_stress",
          ["MAP", "STRESS", "HIERARCHY"], ["stress test", "deep hierarchy", "many topicrefs"], ["minimal repro"], "positive", ["STRESS"], "stress"),
]
