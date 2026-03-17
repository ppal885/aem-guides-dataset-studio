"""
Integration helper for AEM metadata into existing recipes.

This module provides functions to enhance existing dataset generation with AEM metadata.
"""

from typing import Dict, List, Optional
from app.generator.aem_metadata import AEMMetadataGenerator, generate_aem_manifest


def enhance_manifest_with_aem_metadata(
    base_manifest: Dict,
    config,
    include_metadata: bool = True,
    languages: List[str] = None,
    include_translation: bool = False,
    include_workflow: bool = False,
    include_publishing: bool = False,
) -> Dict:
    """Enhance existing manifest with AEM metadata."""
    if languages is None:
        languages = ["en"]
    
    enhanced = base_manifest.copy()
    
    if include_metadata:
        metadata_gen = AEMMetadataGenerator(config.seed)
        
        # Add AEM-specific metadata
        enhanced["aem"] = {
            "jcrStructure": True,
            "contentFragmentSupport": True,
            "translationSupport": include_translation and len(languages) > 1,
            "workflowSupport": include_workflow,
            "publishingSupport": include_publishing,
            "languages": languages,
            "metadata": metadata_gen.generate_complete_aem_metadata(
                content_type="topic",
                language=languages[0] if languages else "en",
                include_translation=include_translation,
                include_workflow=include_workflow,
                include_publishing=include_publishing,
            ),
        }
    
    return enhanced


def add_aem_metadata_to_files(
    files: Dict[str, bytes],
    config,
    include_jcr_properties: bool = True,
    language: str = "en",
) -> Dict[str, bytes]:
    """Add AEM metadata files to dataset."""
    enhanced_files = files.copy()
    
    if include_jcr_properties:
        metadata_gen = AEMMetadataGenerator(config.seed)
        
        # Generate .content.xml files for AEM structure
        # This would be used when importing to AEM
        for path, content in files.items():
            if path.endswith((".dita", ".ditamap")):
                # Generate JCR properties file
                jcr_props = metadata_gen.generate_jcr_properties(
                    content_type="topic" if path.endswith(".dita") else "map",
                    language=language,
                )
                
                # Create .content.xml path
                content_xml_path = path + "/.content.xml"
                
                # Convert to XML format (simplified)
                import json
                import xml.etree.ElementTree as ET
                
                # Create JCR XML structure
                jcr_root = ET.Element("jcr:root")
                jcr_root.set("xmlns:jcr", "http://www.jcp.org/jcr/1.0")
                jcr_root.set("xmlns:dam", "http://www.day.com/dam/1.0")
                jcr_root.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
                
                for key, value in jcr_props.items():
                    if isinstance(value, dict):
                        # Nested properties
                        child = ET.SubElement(jcr_root, key)
                        child.set("jcr:primaryType", value.get("jcr:primaryType", "nt:unstructured"))
                        for k, v in value.items():
                            if k != "jcr:primaryType":
                                child.set(k, str(v))
                    else:
                        jcr_root.set(key, str(value))
                
                xml_content = ET.tostring(jcr_root, encoding="utf-8", xml_declaration=True)
                enhanced_files[content_xml_path] = xml_content
    
    return enhanced_files


def integrate_aem_metadata_into_generation(
    files: Dict[str, bytes],
    manifest: Dict,
    config,
    options: Optional[Dict] = None,
) -> Tuple[Dict[str, bytes], Dict]:
    """Main integration function to add AEM metadata to generated dataset."""
    if options is None:
        options = {
            "include_jcr_properties": True,
            "include_translation": False,
            "include_workflow": False,
            "include_publishing": True,
            "languages": ["en"],
        }
    
    # Enhance files with AEM metadata
    enhanced_files = add_aem_metadata_to_files(
        files,
        config,
        include_jcr_properties=options.get("include_jcr_properties", True),
        language=options.get("languages", ["en"])[0],
    )
    
    # Enhance manifest with AEM metadata
    enhanced_manifest = enhance_manifest_with_aem_metadata(
        manifest,
        config,
        include_metadata=True,
        languages=options.get("languages", ["en"]),
        include_translation=options.get("include_translation", False),
        include_workflow=options.get("include_workflow", False),
        include_publishing=options.get("include_publishing", True),
    )
    
    return enhanced_files, enhanced_manifest
