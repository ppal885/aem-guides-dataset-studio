"""Structured Jira enrichment payload (pre-embed metadata for Jira QA RAG)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JiraEnrichedDocument(BaseModel):
    """JSON-serializable enrichment for one Jira issue before embedding."""

    model_config = ConfigDict(extra="forbid")

    jira_key: str = ""
    summary: str = ""
    description: str = ""
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    customer_names: list[str] = Field(default_factory=list)
    domain: str = "unknown"
    sub_domain: str = ""
    affected_outputs: list[str] = Field(default_factory=list)
    affected_features: list[str] = Field(default_factory=list)
    dita_entities: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    qa_risk_tags: list[str] = Field(default_factory=list)
    automation_fit: str = ""
    missing_info: list[str] = Field(default_factory=list)
    raw_text: str = ""
    enrichment_debug: dict[str, Any] = Field(
        default_factory=dict,
        description="Trace of enrichment decisions: domain scores, entity/output detections, customer extraction, and missing-info flags.",
    )
    customer_detection_debug: dict[str, Any] = Field(
        default_factory=dict,
        description="Trace of customer extraction: from_custom_fields, from_labels, excluded_labels, final_customers.",
    )
    comments_digest: str = Field(
        default="",
        description="Compact comment text supplied by indexer for smart chunking.",
    )
