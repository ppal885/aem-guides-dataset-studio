"""Cross-run feedback aggregation for learning and prompt refinement."""
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.run_feedback_models import RunFeedback
from app.db.jira_models import JiraIssue
from app.services.keyword_extraction_service import _extract_keywords_simple


def _get_evidence_for_jira(session: Session, jira_id: str | None) -> str:
    """Get evidence text from JiraIssue for jira_id."""
    if not jira_id:
        return ""
    row = session.query(JiraIssue).filter(JiraIssue.issue_key == jira_id).first()
    if not row:
        return ""
    parts = []
    if row.summary:
        parts.append(str(row.summary)[:2000])
    if row.description:
        parts.append(str(row.description)[:3000])
    if row.text_for_search:
        parts.append(str(row.text_for_search)[:1000])
    return " ".join(parts).strip() if parts else ""


def aggregate_feedback_insights(
    session: Session,
    limit: int = 200,
    jira_id: str | None = None,
) -> dict[str, Any]:
    """
    Aggregate RunFeedback across runs to identify patterns.
    Returns insights for prompt refinement and recipe deprioritization.
    Includes wrong-recipe corrections from user feedback (thumbs_down + expected_recipe_id).
    """
    from sqlalchemy import or_

    q = session.query(RunFeedback).filter(
        or_(
            RunFeedback.eval_metrics.isnot(None),
            RunFeedback.user_rating.in_(("thumbs_down", "wrong_recipe")),
            RunFeedback.expected_recipe_id.isnot(None),
            RunFeedback.suggested_recipe_id.isnot(None),
        )
    )
    if jira_id:
        q = q.filter(RunFeedback.jira_id == jira_id)
    rows = q.order_by(RunFeedback.created_at.desc()).limit(limit).all()

    recipe_failures = defaultdict(lambda: {"count": 0, "scenario_types": defaultdict(int), "error_patterns": defaultdict(int)})
    scenario_failures = defaultdict(int)
    error_category_counts = defaultdict(int)
    validation_rate = {"passed": 0, "failed": 0}

    for row in rows:
        try:
            metrics = json.loads(row.eval_metrics or "{}")
            passed = metrics.get("validation_passed", False)
            if passed:
                validation_rate["passed"] += 1
            else:
                validation_rate["failed"] += 1

            scenario_type = metrics.get("scenario_type") or "unknown"
            if not passed:
                scenario_failures[scenario_type] += 1

            recipes = metrics.get("recipes_used", [])
            if not passed:
                for r in recipes:
                    recipe_failures[r]["count"] += 1
                    recipe_failures[r]["scenario_types"][scenario_type] += 1
                    for ec in metrics.get("error_categories", []):
                        if ec:
                            recipe_failures[r]["error_patterns"][ec] += 1

            for ec in metrics.get("error_categories", []):
                if ec:
                    error_category_counts[ec] += 1
        except (json.JSONDecodeError, TypeError):
            continue

    total = validation_rate["passed"] + validation_rate["failed"]
    validation_rate_pct = (validation_rate["passed"] / total * 100) if total else 0

    recipe_risk = []
    for rid, data in recipe_failures.items():
        fail_count = recipe_failures[rid]["count"]
        if fail_count >= 2:
            top_scenarios = sorted(
                data["scenario_types"].items(),
                key=lambda x: -x[1],
            )[:3]
            top_errors = sorted(
                data["error_patterns"].items(),
                key=lambda x: -x[1],
            )[:3]
            recipe_risk.append({
                "recipe_id": rid,
                "failure_count": fail_count,
                "top_scenario_types": [s[0] for s in top_scenarios],
                "top_error_patterns": [e[0] for e in top_errors],
            })

    recipe_risk.sort(key=lambda x: -x["failure_count"])

    wrong_recipe_corrections = []
    for row in rows:
        if row.expected_recipe_id:
            recipes_used = []
            if row.recipes_used:
                try:
                    recipes_used = json.loads(row.recipes_used) if isinstance(row.recipes_used, str) else row.recipes_used
                except (json.JSONDecodeError, TypeError):
                    pass
            elif row.eval_metrics:
                try:
                    metrics = json.loads(row.eval_metrics or "{}")
                    recipes_used = metrics.get("recipes_used", [])
                except (json.JSONDecodeError, TypeError):
                    pass
            recipe_used = recipes_used[0] if recipes_used else None
            evidence_text = _get_evidence_for_jira(session, row.jira_id) if row.jira_id else ""
            wrong_recipe_corrections.append({
                "jira_id": row.jira_id,
                "run_id": row.run_id,
                "scenario_id": row.scenario_id,
                "recipe_used": recipe_used,
                "expected_recipe_id": row.expected_recipe_id,
                "selected_feature": row.selected_feature,
                "selected_pattern": row.selected_pattern,
                "evidence_text": evidence_text,
            })
        elif row.user_rating in ("thumbs_down", "wrong_recipe"):
            recipes_used = []
            if row.recipes_used:
                try:
                    recipes_used = json.loads(row.recipes_used) if isinstance(row.recipes_used, str) else row.recipes_used
                except (json.JSONDecodeError, TypeError):
                    pass
            elif row.eval_metrics:
                try:
                    metrics = json.loads(row.eval_metrics or "{}")
                    recipes_used = metrics.get("recipes_used", [])
                except (json.JSONDecodeError, TypeError):
                    pass
            evidence_text = _get_evidence_for_jira(session, row.jira_id) if row.jira_id else ""
            wrong_recipe_corrections.append({
                "jira_id": row.jira_id,
                "run_id": row.run_id,
                "scenario_id": row.scenario_id,
                "recipe_used": recipes_used[0] if recipes_used else None,
                "expected_recipe_id": None,
                "evidence_text": evidence_text,
                "selected_feature": row.selected_feature,
                "selected_pattern": row.selected_pattern,
            })
        elif row.suggested_recipe_id:
            pass  # Handled below: promote only when 2+ similar failures

    # Promote suggested_recipe_id when 2+ validation failures for same jira_id + suggested_recipe_id
    suggested_counts: dict[tuple[str, str], list[RunFeedback]] = defaultdict(list)
    for row in rows:
        if row.suggested_recipe_id and row.jira_id:
            key = (row.jira_id, row.suggested_recipe_id)
            suggested_counts[key].append(row)
    for (jid, suggested_rid), feedback_rows in suggested_counts.items():
        if len(feedback_rows) >= 2:
            row = feedback_rows[0]
            recipes_used = []
            if row.recipes_used:
                try:
                    recipes_used = json.loads(row.recipes_used) if isinstance(row.recipes_used, str) else row.recipes_used
                except (json.JSONDecodeError, TypeError):
                    pass
            elif row.eval_metrics:
                try:
                    metrics = json.loads(row.eval_metrics or "{}")
                    recipes_used = metrics.get("recipes_used", [])
                except (json.JSONDecodeError, TypeError):
                    pass
            evidence_text = _get_evidence_for_jira(session, jid)
            wrong_recipe_corrections.append({
                "jira_id": jid,
                "run_id": row.run_id,
                "scenario_id": row.scenario_id,
                "recipe_used": recipes_used[0] if recipes_used else None,
                "expected_recipe_id": suggested_rid,
                "evidence_text": evidence_text,
                "selected_feature": row.selected_feature,
                "selected_pattern": row.selected_pattern,
            })

    return {
        "validation_rate_pct": round(validation_rate_pct, 2),
        "total_runs": total,
        "passed": validation_rate["passed"],
        "failed": validation_rate["failed"],
        "scenario_failures": dict(scenario_failures),
        "error_category_counts": dict(error_category_counts),
        "recipe_risk": recipe_risk[:10],
        "wrong_recipe_corrections": wrong_recipe_corrections[:50],
        "recommendations": _build_recommendations(
            recipe_risk,
            error_category_counts,
            validation_rate_pct,
        ),
    }


