"""
Heavy content generation - topics with tables and codeblocks.

This module generates DITA topics with heavy content including:
- Multiple tables per topic
- Multiple codeblocks per topic
- Large amounts of structured content

When representative_xml is provided (from Jira evidence), writes those topics
instead of synthetic content for MIN_REPRO / table_content scenarios.
"""

from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id, make_dita_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml, _rel_href
from app.generator.evidence_to_dita import (
    _validate_representative_xml,
    _ensure_root_tag,
    _extract_root_tag,
    _minimal_topic_xml,
)


class HeavyContentGenerator:
    """Generate heavy content topics with tables and codeblocks."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_table(self, cols: int, rows: int) -> ET.Element:
        """Generate a DITA table."""
        table = ET.Element("table")
        table.set("frame", "all")
        table.set("rowsep", "1")
        table.set("colsep", "1")
        
        tgroup = ET.SubElement(table, "tgroup")
        tgroup.set("cols", str(cols))
        tgroup.set("colsep", "1")
        tgroup.set("rowsep", "1")
        
        # Column specifications with varied widths (1*, 2*, etc.) for width-related testing
        width_patterns = ["1*", "2*", "1*", "3*", "1*"]
        for i in range(cols):
            colspec = ET.SubElement(tgroup, "colspec")
            colspec.set("colname", f"col{i+1}")
            colspec.set("colnum", str(i+1))
            colspec.set("colwidth", width_patterns[i % len(width_patterns)])
        
        # Header
        thead = ET.SubElement(tgroup, "thead")
        header_row = ET.SubElement(thead, "row")
        for i in range(cols):
            entry = ET.SubElement(header_row, "entry")
            entry.text = f"Header {i+1}"
        
        # Body rows
        tbody = ET.SubElement(tgroup, "tbody")
        for row_idx in range(rows):
            row = ET.SubElement(tbody, "row")
            for col_idx in range(cols):
                entry = ET.SubElement(row, "entry")
                entry.text = f"Row {row_idx+1}, Col {col_idx+1}"
        
        return table
    
    def generate_codeblock(self, lines: int, language: str = "xml") -> ET.Element:
        """Generate a DITA codeblock."""
        codeblock = ET.Element("codeblock")
        codeblock.set("xml:space", "preserve")
        
        # Generate code lines
        code_lines = []
        for i in range(lines):
            if language == "xml":
                code_lines.append(f'  <element id="item_{i}">Content {i}</element>')
            elif language == "java":
                code_lines.append(f'    public void method{i}() {{ System.out.println("{i}"); }}')
            elif language == "python":
                code_lines.append(f'    def function_{i}():')
                code_lines.append(f'        print("{i}")')
            else:
                code_lines.append(f'    // Code line {i+1}')
        
        codeblock.text = "\n".join(code_lines)
        return codeblock
    
    def generate_heavy_topic(
        self,
        topic_id: str,
        title: str,
        tables_per_topic: int,
        codeblocks_per_topic: int,
        table_cols: int,
        table_rows: int,
        code_lines_per_codeblock: int,
    ) -> bytes:
        """Generate a topic with heavy content (tables and codeblocks)."""
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = title
        
        # Short description
        shortdesc = ET.SubElement(topic, "shortdesc")
        shortdesc.text = f"Heavy content topic: {title}"
        
        # Body
        body = ET.SubElement(topic, "body")
        
        # Add intro paragraph
        intro_p = ET.SubElement(body, "p")
        intro_p.text = f"This topic contains {tables_per_topic} tables and {codeblocks_per_topic} codeblocks for testing content processing."
        
        # Add tables
        for i in range(tables_per_topic):
            section = ET.SubElement(body, "section")
            section.set("id", f"table_section_{i+1}")
            section_title = ET.SubElement(section, "title")
            section_title.text = f"Table {i+1}"
            
            section_p = ET.SubElement(section, "p")
            section_p.text = f"Table {i+1} with {table_cols} columns and {table_rows} rows."
            
            table = self.generate_table(table_cols, table_rows)
            section.append(table)
        
        # Add codeblocks
        languages = ["xml", "java", "python", "javascript"]
        for i in range(codeblocks_per_topic):
            section = ET.SubElement(body, "section")
            section.set("id", f"code_section_{i+1}")
            section_title = ET.SubElement(section, "title")
            section_title.text = f"Code Example {i+1}"
            
            section_p = ET.SubElement(section, "p")
            section_p.text = f"Code example {i+1} with {code_lines_per_codeblock} lines."
            
            language = self.rand.choice(languages)
            codeblock = self.generate_codeblock(code_lines_per_codeblock, language)
            codeblock.set("outputclass", f"language-{language}")
            section.append(codeblock)
        
        # Generate XML
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body


def _generate_from_representative_xml(
    config,
    base: str,
    representative_xml: List[str],
    max_items: int = 6,
    max_chars: int = 2000,
) -> tuple[Dict[str, bytes], List[str]]:
    """
    Parse representative_xml and write topics to heavy_topics/.
    Returns (files dict, list of topic paths for map).
    """
    files: Dict[str, bytes] = {}
    topic_paths: List[str] = []
    used_ids: set = set()
    snippets = _validate_representative_xml(representative_xml, max_items=max_items, max_chars=max_chars)

    if not snippets:
        return files, topic_paths

    topics_dir = safe_join(base, "heavy_topics")
    map_path = safe_join(base, "heavy_topics.ditamap")

    for i, snippet in enumerate(snippets):
        if not snippet or not isinstance(snippet, str):
            continue
        snippet = snippet.strip()
        if not snippet:
            continue

        wrapped = _ensure_root_tag(snippet)
        try:
            root_elem = ET.fromstring(wrapped)
        except ET.ParseError:
            pid = make_dita_id(f"parse_fail_{i}", "ev", used_ids)
            topic_path = safe_join(topics_dir, f"evidence_topic_{i}.dita")
            files[topic_path] = _minimal_topic_xml(config, pid, f"Parse fallback {i}")
            topic_paths.append(topic_path)
            continue

        tag = _extract_root_tag(root_elem)
        elem_id = root_elem.get("id") or root_elem.get("{http://www.w3.org/XML/1998/namespace}id")
        if not elem_id:
            elem_id = make_dita_id(f"elem_{i}", "ev", used_ids)
            root_elem.set("id", elem_id)
        used_ids.add(elem_id)

        if tag == "map":
            continue
        fname = f"evidence_topic_{i}.dita"
        topic_path = safe_join(topics_dir, fname)
        topic_paths.append(topic_path)

        xml_bytes = ET.tostring(root_elem, encoding="utf-8", xml_declaration=False)
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_bytes)
            xml_bytes = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_bytes = xml_bytes.split(b"\n", 1)[1] if b"\n" in xml_bytes else xml_bytes
        except Exception:
            pass

        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
        files[topic_path] = doc.encode("utf-8") + xml_bytes

    return files, topic_paths


def generate_heavy_topics_dataset(
    config,
    base: str,
    topic_count: int = 50,
    tables_per_topic: int = 5,
    codeblocks_per_topic: int = 5,
    table_cols: int = 4,
    table_rows: int = 10,
    code_lines_per_codeblock: int = 20,
    include_map: bool = True,
    map_topicref_count: int = 50,
    representative_xml: Optional[List[str]] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Generate heavy content dataset with tables and codeblocks.
    When representative_xml is provided, writes evidence topics instead of synthetic content."""
    if rand is None:
        import random
        rand = random.Random(config.seed)

    files: Dict[str, bytes] = {}
    used_ids: set = set()
    topics_dir = safe_join(base, "heavy_topics")
    topic_paths: List[str] = []

    generator = HeavyContentGenerator(config, rand)
    evidence_has_tables = False

    if representative_xml and isinstance(representative_xml, list) and len(representative_xml) > 0:
        evidence_files, topic_paths = _generate_from_representative_xml(
            config, base, representative_xml, max_items=6, max_chars=8000
        )
        files.update(evidence_files)
        # Check if evidence topics contain tables (table_content recipe should output tables)
        for content in evidence_files.values():
            if content and (b"<table" in content or b"<simpletable" in content):
                evidence_has_tables = True
                break

    if not evidence_has_tables:
        # Ensure tables in output: either full synthetic or augment evidence with table topics
        for i in range(1, topic_count + 1):
            topic_filename = sanitize_filename(f"heavy_topic_{i:05d}.dita", config.windows_safe_filenames)
            topic_path = safe_join(topics_dir, topic_filename)
            topic_id = stable_id(config.seed, "heavy_topic", str(i), used_ids)

            topic_xml = generator.generate_heavy_topic(
                topic_id,
                f"Heavy Topic {i}",
                tables_per_topic,
                codeblocks_per_topic,
                table_cols,
                table_rows,
                code_lines_per_codeblock,
            )

            files[topic_path] = topic_xml
            topic_paths.append(topic_path)
    
    # Generate map if requested
    if include_map:
        map_dir = base
        map_filename = sanitize_filename("heavy_topics.ditamap", config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        map_id = stable_id(config.seed, "heavy_map", "", used_ids)
        
        # Select topics for map
        selected_topics = topic_paths[:map_topicref_count]
        
        # Generate map XML
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = "Heavy Topics Map"
        
        for topic_path in selected_topics:
            topicref = ET.SubElement(root, "topicref")
            topicref.set("href", _rel_href(map_path, topic_path))
            topicref.set("type", "topic")
        
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files


RECIPE_SPECS = [
    {
        "id": "heavy_topics_tables_codeblocks",
        "title": "Heavy Topics (Tables + Codeblocks)",
        "description": "Generate topics with tables and codeblocks for content processing tests",
        "tags": ["heavy", "tables", "codeblocks"],
        "module": "app.generator.heavy_content",
        "function": "generate_heavy_topics_dataset",
        "params_schema": {"topic_count": "int", "tables_per_topic": "int", "codeblocks_per_topic": "int", "representative_xml": "list"},
        "default_params": {"topic_count": 50, "tables_per_topic": 5, "codeblocks_per_topic": 5},
        "stability": "stable",
        "output_scale": "medium",
        "constructs": ["table", "codeblock", "topic"],
        "scenario_types": ["STRESS", "SCALE", "BOUNDARY"],
        "use_when": ["stress test", "heavy content", "tables codeblocks", "content processing"],
        "avoid_when": ["minimal repro", "light content"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
