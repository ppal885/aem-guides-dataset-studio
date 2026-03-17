"""AI planner service - domain classification, scenario expansion, content extraction, invocation planning."""
import json
from pathlib import Path
from typing import Optional

from app.core.agentic_config import agentic_config
from app.services.feedback_aggregation_service import load_prompt_overrides
from app.services.llm_service import generate_json, is_llm_available
from app.services.scenario_scoring_service import filter_scenarios_by_score
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge
from app.services.feedback_analysis_service import analyze_validation_errors, format_error_analysis_for_prompt
from app.services.feedback_loop_placeholder import get_aggregated_feedback_for_prompt
from app.core.schemas_ai import (
    ScenarioSet,
    Scenario,
    ScenarioType,
    GeneratorInvocationPlan,
    SelectedRecipe,
    ContentFromEvidenceSchema,
)
from app.core.structured_logging import get_structured_logger
from app.utils.evidence_extractor import pre_extract_representative_xml, _looks_like_dita

logger = get_structured_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"

REPRESENTATIVE_XML_MAX_ITEMS = 6
REPRESENTATIVE_XML_MAX_CHARS_PER_ITEM = 8000


def _post_filter_scenarios_for_min_repro(scenarios: list[Scenario], evidence_pack: dict) -> list[Scenario]:
    """
    If evidence mentions minimal reproduction or Representative Sample, deprioritize or drop STRESS scenarios.
    S1_MIN_REPRO is already first (inserted earlier).
    """
    if not scenarios:
        return scenarios
    primary = evidence_pack.get("primary") or {}
    desc = (primary.get("description") or "").lower()
    summary = (primary.get("summary") or "").lower()
    text = f"{summary} {desc}"
    if "minimal reproduction" in text or "representative sample" in text:
        first = [s for s in scenarios if s.id == "S1_MIN_REPRO"][:1]
        rest = [s for s in scenarios if s.id != "S1_MIN_REPRO" and s.type != ScenarioType.STRESS][:4]
        return (first or scenarios[:1]) + rest
    return scenarios


def _find_minimal_alternative(candidates_list: list[dict], exclude_id: str) -> Optional[str]:
    """Find a candidate with output_scale=minimal, excluding exclude_id."""
    for c in candidates_list:
        rid = c.get("id")
        if not rid or rid == exclude_id:
            continue
        scale = (c.get("output_scale") or "").lower()
        if scale == "minimal":
            return rid
    return None


