"""
AEM Guides specific metadata generation.

This module generates AEM/JCR-specific metadata for datasets.
"""

from typing import Dict, List, Optional
from datetime import datetime
import json


class AEMMetadataGenerator:
    """Generate AEM-specific metadata for content."""
    
    def __init__(self, seed: str = "default"):
        self.seed = seed
    
    def generate_jcr_properties(
        self,
        content_type: str = "topic",
        asset_state: str = "active",
        language: str = "en",
    ) -> Dict:
        """Generate JCR properties for AEM content."""
        return {
            "jcr:primaryType": "dam:Asset",
            "jcr:created": self._iso_timestamp(),
            "jcr:createdBy": "admin",
            "jcr:content": {
                "jcr:primaryType": "nt:resource",
                "jcr:mimeType": "application/xml",
                "jcr:lastModified": self._iso_timestamp(),
                "jcr:lastModifiedBy": "admin",
                "dam:assetState": asset_state,
                "dam:size": 0,  # Will be updated with actual size
                "dc:format": "application/xml",
                "dc:title": "",
                "dc:description": "",
            },
            "metadata": {
                "jcr:primaryType": "nt:unstructured",
                "dc:title": "",
                "dc:description": "",
                "dc:language": language,
                "dam:status": "active",
            }
        }
    
    def generate_content_fragment_properties(
        self,
        fragment_type: str = "dita-topic",
        language: str = "en",
    ) -> Dict:
        """Generate properties for AEM Content Fragments."""
        return {
            "jcr:primaryType": "dam:Asset",
            "jcr:content": {
                "jcr:primaryType": "dam:AssetContent",
                "metadata": {
                    "jcr:primaryType": "nt:unstructured",
                    "dc:format": "application/xml",
                    "dc:language": language,
                    "fragmentType": fragment_type,
                }
            }
        }
    
    def generate_translation_metadata(
        self,
        source_language: str = "en",
        target_languages: List[str] = None,
    ) -> Dict:
        """Generate translation workflow metadata."""
        if target_languages is None:
            target_languages = []
        
        return {
            "translation": {
                "sourceLanguage": source_language,
                "targetLanguages": target_languages,
                "translationStatus": {
                    lang: "pending" for lang in target_languages
                },
                "lastTranslated": None,
                "translationProvider": "aem-translation",
            }
        }
    
    def generate_workflow_metadata(
        self,
        workflow_type: str = "review",
        status: str = "pending",
    ) -> Dict:
        """Generate workflow metadata."""
        return {
            "workflow": {
                "type": workflow_type,
                "status": status,
                "startedAt": self._iso_timestamp() if status != "pending" else None,
                "completedAt": None,
                "assignee": None,
                "comments": [],
            }
        }
    
    def generate_publishing_metadata(
        self,
        output_formats: List[str] = None,
    ) -> Dict:
        """Generate publishing status metadata."""
        if output_formats is None:
            output_formats = ["aemsite", "pdf"]
        
        return {
            "publishing": {
                "outputFormats": output_formats,
                "status": {
                    fmt: {
                        "status": "pending",
                        "lastPublished": None,
                        "version": 1,
                    }
                    for fmt in output_formats
                },
                "lastPublished": None,
            }
        }
    
    def generate_version_metadata(
        self,
        version_number: int = 1,
        comment: str = "",
    ) -> Dict:
        """Generate version history metadata."""
        return {
            "version": {
                "number": version_number,
                "created": self._iso_timestamp(),
                "createdBy": "admin",
                "comment": comment,
                "label": f"v{version_number}",
            }
        }
    
    def generate_relationship_metadata(
        self,
        related_content: List[str] = None,
    ) -> Dict:
        """Generate relationship metadata."""
        if related_content is None:
            related_content = []
        
        return {
            "relationships": {
                "relatedTopics": related_content,
                "referencedBy": [],
                "references": [],
            }
        }
    
    def generate_complete_aem_metadata(
        self,
        content_type: str = "topic",
        language: str = "en",
        include_translation: bool = False,
        include_workflow: bool = False,
        include_publishing: bool = False,
    ) -> Dict:
        """Generate complete AEM metadata structure."""
        metadata = {
            "jcr": self.generate_jcr_properties(content_type, language=language),
        }
        
        if include_translation:
            metadata["translation"] = self.generate_translation_metadata(language)
        
        if include_workflow:
            metadata["workflow"] = self.generate_workflow_metadata()
        
        if include_publishing:
            metadata["publishing"] = self.generate_publishing_metadata()
        
        metadata["version"] = self.generate_version_metadata()
        metadata["relationships"] = self.generate_relationship_metadata()
        
        return metadata
    
    def _iso_timestamp(self) -> str:
        """Generate ISO timestamp."""
        return datetime.utcnow().isoformat() + "Z"


def generate_aem_manifest(
    base_manifest: Dict,
    include_metadata: bool = True,
    languages: List[str] = None,
) -> Dict:
    """Enhance manifest with AEM-specific metadata."""
    if languages is None:
        languages = ["en"]
    
    enhanced = base_manifest.copy()
    
    if include_metadata:
        enhanced["aem"] = {
            "jcrStructure": True,
            "contentFragmentSupport": True,
            "translationSupport": len(languages) > 1,
            "workflowSupport": True,
            "publishingSupport": True,
            "languages": languages,
        }
    
    return enhanced
