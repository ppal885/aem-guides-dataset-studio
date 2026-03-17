"""
Customer reuse pack generation.

This module generates customer reuse patterns with:
- Shared topics referenced by multiple maps
- Key definitions for content reuse
- Key groups for organized key management
- External references
"""

from typing import Dict, List
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from typing import Dict
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _rel_href


class CustomerReuseGenerator:
    """Generate customer reuse pack patterns."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_shared_topic(
        self,
        topic_id: str,
        title: str,
        is_reusable: bool = True,
    ) -> bytes:
        """Generate a shared/reusable topic."""
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = title
        
        # Short description
        shortdesc = ET.SubElement(topic, "shortdesc")
        shortdesc.text = f"Shared topic: {title}"
        
        # Body
        body = ET.SubElement(topic, "body")
        
        intro_p = ET.SubElement(body, "p")
        intro_p.text = f"This is a shared topic that can be referenced by multiple maps using keys."
        
        # Add some content
        section = ET.SubElement(body, "section")
        section.set("id", f"content_{topic_id}")
        section_title = ET.SubElement(section, "title")
        section_title.text = "Content"
        
        section_p = ET.SubElement(section, "p")
        section_p.text = f"Content for shared topic {title}. This topic is designed to be reused across multiple maps."
        
        # Generate XML
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body


def generate_customer_reuse_pack_dataset(
    config,
    base: str,
    remove_map_count: int = 10,
    shared_topics: int = 500,
    topic_references_per_map: int = 100,
    key_definitions: int = 200,
    key_groups: int = 5,
    external_references: int = 10,
    rand=None,
) -> Dict[str, bytes]:
    """Generate customer reuse pack dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = CustomerReuseGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate shared topics
    shared_dir = safe_join(base, "customer_reuse", "shared_topics")
    shared_topic_paths = []
    
    for i in range(1, shared_topics + 1):
        topic_filename = sanitize_filename(f"shared_topic_{i:05d}.dita", config.windows_safe_filenames)
        topic_path = safe_join(shared_dir, topic_filename)
        topic_id = stable_id(config.seed, "shared_topic", str(i), used_ids)
        
        topic_xml = generator.generate_shared_topic(
            topic_id,
            f"Shared Topic {i}",
            is_reusable=True,
        )
        
        files[topic_path] = topic_xml
        shared_topic_paths.append(topic_path)
    
    # Generate key definitions
    keydefs = []
    keys_per_group = key_definitions // max(key_groups, 1)
    
    for group_idx in range(key_groups):
        for key_idx in range(keys_per_group):
            key_num = group_idx * keys_per_group + key_idx + 1
            if key_num > key_definitions:
                break
            
            # Select a random shared topic
            topic_idx = rand.randint(0, len(shared_topic_paths) - 1)
            topic_path = shared_topic_paths[topic_idx]
            
            keydefs.append({
                "keys": f"group{group_idx+1}.key{key_num}",
                "topic_path": topic_path,
            })
    
    # Generate maps (remove maps - maps that reference shared topics)
    maps_dir = safe_join(base, "customer_reuse", "maps")
    
    for map_idx in range(1, remove_map_count + 1):
        map_filename = sanitize_filename(f"reuse_map_{map_idx:05d}.ditamap", config.windows_safe_filenames)
        map_path = safe_join(maps_dir, map_filename)
        map_id = stable_id(config.seed, "reuse_map", str(map_idx), used_ids)
        
        # Select topics for this map (using keyrefs)
        selected_keydefs = rand.sample(keydefs, min(topic_references_per_map, len(keydefs)))
        
        # Create map with keyrefs
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = f"Reuse Map {map_idx}"
        
        # Add keydefs
        for keydef_entry in selected_keydefs[:key_definitions // remove_map_count]:
            keydef = ET.SubElement(root, "keydef")
            keydef.set("keys", keydef_entry["keys"])
            rel_href = _rel_href(map_path, keydef_entry["topic_path"])
            keydef.set("href", rel_href)
        
        # Add topicrefs using keyrefs
        for i in range(min(topic_references_per_map, len(selected_keydefs))):
            topicref = ET.SubElement(root, "topicref")
            # Use full key path or just the key name
            key_name = selected_keydefs[i]["keys"].split(".")[-1]
            topicref.set("keyref", key_name)
        
        # Add external references
        for ext_idx in range(min(external_references, 5)):
            topicref = ET.SubElement(root, "topicref")
            topicref.set("href", f"external://reference_{ext_idx+1}.dita")
            topicref.set("scope", "external")
        
        # Generate XML
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files


RECIPE_SPECS = [
    {
        "id": "customer_reuse_pack",
        "title": "Customer Reuse Pack",
        "description": "Generate customer reuse pack with shared topics and keyrefs",
        "tags": ["reuse", "keyref", "customer"],
        "module": "app.generator.customer_reuse",
        "function": "generate_customer_reuse_pack_dataset",
        "params_schema": {"remove_map_count": "int", "shared_topics": "int", "topic_references_per_map": "int"},
        "default_params": {"remove_map_count": 10, "shared_topics": 500, "topic_references_per_map": 100},
        "stability": "stable",
        "avoid_when": ["minimal repro", "S1_MIN_REPRO", "quick validation"],
        "output_scale": "large",
        "constructs": ["keydef", "keyref", "topicref", "map"],
        "scenario_types": ["SCALE", "INTEGRATION"],
        "use_when": ["customer reuse", "shared topics", "keyref reuse across maps", "content reuse pack"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
