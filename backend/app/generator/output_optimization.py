"""
Output format optimization for AEM Guides datasets.

This module optimizes content for different output formats (AEM Site, PDF, HTML5).
"""

from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from app.generator.generate import safe_join


class OutputFormatOptimizer:
    """Optimize content for specific output formats."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def optimize_for_aemsite(
        self,
        topic: ET.Element,
        include_navigation: bool = True,
        include_breadcrumbs: bool = True,
    ) -> ET.Element:
        """Optimize topic for AEM Site output."""
        # Add AEM Site specific metadata
        if include_navigation:
            prolog = topic.find("prolog")
            if prolog is None:
                prolog = ET.SubElement(topic, "prolog")
            
            metadata = prolog.find("metadata")
            if metadata is None:
                metadata = ET.SubElement(prolog, "metadata")
            
            # Add navigation metadata
            othermeta = ET.SubElement(metadata, "othermeta")
            othermeta.set("name", "aem-site-navigation")
            othermeta.set("content", "true")
        
        # Add breadcrumb support
        if include_breadcrumbs:
            prolog = topic.find("prolog")
            if prolog is None:
                prolog = ET.SubElement(topic, "prolog")
            
            metadata = prolog.find("metadata")
            if metadata is None:
                metadata = ET.SubElement(prolog, "metadata")
            
            othermeta = ET.SubElement(metadata, "othermeta")
            othermeta.set("name", "aem-site-breadcrumbs")
            othermeta.set("content", "true")
        
        return topic
    
    def optimize_for_pdf(
        self,
        topic: ET.Element,
        include_page_breaks: bool = True,
        include_toc: bool = True,
    ) -> ET.Element:
        """Optimize topic for PDF output."""
        # Add PDF-specific attributes
        topic.set("outputclass", "pdf-optimized")
        
        # Add page break hints
        if include_page_breaks:
            body = topic.find("body")
            if body is not None:
                # Add page break before first section
                first_section = body.find("section")
                if first_section is not None:
                    first_section.set("outputclass", "page-break-before")
        
        # Add TOC metadata
        if include_toc:
            prolog = topic.find("prolog")
            if prolog is None:
                prolog = ET.SubElement(topic, "prolog")
            
            metadata = prolog.find("metadata")
            if metadata is None:
                metadata = ET.SubElement(prolog, "metadata")
            
            othermeta = ET.SubElement(metadata, "othermeta")
            othermeta.set("name", "pdf-toc")
            othermeta.set("content", "true")
            othermeta.set("toc-level", "1")
        
        return topic
    
    def optimize_for_html5(
        self,
        topic: ET.Element,
        include_responsive: bool = True,
        include_accessibility: bool = True,
    ) -> ET.Element:
        """Optimize topic for HTML5 output."""
        # Add HTML5-specific attributes
        topic.set("outputclass", "html5-optimized")
        
        # Add responsive design metadata
        if include_responsive:
            prolog = topic.find("prolog")
            if prolog is None:
                prolog = ET.SubElement(topic, "prolog")
            
            metadata = prolog.find("metadata")
            if metadata is None:
                metadata = ET.SubElement(prolog, "metadata")
            
            othermeta = ET.SubElement(metadata, "othermeta")
            othermeta.set("name", "html5-responsive")
            othermeta.set("content", "true")
        
        # Add accessibility attributes
        if include_accessibility:
            # Add alt text to images if missing
            for image in topic.findall(".//image"):
                if not image.get("alt"):
                    image.set("alt", "Image")
            
            # Add table headers
            for table in topic.findall(".//table"):
                thead = table.find("thead")
                if thead is None:
                    tgroup = table.find("tgroup")
                    if tgroup is not None:
                        thead = ET.SubElement(tgroup, "thead")
                        row = ET.SubElement(thead, "row")
                        # Add header cells based on cols attribute
                        cols = int(tgroup.get("cols", "1"))
                        for i in range(cols):
                            entry = ET.SubElement(row, "entry")
                            entry.text = f"Header {i+1}"
        
        return topic
    
    def optimize_for_mobile(
        self,
        topic: ET.Element,
        optimize_images: bool = True,
        simplify_structure: bool = True,
    ) -> ET.Element:
        """Optimize topic for mobile output."""
        topic.set("outputclass", "mobile-optimized")
        
        # Optimize images for mobile
        if optimize_images:
            for image in topic.findall(".//image"):
                # Add mobile-specific attributes
                image.set("outputclass", "mobile-responsive")
                # Reduce default size for mobile
                if not image.get("width"):
                    image.set("width", "100%")
        
        # Simplify structure for mobile
        if simplify_structure:
            # Flatten nested sections
            body = topic.find("body")
            if body is not None:
                # Limit nesting depth
                for section in body.findall(".//section"):
                    nested_sections = section.findall(".//section")
                    if len(nested_sections) > 2:
                        # Flatten excessive nesting
                        pass  # Implementation would flatten structure
        
        return topic
    
    def add_output_metadata(
        self,
        base: str,
        output_formats: List[str],
        optimization_settings: Dict[str, Dict],
    ) -> Tuple[str, bytes]:
        """Generate output format metadata file."""
        metadata = {
            "outputFormats": output_formats,
            "optimizationSettings": optimization_settings,
            "lastUpdated": self._iso_timestamp(),
        }
        
        import json
        metadata_path = safe_join(base, "metadata", "output-formats.json")
        metadata_bytes = json.dumps(metadata, indent=2).encode("utf-8")
        
        return metadata_path, metadata_bytes
    
    def _iso_timestamp(self) -> str:
        """Generate ISO timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


