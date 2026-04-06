"""SQLAlchemy models for chunk metadata — rich structural metadata alongside embeddings.

This extends the existing vector store with DITA-aware metadata columns
so retrieval can filter and expand by document structure.

Feature flag: CHUNK_METADATA_ENABLED (default False)
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class ChunkWithMetadata(Base):
    """Chunk with rich structural metadata for hierarchical retrieval."""

    __tablename__ = "chunks_with_metadata"

    chunk_id = Column(String(36), primary_key=True)
    content = Column(Text, nullable=False, default="")
    content_hash = Column(String(64), nullable=False, default="", index=True)

    # Document structure
    doc_type = Column(String(30), nullable=False, default="unknown", index=True)
    root_doc_id = Column(String(36), nullable=True, index=True)
    parent_chunk_id = Column(String(36), nullable=True, index=True)
    child_chunk_ids = Column(JSONB, nullable=False, default=list)
    sibling_prev_id = Column(String(36), nullable=True)
    sibling_next_id = Column(String(36), nullable=True)
    depth_level = Column(Integer, nullable=False, default=0)

    # DITA element info
    element_name = Column(String(100), nullable=False, default="", index=True)
    element_path = Column(Text, nullable=False, default="")
    section_title = Column(Text, nullable=True)
    topic_id = Column(String(200), nullable=True)

    # Semantic region
    region_type = Column(String(30), nullable=False, default="unknown")
    is_standalone = Column(Boolean, nullable=False, default=True)
    requires_context_bundle = Column(Boolean, nullable=False, default=False)

    # DITA relationships (JSONB arrays for GIN index support)
    conref_source_ids = Column(JSONB, nullable=False, default=list)
    conref_target_ids = Column(JSONB, nullable=False, default=list)
    keyref_keys = Column(JSONB, nullable=False, default=list)
    keydef_keys = Column(JSONB, nullable=False, default=list)
    xref_target_ids = Column(JSONB, nullable=False, default=list)
    subject_scheme_bindings = Column(JSONB, nullable=False, default=list)

    # Source provenance
    source_url = Column(Text, nullable=True)
    source_type = Column(String(20), nullable=False, default="seed")
    jira_issue_key = Column(String(50), nullable=True, index=True)
    jira_attachment_id = Column(String(100), nullable=True)

    # Recipe & generation
    recipe_tags = Column(JSONB, nullable=False, default=list)

    # Retrieval hints
    chunk_priority = Column(Float, nullable=False, default=0.5)
    validation_rules = Column(JSONB, nullable=False, default=list)

    # Timestamps
    indexed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_modified_at = Column(DateTime, nullable=True)

    # Embedding — stored as JSONB (list of floats) for portability.
    # When PGVector extension is available, migrate to vector(384) column.
    embedding_json = Column(JSONB, nullable=True)

    # Indexes for hierarchical retrieval
    __table_args__ = (
        Index("ix_chunks_doc_type_element", "doc_type", "element_name"),
        Index("ix_chunks_parent", "parent_chunk_id"),
        Index("ix_chunks_root_doc", "root_doc_id"),
        Index("ix_chunks_content_hash", "content_hash"),
        # GIN indexes on JSONB arrays for containment queries
        Index("ix_chunks_keydef_keys_gin", "keydef_keys", postgresql_using="gin"),
        Index("ix_chunks_keyref_keys_gin", "keyref_keys", postgresql_using="gin"),
        Index("ix_chunks_conref_source_gin", "conref_source_ids", postgresql_using="gin"),
        Index("ix_chunks_recipe_tags_gin", "recipe_tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<ChunkWithMetadata {self.chunk_id} doc_type={self.doc_type} element={self.element_name}>"
