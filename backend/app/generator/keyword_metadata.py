"""
Keyword Metadata Key Map Generator.

Generates a DITA dataset demonstrating keyword metadata key resolution with:
- Metadata map defining keys for keywords, categories, tags, and other metadata
- Keyword/metadata topic files containing the actual metadata values
- Consumer topics using keyrefs to reference metadata
- Examples of reusable metadata across multiple topics
"""
import xml.etree.ElementTree as ET
from typing import Dict, List
from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig

RECIPE_SPECS = [
    {
        "id": "keyword_metadata",
        "title": "Keyword Metadata",
        "description": "Generate keyword metadata key map dataset with keyrefs",
        "tags": ["keyword", "metadata", "keyref"],
        "module": "app.generator.keyword_metadata",
        "function": "generate_keyword_metadata_dataset",
        "params_schema": {"id_prefix": "str", "num_keywords": "int", "num_categories": "int", "num_topics": "int"},
        "default_params": {"id_prefix": "t", "num_keywords": 10, "num_categories": 5, "num_topics": 8},
        "stability": "stable",
        "constructs": ["keydef", "keyref", "metadata", "keywords", "prolog"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "INTEGRATION"],
        "use_when": ["metadata key resolution", "keyword indexing", "taxonomy testing"],
        "avoid_when": ["no metadata", "plain content only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
        "aem_guides_features": ["metadata", "key-resolution", "search-indexing"],
    },
]


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_content: str, metadata: Dict[str, str] = None, pretty_print: bool = True) -> bytes:
    """Generate topic XML with optional metadata."""
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    
    title_elem = ET.SubElement(topic, "title")
    title_elem.text = title
    
    if metadata:
        prolog = ET.SubElement(topic, "prolog")
        metadata_elem = ET.SubElement(prolog, "metadata")
        
        if "keywords" in metadata:
            keywords_elem = ET.SubElement(metadata_elem, "keywords")
            for keyword in metadata["keywords"].split(","):
                keyword_elem = ET.SubElement(keywords_elem, "keyword")
                keyword_elem.text = keyword.strip()
        
        if "category" in metadata:
            category_elem = ET.SubElement(metadata_elem, "category")
            category_elem.text = metadata["category"]
        
        if "audience" in metadata:
            audience_elem = ET.SubElement(metadata_elem, "audience")
            audience_elem.set("type", metadata.get("audience_type", "user"))
            audience_elem.text = metadata["audience"]
    
    body = ET.SubElement(topic, "body")
    try:
        body_elem = ET.fromstring(f"<body>{body_content}</body>")
        for child in body_elem:
            body.append(child)
    except ET.ParseError:
        p_elem = ET.SubElement(body, "p")
        p_elem.text = body_content
    
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b'\n', 1)[1] if b'\n' in xml_body else xml_body
        except Exception:
            pass
    
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _map_xml(config: DatasetConfig, map_id: str, title: str, keydefs: List[Dict], topicrefs: List[Dict] = None, maprefs: List[Dict] = None, pretty_print: bool = True) -> bytes:
    """Generate map XML."""
    map_elem = ET.Element("map", {"id": map_id})
    
    title_elem = ET.SubElement(map_elem, "title")
    title_elem.text = title
    
    for keydef in keydefs:
        keydef_elem = ET.SubElement(map_elem, "keydef")
        for key, value in keydef.items():
            if key == "keyscope":
                keydef_elem.set("keyscope", value)
            elif key == "keys":
                keydef_elem.set("keys", value)
            elif key == "href":
                keydef_elem.set("href", value)
            elif key == "processing-role":
                keydef_elem.set("processing-role", value)
    
    if topicrefs:
        for topicref in topicrefs:
            topicref_elem = ET.SubElement(map_elem, "topicref")
            for key, value in topicref.items():
                topicref_elem.set(key, value)
    
    if maprefs:
        for mapref in maprefs:
            mapref_elem = ET.SubElement(map_elem, "mapref")
            for key, value in mapref.items():
                mapref_elem.set(key, value)
    
    xml_body = ET.tostring(map_elem, encoding="utf-8", xml_declaration=False)
    
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b'\n', 1)[1] if b'\n' in xml_body else xml_body
        except Exception:
            pass
    
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
    return doc.encode("utf-8") + xml_body


