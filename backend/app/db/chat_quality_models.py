"""Quality metrics for chat assistant answers (eval dashboard + self-learning)."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.db.base import Base


class ChatAnswerQuality(Base):
    """Per-assistant-message quality record derived from grounding and feedback."""

    __tablename__ = "chat_answer_quality"

    id = Column(String(36), primary_key=True)
    message_id = Column(
        String(36),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_message_id = Column(String(36), nullable=True, index=True)
    grounding_status = Column(String(30), nullable=False, default="none")
    confidence = Column(Float, nullable=True)
    thin_evidence = Column(Boolean, default=False, nullable=False)
    has_conflict = Column(Boolean, default=False, nullable=False)
    source_domain = Column(String(50), nullable=True)
    answer_kind = Column(String(80), nullable=True)
    source_policy = Column(String(80), nullable=True)
    quality_score = Column(Integer, nullable=False, default=50)
    weak_phrases_detected = Column(Boolean, default=False, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)
    review_status = Column(String(30), nullable=True)
    langsmith_run_id = Column(String(120), nullable=True)
    langsmith_trace_url = Column(String(500), nullable=True)
    improvement_hints_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
