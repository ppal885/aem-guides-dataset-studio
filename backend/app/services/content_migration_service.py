"""Content Migration Copilot service - converts Word/Markdown/HTML content into
properly structured DITA topics with real information typing.

Pure-heuristic classification (no LLM calls) and well-formed DITA XML output."""

import re
import xml.etree.ElementTree as ET
from typing import List, Optional

from app.core.structured_logging import get_structured_logger
from app.services.content_parser_service import (
    ContentBlock,
    detect_format,
    parse_content,
    parse_html,
    parse_markdown,
    parse_plain_text,
)

logger = get_structured_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION_VERBS = {
    "click", "select", "open", "enter", "configure", "run", "navigate",
    "press", "type", "choose", "drag", "drop", "install", "set", "create",
    "delete", "remove", "add", "update", "copy", "paste", "save", "close",
    "start", "stop", "enable", "disable", "check", "uncheck", "expand",
    "collapse", "right-click", "double-click", "download", "upload",
    "go", "log", "sign", "verify", "ensure", "confirm", "execute",
}

_DEFINITION_PATTERN = re.compile(
    r"^(?:(?:an?|the)\s+)?(\w[\w\s]{0,60}?)\s+(?:is|are|refers?\s+to|represents?|defines?|describes?)\s+",
    re.IGNORECASE,
)

_VALID_XML_ID = re.compile(r"^[a-zA-Z_][\w.-]*$")

# DOCTYPE declarations
DOCTYPE_TASK = '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">'
DOCTYPE_CONCEPT = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
DOCTYPE_REFERENCE = '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">'
DOCTYPE_GLOSSENTRY = '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossary Entry//EN" "glossentry.dtd">'
DOCTYPE_MAP = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'

