"""Pydantic models for intent-driven DITA generation pipeline."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DomainSignals(BaseModel):
    aem_guides: bool = False
    dita_ot: bool = False
    web_editor: bool = False
    ui_workflow: bool = False


_ALLOWED_CONTENT_INTENT = frozenset({
    "bug_repro",
    "feature_request",
    "documentation",
    "reference_material",
    "task_procedure",
    "comparison",
    "glossary",
    "map_hierarchy",
    "unknown",
})
_ALLOWED_TOPIC_TYPE = frozenset(
    {"concept", "task", "reference", "topic", "map_only", "mixed", "unknown"}
)


class IntentRecord(BaseModel):
    """Structured intent from user/Jira text (LLM + optional keyword merge)."""

    content_intent: Literal[
        "bug_repro",
        "feature_request",
        "documentation",
        "reference_material",
        "task_procedure",
        "comparison",
        "glossary",
        "map_hierarchy",
        "unknown",
    ] = "unknown"
    dita_topic_type_guess: Literal[
        "concept", "task", "reference", "topic", "map_only", "mixed", "unknown"
    ] = "unknown"
    specialized_construct_required: bool = False
    required_dita_patterns: list[str] = Field(default_factory=list)
    domain_signals: DomainSignals = Field(default_factory=DomainSignals)
    user_expectation: str = ""
    anti_fallback_signals: list[str] = Field(default_factory=list)
    evidence_phrases: list[str] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("content_intent", mode="before")
    @classmethod
    def _coerce_content_intent(cls, v: object) -> str:
        s = str(v) if v is not None else "unknown"
        return s if s in _ALLOWED_CONTENT_INTENT else "unknown"

    @field_validator("dita_topic_type_guess", mode="before")
    @classmethod
    def _coerce_topic_type(cls, v: object) -> str:
        s = str(v) if v is not None else "unknown"
        return s if s in _ALLOWED_TOPIC_TYPE else "unknown"


class RetrievalQueryBundle(BaseModel):
    primary_query: str = ""
    dita_spec_queries: list[str] = Field(default_factory=list)
    aem_guides_queries: list[str] = Field(default_factory=list)
    element_focus: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    max_chunks_per_channel: dict[str, int] = Field(
        default_factory=lambda: {"dita_spec": 6, "aem": 3, "graph": 1}
    )


class RecipeStoreCandidateSummary(BaseModel):
    """One row from the recipe store after retrieval + scoring (before intent adjustments)."""

    recipe_id: str
    title: str = ""
    retrieval_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class AssembledRetrievalContext(BaseModel):
    """
    Separated retrieval channels merged for generation (recipe store, spec store, catalog examples,
    gold XML RAG, AEM docs). Use ``to_prompt_sections()`` for the LLM; ``compact_rag_summary()`` for plans.
    """

    recipe_store_text: str = ""
    recipe_catalog_spec_examples_text: str = ""
    dita_spec_store_text: str = ""
    gold_xml_examples_text: str = ""
    aem_guides_store_text: str = ""
    dita_spec_chunk_count: int = 0
    gold_example_snippet_count: int = 0
    fusion_note: str = ""

    def compact_rag_summary(self, max_chars: int = 4000) -> str:
        """Short digest for GenerationPlan.rag_summary (spec-first, then gold snippets)."""
        parts = [self.dita_spec_store_text, self.gold_xml_examples_text]
        body = "\n---\n".join(p.strip() for p in parts if p and p.strip())
        return body[:max_chars]

    def to_prompt_sections(self, max_chars_per_section: int = 5000) -> str:
        """Ordered sections: recipe retrieval, catalog examples, DITA spec, gold XML, AEM, contract."""
        blocks: list[str] = []
        if self.recipe_store_text.strip():
            blocks.append(
                "=== RECIPE_STORE (catalog retrieval — lexical + embedding + optional LLM rerank) ===\n"
                + self.recipe_store_text.strip()[:max_chars_per_section]
            )
        if self.recipe_catalog_spec_examples_text.strip():
            blocks.append(
                "=== RECIPE_CATALOG_SPEC_EXAMPLES (selected recipe: intended shape / excerpts) ===\n"
                + self.recipe_catalog_spec_examples_text.strip()[:max_chars_per_section]
            )
        if self.dita_spec_store_text.strip():
            blocks.append(
                "=== DITA_SPEC_STORE (normative structure from DITA spec index) ===\n"
                + self.dita_spec_store_text.strip()[:max_chars_per_section]
            )
        if self.gold_xml_examples_text.strip():
            blocks.append(
                "=== GOLD_XML_EXAMPLES (RAG snippets biased toward real markup; imitate element structure) ===\n"
                + self.gold_xml_examples_text.strip()[:max_chars_per_section]
            )
        if self.aem_guides_store_text.strip():
            blocks.append(
                "=== AEM_GUIDES_STORE (product docs; use for UI/workflow, not as a substitute for DITA elements) ===\n"
                + self.aem_guides_store_text.strip()[:max_chars_per_section]
            )
        blocks.append(
            "=== GENERATION_CONTRACT ===\n"
            "If the user or recipe implies a specific DITA construct (table, steps, keydef, conref, map, "
            "glossentry, subjectScheme, etc.), you MUST show that construct in the generated XML—not only "
            "<topic>/<body>/<section>/<p> prose that describes it."
        )
        if self.fusion_note.strip():
            blocks.append("=== RETRIEVAL_FUSION ===\n" + self.fusion_note.strip()[:800])
        return "\n\n".join(blocks)


class PlanConstruct(BaseModel):
    name: str
    min_count: int = 1


class RecipeExecutionContract(BaseModel):
    """
    Hard contract for a selected recipe: required constructs, forbidden fallbacks,
    validation rules, and repair hints. Materialized at selection time.
    """

    recipe_id: str
    required_constructs: list[PlanConstruct] = Field(default_factory=list)
    forbidden_fallback_patterns: list[str] = Field(default_factory=list)
    validation_rules: list[dict[str, Any]] = Field(default_factory=list)
    repair_hints: list[str] = Field(default_factory=list)


class GenerationPlan(BaseModel):
    plan_version: str = "1.0"
    recipe_id: str
    topic_type: str = "topic"
    execution_mode: Literal["recipe_executor", "llm_json_files"] = "llm_json_files"
    required_constructs: list[PlanConstruct] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    validation_rules: list[dict[str, Any]] = Field(default_factory=list)
    repair_hints: list[str] = Field(default_factory=list)
    must_include_sections: list[str] = Field(default_factory=list)
    rag_summary: str = ""
    title_format_hint: str = ""
    raw_user_text_excerpt: str = ""
    intent_summary: str = ""  # one-line for prompts
    source_fidelity_rules: list[str] = Field(default_factory=list)


class SemanticViolation(BaseModel):
    rule_id: str
    severity: Literal["error", "warn"] = "error"
    message: str
    repair_hint: str = ""


class SemanticValidationReport(BaseModel):
    ok: bool = True
    shallow_output: bool = False
    violations: list[SemanticViolation] = Field(default_factory=list)
    construct_counts: dict[str, int] = Field(default_factory=dict)


class CritiqueReport(BaseModel):
    aligned_with_intent: bool = True
    shallow_wrap: bool = False
    missing_required_constructs: list[str] = Field(default_factory=list)
    violations: list[dict[str, Any]] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)


class RecipeSelectionResult(BaseModel):
    recipe_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    candidate_ids_tried: list[str] = Field(default_factory=list)
    execution_contract: Optional[RecipeExecutionContract] = None
    retrieval_candidates: list[RecipeStoreCandidateSummary] = Field(
        default_factory=list,
        description="Top rows from recipe store after retrieval (before final intent-weighted pick).",
    )
