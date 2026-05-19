"""Map hierarchy bundle: vision payload parsing and DITAMAP + topic stub serialization."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import ChatMapOutlineNode
from app.services.map_hierarchy_bundle import build_map_bundle_files, parse_map_outline_payload


def test_parse_roots_wraps_map_root():
    raw = {
        "map_title": "Sample",
        "confidence": 0.9,
        "warnings": [],
        "roots": [
            {"title": "First concept", "dita_type": "concept", "children": []},
            {
                "title": "Parent task",
                "dita_type": "task",
                "children": [
                    {"title": "Ref one", "dita_type": "reference", "children": []},
                    {"title": "Ref two", "dita_type": "reference", "children": []},
                ],
            },
        ],
    }
    tree, title, conf, warns = parse_map_outline_payload(raw)
    assert tree is not None
    assert tree.dita_type == "map_root"
    assert title == "Sample"
    assert conf == 0.9
    assert not warns
    assert len(tree.children) == 2
    assert tree.children[1].children and len(tree.children[1].children) == 2


def test_build_map_bundle_nested_topicrefs_and_stubs():
    root = ChatMapOutlineNode(
        title="DITA map",
        dita_type="map_root",
        children=[
            ChatMapOutlineNode(title="Leaf task", dita_type="task", children=[]),
            ChatMapOutlineNode(
                title="Container task",
                dita_type="task",
                children=[
                    ChatMapOutlineNode(title="Resource profiles", dita_type="reference", children=[]),
                    ChatMapOutlineNode(title="Interface parameters", dita_type="reference", children=[]),
                ],
            ),
        ],
    )
    files, warns = build_map_bundle_files(root, map_title="Radware map", map_basename="root.ditamap")
    assert not warns
    assert len(files) >= 3
    map_path, map_xml = files[0]
    assert map_path == "root.ditamap"
    assert "<topicref" in map_xml
    assert "tasks/container-task.dita" in map_xml or "tasks/container-task" in map_xml
    root_el = ET.fromstring(map_xml.split("?>", 1)[-1].strip())
    assert root_el.tag == "map"
    by_path = dict(files)
    task_xml = by_path.get("tasks/leaf-task.dita") or by_path.get("tasks/leaf-task-2.dita")
    assert task_xml and "<task " in task_xml
    ref_xml = next((x for k, x in by_path.items() if k.startswith("references/")), None)
    assert ref_xml and "<reference " in ref_xml