def _build_recommendations(
    recipe_risk: list[dict],
    error_category_counts: dict[str, int],
    validation_rate_pct: float,
) -> list[str]:
    """Build actionable recommendations from aggregated data."""
    recs = []
    if validation_rate_pct < 80 and validation_rate_pct > 0:
        recs.append("Validation rate is below 80%. Consider improving DITA recipes or adding more error patterns to auto-fix.")
    for r in recipe_risk[:3]:
        if r["failure_count"] >= 3:
            recs.append(f"Recipe '{r['recipe_id']}' fails often. Consider deprioritizing for {r['top_scenario_types']} or fixing recipe.")
    top_errors = sorted(error_category_counts.items(), key=lambda x: -x[1])[:3]
    for e, c in top_errors:
        if c >= 2 and e:
            recs.append(f"Error pattern '{str(e)[:80]}' appears {c} times. Add to error analysis or auto-fix.")
    return recs


def _get_prompt_overrides_path() -> Path:
    """Path for prompt_overrides.json (in storage)."""
    from app.storage import get_storage
    return get_storage().base_path / "prompt_overrides.json"


def _get_routing_overrides_path() -> Path:
    """Path for routing_overrides.json (in storage)."""
    from app.storage import get_storage
    return get_storage().base_path / "routing_overrides.json"


