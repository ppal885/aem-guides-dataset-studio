"""Convert HTML fragments (from scraped pages) to valid DITA topics.

Maps paragraphs, list items, codeph, codeblocks to DITA elements.
Uses xml_escape for all text. Validates output before returning.
"""
import xml.etree.ElementTree as ET
from typing import Optional

from app.utils.xml_escape import xml_escape_text
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DEFAULT_DOCTYPE_TOPIC = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'
MAX_PARAGRAPH_CHARS = 10000
MAX_LIST_ITEM_CHARS = 5000
MAX_CODEPH_CHARS = 500
MAX_CODEBLOCK_CHARS = 8000
MAX_TABLE_ROWS = 50
MAX_TABLE_CELL_CHARS = 2000


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, preserving word boundaries."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars].rsplit(" ", 1)[0] + "..." if " " in text[:max_chars] else text[:max_chars] + "..."


def html_fragments_to_dita_topic(
    fragments: dict,
    topic_id: str,
    title: str,
    doctype_topic: str = DEFAULT_DOCTYPE_TOPIC,
) -> Optional[bytes]:
    """
    Build a valid DITA topic from scraped HTML fragments.

    Args:
        fragments: {paragraphs: [...], list_items: [...], codeph: [...], codeblocks: [...], tables: [[[cell,...],...],...]}
        topic_id: DITA topic id attribute
        title: Topic title text
        doctype_topic: DOCTYPE declaration string

    Returns:
        UTF-8 bytes of valid DITA topic, or None if invalid.
    """
    paragraphs = fragments.get("paragraphs") or []
    list_items = fragments.get("list_items") or []
    codeph = fragments.get("codeph") or []
    codeblocks = fragments.get("codeblocks") or []
    tables = fragments.get("tables") or []

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = xml_escape_text(_truncate(title or "Untitled", 200))

    body = ET.SubElement(topic, "body")
    section = ET.SubElement(body, "section")

    for p in paragraphs[:50]:
        text = _truncate(p, MAX_PARAGRAPH_CHARS)
        if not text.strip():
            continue
        p_elem = ET.SubElement(section, "p")
        p_elem.text = xml_escape_text(text)

    if list_items:
        ul = ET.SubElement(section, "ul")
        for li_text in list_items[:100]:
            text = _truncate(li_text, MAX_LIST_ITEM_CHARS)
            if not text.strip():
                continue
            li = ET.SubElement(ul, "li")
            li.text = xml_escape_text(text)

    for c in codeph[:20]:
        text = _truncate(c, MAX_CODEPH_CHARS)
        if not text.strip():
            continue
        p_wrap = ET.SubElement(section, "p")
        codeph_elem = ET.SubElement(p_wrap, "codeph")
        codeph_elem.text = xml_escape_text(text)

    for cb in codeblocks[:10]:
        text = _truncate(cb, MAX_CODEBLOCK_CHARS)
        if not text.strip():
            continue
        p_intro = ET.SubElement(section, "p")
        p_intro.text = "Code example:"
        codeblock = ET.SubElement(section, "codeblock", {"xml:space": "preserve"})
        codeblock.text = xml_escape_text(text)

    for tbl in tables[:5]:
        if not isinstance(tbl, list) or len(tbl) == 0:
            continue
        first_row = tbl[0] if tbl else []
        num_cols = len(first_row) if isinstance(first_row, list) else 0
        if num_cols == 0:
            continue
        simpletable = ET.SubElement(section, "simpletable")
        simpletable.set("relcolwidth", " ".join(["1*"] * min(num_cols, 20)))
        for row_idx, row in enumerate(tbl[:MAX_TABLE_ROWS]):
            if not isinstance(row, list):
                continue
            strow = ET.SubElement(simpletable, "strow")
            for cell in row[:20]:
                stentry = ET.SubElement(strow, "stentry")
                cell_text = _truncate(str(cell) if cell is not None else "", MAX_TABLE_CELL_CHARS)
                stentry.text = xml_escape_text(cell_text) if cell_text.strip() else None

    try:
        xml_bytes = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    except Exception as e:
        logger.warning_structured(
            "html_to_dita: tostring failed",
            extra_fields={"topic_id": topic_id, "error": str(e)},
        )
        return None

    try:
        ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning_structured(
            "html_to_dita: parse validation failed",
            extra_fields={"topic_id": topic_id, "error": str(e)},
        )
        return None

    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype_topic}\n'
    return doc.encode("utf-8") + xml_bytes
