"""Retrieve, rank, and select recipes using IntentRecord + RecipeSpec metadata."""
from __future__ import annotations

from typing import Optional

from app.core.schemas_dita_pipeline import IntentRecord, RecipeSelectionResult, RecipeStoreCandidateSummary
from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.services.recipe_execution_contract import build_recipe_execution_contract
from app.services.recipe_retriever import retrieve_recipes
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

LLM_FALLBACK_ID = "llm_generated_dita"
ANTI_DOMINANCE_DELTA = 0.15


def _spec_by_id() -> dict[str, RecipeSpec]:
    out: dict[str, RecipeSpec] = {}
    for s in discover_recipe_specs():
        if isinstance(s, RecipeSpec) and s.id:
            out[s.id] = s
    return out


def _construct_overlap_score(intent: IntentRecord, spec: RecipeSpec) -> float:
    """Jaccard-like overlap between intent patterns and recipe constructs/required_constructs."""
    want = set()
    for p in intent.required_dita_patterns:
        if p and p != "none":
            want.add(p.replace("_", ""))
            want.add(p.split("_")[0])
    for a in intent.anti_fallback_signals:
        want.add(a.replace("_", ""))
    if not want:
        return 0.0

    have = set()
    for c in spec.constructs or []:
        have.add(str(c).lower())
    for rc in spec.required_constructs or []:
        if isinstance(rc, dict) and rc.get("name"):
            have.add(str(rc["name"]).lower())
    for t in spec.intent_tags or []:
        have.add(str(t).lower())

    if not have:
        return 0.0
    inter = len(want & have) + sum(1 for w in want if any(w in h or h in w for h in have))
    return min(1.0, inter / max(1, len(want)))


def _intent_penalize_llm(intent: IntentRecord) -> float:
    """When user clearly needs specialized constructs, penalize generic LLM fallback."""
    if not intent.specialized_construct_required:
        return 0.0
    if "table" in intent.required_dita_patterns or "table_alignment" in intent.anti_fallback_signals:
        return 0.35
    if intent.required_dita_patterns and "none" not in intent.required_dita_patterns:
        return 0.2
    return 0.0


async def select_recipe_for_intent(
    intent: IntentRecord,
    user_text: str,
    *,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    top_k: int = 14,
) -> tuple[RecipeSpec, RecipeSelectionResult]:
    """
    Retrieve candidates, adjust scores with intent overlap, apply anti-dominance for llm_generated_dita.
    Returns (RecipeSpec, RecipeSelectionResult).
    """
    by_id = _spec_by_id()
    candidates = await retrieve_recipes(
        user_text[:3000],
        k=top_k,
        evidence_context=user_text[:4000],
        trace_id=trace_id,
        jira_id=jira_id,
    )

    scored: list[tuple[str, float, list[str], float]] = []
    for c in candidates:
        rid = c.get("recipe_id") or ""
        base = float(c.get("score") or 0.0)
        spec = by_id.get(rid)
        if not spec:
            continue
        reasons = list(c.get("matched_features") or [])
        overlap = _construct_overlap_score(intent, spec)
        adjusted = base + overlap * 2.0
        if rid == LLM_FALLBACK_ID:
            adjusted -= _intent_penalize_llm(intent)
        reasons.append(f"intent_construct_overlap:{round(overlap, 2)}")
        scored.append((rid, adjusted, reasons, overlap))

    scored.sort(key=lambda x: -x[1])

    if not scored:
        spec = by_id.get(LLM_FALLBACK_ID)
        if not spec:
            raise RuntimeError("No recipes available including llm_generated_dita")
        fb_contract = build_recipe_execution_contract(spec, intent=intent)
        return spec, RecipeSelectionResult(
            recipe_id=LLM_FALLBACK_ID,
            score=0.0,
            reasons=["no_candidates_fallback"],
            candidate_ids_tried=[],
            execution_contract=fb_contract,
            retrieval_candidates=[],
        )

    best_id, best_score, best_reasons, best_overlap = scored[0]
    second = scored[1] if len(scored) > 1 else None

    if (
        best_id == LLM_FALLBACK_ID
        and second
        and (best_score - second[1]) <= ANTI_DOMINANCE_DELTA
        and second[3] > best_overlap + 0.05
    ):
        best_id, best_score, best_reasons, best_overlap = second[0], second[1], second[2], second[3]
        best_reasons = list(best_reasons) + ["anti_dominance:prefer_construct_overlap_over_llm_fallback"]

    spec = by_id[best_id]
    execution_contract = build_recipe_execution_contract(spec, intent=intent)
    retrieval_candidates = [
        RecipeStoreCandidateSummary(
            recipe_id=rid,
            title=(by_id[rid].title if by_id.get(rid) else "")[:240],
            retrieval_score=round(sc, 3),
            reasons=[str(x) for x in reasons[:8]],
        )
        for rid, sc, reasons, _ in scored[:10]
    ]
    result = RecipeSelectionResult(
        recipe_id=best_id,
        score=round(best_score, 3),
        reasons=best_reasons,
        candidate_ids_tried=[x[0] for x in scored[:8]],
        execution_contract=execution_contract,
        retrieval_candidates=retrieval_candidates,
    )
    logger.info_structured(
        "Recipe selected for intent",
        extra_fields={
            "jira_id": jira_id,
            "recipe_id": best_id,
            "score": best_score,
            "overlap": best_overlap,
        },
    )
    return spec, result


def maybe_override_selection_for_table_alignment(
    current_recipe_id: str,
    intent: IntentRecord,
    evidence_text: str,
) -> Optional[str]:
    """
    Optional Jira-pipeline hook: suggest table_semantics_reference when alignment intent is strong.
    Returns new recipe_id or None to keep current.
    """
    if "table_alignment" not in intent.anti_fallback_signals and "table" not in intent.required_dita_patterns:
        return None
    if "table" not in evidence_text.lower():
        return None
    by_id = _spec_by_id()
    if "table_semantics_reference" in by_id and current_recipe_id == LLM_FALLBACK_ID:
        return "table_semantics_reference"
    return None