def load_prompt_overrides() -> dict[str, Any]:
    """Load prompt overrides from JSON file. Returns empty dict if not found."""
    path = _get_prompt_overrides_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_prompt_overrides(overrides: dict[str, Any]) -> None:
    """Persist prompt overrides to JSON file."""
    path = _get_prompt_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2), encoding="utf-8")


# Seed overrides for known cases (e.g. GUIDES-43199: media issues misrouted to keys.keydef_basic)
# Use longer phrases first so "insert image and multimedia" matches before shorter substrings
_SEED_ROUTING_OVERRIDES: dict[str, Any] = {
    "jira_evidence_keywords": {
        "insert image and multimedia": "media_rich_content",
        "insert image": "media_rich_content",
        "multimedia": "media_rich_content",
        "media": "media_rich_content",
        "image": "media_rich_content",
        "images": "media_rich_content",
        "embed": "media_rich_content",
        "embedding": "media_rich_content",
        "video": "media_rich_content",
        "videos": "media_rich_content",
        "placeholder image": "media_rich_content",
        "placeholder images": "media_rich_content",
        "asset": "media_rich_content",
        "assets": "media_rich_content",
        "figure": "media_rich_content",
        "alt text": "media_rich_content",
    },
    "deprioritize_for_evidence": {
        "media": ["keys.keydef_basic"],
        "image": ["keys.keydef_basic"],
        "images": ["keys.keydef_basic"],
        "embed": ["keys.keydef_basic"],
        "video": ["keys.keydef_basic"],
    },
}


def load_routing_overrides() -> dict[str, Any]:
    """Load routing overrides from JSON file. Merges with seed when file exists. Returns seed when not found."""
    path = _get_routing_overrides_path()
    result = dict(_SEED_ROUTING_OVERRIDES)
    result.setdefault("evidence_similarity_pairs", [])
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            kw = loaded.get("jira_evidence_keywords") or {}
            result["jira_evidence_keywords"] = {**result.get("jira_evidence_keywords", {}), **kw}
            dep = result.get("deprioritize_for_evidence") or {}
            for k, v in (loaded.get("deprioritize_for_evidence") or {}).items():
                dep[k] = list(set(dep.get(k, [])) | set(v))
            result["deprioritize_for_evidence"] = dep
            result["evidence_similarity_pairs"] = loaded.get("evidence_similarity_pairs") or []
        except (json.JSONDecodeError, OSError):
            pass
    return result


def save_routing_overrides(overrides: dict[str, Any]) -> None:
    """Persist routing overrides to JSON file."""
    path = _get_routing_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2), encoding="utf-8")


# Heuristic: (recipe_used, expected_recipe_id) -> evidence keywords that should route to expected
_WRONG_RECIPE_KEYWORD_HINTS: dict[tuple[str | None, str], list[str]] = {
    ("keys.keydef_basic", "media_rich_content"): ["media", "image", "embed", "video", "placeholder"],
    ("keys.keydef_basic", "assets.image_basic"): ["image", "img"],
    ("keys.keydef_basic", "assets.image_with_alt"): ["image", "img", "alt"],
    ("keys.keydef_basic", "keys.keyref_image"): ["image", "keyref"],
}


