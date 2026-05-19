"""Persistent store for UAC anti-repetition (recent scenario titles, drivers, questions per domain)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String

from app.db.base import Base


class UacAntiRepetitionMemory(Base):
    __tablename__ = "uac_anti_repetition_memory"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    domain = Column(String(120), nullable=False, index=True)
    jira_key = Column(String(48), nullable=False, index=True)
    scenario_titles = Column(JSON, nullable=False)
    risk_drivers = Column(JSON, nullable=False)
    clarification_questions = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=True)
