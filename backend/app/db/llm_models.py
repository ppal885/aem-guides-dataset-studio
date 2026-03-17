"""Database models for LLM observability."""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, Text, Integer, DateTime

from app.db.base import Base


class LLMRun(Base):
    """LLM run for observability logging."""

    __tablename__ = "llm_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String(50), nullable=True)
    jira_id = Column(String(50), nullable=True)
    step_name = Column(String(100), nullable=False)
    prompt_version = Column(String(20), nullable=True)
    model = Column(String(100), nullable=True)
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, nullable=True)
    error_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
