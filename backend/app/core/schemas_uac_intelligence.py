"""Pydantic contracts for UAC Requirement Intelligence Engine (structured JSON API)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SeverityLevel = Literal["low", "medium", "high"]


class UacIntelligenceAnalyzeRequest(BaseModel):
    """Request body for enterprise UAC intelligence (distinct from legacy Copilot analyze)."""

    model_config = ConfigDict(extra="forbid")

    jira_key: str = Field(..., min_length=3, max_length=2048)
    debug: bool = False
    include_docs: bool = Field(True, description="Retrieve Experience League + DITA-OT evidence when true")
    max_similar_jiras: int = Field(8, ge=0, le=24)


class AmbiguityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambiguity: str
    why_it_matters: str
    affected_area: str
    who_should_clarify: str
    severity: SeverityLevel
    evidence: list[str] = Field(default_factory=list, description="Evidence record ids e.g. E1")


class AcceptanceCriterionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str
    entity: str
    output: str
    expected_behavior: str
    given: str = ""
    when: str = ""
    then: str = ""
    evidence: list[str] = Field(default_factory=list)


class DiscussionQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    audience: Literal["pm", "dev", "qa", "cross_team"]
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)


class CustomerImpactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_names: list[str] = Field(default_factory=list)
    workflow_impacts: list[str] = Field(default_factory=list)
    potential_customer_risks: list[str] = Field(default_factory=list)
    sensitive_workflows: list[str] = Field(default_factory=list)
    confidence: dict[str, Any] = Field(default_factory=dict)


class OutputExpectationsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs_discussed: list[str] = Field(default_factory=list)
    parity_risks: list[str] = Field(default_factory=list)
    undefined_behavior: list[str] = Field(default_factory=list)
    rendering_risks: list[str] = Field(default_factory=list)
    metadata_propagation_risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class BackwardCompatibilityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behavior_change_signals: list[str] = Field(default_factory=list)
    publishing_compatibility_risks: list[str] = Field(default_factory=list)
    schema_compatibility_risks: list[str] = Field(default_factory=list)
    migration_risks: list[str] = Field(default_factory=list)
    customer_workflow_risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class AutomationFeasibilityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_automation_fit: str = ""
    ui_automation_fit: str = ""
    publishing_validation_fit: str = ""
    deterministic_validation: str = ""
    flaky_risk: str = ""
    required_artifacts: list[str] = Field(default_factory=list)
    relevant_apis: list[str] = Field(default_factory=list)
    recommended_layer: str = ""
    evidence: list[str] = Field(default_factory=list)


class SimilarJiraEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    jira_key: str
    title: str = ""
    why_similar: str = ""
    scores: dict[str, Any] | None = None
    evidence_id: str | None = None
    excerpt: str = ""


class DocumentationEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Literal["experience_league", "dita_ot"]
    title: str = ""
    url: str = ""
    snippet: str = ""
    evidence_id: str | None = None
    retrieval_score_note: str = ""


class RiskSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "unspecified"
    drivers: list[str] = Field(default_factory=list)
    message: str = ""


class UacRequirementIntelligenceResponse(BaseModel):
    """Full structured response for POST /api/v1/ai/uac/requirement-intelligence."""

    model_config = ConfigDict(extra="forbid")

    jira_key: str
    correlation_id: str = ""
    classification: dict[str, Any] = Field(default_factory=dict)
    requirement_understanding: dict[str, Any] = Field(default_factory=dict)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    missing_expectations: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterionItem] = Field(default_factory=list)
    pm_questions: list[DiscussionQuestionItem] = Field(default_factory=list)
    dev_questions: list[DiscussionQuestionItem] = Field(default_factory=list)
    qa_questions: list[DiscussionQuestionItem] = Field(default_factory=list)
    cross_team_decisions: list[str] = Field(default_factory=list)
    customer_impact: CustomerImpactPayload = Field(default_factory=CustomerImpactPayload)
    output_expectations: OutputExpectationsPayload = Field(default_factory=OutputExpectationsPayload)
    backward_compatibility: BackwardCompatibilityPayload = Field(default_factory=BackwardCompatibilityPayload)
    automation_feasibility: AutomationFeasibilityPayload = Field(default_factory=AutomationFeasibilityPayload)
    similar_jira_evidence: list[SimilarJiraEvidenceItem] = Field(default_factory=list)
    documentation_evidence: list[DocumentationEvidenceItem] = Field(default_factory=list)
    risk_summary: RiskSummaryPayload = Field(default_factory=RiskSummaryPayload)
    confidence: dict[str, Any] = Field(default_factory=dict)
    quality_score: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evidence_manifest: list[dict[str, Any]] = Field(
        default_factory=list,
        description="All evidence records for traceability",
    )
    debug: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AcceptanceCriterionItem",
    "AmbiguityItem",
    "AutomationFeasibilityPayload",
    "BackwardCompatibilityPayload",
    "CustomerImpactPayload",
    "DiscussionQuestionItem",
    "DocumentationEvidenceItem",
    "OutputExpectationsPayload",
    "RiskSummaryPayload",
    "SimilarJiraEvidenceItem",
    "UacIntelligenceAnalyzeRequest",
    "UacRequirementIntelligenceResponse",
]
