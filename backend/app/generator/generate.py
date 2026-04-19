"""Core generation utilities."""
import os
import re
from typing import List
import xml.etree.ElementTree as ET
from app.utils.xml_escape import xml_escape_text, xml_escape_attr, xml_escape_href


def safe_join(*parts: str) -> str:
    """Join path parts safely, handling None and empty strings."""
    filtered = [p for p in parts if p]
    joined = os.path.join(*filtered) if filtered else ""
    # Normalize to forward slashes for cross-platform compatibility and AEM Guides
    return joined.replace("\\", "/")


def sanitize_filename(filename: str, windows_safe: bool = False) -> str:
    """Sanitize filename for filesystem compatibility."""
    # Remove or replace invalid characters
    if windows_safe:
        # Windows doesn't allow: < > : " / \ | ? *
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    else:
        # Unix: only / and null are problematic
        filename = filename.replace('/', '_').replace('\x00', '_')
    return filename


def _map_xml(
    config,
    map_id: str,
    title: str,
    topicref_hrefs: List[str],
    topicref_entries: List[dict] = None,
    keydef_entries: List = None,
    scoped_blocks: List = None,
) -> bytes:
    """Generate DITA map XML."""
    from app.generator.dita_utils import stable_id
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Validate inputs
    if topicref_hrefs is None:
        topicref_hrefs = []
    if topicref_entries is None:
        topicref_entries = []

    if topicref_entries:
        normalized_topicrefs = []
        for entry in topicref_entries:
            if not isinstance(entry, dict):
                continue
            href = str(entry.get("href") or "").strip()
            attrs = dict(entry.get("attrs") or {}) if isinstance(entry.get("attrs"), dict) else {}
            if href:
                normalized_topicrefs.append({"href": href, "attrs": attrs})
    else:
        normalized_topicrefs = [{"href": href, "attrs": {}} for href in topicref_hrefs if href]
    
    # Log map generation details for debugging
    logger.debug(f"Generating map '{title}' (id: {map_id}) with {len(normalized_topicrefs)} topicrefs")
    
    root = ET.Element("map", {
        "id": map_id,
        "xmlns": "http://www.oasis-open.org/committees/entity/release/1.1/catalog",
        "xmlns:ditaarch": "http://dita.oasis-open.org/architecture/2005/",
    })
    
    title_elem = ET.SubElement(root, "title")
    title_elem.text = xml_escape_text(title)
    
    # Add topicrefs - ensure ALL are added
    topicref_count = 0
    for entry in normalized_topicrefs:
        href = str(entry.get("href") or "").strip()
        if href:
            attrs = {"href": xml_escape_href(href)}
            for attr_name, attr_value in (entry.get("attrs") or {}).items():
                clean_name = str(attr_name or "").strip()
                clean_value = str(attr_value or "").strip()
                if clean_name and clean_value:
                    attrs[clean_name] = xml_escape_attr(clean_value)
            ET.SubElement(root, "topicref", attrs)
            topicref_count += 1
    
    # Verify all topicrefs were added
    if topicref_count != len(normalized_topicrefs):
        logger.warning(
            f"Map '{title}': Expected {len(normalized_topicrefs)} topicrefs, but added {topicref_count}. "
            f"Some hrefs may be empty or invalid."
        )
    else:
        logger.debug(f"Map '{title}': Successfully added all {topicref_count} topicrefs")
    
    # Add keydefs if provided
    if keydef_entries:
        for keydef_entry in keydef_entries:
            keydef = ET.SubElement(root, "keydef", {
                "keys": xml_escape_attr(keydef_entry.get("keys", "")),
                "href": xml_escape_href(keydef_entry.get("href", "")),
            })
    
    # Add scoped blocks if provided
    if scoped_blocks:
        for block in scoped_blocks:
            attrs = {k: xml_escape_attr(v) for k, v in block.get("attrs", {}).items()}
            scope_elem = ET.SubElement(root, block.get("tag", "topicref"), attrs)
            if block.get("content"):
                scope_elem.text = xml_escape_text(block["content"])
    
    # Convert to bytes with doctype
    ET.indent(root, space="  ")
    xml_body = ET.tostring(root, encoding='utf-8', xml_declaration=False)
    
    # Verify the XML contains expected number of topicrefs
    xml_str = xml_body.decode("utf-8")
    topicref_matches = xml_str.count('<topicref')
    if topicref_matches != topicref_count:
        logger.warning(
            f"Map '{title}': XML serialization mismatch - expected {topicref_count} topicrefs "
            f"in XML, but found {topicref_matches}"
        )
    
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    result = doc.encode("utf-8") + xml_body
    
    logger.debug(f"Map '{title}': Generated {len(result)} bytes of XML with {topicref_matches} topicref elements")
    
    return result


def _rel_href(from_path: str, to_path: str) -> str:
    """Calculate relative href between two paths."""
    from_path_dir = os.path.dirname(from_path) or "."
    rel_path = os.path.relpath(to_path, from_path_dir)
    # Normalize path separators
    return rel_path.replace("\\", "/")
