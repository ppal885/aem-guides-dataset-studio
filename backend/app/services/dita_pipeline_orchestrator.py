"""Orchestrate intent analysis, recipe selection, RAG, plan, generate, validate, repair."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe
from app.core.schemas_generation_trace import GenerationAttemptTrace
from app.core.schemas_dita_pipeline import (
    AssembledRetrievalContext,
    GenerationPlan,
    IntentRecord,
    RecipeExecutionContract,
    RecipeSelectionResult,
    SemanticValidationReport,
)
from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.services.ai_executor_service import execute_plan
from app.services.generation_plan_service import build_generation_plan
from app.services.generation_repair_service import critique_generation_async, format_regeneration_addon
from app.services.intent_analysis_service import analyze_intent_async
from app.services.rag_query_rewrite_service import build_retrieval_bundle
from app.services.retrieval_context_assembly_service import assemble_retrieval_for_generation
from app.services.recipe_selector_service import select_recipe_for_intent
from app.services.semantic_dita_validator import validate_generation_semantics
from app.services.generation_trace_service import (
    build_run_trace,
    infer_trace_outcome,
    log_generation_trace_event,
    make_attempt_trace,
    should_persist_trace,
    write_generation_trace_file,
)
from app.utils.evidence_extractor import pre_extract_representative_xml
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DITA_PIPELINE_MAX_REPAIRS = max(0, int(os.environ.get("DITA_PIPELINE_MAX_REPAIRS", "2")))
LLM_FALLBACK_ID = "llm_generated_dita"


def _user_text_from_evidence(evidence_pack: dict) -> str:
    primary = evidence_pack.get("primary") or {}
    s = (primary.get("summary") or "").strip()
    d = (primary.get("description") or "").strip()
    parts = [s, d]
    # Include structured Jira fields so LLM sees the full context
    for field in ("acceptance_criteria", "steps_to_reproduce", "expected_behavior", "actual_behavior"):
        val = (primary.get(field) or "").strip()
        if val:
            label = field.replace("_", " ").title()
            parts.append(f"\n{label}:\n{val}")
    return "\n\n".join(p for p in parts if p).strip()


def _plan_instruction_block(
    plan: GenerationPlan,
    extra: str = "",
    *,
    retrieval_context: Optional[AssembledRetrievalContext] = None,
    rag_digest_fallback: str = "",
    execution_contract: Optional[RecipeExecutionContract] = None,
    evidence_fields: Optional[dict] = None,
) -> str:
    parts = [
        "GENERATION_PLAN_JSON (mandatory contract — satisfy required_constructs; avoid forbidden_patterns):",
        plan.model_dump_json()[:8000],
    ]

    # Structured Jira field mapping — tells the LLM what maps to what in DITA
    ef = evidence_fields or {}
    field_mapping_lines: list[str] = []
    if ef.get("issue_type"):
        topic_hint = {"bug": "task", "story": "concept", "task": "task", "epic": "map"}.get(
            ef["issue_type"].lower(), plan.topic_type
        )
        field_mapping_lines.append(f"- Issue Type: {ef['issue_type']} → Generate as DITA <{topic_hint}> topic")
    if ef.get("summary"):
        field_mapping_lines.append("- Summary → Use as <title> and <shortdesc> basis")
    if ef.get("steps_to_reproduce"):
        field_mapping_lines.append("- Steps to Reproduce → Map to <steps>/<step>/<cmd> sequence (preserve order and wording)")
    if ef.get("expected_behavior"):
        field_mapping_lines.append("- Expected Behavior → Include in <result> or <stepresult>")
    if ef.get("actual_behavior"):
        field_mapping_lines.append("- Actual Behavior → Include in <context> or problem statement section")
    if ef.get("acceptance_criteria"):
        field_mapping_lines.append("- Acceptance Criteria → Include as verification checklist in <result>")
    if ef.get("environment"):
        field_mapping_lines.append("- Environment → Include in <prereq> or <context>")
    if field_mapping_lines:
        parts.extend([
            "\nSOURCE TICKET FIELD MAPPING (map these Jira fields to DITA elements):",
            *field_mapping_lines,
        ])

    # Source fidelity rules
    if plan.source_fidelity_rules:
        parts.extend([
            "\nSOURCE FIDELITY RULES (MUST follow — content accuracy is critical):",
            *[f"- {r}" for r in plan.source_fidelity_rules],
        ])

    if execution_contract is not None:
        parts.extend(
            [
                "\nRECIPE_EXECUTION_CONTRACT_JSON (hard contract from recipe selection — honor all four sections):",
                execution_contract.model_dump_json()[:6000],
            ]
        )
    if retrieval_context is not None:
        parts.extend(
            [
                "\nRETRIEVAL_CONTEXT (separate channels — follow GENERATION_CONTRACT inside):",
                retrieval_context.to_prompt_sections()[:18000],
            ]
        )
    else:
        parts.extend(["\nRAG_CONTEXT_DIGEST (legacy single block):\n", rag_digest_fallback[:4500]])
    # Attribute test coverage section (for test data generation mode)
    if plan.attribute_test_coverage:
        attr_lines: list[str] = ["\nATTRIBUTE TEST COVERAGE REQUIREMENT:"]
        attr_lines.append("You are generating COMPREHENSIVE TEST DATA, not documentation.")
        attr_lines.append("Generate ALL values listed below, not just the one from the Jira ticket.\n")
        for cov in plan.attribute_test_coverage:
            attr_lines.append(f"Target attribute: @{cov.target_attribute}")
            if cov.target_elements:
                attr_lines.append(f"Target elements: {', '.join(cov.target_elements)}")
            if cov.all_valid_values:
                attr_lines.append(f"ALL valid values (MUST generate each): {', '.join(cov.all_valid_values)}")
            if cov.mentioned_values:
                attr_lines.append(f"Values from Jira ticket: {', '.join(cov.mentioned_values)}")
            if cov.combination_attributes:
                attr_lines.append(f"Combination attributes: {', '.join(cov.combination_attributes)}")
            if cov.test_scenarios:
                attr_lines.append("Test scenarios (generate each as a separate element):")
                for i, sc in enumerate(cov.test_scenarios, 1):
                    attr_lines.append(f"  {i}. {sc}")
            attr_lines.append("")
        parts.extend(attr_lines)

    if extra.strip():
        parts.append("\n" + extra.strip())
    return "\n".join(parts)


def _build_invocation_plan(
    spec: RecipeSpec,
    evidence_pack: dict,
    rep_xml: list,
    trace_id: str,
    jira_id: str,
    plan_instr: str,
    selection_meta: RecipeSelectionResult,
) -> GeneratorInvocationPlan:
    if spec.id == "llm_generated_dita":
        contract_dump: Optional[dict[str, Any]] = None
        if selection_meta.execution_contract is not None:
            contract_dump = selection_meta.execution_contract.model_dump(mode="json")
        llm_params: dict[str, Any] = {
            "evidence_pack": evidence_pack,
            "representative_xml": rep_xml or [],
            "trace_id": trace_id,
            "jira_id": jira_id,
            "additional_instructions": plan_instr,
        }
        if contract_dump is not None:
            llm_params["recipe_execution_contract"] = contract_dump
        return GeneratorInvocationPlan(
            recipes=[
                SelectedRecipe(
                    recipe_id="llm_generated_dita",
                    params=llm_params,
                    evidence_used=["intent_pipeline", selection_meta.recipe_id],
                )
            ],
            selection_rationale=["intent_pipeline", *selection_meta.reasons[:5]],
        )

    params: dict[str, Any] = {}
    primary = evidence_pack.get("primary") or {}
    if spec.id == "table_semantics_reference":
        summ = (primary.get("summary") or "").strip()
        if summ:
            params["issue_summary"] = summ[:300]
    if spec.id == "evidence_to_dita":
        params["representative_xml"] = rep_xml or []

    return GeneratorInvocationPlan(
        recipes=[
            SelectedRecipe(
                recipe_id=spec.id,
                params=params,
                evidence_used=["intent_pipeline", selection_meta.recipe_id],
            )
        ],
        selection_rationale=["intent_pipeline", *selection_meta.reasons[:5]],
    )


def _read_combined_dita_for_critique(scenario_dir: Path, max_chars: int = 24000) -> str:
    chunks: list[str] = []
    for path in sorted(scenario_dir.rglob("*.dita")):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    combined = "\n".join(chunks)
    return combined[:max_chars]


async def run_intent_pipeline_with_execution(
    evidence_pack: dict,
    jira_id: str,
    scenario_dir: Path,
    *,
    seed: str,
    trace_id: Optional[str] = None,
    user_instructions: Optional[str] = None,
) -> dict[str, Any]:
    """
    Full pipeline: intent → recipe → RAG bundle → plan → execute_plan loop with semantic validation
    and LLM repair for llm_generated_dita only.
    """
    trace_id = trace_id or str(uuid4())
    user_text = _user_text_from_evidence(evidence_pack)
    if user_instructions:
        user_text = f"{user_text}\n\nAdditional instructions:\n{user_instructions}"

    intent = await analyze_intent_async(
        user_text, trace_id=trace_id, jira_id=jira_id,
        evidence_fields=evidence_pack.get("primary") or {},
    )
    spec, selection_meta = await select_recipe_for_intent(
        intent, user_text, trace_id=trace_id, jira_id=jira_id
    )

    bundle = build_retrieval_bundle(intent, spec, user_text)
    assembled_ctx = assemble_retrieval_for_generation(
        intent, spec, user_text, bundle, selection_meta
    )
    rag_digest = assembled_ctx.compact_rag_summary()

    gen_plan = build_generation_plan(
        intent,
        spec,
        bundle,
        rag_digest,
        user_text,
        contract=selection_meta.execution_contract,
        evidence_fields=evidence_pack.get("primary") or {},
    )
    rep = pre_extract_representative_xml(evidence_pack.get("primary") or {})

    repair_addon = ""
    last_report = SemanticValidationReport(ok=True)
    last_exec: dict[str, Any] = {}
    last_invocation: Optional[GeneratorInvocationPlan] = None
    attempt_traces: list[GenerationAttemptTrace] = []

    for attempt in range(DITA_PIPELINE_MAX_REPAIRS + 1):
        instr = _plan_instruction_block(
            gen_plan,
            repair_addon,
            retrieval_context=assembled_ctx,
            execution_contract=selection_meta.execution_contract,
            evidence_fields=evidence_pack.get("primary") or {},
        )
        if user_instructions:
            instr = f"{instr}\n\nUSER_REFINEMENT_INSTRUCTIONS:\n{user_instructions[:1500]}"

        gplan = _build_invocation_plan(
            spec, evidence_pack, rep, trace_id, jira_id, instr, selection_meta
        )
        last_invocation = gplan

        last_exec = await asyncio.to_thread(
            execute_plan,
            gplan,
            str(scenario_dir),
            seed=seed[:8] if seed else "intent",
            skip_experience_league_companion=True,
        )

        last_report = validate_generation_semantics(
            gen_plan,
            spec,
            scenario_dir=scenario_dir,
            intent=intent,
        )

        critique = None
        repair_next: Optional[str] = None
        if (
            not last_report.ok
            and spec.id == LLM_FALLBACK_ID
            and attempt < DITA_PIPELINE_MAX_REPAIRS
        ):
            combined_xml = _read_combined_dita_for_critique(scenario_dir)
            critique = await critique_generation_async(
                intent,
                gen_plan,
                combined_xml,
                last_report,
                trace_id=trace_id,
                jira_id=jira_id,
            )
            repair_addon = format_regeneration_addon(last_report, critique, gen_plan)
            repair_next = repair_addon
            logger.info_structured(
                "Intent pipeline: scheduling LLM repair",
                extra_fields={"jira_id": jira_id, "attempt": attempt + 1},
            )

        attempt_traces.append(
            make_attempt_trace(
                attempt,
                scenario_dir,
                last_exec,
                last_report,
                critique=critique,
                repair_addon_for_next_attempt=repair_next,
            )
        )

        if last_report.ok:
            logger.info_structured(
                "Intent pipeline: validation passed",
                extra_fields={"jira_id": jira_id, "recipe_id": spec.id, "attempt": attempt},
            )
            break

        if spec.id != LLM_FALLBACK_ID:
            logger.warning_structured(
                "Intent pipeline: semantic failure on deterministic recipe",
                extra_fields={"jira_id": jira_id, "recipe_id": spec.id},
            )
            break

        if attempt >= DITA_PIPELINE_MAX_REPAIRS:
            break

        repair_addon = repair_next or ""

    outcome = infer_trace_outcome(last_report.ok, spec.id, last_exec)
    generation_trace_path: Optional[str] = None
    if should_persist_trace(last_report.ok):
        trace = build_run_trace(
            trace_id=trace_id,
            jira_id=jira_id,
            user_text=user_text,
            evidence_pack=evidence_pack,
            intent=intent,
            bundle=bundle,
            assembled_ctx=assembled_ctx,
            selection_meta=selection_meta,
            gen_plan=gen_plan,
            spec=spec,
            attempts=attempt_traces,
            final_report=last_report,
            last_exec=last_exec,
            outcome=outcome,
        )
        tp = write_generation_trace_file(scenario_dir, trace)
        generation_trace_path = str(tp)
        log_generation_trace_event(trace, tp)

    return {
        "intent": intent,
        "recipe_selection": selection_meta,
        "generation_plan": gen_plan,
        "spec": spec,
        "semantic_report": last_report,
        "exec_result": last_exec,
        "invocation_plan": last_invocation,
        "trace_id": trace_id,
        "assembled_retrieval": assembled_ctx.model_dump(mode="json"),
        "generation_trace_path": generation_trace_path,
        "generation_outcome": outcome,
    }
