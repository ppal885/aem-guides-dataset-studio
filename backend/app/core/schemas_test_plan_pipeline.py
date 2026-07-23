"""Pydantic models for the unified AEM Guides test-plan pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TestPlanPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_key: str
    tenant_id: str = "kone"
    evidence_k: int = Field(default=8, ge=3, le=12)
    include_repository_evidence: bool = True
    max_repo_matches: int = Field(default=30, ge=5, le=100)
    skip_uac_label_gate: bool = False
    full_rag: bool = True
    include_uac_intelligence: bool = True
    compose_draft_plan: bool = True
    write_starling_artifacts: bool = False
    starling_repo_path: str | None = None
    publish_to_team_ui: bool = False
    human_review_threshold: int = Field(default=50, ge=0, le=100)


class PipelineScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_live: int = 0
    experience_league: int = 0
    similar_jiras: int = 0
    repository_evidence: int = 0
    uac_quality: int = 0
    uac_labels: int = 0
    ambiguity_penalty: int = 0
    mcp_fast_penalty: int = 0


class ConfidenceDimension(BaseModel):
    """Explainable deterministic score dimension for pipeline routing."""

    model_config = ConfigDict(extra="forbid")

    name: str
    weight: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    signals: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class PipelineScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: int = Field(ge=0, le=100)
    tier: Literal["blocked", "low", "medium", "high"]
    human_review_required: bool
    human_review_reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    breakdown: PipelineScoreBreakdown
    dimensions: list[ConfidenceDimension] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    routing_status: Literal[
        "HUMAN_INPUT_REQUIRED",
        "QE_REVIEW_WITH_FLAGS",
        "QE_REVIEW_READY",
        "BLOCKED",
    ] = "HUMAN_INPUT_REQUIRED"


class TicketBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_key: str
    summary: str = ""
    product: str = "AEM Guides"
    component: str = ""
    issue_type: str = ""
    priority: str = ""
    customer: str | None = None
    labels: list[str] = Field(default_factory=list)
    current_behavior: str = ""
    expected_behavior: str = ""
    scope_hint: str = ""


class TicketWorkflowProfileSummary(BaseModel):
    """Lightweight workflow classification attached to pipeline results."""

    model_config = ConfigDict(extra="forbid")

    ticket_category: Literal["bug", "feature_request", "other"] = "other"
    jira_issue_type: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    detection_signals: list[str] = Field(default_factory=list)
    pre_uac_focus: str = ""
    must_run_gate_text: str = ""


class PreUacProductBrief(BaseModel):
    """Product/feature context shown before UAC acceptance criteria work."""

    model_config = ConfigDict(extra="forbid")

    primary_product_area: str = "AEM Guides (general)"
    topic_ids: list[str] = Field(default_factory=list)
    summary_plain_english: str = ""
    how_it_works: list[str] = Field(default_factory=list)
    known_product_behavior: list[str] = Field(default_factory=list)
    documented_behavior: list[str] = Field(default_factory=list)
    ticket_specific_context: str = ""
    official_sources: list[dict[str, str]] = Field(default_factory=list)
    pre_uac_clarifications: list[str] = Field(default_factory=list)


class QeHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["Draft", "Needs human review", "Ready for QE review"]
    assignee_hint: str = "QE / QA owner"
    must_run_before_release: list[str] = Field(default_factory=list)
    pm_questions: list[str] = Field(default_factory=list)
    qa_questions: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)


class PipelineStateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    status: Literal["started", "completed", "skipped", "failed"] = "completed"
    reason: str = ""
    elapsed_ms: int | None = None


class TestPlanPipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: str = "test-plan-pipeline"
    jira_key: str
    correlation_id: str
    stages_completed: list[str] = Field(default_factory=list)
    ticket_brief: TicketBrief
    ticket_workflow: TicketWorkflowProfileSummary | None = None
    pre_uac_product_brief: PreUacProductBrief | None = None
    ticket_analysis: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[dict[str, Any]] = Field(default_factory=list)
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
    coverage_matrix: dict[str, Any] = Field(default_factory=dict)
    score: PipelineScore
    confidence_dimensions: list[ConfidenceDimension] = Field(default_factory=list)
    uac_intelligence: dict[str, Any] | None = None
    rag_packet_summary: dict[str, Any] = Field(default_factory=dict)
    draft_test_plan_markdown: str | None = None
    validation: dict[str, Any] | None = None
    qe_handoff: QeHandoff
    qe_review_package: dict[str, Any] = Field(default_factory=dict)
    state_history: list[PipelineStateTransition] = Field(default_factory=list)
    artifacts_written: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0
