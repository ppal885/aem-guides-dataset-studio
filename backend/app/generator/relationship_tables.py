"""
Relationship table generation for AEM Guides datasets.

Relationship tables are used for navigation and cross-references in AEM Guides.
"""

from typing import List, Dict, Tuple
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id

# Helper functions (these should exist in your generate module)
def safe_join(*parts: str) -> str:
    """Safely join path parts."""
    return "/".join(p.strip("/") for p in parts if p)

def sanitize_filename(filename: str, windows_safe: bool = False) -> str:
    """Sanitize filename."""
    if windows_safe:
        filename = filename.replace(":", "-").replace("<", "").replace(">", "")
    return filename


def _map_xml(config, map_id: str, title: str, topicref_hrefs: List[str], keydef_entries: List, scoped_blocks: List) -> bytes:
    """Generate map XML."""
    map_elem = ET.Element("map", {"id": map_id})
    title_elem = ET.SubElement(map_elem, "title")
    title_elem.text = title
    
    for href in topicref_hrefs:
        topicref = ET.SubElement(map_elem, "topicref")
        topicref.set("href", href)
        topicref.set("type", "topic")
    
    for block in scoped_blocks:
        map_elem.append(block)
    
    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    return doc.encode("utf-8") + xml_body


class RelationshipTableGenerator:
    """Generate relationship tables for maps."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_reltable(
        self,
        map_path: str,
        source_topics: List[Tuple[str, str]],  # (path, id)
        target_topics: List[Tuple[str, str]],
        relationship_types: List[str] = None,
    ) -> ET.Element:
        """Generate a relationship table element."""
        if relationship_types is None:
            relationship_types = ["next", "previous", "related"]
        
        reltable = ET.Element("reltable")
        
        # Generate relationship rows
        for source_path, source_id in source_topics[:10]:  # Limit for performance
            for target_path, target_id in target_topics[:10]:
                if source_path == target_path:
                    continue
                
                # Randomly decide if this relationship exists
                if self.rand.random() > 0.3:  # 30% chance
                    continue
                
                relrow = ET.SubElement(reltable, "relrow")
                
                # Source column
                relcolsource = ET.SubElement(relrow, "relcolspec")
                relcolsource.set("type", "concept")
                topicref_source = ET.SubElement(relcolsource, "topicref")
                topicref_source.set("href", self._rel_href(map_path, source_path))
                topicref_source.set("type", "topic")
                
                # Target column
                relcoltarget = ET.SubElement(relrow, "relcolspec")
                relcoltarget.set("type", "concept")
                topicref_target = ET.SubElement(relcoltarget, "topicref")
                topicref_target.set("href", self._rel_href(map_path, target_path))
                topicref_target.set("type", "topic")
                
                # Add relationship type
                reltype = self.rand.choice(relationship_types)
                topicref_target.set("collection-type", reltype)
        
        return reltable
    
    def generate_reltable_map(
        self,
        base: str,
        map_id: str,
        map_title: str,
        topics: List[Tuple[str, str]],
        relationship_types: List[str] = None,
    ) -> Tuple[str, bytes]:
        """Generate a map with relationship table."""
        map_dir = safe_join(base, "maps")
        map_filename = sanitize_filename(f"{map_id}_reltable.ditamap", self.config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        
        # Generate relationship table
        reltable = self.generate_reltable(
            map_path,
            topics,
            topics,
            relationship_types,
        )
        
        # Create map with reltable
        map_xml = _map_xml(
            self.config,
            map_id=map_id,
            title=map_title,
            topicref_hrefs=[],
            keydef_entries=[],
            scoped_blocks=[reltable],
        )
        
        return map_path, map_xml
    
    def _rel_href(self, from_path: str, to_path: str) -> str:
        """Calculate relative href between two paths."""
        from_parts = from_path.split('/')
        to_parts = to_path.split('/')
        
        # Find common prefix
        common_len = 0
        for i in range(min(len(from_parts), len(to_parts))):
            if from_parts[i] == to_parts[i]:
                common_len += 1
            else:
                break
        
        # Calculate relative path
        up_levels = len(from_parts) - common_len - 1
        rel_path = '../' * up_levels + '/'.join(to_parts[common_len:])
        
        return rel_path


def generate_relationship_table_dataset(
    config,
    base: str,
    topic_count: int = 100,
    relationship_types: List[str] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a dataset focused on relationship tables."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = RelationshipTableGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate topics
    topic_dir = safe_join(base, "topics", "pool")
    topics = []
    for i in range(1, topic_count + 1):
        filename = sanitize_filename(f"topic_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topic_dir, filename)
        topic_id = stable_id(config.seed, "reltable-topic", str(i), used_ids)
        
        # Generate minimal topic
        topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{config.doctype_topic}
<topic id="{topic_id}">
    <title>Topic {i:05d}</title>
    <body>
        <p>Content for topic {i}.</p>
    </body>
</topic>"""
        
        files[path] = topic_xml.encode('utf-8')
        topics.append((path, topic_id))
    
    # Generate map with relationship table
    map_path, map_xml = generator.generate_reltable_map(
        base,
        map_id=stable_id(config.seed, "reltable-map", "", used_ids),
        map_title="Relationship Table Map",
        topics=topics,
        relationship_types=relationship_types,
    )
    
    files[map_path] = map_xml
    
    return files


RECIPE_SPECS = [
    {
        "id": "relationship_table",
        "title": "Relationship Table",
        "description": "Generate topics with relationship tables for next/previous/related navigation",
        "tags": ["reltable", "relationship", "navigation"],
        "module": "app.generator.relationship_tables",
        "function": "generate_relationship_table_dataset",
        "params_schema": {"topic_count": "int", "relationship_types": "list"},
        "default_params": {"topic_count": 100, "relationship_types": ["next", "previous", "related"]},
        "stability": "stable",
        "output_scale": "large",
        "constructs": ["reltable", "relrow", "relcell", "topicref"],
        "scenario_types": ["BOUNDARY", "SCALE"],
        "use_when": ["reltable", "relationship table", "next previous related", "navigation"],
        "avoid_when": ["minimal repro", "no reltable", "simple map"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
