"""Database models for AI chat sessions and messages."""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey

from app.db.base import Base


class ChatSession(Base):
    """Chat session - groups messages into a conversation."""

    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True)
    title = Column(String(500), nullable=True)  # Auto from first message
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ChatMessage(Base):
    """Chat message - user or assistant message with optional tool calls/results."""

    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=True)  # Message text
    tool_calls = Column(Text, nullable=True)  # JSON array of tool call objects
    tool_results = Column(Text, nullable=True)  # JSON object: tool_name -> result
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
