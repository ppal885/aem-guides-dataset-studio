"""Database models for jobs."""
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, JSON
from datetime import datetime
import uuid
from enum import Enum
from app.db.base import Base


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """Job model for dataset generation tasks."""
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending, running, completed, failed
    config = Column(JSON, nullable=False)  # Job configuration
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)  # Job results
    progress_percent = Column(Integer, nullable=True)  # Progress percentage (0-100)
    files_generated = Column(Integer, nullable=True)  # Current number of files generated
    total_files_estimated = Column(Integer, nullable=True)  # Estimated total files
    current_stage = Column(String, nullable=True)  # Current generation stage
    
    def __repr__(self):
        return f"<Job(id={self.id}, name={self.name}, status={self.status})>"


class SavedRecipe(Base):
    """Saved recipe configuration for reuse."""
    __tablename__ = "saved_recipes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    recipe_config = Column(JSON, nullable=False)  # The recipe configuration
    user_id = Column(String, nullable=False, index=True)
    is_public = Column(Boolean, default=False, nullable=False)  # Can be shared with others
    tags = Column(JSON, default=list, nullable=True)  # Tags for categorization
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f"<SavedRecipe(id={self.id}, name={self.name}, user_id={self.user_id})>"
