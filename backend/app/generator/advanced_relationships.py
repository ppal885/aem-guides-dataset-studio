"""
Advanced relationship pattern generation for AEM Guides datasets.

This module extends relationship tables with:
- Hierarchical relationships
- Cross-map relationships
- Conditional relationships
- Dynamic relationship generation
- Relationship table optimization
"""

from typing import Dict, List, Tuple, Optional, Set
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.relationship_tables import RelationshipTableGenerator, safe_join, sanitize_filename, _map_xml


class AdvancedRelationshipGenerator(RelationshipTableGenerator):
    """Extended relationship generator with advanced patterns."""
    
    def generate_hierarchical_reltable(
        self,
        map_path: str,
        topics: List[Tuple[str, str]],  # (path, id)
        hierarchy_levels: int = 3,
        children_per_level: int = 5,
    ) -> ET.Element:
        """Generate hierarchical relationship table."""
        reltable = ET.Element("reltable")
        
        # Build hierarchy
        hierarchy = self._build_topic_hierarchy(topics, hierarchy_levels, children_per_level)
        
        # Generate relationships based on hierarchy
        for parent_path, parent_id in hierarchy.get("parents", []):
            children = hierarchy.get("children", {}).get(parent_id, [])
            
            for child_path, child_id in children:
                relrow = ET.SubElement(reltable, "relrow")
                
                # Parent column
                relcolparent = ET.SubElement(relrow, "relcolspec")
                relcolparent.set("type", "concept")
                topicref_parent = ET.SubElement(relcolparent, "topicref")
                topicref_parent.set("href", self._rel_href(map_path, parent_path))
                topicref_parent.set("type", "topic")
                
                # Child column
                relcolchild = ET.SubElement(relrow, "relcolspec")
                relcolchild.set("type", "concept")
                topicref_child = ET.SubElement(relcolchild, "topicref")
                topicref_child.set("href", self._rel_href(map_path, child_path))
                topicref_child.set("type", "topic")
                topicref_child.set("collection-type", "child")
        
        return reltable
    
    def generate_cross_map_reltable(
        self,
        source_map_path: str,
        target_map_path: str,
        source_topics: List[Tuple[str, str]],
        target_topics: List[Tuple[str, str]],
        relationship_type: str = "related",
        density: float = 0.2,
    ) -> ET.Element:
        """Generate cross-map relationship table."""
        reltable = ET.Element("reltable")
        reltable.set("title", f"Cross-map relationships: {source_map_path} -> {target_map_path}")
        
        # Generate cross-map relationships
        for source_path, source_id in source_topics:
            if self.rand.random() > density:
                continue
            
            # Select random target
            target_path, target_id = self.rand.choice(target_topics)
            
            relrow = ET.SubElement(reltable, "relrow")
            
            # Source column
            relcolsource = ET.SubElement(relrow, "relcolspec")
            relcolsource.set("type", "concept")
            topicref_source = ET.SubElement(relcolsource, "topicref")
            topicref_source.set("href", self._rel_href(source_map_path, source_path))
            topicref_source.set("type", "topic")
            
            # Target column
            relcoltarget = ET.SubElement(relrow, "relcolspec")
            relcoltarget.set("type", "concept")
            topicref_target = ET.SubElement(relcoltarget, "topicref")
            topicref_target.set("href", self._rel_href(target_map_path, target_path))
            topicref_target.set("type", "topic")
            topicref_target.set("collection-type", relationship_type)
        
        return reltable
    
    def generate_conditional_reltable(
        self,
        map_path: str,
        topics: List[Tuple[str, str]],
        conditions: Dict[str, List[str]],  # {condition_name: [topic_ids]}
        relationship_types: List[str] = None,
    ) -> ET.Element:
        """Generate conditional relationship table."""
        if relationship_types is None:
            relationship_types = ["next", "previous", "related"]
        
        reltable = ET.Element("reltable")
        reltable.set("title", "Conditional relationships")
        
        # Group topics by condition
        topic_map = {tid: path for path, tid in topics}
        
        for condition_name, topic_ids in conditions.items():
            # Generate relationships within condition group
            for i, topic_id in enumerate(topic_ids):
                if topic_id not in topic_map:
                    continue
                
                # Link to next topic in condition
                if i < len(topic_ids) - 1:
                    next_id = topic_ids[i + 1]
                    if next_id in topic_map:
                        relrow = ET.SubElement(reltable, "relrow")
                        
                        relcolsource = ET.SubElement(relrow, "relcolspec")
                        relcolsource.set("type", "concept")
                        topicref_source = ET.SubElement(relcolsource, "topicref")
                        topicref_source.set("href", self._rel_href(map_path, topic_map[topic_id]))
                        topicref_source.set("type", "topic")
                        topicref_source.set("audience", condition_name)
                        
                        relcoltarget = ET.SubElement(relrow, "relcolspec")
                        relcoltarget.set("type", "concept")
                        topicref_target = ET.SubElement(relcoltarget, "topicref")
                        topicref_target.set("href", self._rel_href(map_path, topic_map[next_id]))
                        topicref_target.set("type", "topic")
                        topicref_target.set("collection-type", "next")
                        topicref_target.set("audience", condition_name)
        
        return reltable
    
    def generate_dynamic_reltable(
        self,
        map_path: str,
        topics: List[Tuple[str, str]],
        relationship_rules: List[Dict],  # [{type, source_pattern, target_pattern, probability}]
    ) -> ET.Element:
        """Generate dynamic relationship table based on rules."""
        reltable = ET.Element("reltable")
        reltable.set("title", "Dynamic relationships")
        
        for rule in relationship_rules:
            rel_type = rule.get("type", "related")
            source_pattern = rule.get("source_pattern", "*")
            target_pattern = rule.get("target_pattern", "*")
            probability = rule.get("probability", 0.3)
            
            # Filter topics by pattern
            source_topics = self._filter_topics(topics, source_pattern)
            target_topics = self._filter_topics(topics, target_pattern)
            
            # Generate relationships
            for source_path, source_id in source_topics:
                if self.rand.random() > probability:
                    continue
                
                target_path, target_id = self.rand.choice(target_topics)
                if source_path == target_path:
                    continue
                
                relrow = ET.SubElement(reltable, "relrow")
                
                relcolsource = ET.SubElement(relrow, "relcolspec")
                relcolsource.set("type", "concept")
                topicref_source = ET.SubElement(relcolsource, "topicref")
                topicref_source.set("href", self._rel_href(map_path, source_path))
                topicref_source.set("type", "topic")
                
                relcoltarget = ET.SubElement(relrow, "relcolspec")
                relcoltarget.set("type", "concept")
                topicref_target = ET.SubElement(relcoltarget, "topicref")
                topicref_target.set("href", self._rel_href(map_path, target_path))
                topicref_target.set("type", "topic")
                topicref_target.set("collection-type", rel_type)
        
        return reltable
    
    def optimize_reltable(
        self,
        reltable: ET.Element,
        max_relationships: int = 1000,
        optimize_strategy: str = "random",
    ) -> ET.Element:
        """Optimize relationship table for performance."""
        rows = list(reltable.findall("relrow"))
        
        if len(rows) <= max_relationships:
            return reltable
        
        # Optimize based on strategy
        if optimize_strategy == "random":
            # Random sampling
            selected_rows = self.rand.sample(rows, max_relationships)
        elif optimize_strategy == "first":
            # First N relationships
            selected_rows = rows[:max_relationships]
        elif optimize_strategy == "balanced":
            # Balanced distribution
            step = len(rows) // max_relationships
            selected_rows = rows[::step][:max_relationships]
        else:
            selected_rows = rows[:max_relationships]
        
        # Create optimized reltable
        optimized = ET.Element("reltable")
        optimized.set("title", reltable.get("title", "Optimized relationships"))
        for row in selected_rows:
            optimized.append(row)
        
        return optimized
    
    def _build_topic_hierarchy(
        self,
        topics: List[Tuple[str, str]],
        levels: int,
        children_per_level: int,
    ) -> Dict:
        """Build topic hierarchy structure."""
        hierarchy = {
            "parents": [],
            "children": {},
        }
        
        if not topics:
            return hierarchy
        
        # Select root topics (top level)
        root_count = max(1, len(topics) // (levels * children_per_level))
        root_topics = topics[:root_count]
        hierarchy["parents"] = root_topics
        
        # Build hierarchy levels
        remaining_topics = topics[root_count:]
        current_level_parents = root_topics
        
        for level in range(1, levels):
            if not remaining_topics:
                break
            
            level_children = []
            for parent_path, parent_id in current_level_parents:
                if not remaining_topics:
                    break
                
                # Assign children to parent
                num_children = min(children_per_level, len(remaining_topics))
                children = remaining_topics[:num_children]
                remaining_topics = remaining_topics[num_children:]
                
                if parent_id not in hierarchy["children"]:
                    hierarchy["children"][parent_id] = []
                hierarchy["children"][parent_id].extend(children)
                level_children.extend(children)
            
            current_level_parents = level_children
        
        return hierarchy
    
    def _filter_topics(
        self,
        topics: List[Tuple[str, str]],
        pattern: str,
    ) -> List[Tuple[str, str]]:
        """Filter topics by pattern (supports wildcards)."""
        if pattern == "*":
            return topics
        
        filtered = []
        for path, topic_id in topics:
            if pattern in path or pattern in topic_id:
                filtered.append((path, topic_id))
        
        return filtered


def generate_advanced_relationship_dataset(
    config,
    base: str,
    topic_count: int = 200,
    relationship_patterns: List[str] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Generate dataset with advanced relationship patterns."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    if relationship_patterns is None:
        relationship_patterns = ["hierarchical", "cross-map", "conditional"]
    
    generator = AdvancedRelationshipGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate topics
    topic_dir = safe_join(base, "topics", "pool")
    topics = []
    for i in range(1, topic_count + 1):
        filename = sanitize_filename(f"topic_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topic_dir, filename)
        topic_id = stable_id(config.seed, "adv-rel-topic", str(i), used_ids)
        
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
    
    # Generate maps with different relationship patterns
    maps_dir = safe_join(base, "maps")
    
    if "hierarchical" in relationship_patterns:
        # Hierarchical relationships
        hier_reltable = generator.generate_hierarchical_reltable(
            safe_join(maps_dir, "hierarchical.ditamap"),
            topics,
            hierarchy_levels=3,
            children_per_level=5,
        )
        
        hier_map_path = safe_join(maps_dir, "hierarchical.ditamap")
        hier_map_xml = _map_xml(
            config,
            map_id=stable_id(config.seed, "hier-map", "", used_ids),
            title="Hierarchical Relationships",
            topicref_hrefs=[],
            keydef_entries=[],
            scoped_blocks=[hier_reltable],
        )
        files[hier_map_path] = hier_map_xml
    
    if "cross-map" in relationship_patterns and len(topics) >= 100:
        # Split topics for cross-map relationships
        mid = len(topics) // 2
        source_topics = topics[:mid]
        target_topics = topics[mid:]
        
        cross_reltable = generator.generate_cross_map_reltable(
            safe_join(maps_dir, "source.ditamap"),
            safe_join(maps_dir, "target.ditamap"),
            source_topics,
            target_topics,
            relationship_type="related",
            density=0.2,
        )
        
        cross_map_path = safe_join(maps_dir, "cross_map.ditamap")
        cross_map_xml = _map_xml(
            config,
            map_id=stable_id(config.seed, "cross-map", "", used_ids),
            title="Cross-Map Relationships",
            topicref_hrefs=[],
            keydef_entries=[],
            scoped_blocks=[cross_reltable],
        )
        files[cross_map_path] = cross_map_xml
    
    if "conditional" in relationship_patterns:
        # Conditional relationships
        conditions = {
            "admin": [tid for _, tid in topics[:topic_count//3]],
            "user": [tid for _, tid in topics[topic_count//3:2*topic_count//3]],
            "developer": [tid for _, tid in topics[2*topic_count//3:]],
        }
        
        cond_reltable = generator.generate_conditional_reltable(
            safe_join(maps_dir, "conditional.ditamap"),
            topics,
            conditions,
        )
        
        cond_map_path = safe_join(maps_dir, "conditional.ditamap")
        cond_map_xml = _map_xml(
            config,
            map_id=stable_id(config.seed, "cond-map", "", used_ids),
            title="Conditional Relationships",
            topicref_hrefs=[],
            keydef_entries=[],
            scoped_blocks=[cond_reltable],
        )
        files[cond_map_path] = cond_map_xml
    
    return files


RECIPE_SPECS = [
    {
        "id": "advanced_relationships",
        "title": "Advanced Relationships",
        "description": "Generate hierarchical, cross-map, and conditional relationship tables",
        "tags": ["reltable", "hierarchical", "cross-map", "conditional"],
        "module": "app.generator.advanced_relationships",
        "function": "generate_advanced_relationship_dataset",
        "params_schema": {"topic_count": "int", "relationship_patterns": "list"},
        "default_params": {"topic_count": 200, "relationship_patterns": ["hierarchical", "cross-map", "conditional"]},
        "stability": "stable",
        "output_scale": "large",
        "constructs": ["reltable", "relrow", "relcolspec", "topicref"],
        "scenario_types": ["BOUNDARY", "SCALE", "INTEGRATION"],
        "use_when": ["hierarchical reltable", "cross-map relationships", "conditional relationships", "complex navigation"],
        "avoid_when": ["minimal repro", "simple reltable", "single map"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
