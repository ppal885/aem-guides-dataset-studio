"""Pydantic schemas for AI pipeline (scenarios, plans)."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ContentFromEvidenceSchema(BaseModel):
    """Strict schema for content extractor LLM output. Strips unknown fields."""

    model_config = {"extra": "ignore"}

    topic_titles: list[str] = Field(default_factory=list, max_length=5)
    shortdescs: list[str] = Field(default_factory=list, max_length=5)
    steps: list[str] = Field(default_factory=list, max_length=10)
    body_snippets: list[str] = Field(default_factory=list, max_length=5)
    representative_xml: list[str] = Field(default_factory=list, max_length=6)


class ScenarioType(str, Enum):
    MIN_REPRO = "MIN_REPRO"
    BOUNDARY = "BOUNDARY"
    STRESS = "STRESS"
    EDGE = "EDGE"
    INTEGRATION = "INTEGRATION"


class Scenario(BaseModel):
    id: str = Field(..., description="e.g. S1_MIN_REPRO, S2_BOUNDARY")
    type: ScenarioType
    title: str
    description: str
    evidence_refs: list[str] = Field(default_factory=list)


class ScenarioSet(BaseModel):
    scenarios: list[Scenario] = Field(..., max_length=5)


class ReferenceTarget(BaseModel):
    """Optional relation metadata. source.file == target.file allowed for same-file reuse."""
    target_type: str = Field(default="xref", description="xref | conref | conrefend")
    target_element: Optional[str] = Field(default=None, description="section | li | fig | table | p | etc.")
    is_self_reference: bool = Field(default=False, description="True when source and target are in same file")
    end_target_id: Optional[str] = Field(default=None, description="For conrefend range: end element id")


class ConrefRelation(BaseModel):
    """Relation metadata for conref/conrefend. source.file == target.file allowed for same-file reuse."""
    is_self_reference: bool = Field(default=False, description="True when source and target are in same file")
    target_id: str = Field(default="", description="Target element id or topicId/elementId fragment")
    end_target_id: Optional[str] = Field(default=None, description="For conrefend range: end element id")


class SelectedRecipe(BaseModel):
    recipe_id: str
    params: dict = Field(default_factory=dict)
    evidence_used: list[str] = Field(default_factory=list)


class GeneratorInvocationPlan(BaseModel):
    recipes: list[SelectedRecipe] = Field(default_factory=list)
    selection_rationale: list[str] = Field(default_factory=list, description="Brief explanation per recipe: which metadata matched")
