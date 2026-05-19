"""Chat-only saved bulk dataset presets (full job config for reuse from AI chat)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String, UniqueConstraint

from app.db.base import Base


class ChatBulkDatasetPreset(Base):
    """Snapshot of a dataset job config saved from chat after a bulk run (or job id)."""

    __tablename__ = "chat_bulk_dataset_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", "label", name="uq_chat_bulk_preset_user_tenant_label"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(120), nullable=False, index=True)
    tenant_id = Column(String(120), nullable=False, index=True)
    label = Column(String(200), nullable=False)
    source_job_id = Column(String(36), nullable=True, index=True)
    config = Column(JSON, nullable=False)
    runner_script_relpath = Column(String(500), nullable=True)
    jira_key = Column(String(32), nullable=True, index=True)
    classification = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
