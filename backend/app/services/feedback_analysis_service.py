"""Feedback analysis service - map validation errors and eval metrics to actionable suggestions.

Feedback loop (placeholder for future):
- RunFeedback.suggested_updates is stored when validation fails but is not yet consumed.
- Intended flow: batch job or API polls RunFeedback, aggregates suggested_fixes/recipe_hints,
  and injects them into domain_classifier, scenario_expander, or generator_invocation_planner
  prompts for the next run.
- analyze_eval_report() output could drive prompt version A/B testing.
"""
import re
from typing import Any


# Error pattern -> (suggested_fix, recipe_hint)
# Recipe hint phrases -> suggested recipe_id for self-learning
RECIPE_HINT_TO_RECIPE_ID: dict[str, str] = {
    "task_topics": "task_topics",
    "concept_topics": "concept_topics",
    "reference_topics": "reference_topics",
    "conref_pack": "conref_pack",
    "keyref_demo": "keys.keydef_basic",
    "keys.keydef_basic": "keys.keydef_basic",
    "media_rich_content": "media_rich_content",
    "keys.keyref_image": "keys.keyref_image",
    "inline_formatting_nested": "inline_formatting_nested",
    "inline formatting": "inline_formatting_nested",
    "rte": "inline_formatting_nested",
}

VALIDATION_ERROR_PATTERNS = [
    (
        r"Duplicate ID '([^']+)'",
        "Ensure unique @id attributes per topic and element. Each id must be unique across the dataset.",
        "Check task_topics, concept_topics, or any recipe that generates multiple topics with IDs.",
    ),
    (
        r"Broken href '([^']+)'",
        "Fix href/conref targets: ensure referenced files exist and paths are correct. Use relative paths from the referencing file.",
        "conref_pack, keyref_demo, or map recipes may need correct href generation.",
    ),
    (
        r"Broken fragment #([^\s]+)",
        "Fix fragment (#id) references: the target element with that id must exist in the referenced file.",
        "conref_pack or keyref recipes - ensure conref targets include valid element IDs.",
    ),
    (
        r"Parse error:",
        "Fix XML/DITA syntax: check for unclosed tags, invalid characters, or malformed structure.",
        "Any recipe generating DITA content - validate XML structure.",
    ),
    (
        r"Fragment .+ may not exist",
        "Verify the fragment (#id) exists in the target file before referencing.",
        "conref or keyref recipes.",
    ),
    (
        r"keyref|keyref resolution",
        "Fix keyref resolution: ensure keys are defined in the correct keyscope and key definitions exist.",
        "keyref_demo recipes - check keyscope and key definitions in map.",
    ),
    (
        r"keyscope|keyscope resolution",
        "Fix keyscope resolution: ensure keyscope attributes are correct and keys are defined.",
        "keyref_demo or map recipes - verify keyscope hierarchy.",
    ),
    (
        r"conref|conref resolution",
        "Fix conref resolution: ensure conref targets exist and paths are correct.",
        "conref_pack or keyref recipes - validate conref targets.",
    ),
]


def _suggest_recipe_from_hints(recipe_hints: list[str]) -> str | None:
    """Map recipe hints to a suggested recipe_id for self-learning."""
    hint_text = " ".join(recipe_hints).lower()
    for phrase, recipe_id in RECIPE_HINT_TO_RECIPE_ID.items():
        if phrase.lower() in hint_text:
            return recipe_id
    return None


def analyze_validation_errors(errors: list[str]) -> dict[str, Any]:
    """
    Parse validation errors and return structured suggestions for prompt injection.
    Returns {patterns: [...], suggested_fixes: [...], recipe_hints: [...], suggested_recipe_id: str|None}.
    """
    if not errors:
        return {"patterns": [], "suggested_fixes": [], "recipe_hints": [], "suggested_recipe_id": None}

    patterns_found = []
    suggested_fixes = []
    recipe_hints = []

    for err in errors:
        err_lower = (err or "").lower()
        for pattern_re, fix, hint in VALIDATION_ERROR_PATTERNS:
            if re.search(pattern_re, err, re.IGNORECASE):
                if fix not in suggested_fixes:
                    suggested_fixes.append(fix)
                if hint not in recipe_hints:
                    recipe_hints.append(hint)
                patterns_found.append({"pattern": pattern_re, "error": err[:200]})
                break
        else:
            suggested_fixes.append(f"Address: {err[:150]}")
            recipe_hints.append("Review recipe output for this scenario.")

    suggested_recipe_id = _suggest_recipe_from_hints(recipe_hints)

    return {
        "patterns": patterns_found,
        "suggested_fixes": suggested_fixes,
        "recipe_hints": recipe_hints,
        "suggested_recipe_id": suggested_recipe_id,
    }


def format_error_analysis_for_prompt(analysis: dict[str, Any]) -> str:
    """Format analysis result as text block for LLM prompt."""
    fixes = analysis.get("suggested_fixes", [])
    hints = analysis.get("recipe_hints", [])
    if not fixes and not hints:
        return ""
    lines = []
    if fixes:
        lines.append("Suggested fixes:")
        for f in fixes:
            lines.append(f"  - {f}")
    if hints:
        lines.append("Recipe hints:")
        for h in hints:
            lines.append(f"  - {h}")
    return "\n".join(lines)


def analyze_eval_report(report: dict[str, Any]) -> dict[str, Any]:
    """
    Summarize eval report for iteration. Identify weak areas.
    Returns {summary: str, weak_areas: [...], recommendations: [...]}.
    """
    metrics = report.get("metrics", {})

    domain_accuracy = metrics.get("domain_accuracy", 0)
    recipe_accuracy = metrics.get("recipe_selection_accuracy", 0)
    scenario_diversity = metrics.get("scenario_diversity", 0)
    validation_rate = metrics.get("dataset_validation_rate", 0)

    weak_areas = []
    recommendations = []

    if domain_accuracy < 0.7:
        weak_areas.append("domain_classification")
        recommendations.append("Improve domain_classifier prompt or add more domain examples.")
    if recipe_accuracy < 0.7:
        weak_areas.append("recipe_selection")
        recommendations.append("Refine generator_invocation_planner prompt or add more recipe candidates.")
    if scenario_diversity < 0.5:
        weak_areas.append("scenario_diversity")
        recommendations.append("Improve scenario_expander prompt to produce diverse scenario types.")
    if validation_rate < 0.8:
        weak_areas.append("dataset_validation")
        recommendations.append("Improve DITA structure in recipes; ensure unique IDs, valid hrefs.")

    summary = (
        f"Domain accuracy: {domain_accuracy:.2f}, Recipe accuracy: {recipe_accuracy:.2f}, "
        f"Scenario diversity: {scenario_diversity:.2f}, Validation rate: {validation_rate:.2f}."
    )

    return {
        "summary": summary,
        "weak_areas": weak_areas,
        "recommendations": recommendations,
        "metrics": metrics,
    }
