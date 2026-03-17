"""
Conref (content reference) generation for AEM Guides datasets.

Conrefs allow content reuse by referencing elements from other topics.
"""

from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.self_ref_utils import self_conref_value, self_conrefend_value

# Helper functions
def safe_join(*parts: str) -> str:
    """Safely join path parts."""
    return "/".join(p.strip("/") for p in parts if p)

def sanitize_filename(filename: str, windows_safe: bool = False) -> str:
    """Sanitize filename."""
    if windows_safe:
        filename = filename.replace(":", "-").replace("<", "").replace(">", "")
    return filename


def _rel_href(from_path: str, to_path: str) -> str:
    """Calculate relative href."""
    from_parts = from_path.split('/')
    to_parts = to_path.split('/')
    common_len = 0
    for i in range(min(len(from_parts), len(to_parts))):
        if from_parts[i] == to_parts[i]:
            common_len += 1
        else:
            break
    up_levels = len(from_parts) - common_len - 1
    return '../' * up_levels + '/'.join(to_parts[common_len:])


class ConrefGenerator:
    """Generate conref attributes and reusable content."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_reusable_element(
        self,
        element_type: str,
        element_id: str,
        content: str,
    ) -> ET.Element:
        """Generate a reusable element that can be conref'd."""
        element = ET.Element(element_type)
        element.set("id", element_id)
        
        if element_type == "p":
            element.text = content
        elif element_type == "section":
            title = ET.SubElement(element, "title")
            title.text = content
            body = ET.SubElement(element, "body")
            p = ET.SubElement(body, "p")
            p.text = f"Content for {content}"
        elif element_type == "li":
            element.text = content
        
        return element
    
    def add_conref_to_element(
        self,
        element: ET.Element,
        target_path: str,
        target_id: str,
        current_path: str,
    ) -> None:
        """Add conref attribute to an element."""
        href = _rel_href(current_path, target_path)
        element.set("conref", f"{href}#{target_id}")
        element.set("conaction", "pushbefore")  # or "pushafter", "mark", "markpush"

    def add_self_conref_to_element(
        self,
        element: ET.Element,
        topic_id: str,
        target_id: str,
        current_filename: str,
        use_filename: bool = False,
    ) -> None:
        """Add same-file conref. Ensures target_id != element id to prevent self-loop."""
        elem_id = element.get("id")
        if elem_id and elem_id == target_id:
            raise ValueError(f"Self-loop conref: element {elem_id} cannot reference itself")
        element.set("conref", self_conref_value(topic_id, target_id, current_filename, use_filename))

    def add_self_conrefend_range(
        self,
        element: ET.Element,
        topic_id: str,
        start_id: str,
        end_id: str,
        current_filename: str,
        use_filename: bool = False,
    ) -> None:
        """Add same-file conref+conrefend range. Start and end must differ."""
        if start_id == end_id:
            raise ValueError("conrefend range requires different start and end ids")
        element.set("conref", self_conref_value(topic_id, start_id, current_filename, use_filename))
        element.set("conrefend", self_conrefend_value(topic_id, end_id, current_filename, use_filename))
    
    def generate_conref_topic(
        self,
        topic_path: str,
        topic_id: str,
        title: str,
        reusable_elements: List[Tuple[str, str, str]],  # (type, id, content)
        conref_targets: List[Tuple[str, str]],  # (target_path, target_id)
    ) -> bytes:
        """Generate a topic with reusable elements and conrefs."""
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = title
        
        # Body
        body = ET.SubElement(topic, "body")
        
        # Add reusable elements
        for elem_type, elem_id, content in reusable_elements:
            elem = self.generate_reusable_element(elem_type, elem_id, content)
            body.append(elem)
        
        # Add conrefs
        for target_path, target_id in conref_targets:
            conref_elem = ET.SubElement(body, "p")
            self.add_conref_to_element(conref_elem, target_path, target_id, topic_path)
        
        # Generate XML
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body
    
    def generate_conref_dataset(
        self,
        base: str,
        topic_count: int = 50,
        conref_density: float = 0.3,
    ) -> Dict[str, bytes]:
        """Generate a dataset focused on conref usage."""
        files = {}
        topic_dir = safe_join(base, "topics", "pool")
        used_ids = set()
        
        # Generate topics with reusable elements
        topics_with_reusables = []
        reusable_elements_map = {}  # path -> [(type, id, content)]
        
        for i in range(1, topic_count + 1):
            filename = sanitize_filename(f"topic_{i:05d}.dita", self.config.windows_safe_filenames)
            path = safe_join(topic_dir, filename)
            topic_id = stable_id(self.config.seed, "conref-topic", str(i), used_ids)
            
            # Generate reusable elements for this topic
            num_reusables = self.rand.randint(2, 5)
            reusables = []
            for j in range(num_reusables):
                elem_id = f"{topic_id}_reusable_{j}"
                elem_type = self.rand.choice(["p", "section", "li"])
                content = f"Reusable content {i}-{j}"
                reusables.append((elem_type, elem_id, content))
            
            reusable_elements_map[path] = reusables
            
            # Generate topic with reusable elements
            topic_xml = self.generate_conref_topic(
                path,
                topic_id,
                f"Topic {i:05d}",
                reusables,
                [],  # No conrefs yet
            )
            
            files[path] = topic_xml
            topics_with_reusables.append((path, topic_id))
        
        # Now add conrefs to topics
        for i, (topic_path, topic_id) in enumerate(topics_with_reusables):
            # Decide how many conrefs this topic should have
            num_conrefs = int(len(topics_with_reusables) * conref_density)
            num_conrefs = min(num_conrefs, 10)  # Limit to 10
            
            # Select random target topics
            target_indices = self.rand.sample(
                range(len(topics_with_reusables)),
                min(num_conrefs, len(topics_with_reusables))
            )
            
            conref_targets = []
            for idx in target_indices:
                if idx == i:  # Don't conref to self
                    continue
                target_path, target_topic_id = topics_with_reusables[idx]
                
                # Select a random reusable element from target
                if target_path in reusable_elements_map:
                    target_reusables = reusable_elements_map[target_path]
                    if target_reusables:
                        elem_type, elem_id, _ = self.rand.choice(target_reusables)
                        conref_targets.append((target_path, elem_id))
            
            # Regenerate topic with conrefs
            if conref_targets:
                reusables = reusable_elements_map[topic_path]
                topic_xml = self.generate_conref_topic(
                    topic_path,
                    topic_id,
                    f"Topic {i+1:05d}",
                    reusables,
                    conref_targets,
                )
                files[topic_path] = topic_xml
        
        # Generate a map referencing all topics
        map_dir = safe_join(base, "maps")
        map_filename = sanitize_filename("conref_map.ditamap", self.config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        map_id = stable_id(self.config.seed, "conref-map", "", used_ids)
        
        refs = []
        for topic_path, _ in topics_with_reusables[:20]:  # Limit map size
            href = _rel_href(map_path, topic_path)
            refs.append(href)
        
        # Generate map XML
        map_elem = ET.Element("map", {"id": map_id})
        title_elem = ET.SubElement(map_elem, "title")
        title_elem.text = "Conref Test Map"
        
        for href in refs:
            topicref = ET.SubElement(map_elem, "topicref")
            topicref.set("href", href)
            topicref.set("type", "topic")
        
        xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_map}\n'
        map_xml = doc.encode("utf-8") + xml_body
        
        files[map_path] = map_xml
        
        return files


def generate_conref_pack(
    config,
    base: str,
    topic_count: int = 50,
    conref_density: float = 0.3,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a dataset focused on conref usage."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = ConrefGenerator(config, rand)
    return generator.generate_conref_dataset(base, topic_count, conref_density)


RECIPE_SPECS = [
    {
        "id": "conref_pack",
        "mechanism_family": "conref",
        "title": "Conref Pack",
        "description": "Generate DITA topics with content references (conrefs) for content reuse",
        "tags": ["conref", "reuse", "content-reference"],
        "module": "app.generator.conrefs",
        "function": "generate_conref_pack",
        "params_schema": {"topic_count": "int", "conref_density": "float", "include_map": "bool"},
        "default_params": {"topic_count": 50, "conref_density": 0.3, "include_map": True},
        "stability": "stable",
        "constructs": ["conref", "topicref", "topic", "map"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "INTEGRATION"],
        "use_when": ["content reuse needed", "shared blocks across topics", "modular content"],
        "avoid_when": ["single-topic dataset", "no reuse requirements"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
        "aem_guides_features": ["content-reuse", "conref-resolution"],
    },
]