def optimize_dataset_for_output(
    config,
    base: str,
    files: Dict[str, bytes],
    output_format: str = "aemsite",
    optimization_options: Optional[Dict] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Optimize dataset files for specific output format."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    if optimization_options is None:
        optimization_options = {}
    
    optimizer = OutputFormatOptimizer(config, rand)
    optimized_files = {}
    
    # Optimize each topic file
    for path, content in files.items():
        if path.endswith(".dita"):
            try:
                # Parse XML
                root = ET.fromstring(content)
                
                # Optimize based on format
                if output_format == "aemsite":
                    root = optimizer.optimize_for_aemsite(
                        root,
                        include_navigation=optimization_options.get("navigation", True),
                        include_breadcrumbs=optimization_options.get("breadcrumbs", True),
                    )
                elif output_format == "pdf":
                    root = optimizer.optimize_for_pdf(
                        root,
                        include_page_breaks=optimization_options.get("page_breaks", True),
                        include_toc=optimization_options.get("toc", True),
                    )
                elif output_format == "html5":
                    root = optimizer.optimize_for_html5(
                        root,
                        include_responsive=optimization_options.get("responsive", True),
                        include_accessibility=optimization_options.get("accessibility", True),
                    )
                elif output_format == "mobile":
                    root = optimizer.optimize_for_mobile(
                        root,
                        optimize_images=optimization_options.get("optimize_images", True),
                        simplify_structure=optimization_options.get("simplify_structure", True),
                    )
                
                # Regenerate XML
                xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
                doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
                optimized_files[path] = doc.encode("utf-8") + xml_body
            except Exception:
                # If optimization fails, keep original
                optimized_files[path] = content
        else:
            # Keep non-topic files as-is
            optimized_files[path] = content
    
    # Add output metadata
    metadata_path, metadata_bytes = optimizer.add_output_metadata(
        base,
        [output_format],
        {output_format: optimization_options},
    )
    optimized_files[metadata_path] = metadata_bytes
    
    return optimized_files


def generate_output_optimized_dataset(
    config,
    base: str,
    output_format: str = "aemsite",
    optimization_options: Optional[Dict] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Wrapper: generate minimal base content then optimize for output format."""
    from app.generator.specialized import generate_task_topics_dataset
    base_files = generate_task_topics_dataset(config, base, topic_count=5, steps_per_task=3, rand=rand)
    return optimize_dataset_for_output(
        config, base, base_files, output_format, optimization_options, rand
    )


RECIPE_SPECS = [
    {
        "id": "output_optimized",
        "title": "Output Optimized",
        "description": "Optimize content for AEM Site, PDF, HTML5, or Mobile output",
        "tags": ["output", "aemsite", "pdf", "html5"],
        "module": "app.generator.output_optimization",
        "function": "generate_output_optimized_dataset",
        "params_schema": {"output_format": "str", "optimization_options": "dict"},
        "default_params": {"output_format": "aemsite"},
        "stability": "stable",
        "constructs": ["othermeta", "outputclass", "prolog", "metadata"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "INTEGRATION"],
        "use_when": ["AEM Site output", "PDF generation", "HTML5 publish", "mobile output"],
        "avoid_when": ["generic DITA only", "no output format requirements"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "aem_guides_features": ["aem-site", "pdf-output", "html5-publish", "breadcrumbs", "navigation"],
    },
]