def _validate_and_merge_representative_xml(
    pre_extracted: list[str],
    llm_extracted: list[str],
) -> list[str]:
    """
    Merge pre-extracted (trusted) with LLM-extracted. Prefer pre-extracted.
    Validate: DITA-like tags, max items, max chars. Reject non-DITA snippets.
    """
    out: list[str] = []
    seen: set[str] = set()
    for s in pre_extracted + llm_extracted:
        if not s or not isinstance(s, str):
            continue
        s = s.strip()[:REPRESENTATIVE_XML_MAX_CHARS_PER_ITEM]
        if not s or not _looks_like_dita(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= REPRESENTATIVE_XML_MAX_ITEMS:
            break
    return out


async def generate_content_from_evidence(
    evidence_pack: dict,
    scenario: Scenario,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> dict:
    """Extract structured content from Jira evidence for use in DITA generation."""
    if not is_llm_available():
        primary = evidence_pack.get("primary") or {}
        summary = (primary.get("summary") or "Issue")[:50]
        return {
            "content_titles": [f"Reproduction: {summary}"],
            "content_shortdescs": [f"Minimal reproduction for: {summary}"],
            "content_steps": ["Open the map/topic in AEM Guides", "Verify the issue reproduces"],
            "content_body_snippets": [f"Content for {summary}"],
        }
    prompt = _load_prompt("content_from_evidence")
    if not prompt:
        return {"content_titles": [], "content_shortdescs": [], "content_steps": [], "content_body_snippets": []}
    primary = evidence_pack.get("primary") or {}
    pre_extracted = pre_extract_representative_xml(
        primary,
        max_items=REPRESENTATIVE_XML_MAX_ITEMS,
        max_chars_per_item=REPRESENTATIVE_XML_MAX_CHARS_PER_ITEM,
    )
    evidence_text = json.dumps(primary, indent=2)[:12000]
    scenario_text = json.dumps(
        {"title": scenario.title, "description": scenario.description},
        indent=2,
    )
    # RAG: DITA spec and structure to reduce hallucination when extracting representative XML
    query_text = f"{primary.get('summary', '')} {primary.get('description', '')}"[:500]
    dita_block = ""
    try:
        dita_chunks = retrieve_dita_knowledge(query_text, k=4)
        if dita_chunks:
            _tc = lambda c: (c.get("text_content") or "")
            texts = [" ".join(t) if isinstance(t, list) else str(t)[:600] for t in (_tc(c) for c in dita_chunks)]
            dita_block = "DITA KNOWLEDGE (follow strictly; do not invent elements):\n" + "\n---\n".join(texts) + "\n\n"
        graph_block = retrieve_dita_graph_knowledge(element_hint=query_text)
        if graph_block:
            dita_block += "DITA STRUCTURE (nesting and attributes):\n" + graph_block + "\n\n"
    except Exception:
        pass
    pre_extracted_hint = ""
    if pre_extracted:
        pre_extracted_hint = (
            f"\n\nPRE-EXTRACTED REPRESENTATIVE SAMPLE (use these; do NOT invent):\n"
            f"{json.dumps(pre_extracted[:3], indent=2)}\n"
            "Include these in representative_xml. Do NOT hallucinate or invent XML."
        )
    user = f"{dita_block}Evidence:\n{evidence_text}\n\nScenario:\n{scenario_text}{pre_extracted_hint}\n\nOutput JSON only:"
    result = await generate_json(
        prompt, user, max_tokens=800, step_name="content_extractor", trace_id=trace_id, jira_id=jira_id
    )
    raw = {
        "topic_titles": result.get("topic_titles", result.get("content_titles", []))[:5],
        "shortdescs": result.get("shortdescs", result.get("content_shortdescs", []))[:5],
        "steps": result.get("steps", result.get("content_steps", []))[:10],
        "body_snippets": result.get("body_snippets", result.get("content_body_snippets", []))[:5],
        "representative_xml": result.get("representative_xml", [])[:6],
    }
    try:
        validated = ContentFromEvidenceSchema.model_validate(raw)
    except Exception:
        validated = ContentFromEvidenceSchema.model_validate({})
    llm_xml = validated.representative_xml if isinstance(validated.representative_xml, list) else []
    llm_xml = [str(x)[:REPRESENTATIVE_XML_MAX_CHARS_PER_ITEM] for x in llm_xml if x]
    representative_xml = _validate_and_merge_representative_xml(pre_extracted, llm_xml)
    return {
        "content_titles": list(validated.topic_titles)[:5],
        "content_shortdescs": list(validated.shortdescs)[:5],
        "content_steps": list(validated.steps)[:10],
        "content_body_snippets": list(validated.body_snippets)[:5],
        "representative_xml": representative_xml,
    }


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    base = path.read_text(encoding="utf-8") if path.exists() else ""
    if not base or not agentic_config.prompt_overrides_enabled:
        return base
    overrides = load_prompt_overrides()
    prompt_overrides = overrides.get(name, {})
    if not prompt_overrides:
        return base
    parts = [base]
    deprioritize = prompt_overrides.get("deprioritize_recipes", [])
    if deprioritize:
        parts.append(f"\n\nDEPRIORITIZE (avoid unless evidence strongly matches): {', '.join(deprioritize[:5])}.")
    append_rules = prompt_overrides.get("append_rules", [])
    if append_rules:
        parts.append("\n\nCROSS-RUN FEEDBACK (apply these):")
        for r in append_rules[:5]:
            parts.append(f"\n- {r}")
    return "".join(parts)


async def classify_domain(
    evidence_pack: dict,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> dict:
    """Classify domain from evidence pack."""
    if not is_llm_available():
        logger.info_structured("LLM mock mode: returning default domain", extra_fields={"jira_id": jira_id})
        return {"domain": "general", "confidence": 0.5, "keywords": []}
    prompt = _load_prompt("domain_classifier")
    if not prompt:
        return {"domain": "general", "confidence": 0.5, "keywords": []}

    primary = evidence_pack.get("primary") or {}
    similar = evidence_pack.get("similar") or []
    evidence_text = json.dumps({"primary": primary, "similar": similar[:3]}, indent=2)[:8000]

    # RAG: DITA spec to constrain domain (conref, keyscope, conditional, etc.)
    query_text = f"{primary.get('summary', '')} {primary.get('description', '')}"[:500]
    dita_block = ""
    try:
        dita_chunks = retrieve_dita_knowledge(query_text, k=3)
        if dita_chunks:
            _tc = lambda c: (c.get("text_content") or "")
            texts = [" ".join(t) if isinstance(t, list) else str(t)[:400] for t in (_tc(c) for c in dita_chunks)]
            dita_block = "DITA KNOWLEDGE (domain must align with valid DITA features):\n" + "\n---\n".join(texts) + "\n\n"
    except Exception:
        pass

    user = f"{dita_block}Evidence:\n{evidence_text}\n\nOutput JSON only:"
    result = await generate_json(prompt, user, step_name="domain_classifier", trace_id=trace_id, jira_id=jira_id)
    if not result or not isinstance(result, dict):
        return {"domain": "general", "confidence": 0.5, "keywords": []}
    domain = result.get("domain") or "general"
    confidence = result.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    keywords = result.get("keywords")
    if not isinstance(keywords, list):
        keywords = []
    return {"domain": domain, "confidence": float(confidence), "keywords": keywords}


async def expand_scenarios(
    evidence_pack: dict,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> ScenarioSet:
    """Expand evidence into ScenarioSet (max 5, always S1_MIN_REPRO)."""
    if not is_llm_available():
        primary = evidence_pack.get("primary") or {}
        summary = primary.get("summary", "Issue")[:80]
        logger.info_structured("LLM mock mode: returning default scenario", extra_fields={"jira_id": jira_id})
        return ScenarioSet(scenarios=[
            Scenario(id="S1_MIN_REPRO", type=ScenarioType.MIN_REPRO, title="Minimal Repro", description=f"Minimal reproduction for: {summary}", evidence_refs=[])
        ])
    prompt = _load_prompt("scenario_expander")
    if not prompt:
        return ScenarioSet(scenarios=[Scenario(id="S1_MIN_REPRO", type=ScenarioType.MIN_REPRO, title="Minimal Repro", description="Minimal reproduction", evidence_refs=[])])

    primary = evidence_pack.get("primary") or {}
    query_text = f"{primary.get('summary', '')} {primary.get('description', '')} {primary.get('description_excerpt', '')}"
    dita_chunks = retrieve_dita_knowledge(query_text, k=4)
    dita_block = ""
    if dita_chunks:
        _tc = lambda c: (c.get("text_content") or "")
        texts = [" ".join(t) if isinstance(t, list) else str(t)[:800] for t in (_tc(c) for c in dita_chunks)]
        dita_block = "DITA KNOWLEDGE (use for valid scenario design):\n" + "\n---\n".join(texts) + "\n\n"
    graph_block = retrieve_dita_graph_knowledge(element_hint=query_text)
    if graph_block:
        dita_block += "DITA STRUCTURE (nesting and attributes):\n" + graph_block + "\n\n"

    evidence_text = json.dumps(evidence_pack, indent=2)[:12000]
    user = f"{dita_block}Evidence:\n{evidence_text}\n\nOutput JSON only:"
    result = await generate_json(prompt, user, max_tokens=1500, step_name="scenario_expander", trace_id=trace_id, jira_id=jira_id)

    scenarios = []
    for s in (result.get("scenarios", []) if result and isinstance(result, dict) else [])[:5]:
        try:
            type_val = (s.get("type") or "MIN_REPRO").upper().replace(" ", "_")
            stype = ScenarioType(type_val) if type_val in [e.value for e in ScenarioType] else ScenarioType.MIN_REPRO
            scenarios.append(Scenario(
                id=s.get("id", "S1_MIN_REPRO"),
                type=stype,
                title=s.get("title", ""),
                description=s.get("description", ""),
                evidence_refs=s.get("evidence_refs", []),
            ))
        except (ValueError, KeyError):
            scenarios.append(Scenario(id=s.get("id", "S1"), type=ScenarioType.MIN_REPRO, title=s.get("title", ""), description=s.get("description", ""), evidence_refs=s.get("evidence_refs", [])))

    if not scenarios or scenarios[0].id != "S1_MIN_REPRO":
        scenarios.insert(0, Scenario(id="S1_MIN_REPRO", type=ScenarioType.MIN_REPRO, title="Minimal Repro", description="Minimal reproduction case", evidence_refs=[]))

    scenarios = _post_filter_scenarios_for_min_repro(scenarios, evidence_pack)
    scenarios = filter_scenarios_by_score(scenarios[:5], evidence_pack)
    return ScenarioSet(scenarios=scenarios)


async def plan_for_scenario(
    evidence_pack: dict,
    scenario: Scenario,
    candidates: list[dict],
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    validation_errors: Optional[list[str]] = None,
    execution_warnings: Optional[list[str]] = None,
    excluded_recipe_ids: Optional[list[str]] = None,
    content_from_evidence: Optional[dict] = None,
) -> GeneratorInvocationPlan:
    """Plan generator invocations for a scenario from candidates only."""
    if not is_llm_available():
        recipes = []
        for c in (candidates or [])[:2]:
            spec = c.get("spec")
            if spec:
                rid = getattr(spec, "id", None) or (spec.get("id", "") if isinstance(spec, dict) else "")
                if rid and rid not in (excluded_recipe_ids or []):
                    recipes.append(SelectedRecipe(recipe_id=rid, params={}, evidence_used=[]))
        logger.info_structured("LLM mock mode: returning plan from top candidates", extra_fields={"jira_id": jira_id, "recipes": [r.recipe_id for r in recipes]})
        return GeneratorInvocationPlan(recipes=recipes, selection_rationale=[])
    prompt = _load_prompt("generator_invocation_planner")
    rules_path = PROMPTS_DIR / "jira_to_recipe_selection_rules.txt"
    if rules_path.exists():
        prompt = prompt.rstrip() + "\n\n" + rules_path.read_text(encoding="utf-8")
    if not prompt:
        return GeneratorInvocationPlan(recipes=[])

    excluded = set(excluded_recipe_ids or [])

    candidates_list = []
    for c in candidates:
        spec = c.get("spec")
        if spec:
            id_val = getattr(spec, "id", None) or (spec.get("id", "") if isinstance(spec, dict) else "")
            if id_val in excluded:
                continue
            title_val = getattr(spec, "title", None) or (spec.get("title", "") if isinstance(spec, dict) else "")
            desc_val = getattr(spec, "description", None) or (spec.get("description", "") if isinstance(spec, dict) else "")
            params_val = getattr(spec, "default_params", None) or (spec.get("default_params", {}) if isinstance(spec, dict) else {})
            tags_val = getattr(spec, "tags", None) or (spec.get("tags", []) if isinstance(spec, dict) else [])
            use_when_val = getattr(spec, "use_when", None) or (spec.get("use_when", []) if isinstance(spec, dict) else [])
            avoid_when_val = getattr(spec, "avoid_when", None) or (spec.get("avoid_when", []) if isinstance(spec, dict) else [])
            constructs_val = getattr(spec, "constructs", None) or (spec.get("constructs", []) if isinstance(spec, dict) else [])
            scenario_types_val = getattr(spec, "scenario_types", None) or (spec.get("scenario_types", []) if isinstance(spec, dict) else [])
            positive_negative_val = getattr(spec, "positive_negative", None) or (spec.get("positive_negative", "") if isinstance(spec, dict) else "")
            output_scale_val = getattr(spec, "output_scale", None) or (spec.get("output_scale", "") if isinstance(spec, dict) else "")
            candidates_list.append({
                "id": id_val,
                "title": title_val,
                "description": desc_val,
                "default_params": params_val,
                "tags": tags_val,
                "use_when": use_when_val,
                "avoid_when": avoid_when_val,
                "constructs": constructs_val,
                "scenario_types": scenario_types_val,
                "positive_negative": positive_negative_val,
                "output_scale": output_scale_val,
            })

    query_text = f"{scenario.title} {scenario.description} {json.dumps(evidence_pack.get('primary') or {})[:500]}"
    parts = []
    for c in candidates:
        spec = c.get("spec")
        if spec:
            t = getattr(spec, "title", None) or (spec.get("title", "") if isinstance(spec, dict) else "")
            d = getattr(spec, "description", None) or (spec.get("description", "") if isinstance(spec, dict) else "")
            parts.append(f"{t} {d}")
    if parts:
        query_text = f"{query_text} {' '.join(parts)}"
    dita_chunks = retrieve_dita_knowledge(query_text, k=4)
    dita_block = ""
    if dita_chunks:
        _tc = lambda c: (c.get("text_content") or "")
        texts = [" ".join(t) if isinstance(t, list) else str(t)[:800] for t in (_tc(c) for c in dita_chunks)]
        dita_block = "DITA KNOWLEDGE (use for valid scenario design):\n" + "\n---\n".join(texts) + "\n\n"
    graph_block = retrieve_dita_graph_knowledge(element_hint=query_text)
    if graph_block:
        dita_block += "DITA STRUCTURE (nesting and attributes):\n" + graph_block + "\n\n"

    evidence_text = json.dumps({"primary": evidence_pack.get("primary"), "similar": evidence_pack.get("similar", [])[:2]}, indent=2)[:12000]
    scenario_text = json.dumps({"id": scenario.id, "type": scenario.type, "title": scenario.title, "description": scenario.description}, indent=2)
    candidates_text = json.dumps(candidates_list, indent=2)

    feedback_parts = []
    if validation_errors:
        feedback_parts.append(f"VALIDATION FEEDBACK (fix these issues in your next plan):\n" + "\n".join(f"- {e}" for e in validation_errors))
        analysis = analyze_validation_errors(validation_errors)
        error_analysis_block = format_error_analysis_for_prompt(analysis)
        if error_analysis_block:
            feedback_parts.append(f"ERROR ANALYSIS:\n{error_analysis_block}")
    if execution_warnings:
        feedback_parts.append(f"EXECUTION WARNINGS (avoid these recipes/params):\n" + "\n".join(f"- {w}" for w in execution_warnings))
    if excluded:
        feedback_parts.append(f"EXCLUDED RECIPES (do NOT use): {', '.join(sorted(excluded))}")
    feedback_block = "\n\n".join(feedback_parts) if feedback_parts else ""

    user = f"{dita_block}Evidence:\n{evidence_text}\n\nScenario:\n{scenario_text}\n\nCANDIDATES (choose ONLY from these):\n{candidates_text}\n\n"
    if content_from_evidence:
        content_text = json.dumps(content_from_evidence, indent=2)[:2000]
        user += f"CONTENT FROM EVIDENCE (include in params for production-ready output):\n{content_text}\n\n"
    if jira_id:
        try:
            from app.db.session import SessionLocal
            session = SessionLocal()
            try:
                historical = get_aggregated_feedback_for_prompt(session, jira_id=jira_id, limit=10)
                if historical:
                    user += historical
            finally:
                session.close()
        except Exception:
            pass
    if feedback_block:
        user += f"{feedback_block}\n\n"
    user += "Output JSON only:"
    result = await generate_json(prompt, user, step_name="planner", trace_id=trace_id, jira_id=jira_id)

    if not result or not isinstance(result, dict):
        result = {"recipes": [], "selection_rationale": []}

    valid_ids = {c.get("id") for c in candidates_list if c.get("id")}
    spec_by_id = {c.get("recipe_id"): c.get("spec") for c in candidates if c.get("recipe_id") and c.get("spec")}
    candidates_by_id = {c.get("recipe_id"): c for c in candidates if c.get("recipe_id")}
    evidence_lower = (evidence_text or "").lower()
    recipes = []
    selection_rationale = []
    for r in result.get("recipes", []):
        rid = r.get("recipe_id", "")
        if not rid or rid not in valid_ids:
            if rid:
                logger.info_structured(
                    "Dropped invalid recipe_id from plan",
                    extra_fields={"recipe_id": rid, "valid_ids": list(valid_ids)[:10]},
                )
            continue
        cand = candidates_by_id.get(rid)
        spec = cand.get("spec") if cand else spec_by_id.get(rid)
        if spec:
            avoid_when = getattr(spec, "avoid_when", None) or []
            avoid_text = " ".join(str(a).lower() for a in avoid_when)
            if avoid_text and any(kw in evidence_lower and kw in avoid_text for kw in ("keydef", "keyref", "nested", "conref")):
                logger.info_structured(
                    "Planner guard: dropped recipe (evidence conflicts with avoid_when)",
                    extra_fields={"recipe_id": rid, "avoid_when": avoid_when[:3]},
                )
                continue
            output_scale = (getattr(spec, "output_scale", "") or "").lower()
            if scenario.type == ScenarioType.MIN_REPRO and output_scale in ("stress", "large"):
                minimal_alt = _find_minimal_alternative(candidates_list, rid)
                if minimal_alt:
                    original_rid = rid
                    rid = minimal_alt
                    r = {"recipe_id": rid, "params": r.get("params", {}), "evidence_used": r.get("evidence_used", [])}
                    logger.info_structured(
                        "Planner guard: swapped stress/large for minimal recipe",
                        extra_fields={"original": original_rid, "swapped_to": rid},
                    )
                else:
                    logger.warning_structured(
                        "Planner guard: MIN_REPRO with stress/large recipe, no minimal alternative",
                        extra_fields={"recipe_id": rid, "output_scale": output_scale},
                    )
        recipes.append(SelectedRecipe(
            recipe_id=rid,
            params=r.get("params", {}),
            evidence_used=r.get("evidence_used", []),
        ))
        rationale = r.get("selection_rationale", "")
        if rationale:
            selection_rationale.append(rationale)

    if not recipes and content_from_evidence and content_from_evidence.get("representative_xml"):
        representative_xml = content_from_evidence.get("representative_xml")
        if isinstance(representative_xml, list) and representative_xml:
            logger.info_structured(
                "Planner returned no recipes; using evidence_to_dita fallback",
                extra_fields={"jira_id": jira_id, "snippet_count": len(representative_xml)},
            )
            plan = GeneratorInvocationPlan(
                recipes=[SelectedRecipe(recipe_id="evidence_to_dita", params={"representative_xml": representative_xml}, evidence_used=["representative_xml"])],
                selection_rationale=["Fallback: no candidate matched; Representative Sample XML present"],
            )
            return GeneratorInvocationPlan.model_validate(plan.model_dump())

    plan = GeneratorInvocationPlan(recipes=recipes, selection_rationale=selection_rationale)
    return GeneratorInvocationPlan.model_validate(plan.model_dump())