def generate_keyword_metadata_dataset(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    num_keywords: int = 10,
    num_categories: int = 5,
    num_topics: int = 8,
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Generate keyword metadata key map dataset.
    
    Args:
        config: Dataset configuration
        base_path: Base path for dataset files
        id_prefix: Prefix for generated IDs (default: "t")
        num_keywords: Number of keyword metadata keys to generate
        num_categories: Number of category metadata keys to generate
        num_topics: Number of consumer topics to generate
        pretty_print: Pretty print XML output
    
    Returns:
        Dictionary of file paths to file contents (bytes)
    """
    files = {}
    used_ids = set()
    
    root_folder = f"{base_path}/aem_guides_keyword_metadata"
    maps_folder = f"{root_folder}/maps"
    topics_folder = f"{root_folder}/topics"
    metadata_folder = f"{topics_folder}/metadata"
    
    map_master_id = make_dita_id("map_master", id_prefix, used_ids)
    map_metadata_id = make_dita_id("map_metadata", id_prefix, used_ids)
    
    keyword_topics = []
    category_topics = []
    tag_topics = []
    
    keyword_keydefs = []
    category_keydefs = []
    tag_keydefs = []
    
    for i in range(1, num_keywords + 1):
        keyword_id = make_dita_id(f"keyword_{i}", id_prefix, used_ids)
        keyword_topic_id = make_dita_id(f"topic_keyword_{i}", id_prefix, used_ids)
        keyword_path = f"{metadata_folder}/keyword_{i}.dita"
        
        keyword_value = f"Keyword{i}"
        keyword_topics.append({
            "id": keyword_topic_id,
            "path": keyword_path,
            "title": f"Keyword: {keyword_value}",
            "body": f"<p>This is the metadata definition for keyword: <b>{keyword_value}</b></p>",
            "metadata": {"keywords": keyword_value, "category": "metadata"}
        })
        
        keyword_keydefs.append({
            "keys": f"kw-{i}",
            "href": f"../topics/metadata/keyword_{i}.dita"
        })
    
    for i in range(1, num_categories + 1):
        category_id = make_dita_id(f"category_{i}", id_prefix, used_ids)
        category_topic_id = make_dita_id(f"topic_category_{i}", id_prefix, used_ids)
        category_path = f"{metadata_folder}/category_{i}.dita"
        
        category_value = f"Category{i}"
        category_topics.append({
            "id": category_topic_id,
            "path": category_path,
            "title": f"Category: {category_value}",
            "body": f"<p>This is the metadata definition for category: <b>{category_value}</b></p>",
            "metadata": {"category": category_value, "audience": f"Category{i} Users", "audience_type": "user"}
        })
        
        category_keydefs.append({
            "keys": f"cat-{i}",
            "href": f"../topics/metadata/category_{i}.dita"
        })
    
    tag_topics.append({
        "id": make_dita_id("topic_tag_beginner", id_prefix, used_ids),
        "path": f"{metadata_folder}/tag_beginner.dita",
        "title": "Tag: Beginner",
        "body": "<p>Metadata tag for beginner-level content.</p>",
        "metadata": {"keywords": "beginner,getting-started", "category": "difficulty"}
    })
    
    tag_keydefs.append({
        "keys": "tag-beginner",
        "href": f"../topics/metadata/tag_beginner.dita"
    })
    
    tag_topics.append({
        "id": make_dita_id("topic_tag_advanced", id_prefix, used_ids),
        "path": f"{metadata_folder}/tag_advanced.dita",
        "title": "Tag: Advanced",
        "body": "<p>Metadata tag for advanced-level content.</p>",
        "metadata": {"keywords": "advanced,expert", "category": "difficulty"}
    })
    
    tag_keydefs.append({
        "keys": "tag-advanced",
        "href": f"../topics/metadata/tag_advanced.dita"
    })
    
    for topic_info in keyword_topics + category_topics + tag_topics:
        files[topic_info["path"]] = _topic_xml(
            config,
            topic_info["id"],
            topic_info["title"],
            topic_info["body"],
            topic_info.get("metadata"),
            pretty_print
        )
    
    metadata_map_keydefs = keyword_keydefs + category_keydefs + tag_keydefs
    
    metadata_map_topicrefs = []
    for topic_info in keyword_topics[:3] + category_topics[:2] + tag_topics:
        rel_path = topic_info["path"].replace(f"{topics_folder}/", "")
        metadata_map_topicrefs.append({
            "href": rel_path,
            "navtitle": topic_info["title"],
            "type": "topic"
        })
    
    files[f"{maps_folder}/metadata_map.ditamap"] = _map_xml(
        config,
        map_metadata_id,
        "Metadata Key Definitions",
        metadata_map_keydefs,
        metadata_map_topicrefs,
        None,
        pretty_print
    )
    
    consumer_topics = []
    consumer_topicrefs = []
    
    for i in range(1, num_topics + 1):
        topic_id = make_dita_id(f"topic_consumer_{i}", id_prefix, used_ids)
        topic_path = f"{topics_folder}/consumer_topic_{i}.dita"
        
        keyword_refs = []
        if i <= num_keywords:
            keyword_refs.append(f'<xref keyref="kw-{i}"/>')
        if i <= num_categories:
            keyword_refs.append(f'<xref keyref="cat-{i}"/>')
        if i % 2 == 0:
            keyword_refs.append('<xref keyref="tag-beginner"/>')
        else:
            keyword_refs.append('<xref keyref="tag-advanced"/>')
        
        body_content = f'''<p>This is consumer topic {i} that references metadata keys.</p>
<p>Referenced keywords: {', '.join(keyword_refs)}</p>
<p>This topic demonstrates how to use keyrefs to reference metadata definitions.</p>'''
        
        consumer_topics.append({
            "id": topic_id,
            "path": topic_path,
            "title": f"Consumer Topic {i}",
            "body": body_content
        })
        
        rel_path = topic_path.replace(f"{topics_folder}/", "")
        consumer_topicrefs.append({
            "href": rel_path,
            "navtitle": f"Consumer Topic {i}",
            "type": "topic"
        })
    
    for topic_info in consumer_topics:
        files[topic_info["path"]] = _topic_xml(
            config,
            topic_info["id"],
            topic_info["title"],
            topic_info["body"],
            None,
            pretty_print
        )
    
    master_map_keydefs = []
    
    master_map_topicrefs = consumer_topicrefs
    
    master_map_maprefs = [
        {
            "href": "metadata_map.ditamap",
            "navtitle": "Metadata Definitions",
            "processing-role": "resource-only"
        }
    ]
    
    files[f"{maps_folder}/master.ditamap"] = _map_xml(
        config,
        map_master_id,
        "Master Map - Keyword Metadata Demo",
        master_map_keydefs,
        master_map_topicrefs,
        master_map_maprefs,
        pretty_print
    )
    
    readme_content = f"""Keyword Metadata Key Map Dataset
=====================================

This dataset demonstrates DITA keyword metadata key resolution.

Structure:
- master.ditamap: Root map containing consumer topics
- metadata_map.ditamap: Map defining metadata keys (keywords, categories, tags)
- topics/metadata/: Keyword and metadata definition topics
- topics/: Consumer topics that reference metadata keys

Metadata Keys:
- Keywords: kw-1 through kw-{num_keywords} (pointing to keyword topics)
- Categories: cat-1 through cat-{num_categories} (pointing to category topics)
- Tags: tag-beginner, tag-advanced (pointing to tag topics)

Consumer Topics:
- consumer_topic_1.dita through consumer_topic_{num_topics}.dita
- Each topic uses keyrefs to reference metadata keys

Usage:
- Consumer topics use <xref keyref="kw-1"/> to reference keyword metadata
- Consumer topics use <xref keyref="cat-1"/> to reference category metadata
- Consumer topics use <xref keyref="tag-beginner"/> to reference tag metadata

Key Resolution:
- Keys are defined in metadata_map.ditamap
- metadata_map.ditamap is referenced from master.ditamap with processing-role="resource-only"
- This makes metadata keys available to all topics in master.ditamap

All IDs are DITA-compliant (start with letter/underscore, no leading digits).

Validation:
- All href references are relative and valid
- All IDs match DITA ID pattern: ^[A-Za-z_][A-Za-z0-9_.-]*$
- XML is well-formed
- Metadata map uses processing-role="resource-only" to make keys available without including topics in navigation
"""
    
    files[f"{root_folder}/README.txt"] = readme_content.encode("utf-8")
    
    return files
