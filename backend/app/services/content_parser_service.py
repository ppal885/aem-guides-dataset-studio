"""Content parser service - converts Markdown, HTML, and plain text into a
structured intermediate representation of ContentBlock objects."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


# ---------------------------------------------------------------------------
# Intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    """A single structural block parsed from source content."""
    block_type: str  # heading, paragraph, ordered_list, unordered_list, code_block, table, image
    content: str = ""
    level: int = 0  # heading level 1-6 or list nesting depth
    children: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"ContentBlock(type={self.block_type!r}, level={self.level}, "
            f"content={self.content[:60]!r}{'...' if len(self.content) > 60 else ''})"
        )


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_MD_ORDERED_ITEM = re.compile(r"^(\s*)\d+[.)]\s+(.+)$")
_MD_UNORDERED_ITEM = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_MD_CODE_FENCE = re.compile(r"^```(\w*)$")
_MD_TABLE_SEP = re.compile(r"^\|?\s*[-:]+[-|:\s]+$")
_MD_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")


def parse_markdown(text: str) -> List[ContentBlock]:
    """Parse Markdown text into a list of ContentBlock objects."""
    blocks: List[ContentBlock] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # --- Code fence ---
        m = _MD_CODE_FENCE.match(line.strip())
        if m:
            lang = m.group(1)
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _MD_CODE_FENCE.match(lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            blocks.append(ContentBlock(
                block_type="code_block",
                content="\n".join(code_lines),
                metadata={"language": lang} if lang else {},
            ))
            i += 1  # skip closing fence
            continue

        # --- Heading ---
        m = _MD_HEADING.match(line.strip())
        if m:
            blocks.append(ContentBlock(
                block_type="heading",
                content=m.group(2).strip(),
                level=len(m.group(1)),
            ))
            i += 1
            continue

        # --- Table ---
        m = _MD_TABLE_ROW.match(line.strip())
        if m:
            table_rows: list[list[str]] = []
            while i < len(lines):
                row_line = lines[i].strip()
                if _MD_TABLE_SEP.match(row_line):
                    i += 1
                    continue
                row_m = _MD_TABLE_ROW.match(row_line)
                if row_m:
                    cells = [c.strip() for c in row_m.group(1).split("|")]
                    table_rows.append(cells)
                    i += 1
                else:
                    break
            if table_rows:
                blocks.append(ContentBlock(
                    block_type="table",
                    content=str(table_rows),
                    metadata={"rows": table_rows, "header": table_rows[0] if table_rows else []},
                ))
            continue

        # --- Ordered list ---
        m = _MD_ORDERED_ITEM.match(line)
        if m:
            items: list[str] = []
            indent_base = len(m.group(1))
            while i < len(lines):
                om = _MD_ORDERED_ITEM.match(lines[i])
                if om and len(om.group(1)) == indent_base:
                    items.append(om.group(2).strip())
                    i += 1
                elif lines[i].strip() == "":
                    i += 1
                    break
                else:
                    break
            blocks.append(ContentBlock(
                block_type="ordered_list",
                content="\n".join(items),
                children=items,
                level=1,
            ))
            continue

        # --- Unordered list ---
        m = _MD_UNORDERED_ITEM.match(line)
        if m:
            items = []
            indent_base = len(m.group(1))
            while i < len(lines):
                um = _MD_UNORDERED_ITEM.match(lines[i])
                if um and len(um.group(1)) == indent_base:
                    items.append(um.group(2).strip())
                    i += 1
                elif lines[i].strip() == "":
                    i += 1
                    break
                else:
                    break
            blocks.append(ContentBlock(
                block_type="unordered_list",
                content="\n".join(items),
                children=items,
                level=1,
            ))
            continue

        # --- Image (standalone) ---
        m = _MD_IMAGE.match(line.strip())
        if m:
            blocks.append(ContentBlock(
                block_type="image",
                content=m.group(1),
                metadata={"src": m.group(2), "alt": m.group(1)},
            ))
            i += 1
            continue

        # --- Paragraph (collect contiguous non-empty lines) ---
        if line.strip():
            para_lines: list[str] = []
            while i < len(lines) and lines[i].strip() and not _MD_HEADING.match(lines[i].strip()):
                # stop if the next line starts a different structure
                if (_MD_ORDERED_ITEM.match(lines[i]) or
                        _MD_UNORDERED_ITEM.match(lines[i]) or
                        _MD_CODE_FENCE.match(lines[i].strip()) or
                        _MD_TABLE_ROW.match(lines[i].strip()) or
                        _MD_IMAGE.match(lines[i].strip())):
                    break
                para_lines.append(lines[i].strip())
                i += 1
            if para_lines:
                blocks.append(ContentBlock(
                    block_type="paragraph",
                    content=" ".join(para_lines),
                ))
            continue

        i += 1  # skip blank lines

    logger.info("Parsed %d blocks from Markdown input", len(blocks))
    return blocks


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

class _HTMLBlockParser(HTMLParser):
    """Simple HTML parser that produces ContentBlock objects."""

    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    LIST_TAGS = {"ol", "ul"}
    INLINE_TAGS = {"strong", "em", "b", "i", "a", "code", "span"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: List[ContentBlock] = []
        self._tag_stack: list[str] = []
        self._text_buf: list[str] = []
        self._list_items: list[str] = []
        self._list_type: Optional[str] = None
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._in_code_block = False
        self._code_buf: list[str] = []
        self._current_link: Optional[str] = None
        self._current_img: Optional[dict] = None

    # -- helpers --
    def _flush_text(self) -> str:
        text = "".join(self._text_buf).strip()
        self._text_buf.clear()
        return text

    # -- handler overrides --
    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        attr_dict = dict(attrs)
        self._tag_stack.append(tag)

        if tag in ("pre", "code") and "pre" in self._tag_stack[:-1] or tag == "pre":
            self._in_code_block = True
            self._code_buf.clear()
        elif tag in self.LIST_TAGS:
            self._list_type = "ordered_list" if tag == "ol" else "unordered_list"
            self._list_items = []
        elif tag == "li":
            self._text_buf.clear()
        elif tag == "table":
            self._table_rows = []
        elif tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._text_buf.clear()
        elif tag == "a":
            self._current_link = attr_dict.get("href", "")
        elif tag == "img":
            self.blocks.append(ContentBlock(
                block_type="image",
                content=attr_dict.get("alt", ""),
                metadata={"src": attr_dict.get("src", ""), "alt": attr_dict.get("alt", "")},
            ))
        elif tag in self.HEADING_TAGS:
            self._text_buf.clear()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "pre":
            code = "".join(self._code_buf).strip()
            self.blocks.append(ContentBlock(block_type="code_block", content=code))
            self._in_code_block = False
            self._code_buf.clear()
        elif tag in self.HEADING_TAGS:
            text = self._flush_text()
            if text:
                level = int(tag[1])
                self.blocks.append(ContentBlock(block_type="heading", content=text, level=level))
        elif tag == "li":
            text = self._flush_text()
            self._list_items.append(text)
        elif tag in self.LIST_TAGS and self._list_type:
            self.blocks.append(ContentBlock(
                block_type=self._list_type,
                content="\n".join(self._list_items),
                children=list(self._list_items),
                level=1,
            ))
            self._list_type = None
            self._list_items = []
        elif tag in ("td", "th"):
            self._current_row.append(self._flush_text())
        elif tag == "tr":
            if self._current_row:
                self._table_rows.append(list(self._current_row))
            self._current_row = []
        elif tag == "table":
            if self._table_rows:
                self.blocks.append(ContentBlock(
                    block_type="table",
                    content=str(self._table_rows),
                    metadata={"rows": self._table_rows, "header": self._table_rows[0] if self._table_rows else []},
                ))
            self._table_rows = []
        elif tag == "p":
            text = self._flush_text()
            if text:
                self.blocks.append(ContentBlock(block_type="paragraph", content=text))
        elif tag == "a":
            self._current_link = None

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_code_block:
            self._code_buf.append(data)
        else:
            self._text_buf.append(data)


def parse_html(text: str) -> List[ContentBlock]:
    """Parse HTML text into a list of ContentBlock objects."""
    parser = _HTMLBlockParser()
    parser.feed(text)
    # Capture any trailing text not in a tag as a paragraph
    trailing = parser._flush_text()
    if trailing:
        parser.blocks.append(ContentBlock(block_type="paragraph", content=trailing))
    logger.info("Parsed %d blocks from HTML input", len(parser.blocks))
    return parser.blocks


# ---------------------------------------------------------------------------
# Plain text parser
# ---------------------------------------------------------------------------

_PT_NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.+)$")
_PT_BULLET = re.compile(r"^\s*[-*\u2022]\s+(.+)$")
_PT_HEADING_UPPER = re.compile(r"^[A-Z][A-Z\s:]{2,}$")
_PT_HEADING_COLON = re.compile(r"^(.{3,60}):$")


def parse_plain_text(text: str) -> List[ContentBlock]:
    """Parse plain text into ContentBlock objects by detecting structural patterns."""
    blocks: List[ContentBlock] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # --- Numbered list ---
        m = _PT_NUMBERED.match(line)
        if m:
            items: list[str] = []
            while i < len(lines):
                nm = _PT_NUMBERED.match(lines[i])
                if nm:
                    items.append(nm.group(2).strip())
                    i += 1
                elif lines[i].strip() == "":
                    i += 1
                    break
                else:
                    break
            blocks.append(ContentBlock(
                block_type="ordered_list",
                content="\n".join(items),
                children=items,
                level=1,
            ))
            continue

        # --- Bullet list ---
        m = _PT_BULLET.match(line)
        if m:
            items = []
            while i < len(lines):
                bm = _PT_BULLET.match(lines[i])
                if bm:
                    items.append(bm.group(1).strip())
                    i += 1
                elif lines[i].strip() == "":
                    i += 1
                    break
                else:
                    break
            blocks.append(ContentBlock(
                block_type="unordered_list",
                content="\n".join(items),
                children=items,
                level=1,
            ))
            continue

        # --- Heading-like line (all caps or ends with colon and short) ---
        if _PT_HEADING_UPPER.match(stripped):
            blocks.append(ContentBlock(
                block_type="heading",
                content=stripped.title(),
                level=1,
            ))
            i += 1
            continue

        colon_m = _PT_HEADING_COLON.match(stripped)
        if colon_m and len(stripped) < 60:
            blocks.append(ContentBlock(
                block_type="heading",
                content=colon_m.group(1).strip(),
                level=2,
            ))
            i += 1
            continue

        # --- Paragraph ---
        para_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            if (_PT_NUMBERED.match(lines[i]) or
                    _PT_BULLET.match(lines[i]) or
                    _PT_HEADING_UPPER.match(lines[i].strip())):
                break
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            blocks.append(ContentBlock(
                block_type="paragraph",
                content=" ".join(para_lines),
            ))

    logger.info("Parsed %d blocks from plain text input", len(blocks))
    return blocks


# ---------------------------------------------------------------------------
# Format detection and unified entry point
# ---------------------------------------------------------------------------

_HTML_TAG_PATTERN = re.compile(r"<\s*(html|head|body|div|p|h[1-6]|ul|ol|table|br|img|a)\b", re.IGNORECASE)
_MD_INDICATORS = re.compile(r"(^#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s|```|\*\*.+\*\*|\[.+\]\(.+\)|\!\[)", re.MULTILINE)


def detect_format(text: str) -> str:
    """Return 'markdown', 'html', or 'plain_text' based on content heuristics."""
    if not text or not text.strip():
        return "plain_text"

    html_matches = len(_HTML_TAG_PATTERN.findall(text))
    md_matches = len(_MD_INDICATORS.findall(text))

    if html_matches >= 2:
        return "html"
    if md_matches >= 2:
        return "markdown"
    if html_matches == 1 and md_matches == 0:
        return "html"
    if md_matches == 1 and html_matches == 0:
        return "markdown"

    return "plain_text"


def parse_content(text: str) -> List[ContentBlock]:
    """Auto-detect the input format and parse into ContentBlock objects."""
    fmt = detect_format(text)
    logger.info("Auto-detected content format: %s", fmt)

    if fmt == "markdown":
        return parse_markdown(text)
    elif fmt == "html":
        return parse_html(text)
    else:
        return parse_plain_text(text)
