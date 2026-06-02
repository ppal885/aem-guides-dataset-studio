"""Data models for hierarchical retrieval chunk metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DocType(str, Enum):
    TOPIC = "topic"
    MAP = "map"
    BOOKMAP = "bookmap"
    DITAVAL = "ditaval"
    GLOSSENTRY = "glossentry"
    SUBJECT_SCHEME = "subject_scheme"
    KEYDEF_MAP = "keydef_map"
    AEM_DOC = "aem_doc"
    JIRA_ISSUE = "jira_issue"
    UNKNOWN = "unknown"


class RegionType(str, Enum):
    TITLE = "title"
    SHORTDESC = "shortdesc"
    BODY = "body"
    PREREQ = "prereq"
    STEPS = "steps"
    RESULT = "result"
    EXAMPLE = "example"
    TABLE = "table"
    CODEBLOCK = "codeblock"
    NOTE = "note"
    RELATED_LINKS = "related_links"
    PROLOG = "prolog"
    FULL_TOPIC = "full_topic"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    SEED = "seed"
    CRAWL = "crawl"
    JIRA = "jira"
    UPLOAD = "upload"
    UNKNOWN = "unknown"


@dataclass
class ChunkMetadata:
    chunk_id: str = ""
    source_type: SourceType = SourceType.CRAWL
    doc_type: DocType = DocType.UNKNOWN
    chunk_priority: float = 0.5
    content_hash: Optional[str] = None
    parent_chunk_id: Optional[str] = None
    child_chunk_ids: list[str] = field(default_factory=list)
    conref_source_ids: list[str] = field(default_factory=list)
    keydef_ids: list[str] = field(default_factory=list)
    sibling_prev_id: Optional[str] = None
    sibling_next_id: Optional[str] = None
    requires_context_bundle: bool = False
    source_url: Optional[str] = None
    title: Optional[str] = None
    element_name: Optional[str] = None
    section_title: Optional[str] = None
    root_doc_id: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.doc_type, str):
            try:
                self.doc_type = DocType(self.doc_type)
            except ValueError:
                self.doc_type = DocType.UNKNOWN


@dataclass
class ScoredChunk:
    chunk_id: str
    content: str
    metadata: ChunkMetadata
    semantic_similarity: float = 0.0
    authority_score: float = 0.5
    structural_relevance: float = 0.0
    final_score: float = 0.0
    relationship_type: Optional[str] = None


@dataclass
class RetrievalBundle:
    query: str = ""
    primary_chunks: list[ScoredChunk] = field(default_factory=list)
    context_chunks: list[ScoredChunk] = field(default_factory=list)
    relationships_used: list[str] = field(default_factory=list)
    total_tokens: int = 0
    root_docs: list[str] = field(default_factory=list)
