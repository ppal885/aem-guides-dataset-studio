"""
Conditional processing generation for AEM Guides datasets.

This module generates DITAVAL files and conditional content attributes.
"""

from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET
from app.generator.dita_utils import make_dita_id
from app.generator.generate import safe_join, sanitize_filename


class ConditionalProcessor:
    """Generate conditional processing attributes and DITAVAL files."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def add_conditional_attributes(
        self,
        element: ET.Element,
        audience: Optional[str] = None,
        platform: Optional[str] = None,
        product: Optional[str] = None,
        other_condition: Optional[str] = None,
    ) -> None:
        """Add conditional processing attributes to an element."""
        if audience:
            element.set("audience", audience)
        if platform:
            element.set("platform", platform)
        if product:
            element.set("product", product)
        if other_condition:
            element.set("otherprops", other_condition)
    
    def generate_ditaval(
        self,
        base: str,
        profiles: List[Dict[str, List[str]]],
    ) -> Tuple[str, bytes]:
        """Generate a DITAVAL file for conditional processing."""
        ditaval = ET.Element("val")
        ditaval.set("xmlns:ditaarch", "http://dita.oasis-open.org/architecture/2005/")
        
        # Generate propdefs for each profile
        for profile_name, conditions in profiles.items():
            for condition_type, values in conditions.items():
                for value in values:
                    propdef = ET.SubElement(ditaval, "propdef")
                    propdef.set("att", condition_type)
                    propdef.set("val", value)
                    propdef.set("action", "include")
        
        # Generate prop actions (exclude others)
        for profile_name, conditions in profiles.items():
            for condition_type, values in conditions.items():
                # Exclude values not in this profile
                all_values = self._get_all_values_for_type(condition_type, profiles)
                excluded_values = [v for v in all_values if v not in values]
                
                for value in excluded_values:
                    prop = ET.SubElement(ditaval, "prop")
                    prop.set("att", condition_type)
                    prop.set("val", value)
                    prop.set("action", "exclude")
        
        # Generate XML
        xml_body = ET.tostring(ditaval, encoding="utf-8", xml_declaration=False)
        doc = '<?xml version="1.0" encoding="UTF-8"?>\n'
        ditaval_content = doc.encode("utf-8") + xml_body
        
        ditaval_path = safe_join(base, "profiles", f"{profile_name}.ditaval")
        return ditaval_path, ditaval_content
    
    def generate_conditional_topic(
        self,
        topic_path: str,
        topic_id: str,
        title: str,
        conditional_content: List[Dict],
    ) -> bytes:
        """Generate a topic with conditional content."""
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = title
        
        # Body
        body = ET.SubElement(topic, "body")
        
        # Add conditional content
        for content_item in conditional_content:
            elem_type = content_item.get("type", "p")
            elem = ET.Element(elem_type)
            elem.text = content_item.get("content", "")
            
            # Add conditional attributes
            self.add_conditional_attributes(
                elem,
                audience=content_item.get("audience"),
                platform=content_item.get("platform"),
                product=content_item.get("product"),
                other_condition=content_item.get("otherprops"),
            )
            
            body.append(elem)
        
        # Generate XML
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body
    
    def generate_conditional_dataset(
        self,
        base: str,
        topic_count: int = 50,
        audiences: List[str] = None,
        platforms: List[str] = None,
        products: List[str] = None,
        include_map: bool = True,
    ) -> Dict[str, bytes]:
        """Generate a dataset with conditional content."""
        if audiences is None:
            audiences = ["admin", "user", "developer"]
        if platforms is None:
            platforms = ["windows", "mac", "linux"]
        if products is None:
            products = ["product-a", "product-b", "product-c"]
        
        files = {}
        topic_dir = safe_join(base, "topics", "pool")
        topic_paths = []
        
        # Generate topics with conditional content
        for i in range(1, topic_count + 1):
            filename = sanitize_filename(f"topic_{i:05d}.dita", self.config.windows_safe_filenames)
            path = safe_join(topic_dir, filename)
            topic_id = f"topic_{i:05d}"
            
            # Generate conditional content items
            conditional_content = []
            
            # Base content (no conditions)
            conditional_content.append({
                "type": "p",
                "content": f"Base content for topic {i}.",
            })
            
            # Audience-specific content
            for audience in audiences:
                if self.rand.random() > 0.5:  # 50% chance
                    conditional_content.append({
                        "type": "p",
                        "content": f"Content for {audience} audience.",
                        "audience": audience,
                    })
            
            # Platform-specific content
            for platform in platforms:
                if self.rand.random() > 0.6:  # 40% chance
                    conditional_content.append({
                        "type": "p",
                        "content": f"Content for {platform} platform.",
                        "platform": platform,
                    })
            
            # Product-specific content
            for product in products:
                if self.rand.random() > 0.7:  # 30% chance
                    conditional_content.append({
                        "type": "p",
                        "content": f"Content for {product}.",
                        "product": product,
                    })
            
            # Generate topic
            topic_xml = self.generate_conditional_topic(
                path,
                topic_id,
                f"Conditional Topic {i:05d}",
                conditional_content,
            )
            
            files[path] = topic_xml
            topic_paths.append(path)
        
        # Generate map if requested
        if include_map:
            from app.generator.generate import _map_xml, _rel_href
            from app.generator.dita_utils import stable_id
            
            map_filename = sanitize_filename("conditional_content.ditamap", self.config.windows_safe_filenames)
            map_path = safe_join(base, map_filename)
            map_id = stable_id(self.config.seed, "conditional_map", "", set())
            
            hrefs = [_rel_href(map_path, tp) for tp in topic_paths]
            
            map_xml = _map_xml(
                self.config,
                map_id=map_id,
                title="Conditional Content Map",
                topicref_hrefs=hrefs,
                keydef_entries=[],
                scoped_blocks=[],
            )
            files[map_path] = map_xml
        
        # Generate DITAVAL files for different profiles
        profiles = {
            "admin-windows-product-a": {
                "audience": ["admin"],
                "platform": ["windows"],
                "product": ["product-a"],
            },
            "user-all-platforms": {
                "audience": ["user"],
                "platform": ["windows", "mac", "linux"],
                "product": [],
            },
            "developer-linux": {
                "audience": ["developer"],
                "platform": ["linux"],
                "product": [],
            },
        }
        
        for profile_name, conditions in profiles.items():
            ditaval_path, ditaval_content = self.generate_ditaval(base, {profile_name: conditions})
            files[ditaval_path] = ditaval_content
        
        return files
    
    def _get_all_values_for_type(self, condition_type: str, profiles: Dict) -> List[str]:
        """Get all values for a condition type across all profiles."""
        all_values = set()
        for profile_conditions in profiles.values():
            if condition_type in profile_conditions:
                all_values.update(profile_conditions[condition_type])
        return list(all_values)


def generate_conditional_dataset(
    config,
    base: str,
    topic_count: int = 50,
    audiences: List[str] = None,
    platforms: List[str] = None,
    products: List[str] = None,
    generate_ditaval: bool = True,
    ditaval_profiles: List[str] = None,
    include_map: bool = True,
    pretty_print: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a dataset with conditional processing."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    processor = ConditionalProcessor(config, rand)
    return processor.generate_conditional_dataset(base, topic_count, audiences, platforms, products, include_map=include_map)


def generate_conditionals_audience_filter(config, base: str, **kwargs):
    """Conditional audience filter. Minimal dataset."""
    return generate_conditional_dataset(config, base, topic_count=3, audiences=["admin", "user"], **kwargs)


def generate_conditionals_platform_filter(config, base: str, **kwargs):
    """Conditional platform filter. Minimal dataset."""
    return generate_conditional_dataset(config, base, topic_count=3, platforms=["windows", "linux"], **kwargs)


def generate_conditionals_product_filter(config, base: str, **kwargs):
    """Conditional product filter. Minimal dataset."""
    return generate_conditional_dataset(config, base, topic_count=3, products=["product-a", "product-b"], **kwargs)


def generate_conditionals_flagging_basic(config, base: str, **kwargs):
    """Conditional flagging basic. Uses conditional dataset."""
    return generate_conditional_dataset(config, base, topic_count=2, **kwargs)


RECIPE_SPECS = [
    {
        "id": "conditional_content",
        "title": "Conditional Content",
        "description": "Generate topics with conditional processing attributes and DITAVAL",
        "tags": ["conditional", "ditaval", "audience", "platform"],
        "module": "app.generator.conditionals",
        "function": "generate_conditional_dataset",
        "params_schema": {"topic_count": "int", "audiences": "list", "platforms": "list", "products": "list"},
        "default_params": {"topic_count": 50, "include_map": True},
        "stability": "stable",
        "constructs": ["audience", "platform", "product", "otherprops", "ditaval", "prop"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "EDGE"],
        "use_when": ["conditional filtering", "audience targeting", "platform-specific content", "product variants"],
        "avoid_when": ["unconditional content", "single variant"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
        "aem_guides_features": ["conditional-processing", "ditaval", "filtering", "audience-targeting"],
    },
    {
        "id": "conditionals.audience_filter",
        "mechanism_family": "ditaval",
        "title": "Conditionals Audience Filter",
        "description": "Topics with audience conditional attributes.",
        "tags": ["CONDITIONAL", "AUDIENCE"],
        "module": "app.generator.conditionals",
        "function": "generate_conditionals_audience_filter",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["audience", "conditional"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["audience filter", "audience targeting"],
        "avoid_when": ["unconditional"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "conditionals.platform_filter",
        "title": "Conditionals Platform Filter",
        "description": "Topics with platform conditional attributes.",
        "tags": ["CONDITIONAL", "PLATFORM"],
        "module": "app.generator.conditionals",
        "function": "generate_conditionals_platform_filter",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["platform", "conditional"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["platform filter", "platform-specific"],
        "avoid_when": ["unconditional"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "conditionals.product_filter",
        "title": "Conditionals Product Filter",
        "description": "Topics with product conditional attributes.",
        "tags": ["CONDITIONAL", "PRODUCT"],
        "module": "app.generator.conditionals",
        "function": "generate_conditionals_product_filter",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["product", "conditional"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["product filter", "product variants"],
        "avoid_when": ["unconditional"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "conditionals.flagging_basic",
        "title": "Conditionals Flagging Basic",
        "description": "Basic conditional flagging with DITAVAL.",
        "tags": ["CONDITIONAL", "FLAGGING", "DITAVAL"],
        "module": "app.generator.conditionals",
        "function": "generate_conditionals_flagging_basic",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["ditaval", "prop", "conditional"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["flagging", "ditaval", "conditional"],
        "avoid_when": ["unconditional"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]
