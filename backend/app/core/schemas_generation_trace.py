"""Structured debug trace for DITA generation (failed runs and optional success)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GenerationAttemptTrace(BaseModel):
    """One execute → validate → (optional) critique cycle."""

    attempt_index: int = 0
    recipes_executed: list[str] = Field(default_factory=list)
    exec_warnings: list[str] = Field(default_factory=list)
    output_relative_paths: list[str] = Field(default_factory=list)
    generated_xml_combined_preview: str = Field(
        default="",
        description="Scenario XML snapshot after this attempt; when is_regeneration is True, this is the regenerated output.",
    )
    semantic_validation: dict[str, Any] = Field(default_factory=dict)
    critique_result: Optional[dict[str, Any]] = None
    """LLM critique JSON when a repair attempt was prepared."""
    repair_addon_for_next_attempt: Optional[str] = None
    """Instructions appended before regeneration (next attempt)."""
    is_regeneration: bool = False
    """True for attempts > 0 after a repair loop."""


class GenerationRunTrace(BaseModel):
    """
    Full observability payload for debugging generation.
    Written to ``scenario_dir/generation_trace.json`` on failure (or always if env set).
    """

    schema_version: str = "1.0"
    trace_id: str = ""
    jira_id: str = ""
    outcome: Literal[
        "success",
        "validation_failed",
        "deterministic_recipe_failed",
        "exec_failed",
    ] = "success"

    raw_user_text: str = Field("", description="Normalized user/Jira text fed to intent + generation.")
    raw_evidence_primary: dict[str, Any] = Field(
        default_factory=dict,
        description="Subset of evidence_pack.primary (summary, description, issue_key).",
    )

    intent_record: dict[str, Any] = Field(default_factory=dict)
    rewritten_retrieval_bundle: dict[str, Any] = Field(
        default_factory=dict,
        description="RetrievalQueryBundle (queries for DITA spec / gold / AEM channels).",
    )
    assembled_retrieval_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Counts and fusion note from AssembledRetrievalContext.",
    )

    retrieved_recipes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recipe store candidates after retrieval + intent scoring.",
    )
    selected_recipe: dict[str, Any] = Field(default_factory=dict)
    execution_contract: Optional[dict[str, Any]] = None

    generation_plan: dict[str, Any] = Field(default_factory=dict)
    selection_reasons: list[str] = Field(default_factory=list)

    attempts: list[GenerationAttemptTrace] = Field(default_factory=list)

    final_semantic_validation: dict[str, Any] = Field(default_factory=dict)
    validation_failure_summary: str = ""
    """Human-readable one-line summary of why validation failed (if applicable)."""

    construct_demonstration_reminder: str = (
        "If the request implies a specific DITA construct, emit that construct in real markup "
        "(table, steps, keydef, map, etc.)—not only <topic>/<body>/<section>/<p> prose about it."
    )
