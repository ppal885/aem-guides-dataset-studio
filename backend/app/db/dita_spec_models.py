"""Database models for DITA spec indexing."""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from backend.app.db.base import Base


class DitaSpecChunk(Base):
    """DITA specification chunk for RAG retrieval."""

    __tablename__ = "dita_spec_chunks"

    id = Column(String(36), primary_key=True)
    element_name = Column(String(100), nullable=True, index=True)
    content_type = Column(String(50), nullable=True)
    parent_element = Column(String(100), nullable=True)
    children_elements = Column(Text, nullable=True)
    attributes = Column(Text, nullable=True)
    text_content = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