def _build_routing_overrides_from_corrections(
    wrong_recipe_corrections: list[dict],
) -> dict[str, Any]:
    """Build routing_overrides from wrong_recipe_corrections. Uses extracted keywords from evidence when available."""
    jira_evidence_keywords: dict[str, str] = {}
    deprioritize_for_evidence: dict[str, list[str]] = defaultdict(list)
    evidence_similarity_pairs: list[dict] = []

    for c in wrong_recipe_corrections:
        recipe_used = c.get("recipe_used")
        expected = c.get("expected_recipe_id")
        evidence_text = c.get("evidence_text") or ""
        if not expected:
            continue

        # 1. Keywords: prefer extracted from evidence, else heuristics
        keywords = _WRONG_RECIPE_KEYWORD_HINTS.get((recipe_used, expected))
        if not keywords and expected == "media_rich_content" and recipe_used and recipe_used != expected:
            keywords = ["media", "image", "embed", "video"]
        if not keywords and evidence_text:
            keywords = _extract_keywords_simple(evidence_text, max_keywords=5)
        if keywords:
            for kw in keywords:
                kw_lower = kw.lower().strip()
                if kw_lower and kw_lower not in jira_evidence_keywords:
                    jira_evidence_keywords[kw_lower] = expected
                if recipe_used and kw_lower and recipe_used not in deprioritize_for_evidence.get(kw_lower, []):
                    deprioritize_for_evidence[kw_lower].append(recipe_used)

        # 2. Evidence similarity: store snippet for similarity-based override
        if evidence_text and len(evidence_similarity_pairs) < 100:
            evidence_similarity_pairs.append({
                "evidence_snippet": evidence_text[:800],
                "expected_recipe_id": expected,
            })

    return {
        "jira_evidence_keywords": jira_evidence_keywords,
        "deprioritize_for_evidence": dict(deprioritize_for_evidence),
        "evidence_similarity_pairs": evidence_similarity_pairs,
    }


def compute_prompt_overrides_from_feedback(
    session: Session,
    limit: int = 200,
    jira_id: str | None = None,
) -> dict[str, Any]:
    """
    Compute prompt overrides from RunFeedback aggregation.
    Returns override dict: {prompt_name: {append_rules: [...], deprioritize_recipes: [...]}}.
    Also writes routing_overrides.json from wrong_recipe_corrections.
    """
    insights = aggregate_feedback_insights(session, limit=limit, jira_id=jira_id)
    overrides = load_prompt_overrides()

    planner = overrides.setdefault("generator_invocation_planner", {})
    deprioritize = list(planner.get("deprioritize_recipes", []))
    append_rules = list(planner.get("append_rules", []))

    for r in insights.get("recipe_risk", [])[:5]:
        if r["failure_count"] >= 2 and r["recipe_id"] not in deprioritize:
            deprioritize.append(r["recipe_id"])

    wrong_corrections = insights.get("wrong_recipe_corrections", [])
    for c in wrong_corrections:
        rid = c.get("recipe_used")
        if rid and rid not in deprioritize:
            deprioritize.append(rid)
    prefer_recipes = list(planner.get("prefer_recipes", []))
    for c in wrong_corrections:
        exp = c.get("expected_recipe_id")
        if exp and exp not in prefer_recipes:
            prefer_recipes.append(exp)
    planner["prefer_recipes"] = prefer_recipes[:10]

    for rec in insights.get("recommendations", [])[:5]:
        if rec and rec not in append_rules:
            append_rules.append(rec)

    planner["deprioritize_recipes"] = deprioritize[:10]
    planner["append_rules"] = append_rules[:10]
    overrides["generator_invocation_planner"] = planner

    routing = _build_routing_overrides_from_corrections(wrong_corrections)
    if routing.get("jira_evidence_keywords") or routing.get("deprioritize_for_evidence") or routing.get("evidence_similarity_pairs"):
        existing = load_routing_overrides()
        existing["jira_evidence_keywords"] = {**existing.get("jira_evidence_keywords", {}), **routing.get("jira_evidence_keywords", {})}
        deprioritize_merged = defaultdict(list)
        for k, v in existing.get("deprioritize_for_evidence", {}).items():
            deprioritize_merged[k] = list(v)
        for k, v in routing.get("deprioritize_for_evidence", {}).items():
            for r in v:
                if r not in deprioritize_merged[k]:
                    deprioritize_merged[k].append(r)
        existing["deprioritize_for_evidence"] = dict(deprioritize_merged)
        # Merge evidence_similarity_pairs (append new, cap total)
        existing_pairs = list(existing.get("evidence_similarity_pairs", []))
        new_pairs = routing.get("evidence_similarity_pairs", [])
        for p in new_pairs:
            if p not in existing_pairs and len(existing_pairs) < 100:
                existing_pairs.append(p)
        existing["evidence_similarity_pairs"] = existing_pairs[-100:]  # Keep last 100
        save_routing_overrides(existing)

    return overrides
