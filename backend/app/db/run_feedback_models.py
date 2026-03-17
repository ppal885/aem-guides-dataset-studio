"""Database models for run feedback (validation errors, eval metrics) persistence."""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class RunFeedback(Base):
    """Run feedback record for validation errors and eval metrics."""

    __tablename__ = "run_feedback"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), nullable=True, index=True)
    jira_id = Column(String(50), nullable=True, index=True)
    scenario_id = Column(String(100), nullable=True, index=True)  # scenario that failed
    validation_errors = Column(Text, nullable=True)  # JSON array of error strings
    eval_metrics = Column(Text, nullable=True)  # JSON object of metrics
    suggested_updates = Column(Text, nullable=True)  # JSON object from feedback analysis
    user_rating = Column(String(20), nullable=True)  # thumbs_down | thumbs_up | wrong_recipe
    expected_recipe_id = Column(String(100), nullable=True)  # user-specified correct recipe
    suggested_recipe_id = Column(String(100), nullable=True)  # auto-suggested from validation failure analysis
    selected_feature = Column(String(50), nullable=True)  # mechanism_classifier output
    selected_pattern = Column(String(50), nullable=True)  # pattern_classifier output
    recipes_used = Column(Text, nullable=True)  # JSON array - always store for feedback
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
