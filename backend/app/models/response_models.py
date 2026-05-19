"""FastAPI request/response models for the enterprise QA copilot."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.jira_models import (
    AutomationFit,
    AutomationScenario,
    CommonPattern,
    GroundingReport,
    JiraIssueSearchResult,
    UacPoint,
)
from app.models.tool_models import ExtractedEntities, ToolExecutionRecord


class QaCopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    limit: int = Field(default=10, ge=1, le=25)
    include_debug: bool = False


class QaCopilotChatResponse(BaseModel):
    query: str
    entities: ExtractedEntities
    tool_calls: list[ToolExecutionRecord] = Field(default_factory=list)
    retrieved_issues: list[JiraIssueSearchResult] = Field(default_factory=list)
    patterns: list[CommonPattern] = Field(default_factory=list)
    automation_scenarios: list[AutomationScenario] = Field(default_factory=list)
    uac_points: list[UacPoint] = Field(default_factory=list)
    automation_fit: AutomationFit | None = None
    final_response: str
    grounding: GroundingReport = Field(default_factory=GroundingReport)
    observability: dict[str, Any] = Field(default_factory=dict)
    debug: dict[str, Any] | None = None

