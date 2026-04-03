"""
Recipe pipeline orchestrator - multi-stage deterministic flow.

Runs: normalize evidence -> classify mechanism -> classify pattern ->
      route recipe -> validate -> build plan.
"""
import os
from typing import Optional
from uuid import uuid4

from app.core.agentic_config import agentic_config
from app.core.schemas_pipeline import (
    IssueEvidence,
    MechanismClassification,
    PatternClassification,
    RecipeSelection,
    RecipeSelectionOutput,
    RejectedRecipe,
    normalize_evidence_from_pack,
)
from app.core.schemas_ai import Scenario, ScenarioSet, ScenarioType, GeneratorInvocationPlan, SelectedRecipe
from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.services.mechanism_classifier_service import classify_mechanism
from app.services.pattern_classifier_service import classify_pattern
from app.services.recipe_router import route_recipe
from app.services.recipe_execution_contract import build_recipe_execution_contract
from app.services.recipe_scoring_service import ROUTE_TABLE, evidence_mentions_novel_construct
from app.services.anti_blend_validator import validate_recipe_family_match
from app.services.ai_planner_service import generate_content_from_evidence
from app.utils.evidence_extractor import pre_extract_representative_xml
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


async def run_recipe_pipeline(
    evidence_pack: dict,
    jira_id: str,
    trace_id: Optional[str] = None,
    use_llm_classification: bool = True,
    force_recipe_id: Optional[str] = None,
) -> dict:
    """
    Run deterministic recipe pipeline. Returns plan-compatible result with
    evidence_pack, scenario_set (single S1_MIN_REPRO), per_scenario, domain, pipeline_stages.
    When force_recipe_id is set, skips mechanism/pattern classification and uses that recipe.
    """
    trace_id = trace_id or str(uuid4())
    primary = evidence_pack.get("primary") or {}
    issue_evidence = normalize_evidence_from_pack(primary, jira_id)

    if force_recipe_id:
        scenario = Scenario(
            id="S1_MIN_REPRO",
            type=ScenarioType.MIN_REPRO,
            title="Minimal Repro",
            description=f"Minimal reproduction for: {primary.get('summary', 'Issue')[:80]}",
            evidence_refs=[],
        )
        content_from_evidence = await generate_content_from_evidence(
            evidence_pack, scenario, trace_id=trace_id, jira_id=jira_id
        )
        params: dict = {}
        rep_xml = content_from_evidence.get("representative_xml") or []
        pre_extracted = pre_extract_representative_xml(primary, max_items=6, max_chars_per_item=8000)
        if rep_xml or pre_extracted:
            params["representative_xml"] = rep_xml if rep_xml else pre_extracted
        plan = GeneratorInvocationPlan(
            recipes=[
                SelectedRecipe(
                    recipe_id=force_recipe_id,
                    params=params,
                    evidence_used=["force_recipe"],
                )
            ],
            selection_rationale=[f"force_recipe:{force_recipe_id}"],
        )
        mechanism_dump = {"selected_feature": "force", "confidence": 1.0, "evidence": [], "rejected_features": [], "assumptions": ["force_recipe_id"], "unknowns": []}
        pattern_dump = {"selected_pattern": "force", "confidence": 1.0}
        selection_dump = {"selected_recipe": force_recipe_id, "selected_feature": "force", "selected_pattern": "force", "route_reason": f"force_recipe:{force_recipe_id}"}
        scenario_set = ScenarioSet(scenarios=[scenario])
        per_scenario = {
            "S1_MIN_REPRO": {
                "candidates": [],
                "plan": plan.model_dump(),
                "pipeline_stages": {
                    "mechanism": mechanism_dump,
                    "pattern": pattern_dump,
                    "selection": selection_dump,
                },
            }
        }
        return {
            "evidence_pack": evidence_pack,
            "intent": evidence_pack.get("intent") or {},
            "scenario_set": scenario_set.model_dump(),
            "domain": "force",
            "per_scenario": per_scenario,
            "trace_id": trace_id,
            "pipeline_stages": {"mechanism": mechanism_dump, "pattern": pattern_dump, "selection": selection_dump},
            "recipe_selection_output": {"selected_recipe": force_recipe_id, "confidence": 1.0, "selection_reason": [f"force_recipe:{force_recipe_id}"], "rejected_recipes": []},
            "low_confidence": False,
        }

    # Stage 1: Mechanism classification
    mechanism: MechanismClassification = await classify_mechanism(
        issue_evidence,
        trace_id=trace_id,
        jira_id=jira_id,
        use_llm=use_llm_classification,
    )
    logger.info_structured(
        "Pipeline stage: mechanism",
        extra_fields={
            "selected_feature": mechanism.selected_feature,
            "confidence": mechanism.confidence,
        },
    )

    # Stage 2: Pattern classification
    pattern: PatternClassification = await classify_pattern(
        issue_evidence,
        mechanism.selected_feature,
        trace_id=trace_id,
        jira_id=jira_id,
        use_llm=use_llm_classification,
    )
    logger.info_structured(
        "Pipeline stage: pattern",
        extra_fields={
            "selected_pattern": pattern.selected_pattern,
            "confidence": pattern.confidence,
        },
    )

    # Stage 2.5: Confidence threshold check (log warning when below threshold)
    avg_confidence = (mechanism.confidence + pattern.confidence) / 2.0
    min_threshold = getattr(agentic_config, "min_confidence_threshold", 0.0)
    low_confidence = min_threshold > 0 and avg_confidence < min_threshold
    if low_confidence:
        logger.warning_structured(
            "low_confidence_classification",
            extra_fields={
                "avg_confidence": round(avg_confidence, 2),
                "min_threshold": min_threshold,
                "mechanism": mechanism.selected_feature,
                "pattern": pattern.selected_pattern,
            },
        )

    # Stage 3: Deterministic recipe routing
    evidence_text = (issue_evidence.raw_text or "") + " " + (issue_evidence.summary or "") + " " + (issue_evidence.description or "")
    selection: RecipeSelection = route_recipe(
        mechanism.selected_feature,
        pattern.selected_pattern,
        evidence_text=evidence_text or None,
    )

    # Stage 4: Anti-blending validation
    validation = validate_recipe_family_match(
        mechanism.selected_feature,
        selection.selected_recipe,
    )
    if not validation.valid:
        logger.warning_structured(
            "Pipeline: validation failed, using fallback",
            extra_fields={"reason": validation.reason},
        )
        selection = route_recipe("keyref", "basic_key_resolution", evidence_text=None)

    # Stage 5: Content from evidence (for params)
    scenario = Scenario(
        id="S1_MIN_REPRO",
        type=ScenarioType.MIN_REPRO,
        title="Minimal Repro",
        description=f"Minimal reproduction for: {primary.get('summary', 'Issue')[:80]}",
        evidence_refs=[],
    )
    content_from_evidence = await generate_content_from_evidence(
        evidence_pack, scenario, trace_id=trace_id, jira_id=jira_id
    )

    # Build params: include representative_xml when present; content_* for task/concept recipes
    params: dict = {}
    rep_xml = content_from_evidence.get("representative_xml") or []
    pre_extracted = pre_extract_representative_xml(primary, max_items=6, max_chars_per_item=8000)
    if rep_xml or pre_extracted:
        params["representative_xml"] = rep_xml if rep_xml else pre_extracted
    # Content from evidence (steps, titles, shortdescs) for task_topics and other content recipes
    for key in ("content_steps", "content_titles", "content_shortdescs", "content_body_snippets"):
        val = content_from_evidence.get(key)
        if val and isinstance(val, list) and len(val) > 0:
            params[key] = val[:10] if key == "content_steps" else val[:5]

    # Reference/task topics: include choicetable when evidence mentions choicetable
    ev_lower = (evidence_text or "").lower()
    if ("choicetable" in ev_lower or "choice table" in ev_lower) and selection.selected_recipe in ("reference_topics", "task_topics"):
        params["include_choicetable"] = True

    # Table alignment reference: pass Jira summary for topic title context
    if selection.selected_recipe == "table_semantics_reference":
        summ = (primary.get("summary") or "").strip()
        if summ:
            params["issue_summary"] = summ[:300]

    # Override: llm_generated_dita when evidence mentions novel construct or low-confidence generic fallback
    if evidence_mentions_novel_construct(evidence_text or ""):
        selection = RecipeSelection(
            selected_feature=mechanism.selected_feature,
            selected_pattern=pattern.selected_pattern,
            selected_recipe="llm_generated_dita",
            route_reason="fallback:novel_construct",
            cross_feature_blocked=False,
        )
        params = {
            "evidence_pack": evidence_pack,
            "representative_xml": rep_xml if rep_xml else pre_extracted,
            "trace_id": trace_id,
            "jira_id": jira_id,
        }
    elif selection.selected_recipe == "keys.keydef_basic" and low_confidence:
        # Confidence-based self-correction: try evidence similarity with lower threshold before LLM
        similar_recipe = None
        try:
            from app.services.feedback_aggregation_service import load_routing_overrides
            from app.services.feedback_evidence_service import find_similar_feedback_recipe

            overrides = load_routing_overrides()
            pairs = overrides.get("evidence_similarity_pairs") or []
            result = find_similar_feedback_recipe(evidence_text or "", pairs, threshold=0.15)
            if result:
                similar_recipe, sim_score = result
        except Exception:
            pass
        if similar_recipe:
            feature, pattern = None, None
            for (f, p), rid in ROUTE_TABLE.items():
                if rid == similar_recipe:
                    feature, pattern = f, p
                    break
            if not feature:
                feature, pattern = "keyref", "basic_key_resolution"
            selection = RecipeSelection(
                selected_feature=feature,
                selected_pattern=pattern,
                selected_recipe=similar_recipe,
                route_reason=f"fallback:low_confidence_similar_feedback:{round(sim_score, 2)}",
                cross_feature_blocked=False,
            )
            logger.info_structured(
                "Low-confidence: using similar feedback recipe",
                extra_fields={"recipe": similar_recipe, "similarity": round(sim_score, 2)},
            )
        else:
            selection = RecipeSelection(
                selected_feature=mechanism.selected_feature,
                selected_pattern=pattern.selected_pattern,
                selected_recipe="llm_generated_dita",
                route_reason="fallback:low_confidence_generic",
                cross_feature_blocked=False,
            )
            params = {
                "evidence_pack": evidence_pack,
                "representative_xml": rep_xml if rep_xml else pre_extracted,
                "trace_id": trace_id,
                "jira_id": jira_id,
            }
    # Fallback: evidence_to_dita when no suitable recipe and representative_xml present
    elif not validation.valid and (rep_xml or pre_extracted):
        selection = RecipeSelection(
            selected_feature=mechanism.selected_feature,
            selected_pattern=pattern.selected_pattern,
            selected_recipe="evidence_to_dita",
            route_reason="fallback:representative_xml present",
            cross_feature_blocked=False,
        )
        params = {"representative_xml": rep_xml if rep_xml else pre_extracted}

    # Optional: promote table_semantics_reference when intent matches alignment + table (skips generic LLM)
    intent_for_contract = None
    if os.getenv("PIPELINE_INTENT_ENHANCEMENT", "false").lower() in ("true", "1", "yes"):
        if (
            selection.selected_recipe == "llm_generated_dita"
            and not evidence_mentions_novel_construct(evidence_text or "")
        ):
            from app.services.intent_analysis_service import analyze_intent_sync
            from app.services.recipe_selector_service import maybe_override_selection_for_table_alignment

            intent_for_contract = analyze_intent_sync(evidence_text or "")
            alt_id = maybe_override_selection_for_table_alignment(
                selection.selected_recipe, intent_for_contract, evidence_text or ""
            )
            if alt_id:
                for (f, p), rid in ROUTE_TABLE.items():
                    if rid == alt_id:
                        selection = RecipeSelection(
                            selected_feature=f,
                            selected_pattern=p,
                            selected_recipe=alt_id,
                            route_reason="intent_enhancement:table_alignment",
                            cross_feature_blocked=selection.cross_feature_blocked,
                        )
                        params = {}
                        summ = (primary.get("summary") or "").strip()
                        if summ:
                            params["issue_summary"] = summ[:300]
                        break

    specs_by_id = {s.id: s for s in discover_recipe_specs() if isinstance(s, RecipeSpec)}
    selected_spec = specs_by_id.get(selection.selected_recipe)
    execution_contract_out = None
    if (
        selection.selected_recipe == "llm_generated_dita"
        and selected_spec
        and isinstance(params, dict)
    ):
        c = build_recipe_execution_contract(selected_spec, intent=intent_for_contract)
        execution_contract_out = c.model_dump(mode="json")
        params["recipe_execution_contract"] = execution_contract_out

    plan = GeneratorInvocationPlan(
        recipes=[
            SelectedRecipe(
                recipe_id=selection.selected_recipe,
                params=params,
                evidence_used=[mechanism.selected_feature, pattern.selected_pattern],
            )
        ],
        selection_rationale=[selection.route_reason],
    )

    confidence = (mechanism.confidence + pattern.confidence) / 2.0
    selection_reasons = [selection.route_reason]
    if mechanism.evidence:
        for e in mechanism.evidence[:2]:
            if isinstance(e, str):
                selection_reasons.append(e)
            elif isinstance(e, list):
                selection_reasons.append(" ".join(str(x) for x in e))
            else:
                selection_reasons.append(str(e))
    if selection.selected_recipe == "keyref_nested_keydef_chain_map_to_map_to_topic":
        selection_reasons.insert(
            0,
            "Jira primarily describes nested keydef chain resolution across outer map -> intermediate keymap -> keyword/topic source; DITA-OT resolves correctly but Web Editor author/preview does not",
        )
    feature_to_recipe: dict[str, str] = {}
    for (f, _), rid in ROUTE_TABLE.items():
        if f not in feature_to_recipe:
            feature_to_recipe[f] = rid
    rejected = [
        RejectedRecipe(
            recipe=feature_to_recipe.get(f, f),
            reason=f"Jira is not primarily about {f}",
        )
        for f in mechanism.rejected_features[:5]
    ]
    recipe_selection_output = RecipeSelectionOutput(
        selected_recipe=selection.selected_recipe,
        confidence=confidence,
        selection_reason=selection_reasons,
        rejected_recipes=rejected,
        execution_contract=execution_contract_out,
    )

    scenario_set = ScenarioSet(scenarios=[scenario])
    per_scenario = {
        "S1_MIN_REPRO": {
            "candidates": [],
            "plan": plan.model_dump(),
            "pipeline_stages": {
                "mechanism": mechanism.model_dump(),
                "pattern": pattern.model_dump(),
                "selection": selection.model_dump(),
            },
        }
    }

    return {
        "evidence_pack": evidence_pack,
        "intent": evidence_pack.get("intent") or {},
        "scenario_set": scenario_set.model_dump(),
        "domain": mechanism.selected_feature,
        "per_scenario": per_scenario,
        "trace_id": trace_id,
        "pipeline_stages": {
            "mechanism": mechanism.model_dump(),
            "pattern": pattern.model_dump(),
            "selection": selection.model_dump(),
        },
        "recipe_selection_output": recipe_selection_output.model_dump(),
        "low_confidence": low_confidence,
    }
