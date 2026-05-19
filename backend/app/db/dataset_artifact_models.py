"""Index of completed dataset ZIPs keyed by content fingerprint + tenant."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.db.base import Base


class DatasetArtifactIndex(Base):
    """Maps (tenant_id, artifact_key) to a canonical completed dataset job id."""

    __tablename__ = "dataset_artifact_index"
    __table_args__ = (UniqueConstraint("tenant_id", "artifact_key", name="uq_dataset_artifact_tenant_key"),)

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(120), nullable=False, index=True)
    artifact_key = Column(String(64), nullable=False)
    source_job_id = Column(String(36), nullable=False, index=True)
    created_by_user_id = Column(String(120), nullable=False)
    recipe_summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="completed")
    hit_count = Column(Integer, nullable=False, default=0)
    last_hit_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
