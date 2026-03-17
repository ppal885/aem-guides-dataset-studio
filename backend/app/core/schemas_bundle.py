"""Pydantic schemas for bundle output."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BundleScenarioResult(BaseModel):
    scenario_id: str
    scenario_dir: str
    metadata_path: str = Field(default="metadata.json", description="Path to metadata.json relative to scenario_dir")
    recipes_executed: list[str] = Field(default_factory=list)
    validation_passed: bool = True
    warnings: list[str] = Field(default_factory=list)


class BundleManifest(BaseModel):
    jira_id: str
    run_id: str
    scenarios: list[BundleScenarioResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    stats: dict = Field(default_factory=dict)
    prompt_versions: dict = Field(default_factory=dict)