DOCTYPE_MAP_BY_TYPE = {
    "task": DOCTYPE_TASK,
    "concept": DOCTYPE_CONCEPT,
    "reference": DOCTYPE_REFERENCE,
    "glossentry": DOCTYPE_GLOSSENTRY,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Create a valid XML ID from a title string."""
    slug = re.sub(r"[^\w\s-]", "", text.lower().strip())
    slug = re.sub(r"[\s-]+", "_", slug)
    slug = slug.strip("_")
    if not slug:
        slug = "topic"
    # Ensure it starts with a letter or underscore
    if slug[0].isdigit():
        slug = "t_" + slug
    return slug


def _escape_xml(text: str) -> str:
    """Escape special XML characters in text content."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def _xml_to_string(element: ET.Element) -> str:
    """Serialize an ElementTree element to a UTF-8 XML string."""
    return ET.tostring(element, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# Section splitter - split parsed blocks into sections by heading
# ---------------------------------------------------------------------------

def _split_into_sections(blocks: List[ContentBlock]) -> list[dict]:
    """Split a flat list of content blocks into sections grouped by heading.

    Returns a list of dicts: {"title": str, "level": int, "blocks": list[ContentBlock]}
    """
    if not blocks:
        return []

    sections: list[dict] = []
    current_title = "Untitled"
    current_level = 1
    current_blocks: list[ContentBlock] = []

    for block in blocks:
        if block.block_type == "heading":
            # Save previous section
            if current_blocks:
                sections.append({
                    "title": current_title,
                    "level": current_level,
                    "blocks": current_blocks,
                })
            current_title = block.content
            current_level = block.level
            current_blocks = []
        else:
            current_blocks.append(block)

    # Save last section
    if current_blocks:
        sections.append({
            "title": current_title,
            "level": current_level,
            "blocks": current_blocks,
        })
    elif not sections:
        # No headings at all - treat everything as one section
        sections.append({
            "title": "Untitled",
            "level": 1,
            "blocks": blocks,
        })

    return sections


# ---------------------------------------------------------------------------
# Heuristic classifier
# ---------------------------------------------------------------------------

def _has_action_verb_list(blocks: List[ContentBlock]) -> bool:
    """Check if blocks contain an ordered list with action verbs."""
    for block in blocks:
        if block.block_type == "ordered_list":
            items = block.children if block.children else block.content.split("\n")
            for item in items:
                first_word = item.strip().split()[0].lower().rstrip(".,;:") if item.strip() else ""
                if first_word in ACTION_VERBS:
                    return True
    return False


def _has_table_with_rows(blocks: List[ContentBlock], min_rows: int = 3) -> bool:
    """Check if blocks contain a table with at least min_rows rows."""
    for block in blocks:
        if block.block_type == "table":
            rows = block.metadata.get("rows", [])
            if len(rows) >= min_rows:
                return True
    return False


def _is_definition_paragraph(blocks: List[ContentBlock]) -> bool:
    """Check if the first paragraph looks like a definition."""
    for block in blocks:
        if block.block_type == "paragraph":
            if _DEFINITION_PATTERN.match(block.content.strip()):
                return True
            break  # Only check the first paragraph
    return False


def _is_mostly_prose(blocks: List[ContentBlock]) -> bool:
    """Check if the section is mostly paragraphs without lists."""
    if not blocks:
        return False
    para_count = sum(1 for b in blocks if b.block_type == "paragraph")
    list_count = sum(1 for b in blocks if b.block_type in ("ordered_list", "unordered_list"))
    return para_count > 0 and para_count >= list_count


def _is_short_definition(section: dict) -> bool:
    """Check if a section is a short glossary-style definition."""
    blocks = section.get("blocks", [])
    total_text = " ".join(b.content for b in blocks if b.block_type == "paragraph")
    if len(total_text.split()) <= 30 and _is_definition_paragraph(blocks):
        return True
    return False


def _classify_section(section: dict) -> str:
    """Classify a section into a DITA topic type using heuristics."""
    blocks = section.get("blocks", [])

    if not blocks:
        return "concept"

    # Check for glossentry first (short definitions)
    if _is_short_definition(section):
        return "glossentry"

    # Check for task (ordered list with action verbs)
    if _has_action_verb_list(blocks):
        return "task"

    # Check for ordered lists even without action verbs - still likely a task
    has_ordered = any(b.block_type == "ordered_list" for b in blocks)
    if has_ordered:
        return "task"

    # Check for reference (tables with data)
    if _has_table_with_rows(blocks, min_rows=3):
        return "reference"

    # Check for definition paragraph
    if _is_definition_paragraph(blocks):
        return "concept"

    # Mostly prose defaults to concept
    if _is_mostly_prose(blocks):
        return "concept"

    # Tables with fewer rows still suggest reference
    if any(b.block_type == "table" for b in blocks):
        return "reference"

    return "concept"


# ---------------------------------------------------------------------------
# Public: parse_and_classify
# ---------------------------------------------------------------------------

def parse_and_classify(content: str, source_format: str = "auto") -> dict:
    """Parse input content and classify each section by DITA topic type.

    Returns:
        {
            "sections": [{"title": str, "topic_type": str, "blocks": list}],
            "source_format": str,
            "migration_notes": [str],
        }
    """
    if not content or not content.strip():
        logger.warning("Empty content provided for migration")
        return {
            "sections": [],
            "source_format": "plain_text",
            "migration_notes": ["Input content is empty."],
        }

    # Detect or use specified format
    if source_format == "auto":
        fmt = detect_format(content)
    else:
        fmt = source_format

    # Parse
    if fmt == "markdown":
        blocks = parse_markdown(content)
    elif fmt == "html":
        blocks = parse_html(content)
    else:
        blocks = parse_plain_text(content)

    # Split into sections
    sections = _split_into_sections(blocks)
    notes: list[str] = []

    if not sections:
        notes.append("No sections detected in the input content.")
        return {
            "sections": [],
            "source_format": fmt,
            "migration_notes": notes,
        }

    # Classify each section
    classified: list[dict] = []
    for section in sections:
        topic_type = _classify_section(section)
        classified.append({
            "title": section["title"],
            "level": section.get("level", 1),
            "topic_type": topic_type,
            "blocks": section["blocks"],
        })

    # Generate migration notes
    type_counts = {}
    for s in classified:
        type_counts[s["topic_type"]] = type_counts.get(s["topic_type"], 0) + 1

    if len(classified) == 1 and classified[0]["title"] == "Untitled":
        notes.append("No headings found; content was treated as a single topic.")

    # Check for ambiguous sections
    for s in classified:
        blk = s["blocks"]
        has_list = any(b.block_type in ("ordered_list", "unordered_list") for b in blk)
        has_table = any(b.block_type == "table" for b in blk)
        has_prose = any(b.block_type == "paragraph" for b in blk)
        if has_list and has_table:
            notes.append(
                "Section '%s' has both lists and tables; classified as %s." % (s["title"], s["topic_type"])
            )
        elif has_list and has_prose and s["topic_type"] == "concept":
            notes.append(
                "Section '%s' has mixed prose and lists; classified as concept." % s["title"]
            )

    logger.info(
        "Classified %d sections: %s",
        len(classified),
        ", ".join("%s=%d" % (k, v) for k, v in type_counts.items()),
    )

    return {
        "sections": classified,
        "source_format": fmt,
        "migration_notes": notes,
    }


# ---------------------------------------------------------------------------
# DITA XML generators
# ---------------------------------------------------------------------------

def _build_steps_xml(blocks: List[ContentBlock]) -> ET.Element:
    """Build a <steps> element from ordered list blocks."""
    steps = ET.Element("steps")
    for block in blocks:
        if block.block_type == "ordered_list":
            items = block.children if block.children else block.content.split("\n")
            for item_text in items:
                step = ET.SubElement(steps, "step")
                cmd = ET.SubElement(step, "cmd")
                cmd.text = item_text.strip()
    # If no steps were added, add a placeholder
    if len(steps) == 0:
        step = ET.SubElement(steps, "step")
        cmd = ET.SubElement(step, "cmd")
        cmd.text = "Perform the required action."
    return steps


def _build_simpletable(block: ContentBlock) -> ET.Element:
    """Build a <simpletable> element from a table block."""
    rows = block.metadata.get("rows", [])
    table = ET.Element("simpletable")
    if not rows:
        return table

    # First row as header
    header = ET.SubElement(table, "sthead")
    for cell in rows[0]:
        entry = ET.SubElement(header, "stentry")
        entry.text = cell

    # Remaining rows
    for row in rows[1:]:
        strow = ET.SubElement(table, "strow")
        for cell in row:
            entry = ET.SubElement(strow, "stentry")
            entry.text = cell

    return table


def _build_paragraphs(blocks: List[ContentBlock]) -> list[ET.Element]:
    """Build paragraph and list elements from content blocks."""
    elements: list[ET.Element] = []
    for block in blocks:
        if block.block_type == "paragraph":
            p = ET.Element("p")
            p.text = block.content
            elements.append(p)
        elif block.block_type == "unordered_list":
            ul = ET.Element("ul")
            items = block.children if block.children else block.content.split("\n")
            for item_text in items:
                li = ET.SubElement(ul, "li")
                li.text = item_text.strip()
            elements.append(ul)
        elif block.block_type == "code_block":
            pre = ET.Element("codeblock")
            pre.text = block.content
            elements.append(pre)
        elif block.block_type == "image":
            fig = ET.Element("fig")
            image = ET.SubElement(fig, "image")
            image.set("href", block.metadata.get("src", ""))
            alt = ET.SubElement(image, "alt")
            alt.text = block.content or block.metadata.get("alt", "")
            elements.append(fig)
        elif block.block_type == "table":
            elements.append(_build_simpletable(block))
    return elements


def _generate_task_xml(section: dict) -> str:
    """Generate a DITA task topic XML string."""
    title = section["title"]
    topic_id = _slugify(title)
    blocks = section["blocks"]

    root = ET.Element("task")
    root.set("id", topic_id)
    root.set("xml:lang", "en")

    title_el = ET.SubElement(root, "title")
    title_el.text = title

    taskbody = ET.SubElement(root, "taskbody")

    # Context from paragraphs before the first ordered list
    context_blocks = []
    remaining_blocks = list(blocks)
    for i, block in enumerate(blocks):
        if block.block_type == "ordered_list":
            context_blocks = blocks[:i]
            remaining_blocks = blocks[i:]
            break

    if context_blocks:
        context = ET.SubElement(taskbody, "context")
        for el in _build_paragraphs(context_blocks):
            context.append(el)

    # Steps
    steps_el = _build_steps_xml(remaining_blocks)
    taskbody.append(steps_el)

    # Result from paragraphs after the last ordered list
    after_steps = []
    found_last_ol = False
    for block in reversed(remaining_blocks):
        if block.block_type == "ordered_list":
            found_last_ol = True
            break
        after_steps.insert(0, block)

    if after_steps and found_last_ol:
        result = ET.SubElement(taskbody, "result")
        for el in _build_paragraphs(after_steps):
            result.append(el)

    xml_str = _xml_to_string(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n%s\n%s' % (DOCTYPE_TASK, xml_str)


def _generate_concept_xml(section: dict) -> str:
    """Generate a DITA concept topic XML string."""
    title = section["title"]
    topic_id = _slugify(title)
    blocks = section["blocks"]

    root = ET.Element("concept")
    root.set("id", topic_id)
    root.set("xml:lang", "en")

    title_el = ET.SubElement(root, "title")
    title_el.text = title

    conbody = ET.SubElement(root, "conbody")

    if blocks:
        section_el = ET.SubElement(conbody, "section")
        for el in _build_paragraphs(blocks):
            section_el.append(el)
    else:
        p = ET.SubElement(conbody, "p")
        p.text = title

    xml_str = _xml_to_string(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n%s\n%s' % (DOCTYPE_CONCEPT, xml_str)


def _generate_reference_xml(section: dict) -> str:
    """Generate a DITA reference topic XML string."""
    title = section["title"]
    topic_id = _slugify(title)
    blocks = section["blocks"]

    root = ET.Element("reference")
    root.set("id", topic_id)
    root.set("xml:lang", "en")

    title_el = ET.SubElement(root, "title")
    title_el.text = title

    refbody = ET.SubElement(root, "refbody")

    # Add paragraphs before tables
    non_table = [b for b in blocks if b.block_type != "table"]
    tables = [b for b in blocks if b.block_type == "table"]

    if non_table:
        section_el = ET.SubElement(refbody, "section")
        for el in _build_paragraphs(non_table):
            section_el.append(el)

    for table_block in tables:
        refbody.append(_build_simpletable(table_block))

    if not blocks:
        p_el = ET.SubElement(refbody, "p")
        p_el.text = title

    xml_str = _xml_to_string(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n%s\n%s' % (DOCTYPE_REFERENCE, xml_str)


def _generate_glossentry_xml(section: dict) -> str:
    """Generate a DITA glossentry topic XML string."""
    title = section["title"]
    topic_id = _slugify(title)
    blocks = section["blocks"]

    root = ET.Element("glossentry")
    root.set("id", topic_id)
    root.set("xml:lang", "en")

    glossterm = ET.SubElement(root, "glossterm")
    glossterm.text = title

    glossdef = ET.SubElement(root, "glossdef")
    text_parts = [b.content for b in blocks if b.block_type == "paragraph"]
    glossdef.text = " ".join(text_parts) if text_parts else title

    xml_str = _xml_to_string(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n%s\n%s' % (DOCTYPE_GLOSSENTRY, xml_str)


_GENERATOR_MAP = {
    "task": _generate_task_xml,
    "concept": _generate_concept_xml,
    "reference": _generate_reference_xml,
    "glossentry": _generate_glossentry_xml,
}


# ---------------------------------------------------------------------------
# Public: generate_dita_topics
# ---------------------------------------------------------------------------

def generate_dita_topics(classified_sections: list[dict]) -> list[dict]:
    """Generate DITA XML for each classified section.

    Returns a list of dicts: {"title": str, "topic_type": str, "xml": str, "filename": str}
    """
    topics: list[dict] = []
    seen_ids: set[str] = set()

    for section in classified_sections:
        topic_type = section.get("topic_type", "concept")
        title = section.get("title", "Untitled")
        generator = _GENERATOR_MAP.get(topic_type, _generate_concept_xml)

        xml_str = generator(section)

        # Build unique filename
        base_slug = _slugify(title)
        slug = base_slug
        counter = 2
        while slug in seen_ids:
            slug = "%s_%d" % (base_slug, counter)
            counter += 1
        seen_ids.add(slug)

        filename = "%s.dita" % slug

        topics.append({
            "title": title,
            "topic_type": topic_type,
            "xml": xml_str,
            "filename": filename,
        })

    logger.info("Generated %d DITA topics", len(topics))
    return topics


# ---------------------------------------------------------------------------
# Public: generate_ditamap
# ---------------------------------------------------------------------------

def generate_ditamap(topics: list[dict], map_title: str = "Migrated Content") -> str:
    """Generate a ditamap XML string that references all generated topics."""
    root = ET.Element("map")
    title_el = ET.SubElement(root, "title")
    title_el.text = map_title

    for topic in topics:
        topicref = ET.SubElement(root, "topicref")
        topicref.set("href", topic["filename"])
        if topic.get("topic_type"):
            topicref.set("type", topic["topic_type"])

    xml_str = _xml_to_string(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n%s\n%s' % (DOCTYPE_MAP, xml_str)


# ---------------------------------------------------------------------------
# Public: migrate_content  (main entry point)
# ---------------------------------------------------------------------------

def migrate_content(content: str, source_format: str = "auto") -> dict:
    """Migrate content from Markdown/HTML/plain text to structured DITA topics.

    Returns:
        {
            "topics": [{"title": str, "topic_type": str, "xml": str, "filename": str}],
            "ditamap": str,
            "summary": {
                "total_topics": int,
                "by_type": {"task": int, "concept": int, "reference": int, "glossentry": int},
                "source_format": str,
                "sections_detected": int,
            },
            "migration_notes": [str],
        }
    """
    logger.info("Starting content migration (source_format=%s)", source_format)

    # Step 1: Parse and classify
    result = parse_and_classify(content, source_format)
    sections = result["sections"]
    fmt = result["source_format"]
    notes = list(result["migration_notes"])

    if not sections:
        return {
            "topics": [],
            "ditamap": "",
            "summary": {
                "total_topics": 0,
                "by_type": {"task": 0, "concept": 0, "reference": 0, "glossentry": 0},
                "source_format": fmt,
                "sections_detected": 0,
            },
            "migration_notes": notes,
        }

    # Step 2: Generate DITA topics
    topics = generate_dita_topics(sections)

    # Step 3: Generate ditamap
    # Use the first heading or a default title
    map_title = sections[0]["title"] if sections and sections[0]["title"] != "Untitled" else "Migrated Content"
    ditamap = generate_ditamap(topics, map_title=map_title)

    # Step 4: Build summary
    by_type = {"task": 0, "concept": 0, "reference": 0, "glossentry": 0}
    for topic in topics:
        tt = topic["topic_type"]
        if tt in by_type:
            by_type[tt] += 1

    summary = {
        "total_topics": len(topics),
        "by_type": by_type,
        "source_format": fmt,
        "sections_detected": len(sections),
    }

    logger.info(
        "Migration complete: %d topics (%s)",
        len(topics),
        ", ".join("%s=%d" % (k, v) for k, v in by_type.items() if v > 0),
    )

    return {
        "topics": topics,
        "ditamap": ditamap,
        "summary": summary,
        "migration_notes": notes,
    }
