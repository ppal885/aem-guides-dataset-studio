"""
Map parsing stress test generation.

This module generates maps with many topicrefs to stress test map parsing.
"""

from typing import Dict
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _rel_href
from app.generator.specialized import SpecializedContentGenerator

RECIPE_SPECS = [
    {
        "id": "map_parse_stress",
        "title": "Map Parse Stress",
        "description": "Generate maps with many topicrefs for map parsing stress tests",
        "tags": ["map", "stress", "topicref"],
        "module": "app.generator.map_stress",
        "function": "generate_map_parse_stress_dataset",
        "params_schema": {"map_count": "int", "topicrefs_per_map": "int"},
        "default_params": {"map_count": 10, "topicrefs_per_map": 1000},
        "stability": "stable",
        "constructs": ["map", "topicref", "topic"],
        "scenario_types": ["STRESS", "SCALE", "BOUNDARY"],
        "use_when": ["map parsing performance", "large map stress", "topicref scaling"],
        "avoid_when": ["small dataset", "quick validation", "minimal repro", "S1_MIN_REPRO"],
        "positive_negative": "positive",
        "complexity": "stress",
        "output_scale": "stress",
        "aem_guides_features": ["map-parsing", "navigation", "toc-generation"],
    },
]


def generate_map_parse_stress_dataset(
    config,
    base: str,
    map_count: int = 10,
    topicrefs_per_map: int = 1000,
    pretty_print: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate map parsing stress test dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate topics pool (enough for all maps)
    total_topics_needed = map_count * topicrefs_per_map
    topics_dir = safe_join(base, "map_stress", "topics")
    all_topic_paths = []
    
    for i in range(1, total_topics_needed + 1):
        topic_filename = sanitize_filename(f"stress_topic_{i:05d}.dita", config.windows_safe_filenames)
        topic_path = safe_join(topics_dir, topic_filename)
        topic_id = stable_id(config.seed, "stress_topic", str(i), used_ids)
        
        # Generate simple concept topic
        topic_xml = generator.generate_concept_topic(
            topic_id,
            f"Stress Test Topic {i}",
            section_count=2,
        )
        
        files[topic_path] = topic_xml
        all_topic_paths.append(topic_path)
    
    # Generate maps with many topicrefs
    maps_dir = safe_join(base, "map_stress", "maps")
    
    for map_idx in range(1, map_count + 1):
        map_filename = sanitize_filename(f"stress_map_{map_idx:05d}.ditamap", config.windows_safe_filenames)
        map_path = safe_join(maps_dir, map_filename)
        map_id = stable_id(config.seed, "stress_map", str(map_idx), used_ids)
        
        # Select topics for this map
        start_idx = (map_idx - 1) * topicrefs_per_map
        end_idx = start_idx + topicrefs_per_map
        selected_topics = all_topic_paths[start_idx:end_idx]
        
        # Generate map with many topicrefs
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = f"Stress Test Map {map_idx}"
        
        for topic_path in selected_topics:
            topicref = ET.SubElement(root, "topicref")
            topicref.set("href", _rel_href(map_path, topic_path))
            topicref.set("type", "topic")
        
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files
