"""Chunk metadata extraction pipeline.

Extracts rich structural metadata from DITA XML, crawled HTML pages,
and Jira issues during indexing.

Feature flag: CHUNK_METADATA_ENABLED (default False)
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.models.chunk_metadata import ChunkMetadata, DocType, RegionType, SourceType


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect_doc_type(content: str, file_path: str = "") -> DocType:
    """Detect DITA document type from content and file path."""
    lower = content[:2000].lower()
    path_lower = file_path.lower()

    if path_lower.endswith(".ditamap"):
        if "<bookmap" in lower:
            return DocType.BOOKMAP
        return DocType.MAP
    if path_lower.endswith(".ditaval"):
        return DocType.DITAVAL

    # Check root element
    if "<task" in lower and ("<!DOCTYPE task" in content[:500] or "<taskbody" in lower):
        return DocType.TOPIC
    if "<concept" in lower and ("<!DOCTYPE concept" in content[:500] or "<conbody" in lower):
        return DocType.TOPIC
    if "<reference" in lower and ("<!DOCTYPE reference" in content[:500] or "<refbody" in lower):
        return DocType.TOPIC
    if "<topic" in lower:
        return DocType.TOPIC
    if "<glossentry" in lower:
        return DocType.GLOSSENTRY
    if "<subjectScheme" in lower or "<subjectscheme" in lower:
        return DocType.SUBJECT_SCHEME
    if "<map" in lower and "<keydef" in lower:
        return DocType.KEYDEF_MAP
    if "<map" in lower or "<bookmap" in lower:
        return DocType.MAP

    return DocType.UNKNOWN


def _detect_region_type(content: str, element_name: str = "") -> RegionType:
    """Detect the semantic region of a chunk."""
    lower = content[:1000].lower()

    if element_name in ("title", "searchtitle"):
        return RegionType.TITLE
    if element_name == "shortdesc":
        return RegionType.SHORTDESC
    if element_name in ("taskbody", "conbody", "refbody", "body"):
        return RegionType.BODY
    if element_name == "prereq":
        return RegionType.PREREQ
    if element_name in ("steps", "steps-unordered"):
        return RegionType.STEPS
    if element_name == "result":
        return RegionType.RESULT
    if element_name == "example":
        return RegionType.EXAMPLE
    if element_name in ("table", "simpletable", "choicetable"):
        return RegionType.TABLE
    if element_name == "codeblock":
        return RegionType.CODEBLOCK
    if element_name == "note":
        return RegionType.NOTE
    if element_name == "related-links":
        return RegionType.RELATED_LINKS
    if element_name == "prolog":
        return RegionType.PROLOG

    # Fallback: detect from content
    if "<steps" in lower or "<step>" in lower:
        return RegionType.STEPS
    if "<table" in lower or "<simpletable" in lower:
        return RegionType.TABLE
    if "<codeblock" in lower:
        return RegionType.CODEBLOCK
    if "<note" in lower:
        return RegionType.NOTE

    return RegionType.UNKNOWN


def _extract_element_name(content: str) -> str:
    """Extract the root element name from XML content."""
    # Skip XML declaration and DOCTYPE
    stripped = re.sub(r"<\?xml[^>]*\?>", "", content[:500]).strip()
    stripped = re.sub(r"<!DOCTYPE[^>]*>", "", stripped).strip()
    m = re.match(r"<(\w[\w.-]*)", stripped)
    return m.group(1) if m else ""


def _extract_topic_id(content: str) -> Optional[str]:
    """Extract the @id from the root element."""
    m = re.search(r'<\w+[^>]*\bid=["\']([^"\']+)["\']', content[:500])
    return m.group(1) if m else None


def _extract_title(content: str) -> Optional[str]:
    """Extract the first <title> text."""
    m = re.search(r"<title[^>]*>(.*?)</title>", content[:2000], re.DOTALL)
    if m:
        # Strip inner XML tags
        title_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return title_text if title_text else None
    return None


def _extract_conrefs(content: str) -> list[str]:
    """Extract conref target paths."""
    return re.findall(r'conref=["\']([^"\']+)["\']', content)


def _extract_keyrefs(content: str) -> list[str]:
    """Extract keyref references."""
    return re.findall(r'keyref=["\']([^"\']+)["\']', content)


def _extract_keydefs(content: str) -> list[str]:
    """Extract keys defined by keydef elements."""
    return re.findall(r'<keydef\s+keys=["\']([^"\']+)["\']', content)


def _extract_xrefs(content: str) -> list[str]:
    """Extract xref href targets."""
    return re.findall(r'<xref\s+[^>]*href=["\']([^"\']+)["\']', content)


def _determine_priority(doc_type: DocType, region_type: RegionType, element_name: str) -> float:
    """Assign retrieval priority based on content characteristics."""
    base = 0.5

    # Maps and structure get higher priority
    if doc_type == DocType.MAP:
        base = 0.7
    elif doc_type == DocType.KEYDEF_MAP:
        base = 0.8
    elif doc_type == DocType.SUBJECT_SCHEME:
        base = 0.7

    # Certain regions are more important
    if region_type == RegionType.STEPS:
        base = max(base, 0.7)
    elif region_type == RegionType.TABLE:
        base = max(base, 0.6)
    elif region_type == RegionType.TITLE:
        base = max(base, 0.65)
    elif region_type == RegionType.SHORTDESC:
        base = max(base, 0.6)

    return min(1.0, base)


def _needs_context_bundle(doc_type: DocType, region_type: RegionType, content: str) -> bool:
    """Determine if this chunk requires surrounding context for meaning."""
    # Tables without headers are meaningless alone
    if region_type == RegionType.TABLE:
        return True
    # Steps often need prereq and result
    if region_type in (RegionType.STEPS, RegionType.RESULT, RegionType.PREREQ):
        return True
    # Code blocks need surrounding explanation
    if region_type == RegionType.CODEBLOCK:
        return True
    # Short chunks that reference other content
    if len(content) < 200 and ("<xref" in content or "<conref" in content.lower()):
        return True
    return False


# ── Public extraction functions ──


def extract_metadata_from_dita_xml(
    content: str,
    file_path: str = "",
    *,
    parent_chunk_id: Optional[str] = None,
    root_doc_id: Optional[str] = None,
    depth: int = 0,
) -> ChunkMetadata:
    """Extract rich metadata from DITA XML content."""
    chunk_id = str(uuid4())
    doc_type = _detect_doc_type(content, file_path)
    element_name = _extract_element_name(content)
    region_type = _detect_region_type(content, element_name)
    topic_id = _extract_topic_id(content)
    title = _extract_title(content)
    conrefs = _extract_conrefs(content)
    keyrefs = _extract_keyrefs(content)
    keydefs = _extract_keydefs(content)
    xrefs = _extract_xrefs(content)
    priority = _determine_priority(doc_type, region_type, element_name)
    needs_bundle = _needs_context_bundle(doc_type, region_type, content)

    return ChunkMetadata(
        chunk_id=chunk_id,
        content_hash=_sha256(content),
        doc_type=doc_type,
        root_doc_id=root_doc_id,
        parent_chunk_id=parent_chunk_id,
        depth_level=depth,
        element_name=element_name,
        element_path=f"{element_name}" if element_name else "",
        section_title=title,
        topic_id=topic_id,
        region_type=region_type,
        is_standalone=not needs_bundle,
        requires_context_bundle=needs_bundle,
        conref_source_ids=[],  # Resolved later during graph build
        conref_target_ids=[],
        keyref_keys=keyrefs,
        keydef_keys=keydefs,
        xref_target_ids=[],  # Resolved later
        source_url=file_path or None,
        source_type=SourceType.SEED,
        chunk_priority=priority,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


def extract_metadata_from_crawled_page(
    content: str,
    url: str = "",
    title: str = "",
) -> ChunkMetadata:
    """Extract metadata from a crawled AEM Guides documentation page."""
    chunk_id = str(uuid4())
    # Crawled pages are typically AEM docs
    doc_type = DocType.AEM_DOC

    return ChunkMetadata(
        chunk_id=chunk_id,
        content_hash=_sha256(content),
        doc_type=doc_type,
        element_name="page",
        section_title=title or None,
        region_type=RegionType.BODY,
        is_standalone=True,
        requires_context_bundle=False,
        source_url=url or None,
        source_type=SourceType.CRAWL,
        chunk_priority=0.5,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


def extract_metadata_from_jira(
    content: str,
    issue_key: str = "",
    attachment_id: Optional[str] = None,
) -> ChunkMetadata:
    """Extract metadata from a Jira issue or attachment."""
    chunk_id = str(uuid4())

    return ChunkMetadata(
        chunk_id=chunk_id,
        content_hash=_sha256(content),
        doc_type=DocType.JIRA_ISSUE,
        element_name="jira_issue",
        region_type=RegionType.FULL_TOPIC,
        is_standalone=True,
        requires_context_bundle=False,
        source_type=SourceType.JIRA,
        jira_issue_key=issue_key or None,
        jira_attachment_id=attachment_id,
        chunk_priority=0.6,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )
