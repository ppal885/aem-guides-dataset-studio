"""Jira, pattern, UAC, and automation response models for QA copilot."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JiraIssueSearchResult(BaseModel):
    issue_key: str
    summary: str = ""
    customer: str | None = None
    feature: str | None = None
    labels: list[str] = Field(default_factory=list)
    issue_type: str | None = None
    component: str | None = None
    environment: str | None = None
    similarity_score: float = 0.0
    matched_snippet: str = ""
    resolution: str | None = None
    root_cause_summary: str | None = None
    why_relevant: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class JiraIssueDetails(BaseModel):
    issue_key: str
    summary: str = ""
    description: str = ""
    comments_summary: str = ""
    linked_issues: list[str] = Field(default_factory=list)
    regression_patterns: list[str] = Field(default_factory=list)
    root_cause: str | None = None
    affected_areas: list[str] = Field(default_factory=list)
    impacted_customers: list[str] = Field(default_factory=list)
    qa_notes: str = ""
    automation_notes: str = ""
    evidence_chunks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommonPattern(BaseModel):
    pattern: str
    frequency: int
    probable_root_causes: list[str] = Field(default_factory=list)
    regression_risk: str = "Medium"
    impacted_modules: list[str] = Field(default_factory=list)
    supporting_issues: list[str] = Field(default_factory=list)


class AutomationScenario(BaseModel):
    title: str
    priority: str = "P2"
    framework: str = "Python Behave + Playwright/Selenium + AEM Guides"
    feature_name: str
    scenario_text: str
    assertions: list[str] = Field(default_factory=list)
    test_data: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    negative: bool = False
    grounded_in: list[str] = Field(default_factory=list)


class UacPoint(BaseModel):
    category: str
    point: str
    risk_level: str = "Medium"
    grounded_in: list[str] = Field(default_factory=list)


class AutomationFit(BaseModel):
    automation_recommended: bool
    priority: str = "P2"
    framework: str = "Python Behave + Playwright/Selenium + AEM Guides"
    dependencies: list[str] = Field(default_factory=list)
    required_test_data: list[str] = Field(default_factory=list)
    complexity: str = "Medium"
    score_0_10: float = 0.0
    rationale: str = ""


class GroundingReport(BaseModel):
    grounded_issue_keys: list[str] = Field(default_factory=list)
    semantic_fallback_used: bool = False
    metadata_filter_used: bool = True
    warnings: list[str] = Field(default_factory=list)
    hallucination_prevention_triggered: bool = False

