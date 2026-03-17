"""Pydantic schemas for recipe scoring and routing pipeline."""
from typing import Optional

from pydantic import BaseModel, Field


class MechanismClassification(BaseModel):
    """Output of mechanism classification stage."""

    model_config = {"extra": "ignore"}

    feature_scores: dict[str, float] = Field(default_factory=dict)
    selected_feature: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    rejected_features: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class PatternClassification(BaseModel):
    """Output of pattern classification stage."""

    model_config = {"extra": "ignore"}

    selected_feature: str = Field(default="")
    pattern_scores: dict[str, float] = Field(default_factory=dict)
    selected_pattern: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    rejected_patterns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class RecipeParameters(BaseModel):
    """Topology extraction / recipe parameters."""

    model_config = {"extra": "ignore"}

    root_map_count: int = Field(default=0, ge=0)
    submap_count: int = Field(default=0, ge=0)
    nested_depth: int = Field(default=0, ge=0)
    referencing_topic_count: int = Field(default=0, ge=0)
    target_topic_count: int = Field(default=0, ge=0)
    duplicate_key_names: list[str] = Field(default_factory=list)
    duplicate_key_locations: list[str] = Field(default_factory=list)
    consumer_location: str = Field(default="")
    target_types: list[str] = Field(default_factory=list)
    requires_negative_case: bool = Field(default=False)
    requires_boundary_case: bool = Field(default=False)
    generation_mode: str = Field(default="minimal_repro")
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class RecipeSelection(BaseModel):
    """Output of deterministic recipe routing."""

    model_config = {"extra": "ignore"}

    selected_feature: str = Field(default="")
    selected_pattern: str = Field(default="")
    selected_recipe: str = Field(default="")
    route_reason: str = Field(default="")
    cross_feature_blocked: bool = Field(default=True)


class IssueEvidence(BaseModel):
    """Normalized Jira evidence for recipe scoring. Build from evidence_pack.primary."""

    model_config = {"extra": "ignore"}

    jira_id: str = Field(default="", description="Jira issue key")
    summary: str = Field(default="", description="Issue summary")
    description: str = Field(default="", description="Full description")
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    raw_text: str = Field(
        default="",
        description="Combined searchable text: summary + description + attachment excerpts",
    )


class RejectedRecipe(BaseModel):
    """A recipe considered but rejected with reason."""

    recipe: str = Field(default="", description="Recipe ID rejected")
    reason: str = Field(default="", description="Why this recipe was rejected")


class RecipeSelectionOutput(BaseModel):
    """Structured Jira-to-recipe selection output for LLM/API."""

    model_config = {"extra": "ignore"}

    selected_recipe: str = Field(default="", description="Recipe ID selected")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence 0-1")
    selection_reason: list[str] = Field(
        default_factory=list,
        description="Reasons this recipe was selected (e.g. Jira requests large topic)",
    )
    rejected_recipes: list[RejectedRecipe] = Field(
        default_factory=list,
        description="Recipes considered but rejected with reasons",
    )


class RecipeScoringResult(BaseModel):
    """Output of recipe scoring and routing pipeline."""

    model_config = {"extra": "ignore"}

    feature_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Score per DITA mechanism (keyref, xref, conref, ditaval, etc.)",
    )
    selected_feature: str = Field(default="", description="Primary DITA mechanism")
    pattern_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Score per pattern within selected feature",
    )
    selected_pattern: str = Field(default="", description="Pattern within feature")
    selected_recipe: str = Field(default="", description="Recipe ID from deterministic routing")
    cross_feature_blocked: bool = Field(
        default=True,
        description="True when xref/conref/ditaval blocked for keyref issue",
    )
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


def normalize_evidence_from_pack(primary: dict, jira_id: str = "") -> IssueEvidence:
    """Build IssueEvidence from evidence_pack.primary dict."""
    if not primary:
        return IssueEvidence(jira_id=jira_id)

    summary = (primary.get("summary") or "").strip()
    description = (primary.get("description") or "").strip()
    labels = primary.get("labels") or []
    if isinstance(labels, str):
        labels = [labels] if labels else []
    components = primary.get("components") or []
    if isinstance(components, str):
        components = [components] if components else []

    parts = [summary, description]
    for att in primary.get("attachments") or []:
        content = att.get("full_content") or att.get("excerpt") or ""
        if content:
            parts.append(str(content)[:3000])
    for c in primary.get("comments") or []:
        body = c.get("body_text", "") if isinstance(c, dict) else ""
        if body:
            parts.append(str(body)[:1500])

    raw_text = " ".join(p for p in parts if p).strip()

    return IssueEvidence(
        jira_id=jira_id or (primary.get("issue_key") or ""),
        summary=summary,
        description=description,
        labels=list(labels)[:20],
        components=list(components)[:20],
        raw_text=raw_text[:15000],
    )
