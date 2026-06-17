"""Database model for learned prompt-answer corpus entries."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.base import Base


class LearnedPromptEntry(Base):
    """Reviewed or candidate prompt-answer item for learned QA retrieval."""

    __tablename__ = "learned_prompt_entries"

    id = Column(String(36), primary_key=True)
    prompt = Column(Text, nullable=False)
    normalized_prompt = Column(Text, nullable=False)
    prompt_hash = Column(String(64), nullable=False, index=True)
    final_answer = Column(Text, nullable=False)
    tags_json = Column(Text, nullable=True)
    topic = Column(String(120), nullable=True, index=True)
    source_type = Column(String(50), nullable=False, default="chat_feedback")
    answer_style = Column(String(100), nullable=False, default="senior_technical_docs")
    status = Column(String(30), nullable=False, default="pending_review", index=True)
    accepted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    session_id = Column(String(36), nullable=True, index=True)
    message_id = Column(String(36), nullable=True, index=True)
    support_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
