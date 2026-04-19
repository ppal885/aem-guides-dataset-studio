"""Merge IntentRecord + RecipeSpec + RAG digest into GenerationPlan."""
from __future__ import annotations

from typing import Literal, cast

from app.core.schemas_dita_pipeline import (
    AttributeTestCoverage,
    GenerationPlan,
    IntentRecord,
    PlanConstruct,
    RecipeExecutionContract,
    RetrievalQueryBundle,
)
from app.generator.recipe_manifest import RecipeSpec
from app.services.dita_attribute_catalog import build_test_scenarios, get_attribute_spec

DEFAULT_SECTIONS = [
    "problem_statement",
    "business_objective",
    "issue_context",
    "technical_reference_with_table",
]


def build_generation_plan(
    intent: IntentRecord,
    spec: RecipeSpec,
    bundle: RetrievalQueryBundle,
    rag_digest: str,
    user_text_excerpt: str,
    *,
    execution_mode: str | None = None,
    contract: RecipeExecutionContract | None = None,
    evidence_fields: dict | None = None,
) -> GenerationPlan:
    validation_rules: list[dict] = []
    repair_hints: list[str] = []

    if contract is not None:
        req = [PlanConstruct(name=c.name, min_count=max(1, c.min_count)) for c in contract.required_constructs]
        forbidden = list(contract.forbidden_fallback_patterns)
        validation_rules = [dict(r) for r in contract.validation_rules]
        repair_hints = list(contract.repair_hints)
    else:
        req = []
        for rc in spec.required_constructs or []:
            if isinstance(rc, dict) and rc.get("name"):
                req.append(
                    PlanConstruct(
                        name=str(rc["name"]),
                        min_count=int(rc.get("min_count") or 1),
                    )
                )
        if not req:
            for p in intent.required_dita_patterns:
                if p in ("table", "simpletable", "menucascade") and p != "none":
                    req.append(PlanConstruct(name=p if p != "simpletable" else "simpletable", min_count=1))

        forbidden = list(spec.forbidden_fallback_patterns or [])
        for ap in spec.anti_patterns or []:
            if isinstance(ap, dict) and ap.get("id"):
                forbidden.append(str(ap["id"]))

    if "table" in [r.name for r in req] or "table_alignment" in intent.anti_fallback_signals:
        forbidden.extend(
            [
                "paragraph_only_body_without_table_when_table_required",
                "ul_only_allowed_values_without_table",
            ]
        )

    topic_type = (spec.topic_type or "").strip() or (
        intent.dita_topic_type_guess if intent.dita_topic_type_guess != "unknown" else "topic"
    )

    mode: Literal["recipe_executor", "llm_json_files"]
    if execution_mode in ("recipe_executor", "llm_json_files"):
        mode = cast(Literal["recipe_executor", "llm_json_files"], execution_mode)
    elif spec.id != "llm_generated_dita" and spec.function:
        mode = "recipe_executor"
    else:
        mode = "llm_json_files"

    intent_summary = f"{intent.content_intent}; patterns={intent.required_dita_patterns[:5]}; anti={intent.anti_fallback_signals[:5]}"

    # Build source fidelity rules based on structured Jira fields
    fidelity_rules: list[str] = [
        "Preserve the user's terminology — do not paraphrase technical terms",
        "Do NOT add steps or details not present in the source ticket",
    ]
    ef = evidence_fields or {}
    if ef.get("steps_to_reproduce"):
        fidelity_rules.append("All steps from 'Steps to Reproduce' MUST appear as <step>/<cmd> elements in order")
        if "steps" not in [r.name for r in req]:
            req.append(PlanConstruct(name="steps", min_count=1))
    if ef.get("acceptance_criteria"):
        fidelity_rules.append("Acceptance criteria MUST appear in <result> or as a verification checklist")
    if ef.get("expected_behavior"):
        fidelity_rules.append("Expected behavior MUST be included (e.g., in <result> or <stepresult>)")
    if ef.get("actual_behavior"):
        fidelity_rules.append("Actual behavior/current behavior MUST be documented (e.g., in <context> or problem statement)")
    if ef.get("expected_behavior") and ef.get("actual_behavior"):
        forbidden.append("omit_expected_vs_actual_comparison")

    # Build attribute test coverage when DITA constructs are detected
    attr_coverage: list[AttributeTestCoverage] = []
    ddc = intent.detected_dita_construct
    if ddc.confidence >= 0.5 and ddc.attributes:
        for attr_name in ddc.attributes:
            attr_spec = get_attribute_spec(attr_name)
            target_elems = ddc.elements or (
                attr_spec.supported_elements if attr_spec else []
            )
            mentioned = ddc.specific_values.get(attr_name, [])
            all_vals = attr_spec.all_valid_values if attr_spec else mentioned
            combo_attrs = attr_spec.combination_attributes if attr_spec else []
            scenarios = build_test_scenarios(attr_name, target_elems, mentioned)
            attr_coverage.append(
                AttributeTestCoverage(
                    target_attribute=attr_name,
                    target_elements=target_elems[:6],
                    all_valid_values=all_vals,
                    mentioned_values=mentioned,
                    combination_attributes=combo_attrs[:4],
                    test_scenarios=scenarios[:15],
                )
            )

    return GenerationPlan(
        recipe_id=spec.id,
        topic_type=topic_type,
        execution_mode=mode,
        required_constructs=req,
        forbidden_patterns=list(dict.fromkeys(forbidden)),
        validation_rules=validation_rules,
        repair_hints=repair_hints,
        must_include_sections=list(DEFAULT_SECTIONS) if intent.specialized_construct_required else [],
        rag_summary=rag_digest[:4000],
        title_format_hint="[ISSUE-KEY]: short feature title",
        raw_user_text_excerpt=user_text_excerpt[:2000],
        intent_summary=intent_summary[:500],
        source_fidelity_rules=fidelity_rules,
        attribute_test_coverage=attr_coverage,
    )
