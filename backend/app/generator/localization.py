"""
Localization and multi-language content generation for AEM Guides.

This module generates language variants and translation-ready content.
"""

from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET

# Helper functions
def safe_join(*parts: str) -> str:
    """Safely join path parts."""
    return "/".join(p.strip("/") for p in parts if p)


class LocalizationGenerator:
    """Generate localized content variants."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_language_variant(
        self,
        base_content: bytes,
        source_language: str,
        target_language: str,
        translation_metadata: Optional[Dict] = None,
    ) -> Tuple[bytes, Dict]:
        """Generate a language variant of content."""
        # Parse base content
        try:
            root = ET.fromstring(base_content)
        except ET.ParseError:
            # If not XML, return as-is with metadata
            return base_content, self._generate_translation_metadata(source_language, target_language)
        
        # Add language attributes
        root.set("xml:lang", target_language)
        
        # Translate titles (simple placeholder translation)
        for title in root.findall(".//title"):
            if title.text:
                title.text = f"[{target_language.upper()}] {title.text}"
        
        # Translate body content (placeholder)
        for para in root.findall(".//p"):
            if para.text and para.text.strip():
                para.text = f"[{target_language.upper()}] {para.text}"
        
        # Generate XML
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        variant_content = doc.encode("utf-8") + xml_body
        
        metadata = self._generate_translation_metadata(source_language, target_language, translation_metadata)
        
        return variant_content, metadata
    
    def generate_language_copies(
        self,
        base_path: str,
        base_content: bytes,
        source_language: str,
        target_languages: List[str],
    ) -> Dict[str, Tuple[str, bytes, Dict]]:
        """Generate language copies for AEM structure."""
        language_copies = {}
        
        for target_lang in target_languages:
            # Generate language-specific path
            lang_path = self._get_language_path(base_path, source_language, target_lang)
            
            # Generate variant content
            variant_content, metadata = self.generate_language_variant(
                base_content,
                source_language,
                target_lang,
            )
            
            language_copies[target_lang] = (lang_path, variant_content, metadata)
        
        return language_copies
    
    def generate_translation_metadata_file(
        self,
        base: str,
        source_language: str,
        target_languages: List[str],
        content_paths: List[str],
    ) -> Tuple[str, bytes]:
        """Generate translation metadata JSON file."""
        metadata = {
            "sourceLanguage": source_language,
            "targetLanguages": target_languages,
            "translationStatus": {},
            "contentPaths": content_paths,
            "lastUpdated": self._iso_timestamp(),
        }
        
        # Initialize translation status for each content path and language
        for path in content_paths:
            metadata["translationStatus"][path] = {
                lang: {
                    "status": "pending",
                    "lastTranslated": None,
                    "translationProvider": "aem-translation",
                }
                for lang in target_languages
            }
        
        import json
        metadata_path = safe_join(base, "metadata", "translation-status.json")
        metadata_bytes = json.dumps(metadata, indent=2).encode("utf-8")
        
        return metadata_path, metadata_bytes
    
    def _get_language_path(self, base_path: str, source_lang: str, target_lang: str) -> str:
        """Convert path to language-specific path."""
        # AEM Guides structure: /content/dam/{lang}/...
        parts = base_path.split("/")
        
        # Find language folder and replace
        for i, part in enumerate(parts):
            if part == source_lang:
                parts[i] = target_lang
                break
        else:
            # Insert language folder if not found
            if "/content/dam/" in base_path:
                idx = base_path.find("/content/dam/") + len("/content/dam/")
                base_path = base_path[:idx] + f"{target_lang}/" + base_path[idx:]
                return base_path
        
        return "/".join(parts)
    
    def _generate_translation_metadata(
        self,
        source_language: str,
        target_language: str,
        additional_metadata: Optional[Dict] = None,
    ) -> Dict:
        """Generate translation metadata."""
        metadata = {
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
            "translationStatus": "pending",
            "lastTranslated": None,
            "translationProvider": "aem-translation",
        }
        
        if additional_metadata:
            metadata.update(additional_metadata)
        
        return metadata
    
    def _iso_timestamp(self) -> str:
        """Generate ISO timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


def generate_localized_dataset(
    config,
    base: str,
    base_content: Dict[str, bytes],
    source_language: str = "en",
    target_languages: List[str] = None,
) -> Dict[str, bytes]:
    """Generate a localized dataset with language variants."""
    if target_languages is None:
        target_languages = ["es", "fr", "de"]
    
    import random
    rand = random.Random(config.seed)
    generator = LocalizationGenerator(config, rand)
    
    files = {}
    all_content_paths = []
    
    # Generate language variants for each content file
    for base_path, content in base_content.items():
        all_content_paths.append(base_path)
        
        # Generate variants for each target language
        language_copies = generator.generate_language_copies(
            base_path,
            content,
            source_language,
            target_languages,
        )
        
        # Add language copies to files
        for lang, (lang_path, lang_content, metadata) in language_copies.items():
            files[lang_path] = lang_content
            
            # Store metadata (could be added to manifest or separate file)
            metadata_path = lang_path.replace(".dita", ".metadata.json")
            import json
            files[metadata_path] = json.dumps(metadata, indent=2).encode("utf-8")
    
    # Generate translation metadata file
    metadata_path, metadata_bytes = generator.generate_translation_metadata_file(
        base,
        source_language,
        target_languages,
        all_content_paths,
    )
    files[metadata_path] = metadata_bytes
    
    return files


def generate_localized_content_dataset(
    config,
    base: str,
    source_language: str = "en",
    target_languages: List[str] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Wrapper: generate minimal base content then localize."""
    from app.generator.specialized import generate_task_topics_dataset
    if rand is None:
        import random
        rand = random.Random(config.seed)
    base_content = generate_task_topics_dataset(config, base, topic_count=5, steps_per_task=3, rand=rand)
    localized = generate_localized_dataset(config, base, base_content, source_language, target_languages)
    localized.update(base_content)
    return localized


RECIPE_SPECS = [
    {
        "id": "localized_content",
        "title": "Localized Content",
        "description": "Generate localized/multi-language content variants",
        "tags": ["localization", "translation", "multilingual"],
        "module": "app.generator.localization",
        "function": "generate_localized_content_dataset",
        "params_schema": {"source_language": "str", "target_languages": "list"},
        "default_params": {"source_language": "en", "target_languages": ["es", "fr", "de"]},
        "stability": "stable",
        "constructs": ["xml:lang", "topic", "language-copy"],
        "scenario_types": ["BOUNDARY", "INTEGRATION"],
        "use_when": ["multi-language", "translation", "localization", "language variants"],
        "avoid_when": ["single language", "English only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "aem_guides_features": ["localization", "translation", "language-copies"],
    },
]
