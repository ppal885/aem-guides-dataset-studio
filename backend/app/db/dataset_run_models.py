"""Database models for dataset run tracking."""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class DatasetRun(Base):
    """Dataset run record for search and discovery."""

    __tablename__ = "dataset_runs"

    id = Column(String(36), primary_key=True)
    jira_id = Column(String(50), nullable=False, index=True)
    scenario_type = Column(String(50), nullable=True, index=True)
    recipes_used = Column(Text, nullable=True)  # JSON array of recipe ids
    bundle_zip = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
