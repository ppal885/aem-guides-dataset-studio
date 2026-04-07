"""Persist and log generation debug traces (failed runs by default)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

from app.core.observability import get_observability_logger
from app.core.schemas_dita_pipeline import (
    AssembledRetrievalContext,
    CritiqueReport,
    GenerationPlan,
    IntentRecord,
    RecipeSelectionResult,
    RetrievalQueryBundle,
    SemanticValidationReport,
)
from app.core.schemas_generation_trace import GenerationAttemptTrace, GenerationRunTrace
from app.core.structured_logging import get_structured_logger
from app.generator.recipe_manifest import RecipeSpec

logger = get_structured_logger(__name__)
obs_log = get_observability_logger("generation_trace")

TRACE_FILE_NAME = "generation_trace.json"
MAX_XML_PREVIEW = int(os.environ.get("DITA_GENERATION_TRACE_MAX_XML_CHARS", "96000"))
MAX_REPAIR_TEXT = 12000
TRACE_ALWAYS = os.environ.get("DITA_GENERATION_TRACE_ALWAYS", "false").lower() in ("true", "1", "yes")


def _primary_subset(evidence_pack: dict) -> dict[str, Any]:
    p = evidence_pack.get("primary") or {}
    if not isinstance(p, dict):
        return {}
    return {
        k: (str(p[k])[:20000] if isinstance(p.get(k), str) else p.get(k))
        for k in ("summary", "description", "issue_key")
        if k in p
    }


def gather_scenario_xml_snapshot(scenario_dir: Path) -> tuple[list[str], str]:
    """Collect relative paths and concatenated XML-ish content for trace preview."""
    paths: list[str] = []
    chunks: list[str] = []
    base = scenario_dir.resolve()
    for pattern in ("**/*.dita", "**/*.ditamap", "**/*.xml"):
        for path in sorted(scenario_dir.glob(pattern)):
            if not path.is_file():
                continue
            try:
                rel = str(path.resolve().relative_to(base)).replace("\\", "/")
            except ValueError:
                rel = path.name
            paths.append(rel)
            try:
                chunks.append(f"<!-- file: {rel} -->\n{path.read_text(encoding='utf-8', errors='ignore')}")
            except OSError:
                continue
    combined = "\n\n".join(chunks)
    return paths[:80], combined[:MAX_XML_PREVIEW]


TraceOutcome = Literal["success", "validation_failed", "deterministic_recipe_failed", "exec_failed"]


def infer_trace_outcome(
    validation_ok: bool,
    recipe_id: str,
    last_exec: dict[str, Any],
) -> TraceOutcome:
    if validation_ok:
        return "success"
    warnings = last_exec.get("warnings") or []
    executed = last_exec.get("recipes_executed") or []
    if not executed and warnings:
        joined = " ".join(str(w).lower() for w in warnings)
        if "failed" in joined or "error" in joined:
            return "exec_failed"
    if recipe_id != "llm_generated_dita":
        return "deterministic_recipe_failed"
    return "validation_failed"


def validation_failure_summary(report: SemanticValidationReport) -> str:
    if report.ok:
        return ""
    parts = [f"{v.rule_id}: {v.message}" for v in report.violations if v.severity == "error"]
    if not parts:
        parts = [f"{v.rule_id}: {v.message}" for v in report.violations]
    return "; ".join(parts[:12])[:4000]


def build_run_trace(
    *,
    trace_id: str,
    jira_id: str,
    user_text: str,
    evidence_pack: dict,
    intent: IntentRecord,
    bundle: RetrievalQueryBundle,
    assembled_ctx: AssembledRetrievalContext,
    selection_meta: RecipeSelectionResult,
    gen_plan: GenerationPlan,
    spec: RecipeSpec,
    attempts: list[GenerationAttemptTrace],
    final_report: SemanticValidationReport,
    last_exec: dict[str, Any],
    outcome: TraceOutcome,
) -> GenerationRunTrace:
    retrieved = [c.model_dump(mode="json") for c in (selection_meta.retrieval_candidates or [])]
    contract = (
        selection_meta.execution_contract.model_dump(mode="json")
        if selection_meta.execution_contract
        else None
    )
    return GenerationRunTrace(
        trace_id=trace_id,
        jira_id=jira_id,
        outcome=outcome,
        raw_user_text=user_text[:50000],
        raw_evidence_primary=_primary_subset(evidence_pack),
        intent_record=intent.model_dump(mode="json"),
        rewritten_retrieval_bundle=bundle.model_dump(mode="json"),
        assembled_retrieval_meta={
            "dita_spec_chunk_count": assembled_ctx.dita_spec_chunk_count,
            "gold_example_snippet_count": assembled_ctx.gold_example_snippet_count,
            "fusion_note": assembled_ctx.fusion_note,
        },
        retrieved_recipes=retrieved,
        selected_recipe={
            "recipe_id": selection_meta.recipe_id,
            "score": selection_meta.score,
            "candidate_ids_tried": selection_meta.candidate_ids_tried,
            "reasons": selection_meta.reasons,
            "title": spec.title,
            "module": spec.module,
            "function": spec.function,
        },
        execution_contract=contract,
        generation_plan=gen_plan.model_dump(mode="json"),
        selection_reasons=list(selection_meta.reasons or []),
        attempts=attempts,
        final_semantic_validation=final_report.model_dump(mode="json"),
        validation_failure_summary=validation_failure_summary(final_report),
    )


def write_generation_trace_file(scenario_dir: Path, trace: GenerationRunTrace) -> Path:
    path = scenario_dir / TRACE_FILE_NAME
    scenario_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return path


def log_generation_trace_event(
    trace: GenerationRunTrace,
    trace_path: Path,
) -> None:
    """Emit observability + structured logs; full payload is on disk at trace_path."""
    payload = {
        "trace_id": trace.trace_id,
        "jira_id": trace.jira_id,
        "outcome": trace.outcome,
        "trace_file": str(trace_path),
        "attempts": len(trace.attempts),
        "validation_ok": trace.final_semantic_validation.get("ok"),
        "failure_summary": (trace.validation_failure_summary or "")[:500],
    }
    obs_log.info("dita_generation_trace", **payload)

    if trace.outcome != "success":
        logger.warning_structured("Generation trace persisted (failure or trace-always)", extra_fields=payload)
    else:
        logger.info_structured("Generation trace persisted", extra_fields=payload)


def should_persist_trace(validation_ok: bool) -> bool:
    return TRACE_ALWAYS or not validation_ok


def make_attempt_trace(
    attempt_index: int,
    scenario_dir: Path,
    last_exec: dict[str, Any],
    semantic_report: SemanticValidationReport,
    *,
    critique: Optional[CritiqueReport] = None,
    repair_addon_for_next_attempt: Optional[str] = None,
) -> GenerationAttemptTrace:
    rel_paths, xml_preview = gather_scenario_xml_snapshot(scenario_dir)
    return GenerationAttemptTrace(
        attempt_index=attempt_index,
        recipes_executed=list(last_exec.get("recipes_executed") or []),
        exec_warnings=list(last_exec.get("warnings") or [])[:40],
        output_relative_paths=rel_paths,
        generated_xml_combined_preview=xml_preview,
        semantic_validation=semantic_report.model_dump(mode="json"),
        critique_result=critique.model_dump(mode="json") if critique else None,
        repair_addon_for_next_attempt=(
            (repair_addon_for_next_attempt or "")[:MAX_REPAIR_TEXT] if repair_addon_for_next_attempt else None
        ),
        is_regeneration=attempt_index > 0,
    )
