"""
Legacy pattern generators.

This module generates legacy DITA patterns:
- Hub-spoke inbound patterns
- Keydef-heavy patterns
"""

from typing import Dict
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _rel_href
from app.generator.specialized import SpecializedContentGenerator


def generate_hub_spoke_inbound_dataset(
    config,
    base: str,
    topic_count: int = 100,
    include_map: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate hub-spoke inbound pattern dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate hub topic (central topic)
    hub_dir = safe_join(base, "hub_spoke", "hub")
    hub_filename = sanitize_filename("hub_topic.dita", config.windows_safe_filenames)
    hub_path = safe_join(hub_dir, hub_filename)
    hub_id = stable_id(config.seed, "hub", "", used_ids)
    
    hub_xml = generator.generate_concept_topic(
        hub_id,
        "Hub Topic",
        section_count=5,
    )
    files[hub_path] = hub_xml
    
    # Generate spoke topics (topics that reference hub)
    spoke_dir = safe_join(base, "hub_spoke", "spokes")
    spoke_paths = []
    
    for i in range(1, topic_count + 1):
        spoke_filename = sanitize_filename(f"spoke_topic_{i:05d}.dita", config.windows_safe_filenames)
        spoke_path = safe_join(spoke_dir, spoke_filename)
        spoke_id = stable_id(config.seed, "spoke", str(i), used_ids)
        
        # Generate spoke topic with xref to hub
        spoke = ET.Element("topic", {"id": spoke_id, "xml:lang": "en"})
        title_elem = ET.SubElement(spoke, "title")
        title_elem.text = f"Spoke Topic {i}"
        
        shortdesc = ET.SubElement(spoke, "shortdesc")
        shortdesc.text = f"Spoke topic {i} referencing hub topic"
        
        body = ET.SubElement(spoke, "body")
        p = ET.SubElement(body, "p")
        p.text = f"This spoke topic references the hub topic. "
        
        # Add xref to hub
        xref = ET.SubElement(body, "xref")
        xref.set("href", _rel_href(spoke_path, hub_path))
        xref.set("type", "topic")
        xref.text = "Hub Topic"
        
        # Generate XML
        xml_body = ET.tostring(spoke, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
        files[spoke_path] = doc.encode("utf-8") + xml_body
        spoke_paths.append(spoke_path)
    
    # Generate map if requested
    if include_map:
        map_dir = safe_join(base, "hub_spoke")
        map_filename = sanitize_filename("hub_spoke.ditamap", config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        map_id = stable_id(config.seed, "hub_spoke_map", "", used_ids)
        
        # Map includes hub and all spokes
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = "Hub-Spoke Map"
        
        # Add hub first
        hub_ref = ET.SubElement(root, "topicref")
        hub_ref.set("href", _rel_href(map_path, hub_path))
        hub_ref.set("type", "topic")
        
        # Add spokes
        for spoke_path in spoke_paths:
            topicref = ET.SubElement(root, "topicref")
            topicref.set("href", _rel_href(map_path, spoke_path))
            topicref.set("type", "topic")
        
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files


def generate_keydef_heavy_dataset(
    config,
    base: str,
    topic_count: int = 100,
    keydef_count: int = 50,
    include_map: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate keydef-heavy dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate topics
    topics_dir = safe_join(base, "keydef_heavy", "topics")
    topic_paths = []
    
    for i in range(1, topic_count + 1):
        topic_filename = sanitize_filename(f"keydef_topic_{i:05d}.dita", config.windows_safe_filenames)
        topic_path = safe_join(topics_dir, topic_filename)
        topic_id = stable_id(config.seed, "keydef_topic", str(i), used_ids)
        
        topic_xml = generator.generate_concept_topic(
            topic_id,
            f"Keydef Topic {i}",
            section_count=3,
        )
        
        files[topic_path] = topic_xml
        topic_paths.append(topic_path)
    
    # Generate map with many keydefs
    if include_map:
        map_dir = safe_join(base, "keydef_heavy")
        map_filename = sanitize_filename("keydef_heavy.ditamap", config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        map_id = stable_id(config.seed, "keydef_map", "", used_ids)
        
        # Create map
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = "Keydef Heavy Map"
        
        # Add keydefs
        selected_topics = rand.sample(topic_paths, min(keydef_count, len(topic_paths)))
        keydef_entries = []
        
        for i, topic_path in enumerate(selected_topics):
            key_name = f"key_{i+1}"
            keydef = ET.SubElement(root, "keydef")
            keydef.set("keys", key_name)
            keydef.set("href", _rel_href(map_path, topic_path))
            keydef_entries.append(key_name)
        
        # Add topicrefs using keyrefs
        for key_name in keydef_entries:
            topicref = ET.SubElement(root, "topicref")
            topicref.set("keyref", key_name)
        
        # Generate XML
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files


RECIPE_SPECS = [
    {
        "id": "hub_spoke_inbound",
        "title": "Hub-Spoke Inbound",
        "description": "Generate hub-spoke pattern with central hub topic and spoke topics with xrefs",
        "tags": ["hub", "spoke", "xref", "legacy"],
        "module": "app.generator.legacy_patterns",
        "function": "generate_hub_spoke_inbound_dataset",
        "params_schema": {"topic_count": "int", "include_map": "bool"},
        "default_params": {"topic_count": 100, "include_map": True},
        "stability": "stable",
        "output_scale": "large",
        "constructs": ["xref", "topicref", "map"],
        "scenario_types": ["SCALE", "BOUNDARY"],
        "use_when": ["hub-spoke", "central hub", "spoke xrefs", "inbound links"],
        "avoid_when": ["minimal repro", "flat structure"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
    {
        "id": "keydef_heavy",
        "title": "Keydef Heavy",
        "description": "Generate maps with many key definitions and topicrefs using keyrefs",
        "tags": ["keydef", "keyref", "legacy"],
        "module": "app.generator.legacy_patterns",
        "function": "generate_keydef_heavy_dataset",
        "params_schema": {"topic_count": "int", "keydef_count": "int", "include_map": "bool"},
        "default_params": {"topic_count": 100, "keydef_count": 50, "include_map": True},
        "stability": "stable",
        "output_scale": "large",
        "constructs": ["keydef", "keyref", "topicref", "map"],
        "scenario_types": ["SCALE", "STRESS"],
        "use_when": ["many keydefs", "keyref heavy", "key resolution stress"],
        "avoid_when": ["minimal repro", "few keys"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
