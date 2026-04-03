from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.storage import get_storage

logger = get_structured_logger(__name__)

STATE_VERSION = 1
QUERY_FAILURE_THRESHOLD = 2
QUERY_COOLDOWN_MINUTES = max(1, int(os.getenv("AI_FLOW_QUERY_COOLDOWN_MINUTES", "30")))
AUTHORING_GOOD_QUALITY = 70

_EMPTY_STATE: dict[str, Any] = {
    "version": STATE_VERSION,
    "updated_at": "",
    "query_health": {},
    "authoring_health": {},
    "recipe_health": {},
}

_AUTHORING_HINTS = {
    "XML declaration present": "Start exactly with the XML declaration and the correct AEM Guides DTD header.",
    "Required DTD header present": "Use the exact AEM Guides DTD for the resolved topic type before the root element.",
    "XML parse error": "Return well-formed XML only and close every tag correctly before adding more content.",
    "id attribute on root": "Set a stable id on the root topic element before adding body content.",
    "shortdesc present": "Always include a concise <shortdesc> immediately after the title.",
    "xml:lang present": "Set xml:lang=\"en-US\" on the root element.",
    "taskbody present": "Task topics must include a <taskbody> wrapper.",
    "steps present": "Task topics should contain actionable <steps>.",
    "cmd in steps": "Each task step needs a <cmd> element.",
    "conbody present": "Concept topics must include <conbody>.",
    "refbody present": "Reference topics must include <refbody>.",
    "body present": "Generic topic documents must include <body>.",
    "glossdef present": "Glossentry topics must include <glossdef>.",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _future_timestamp(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _state_path() -> Path:
    path = get_storage().base_path / "ai_flow_intelligence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return copy.deepcopy(_EMPTY_STATE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return copy.deepcopy(_EMPTY_STATE)
    except Exception:
        return copy.deepcopy(_EMPTY_STATE)

    state = copy.deepcopy(_EMPTY_STATE)
    state.update(payload)
    for key in ("query_health", "authoring_health", "recipe_health"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    return state


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    state["version"] = STATE_VERSION
    state["updated_at"] = _utcnow()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _query_category_entry(state: dict[str, Any], tenant_id: str, category: str) -> dict[str, Any]:
    tenant_entry = state.setdefault("query_health", {}).setdefault(tenant_id, {})
    category_entry = tenant_entry.setdefault(
        category,
        {
            "preferred_source": "",
            "degraded_until": "",
            "learning_note": "",
            "sources": {},
        },
    )
    for source in ("rag", "tavily"):
        category_entry["sources"].setdefault(
            source,
            {
                "successes": 0,
                "failures": 0,
                "empty_results": 0,
                "consecutive_successes": 0,
                "consecutive_failures": 0,
                "last_error": "",
                "last_used_at": "",
                "last_success_at": "",
                "last_failure_at": "",
            },
        )
    return category_entry


def _authoring_entry(state: dict[str, Any], tenant_id: str, dita_type: str) -> dict[str, Any]:
    tenant_entry = state.setdefault("authoring_health", {}).setdefault(tenant_id, {})
    return tenant_entry.setdefault(
        dita_type,
        {
            "attempts": 0,
            "clean_runs": 0,
            "healed_runs": 0,
            "avg_quality": 0.0,
            "last_quality": 0,
            "failed_checks": {},
            "healing_strategies": {},
        },
    )


def _route_key(feature: str, pattern: str) -> str:
    return f"{feature}::{pattern}"


def _recipe_entry(state: dict[str, Any], feature: str, pattern: str) -> dict[str, Any]:
    route_entry = state.setdefault("recipe_health", {}).setdefault(
        _route_key(feature, pattern),
        {
            "feature": feature,
            "pattern": pattern,
            "recommended_recipe": "",
            "recipes": {},
        },
    )
    route_entry.setdefault("recipes", {})
    return route_entry


def _recipe_stats(route_entry: dict[str, Any], recipe_id: str) -> dict[str, Any]:
    return route_entry["recipes"].setdefault(
        recipe_id,
        {
            "successes": 0,
            "failures": 0,
            "low_confidence": 0,
            "last_reason": "",
            "last_used_at": "",
            "last_success_at": "",
            "last_failure_at": "",
        },
    )


def _top_items(mapping: dict[str, Any], limit: int = 5) -> list[tuple[str, Any]]:
    return sorted(mapping.items(), key=lambda item: (-item[1], item[0]))[:limit]


def choose_query_source(tenant_id: str, category: str, default_source: str) -> tuple[str, str]:
    state = _load_state()
    entry = _query_category_entry(state, tenant_id, category)
    preferred_source = entry.get("preferred_source") or default_source
    degraded_until = _parse_timestamp(entry.get("degraded_until", ""))
    tavily_stats = entry["sources"]["tavily"]

    if default_source != "tavily":
        return default_source, ""

    if degraded_until and degraded_until > datetime.now(timezone.utc):
        note = entry.get("learning_note") or "Learning: web search is temporarily degraded, so this category will use local RAG."
        return "rag", note

    if tavily_stats["consecutive_failures"] >= QUERY_FAILURE_THRESHOLD:
        entry["preferred_source"] = "rag"
        entry["degraded_until"] = _future_timestamp(QUERY_COOLDOWN_MINUTES)
        entry["learning_note"] = (
            "Learning: Tavily failed repeatedly for this tenant/category, so queries are temporarily routed to local RAG."
        )
        _save_state(state)
        return "rag", entry["learning_note"]

    if preferred_source == "rag" and tavily_stats["successes"] > 0 and tavily_stats["consecutive_failures"] == 0:
        entry["preferred_source"] = "tavily"
        entry["degraded_until"] = ""
        entry["learning_note"] = "Self-healing: Tavily recovered recently, so web-backed research is enabled again."
        _save_state(state)
        return "tavily", entry["learning_note"]

    if preferred_source == "rag":
        return "rag", entry.get("learning_note", "")
    return default_source, ""


def record_query_result(
    tenant_id: str,
    category: str,
    source: str,
    *,
    success: bool,
    error: str = "",
    result_count: int = 0,
) -> None:
    state = _load_state()
    entry = _query_category_entry(state, tenant_id, category)
    stats = entry["sources"].setdefault(source, {})
    now = _utcnow()
    stats["last_used_at"] = now

    if success:
        stats["successes"] = int(stats.get("successes", 0)) + 1
        stats["consecutive_successes"] = int(stats.get("consecutive_successes", 0)) + 1
        stats["consecutive_failures"] = 0
        stats["last_success_at"] = now
        if result_count == 0:
            stats["empty_results"] = int(stats.get("empty_results", 0)) + 1
        if source == "tavily":
            entry["preferred_source"] = "tavily"
            entry["degraded_until"] = ""
            entry["learning_note"] = "Self-healing: Tavily returned results again, so web-backed research is restored."
    else:
        stats["failures"] = int(stats.get("failures", 0)) + 1
        stats["consecutive_failures"] = int(stats.get("consecutive_failures", 0)) + 1
        stats["consecutive_successes"] = 0
        stats["last_failure_at"] = now
        stats["last_error"] = (error or "No results returned")[:240]
        if source == "tavily" and stats["consecutive_failures"] >= QUERY_FAILURE_THRESHOLD:
            entry["preferred_source"] = "rag"
            entry["degraded_until"] = _future_timestamp(QUERY_COOLDOWN_MINUTES)
            entry["learning_note"] = (
                "Learning: repeated Tavily failures triggered a temporary switch to local RAG for this category."
            )

    _save_state(state)


def _hint_for_failed_check(label: str) -> str:
    for prefix, hint in _AUTHORING_HINTS.items():
        if label.startswith(prefix):
            return hint
    return f"Fix recurring validation issue: {label}."


def get_authoring_hints(tenant_id: str, dita_type: str, limit: int = 5) -> list[str]:
    state = _load_state()
    entry = _authoring_entry(state, tenant_id, dita_type)
    hints: list[str] = []

    for label, _count in _top_items(entry.get("failed_checks", {}), limit=limit):
        hint = _hint_for_failed_check(label)
        if hint not in hints:
            hints.append(hint)

    strategies = entry.get("healing_strategies", {})
    if strategies.get("repair_prompt"):
        hints.append("When structure is weak, repair the XML in place instead of rewriting the topic from scratch.")
    if strategies.get("structural_repair"):
        hints.append("Preserve valid content and deterministically add any missing required DITA wrappers before escalating.")
    return hints[:limit]


def record_authoring_outcome(
    tenant_id: str,
    dita_type: str,
    *,
    quality_score: int,
    validation: list[dict],
    healed: bool = False,
    healing_actions: list[str] | None = None,
) -> None:
    state = _load_state()
    entry = _authoring_entry(state, tenant_id, dita_type)
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    attempts = entry["attempts"]
    previous_avg = float(entry.get("avg_quality", 0.0))
    entry["avg_quality"] = round(((previous_avg * (attempts - 1)) + quality_score) / attempts, 2)
    entry["last_quality"] = quality_score

    failed = [str(item.get("label", "")) for item in validation if not item.get("passing")]
    if not failed and quality_score >= AUTHORING_GOOD_QUALITY:
        entry["clean_runs"] = int(entry.get("clean_runs", 0)) + 1
    if healed:
        entry["healed_runs"] = int(entry.get("healed_runs", 0)) + 1

    failed_checks = entry.setdefault("failed_checks", {})
    for label in failed:
        failed_checks[label] = int(failed_checks.get(label, 0)) + 1

    strategy_counts = entry.setdefault("healing_strategies", {})
    for action in healing_actions or []:
        strategy_counts[action] = int(strategy_counts.get(action, 0)) + 1

    _save_state(state)


def recommend_recipe(feature: str, pattern: str, default_recipe: str) -> tuple[str, str]:
    state = _load_state()
    route_entry = _recipe_entry(state, feature, pattern)
    default_stats = _recipe_stats(route_entry, default_recipe)
    default_score = int(default_stats.get("successes", 0)) - (2 * int(default_stats.get("failures", 0)))

    best_recipe = default_recipe
    best_reason = ""
    best_score = default_score

    for recipe_id, stats in route_entry.get("recipes", {}).items():
        if recipe_id == default_recipe:
            continue
        score = int(stats.get("successes", 0)) - (2 * int(stats.get("failures", 0)))
        if int(stats.get("successes", 0)) < 2:
            continue
        if score <= best_score + 1:
            continue
        if int(default_stats.get("failures", 0)) < 2 and int(stats.get("successes", 0)) < 3:
            continue
        best_recipe = recipe_id
        best_score = score
        best_reason = (
            f"Learning: {recipe_id} has performed better than {default_recipe} for {feature}/{pattern} recently."
        )

    if best_recipe != default_recipe:
        route_entry["recommended_recipe"] = best_recipe
        _save_state(state)
        return best_recipe, best_reason

    return default_recipe, ""


def record_recipe_outcome(
    feature: str,
    pattern: str,
    recipe_id: str,
    *,
    success: bool,
    low_confidence: bool = False,
    reason: str = "",
) -> None:
    state = _load_state()
    route_entry = _recipe_entry(state, feature, pattern)
    stats = _recipe_stats(route_entry, recipe_id)
    now = _utcnow()
    stats["last_used_at"] = now
    if reason:
        stats["last_reason"] = reason[:240]
    if low_confidence:
        stats["low_confidence"] = int(stats.get("low_confidence", 0)) + 1

    if success:
        stats["successes"] = int(stats.get("successes", 0)) + 1
        stats["last_success_at"] = now
    else:
        stats["failures"] = int(stats.get("failures", 0)) + 1
        stats["last_failure_at"] = now

    _save_state(state)


def get_tenant_flow_intelligence(tenant_id: str) -> dict[str, Any]:
    state = _load_state()
    query_health = state.get("query_health", {}).get(tenant_id, {})
    authoring_health = state.get("authoring_health", {}).get(tenant_id, {})

    recipe_health = []
    for entry in state.get("recipe_health", {}).values():
        route_recipes = entry.get("recipes", {})
        recipe_health.append(
            {
                "feature": entry.get("feature", ""),
                "pattern": entry.get("pattern", ""),
                "recommended_recipe": entry.get("recommended_recipe", ""),
                "recipes": [
                    {"recipe_id": recipe_id, **stats}
                    for recipe_id, stats in sorted(
                        route_recipes.items(),
                        key=lambda item: (
                            -(int(item[1].get("successes", 0)) - int(item[1].get("failures", 0))),
                            item[0],
                        ),
                    )
                ][:5],
            }
        )

    return {
        "tenant_id": tenant_id,
        "updated_at": state.get("updated_at", ""),
        "query_health": [
            {
                "category": category,
                "preferred_source": entry.get("preferred_source") or "",
                "degraded_until": entry.get("degraded_until") or "",
                "learning_note": entry.get("learning_note") or "",
                "sources": entry.get("sources", {}),
            }
            for category, entry in sorted(query_health.items())
        ],
        "authoring_health": [
            {
                "dita_type": dita_type,
                "attempts": entry.get("attempts", 0),
                "clean_runs": entry.get("clean_runs", 0),
                "healed_runs": entry.get("healed_runs", 0),
                "avg_quality": entry.get("avg_quality", 0.0),
                "last_quality": entry.get("last_quality", 0),
                "top_failed_checks": [
                    {"label": label, "count": count}
                    for label, count in _top_items(entry.get("failed_checks", {}))
                ],
                "learned_hints": get_authoring_hints(tenant_id, dita_type),
                "healing_strategies": [
                    {"strategy": label, "count": count}
                    for label, count in _top_items(entry.get("healing_strategies", {}))
                ],
            }
            for dita_type, entry in sorted(authoring_health.items())
        ],
        "recipe_health": sorted(recipe_health, key=lambda item: (item["feature"], item["pattern"])),
    }


def reset_flow_intelligence() -> None:
    _save_state(copy.deepcopy(_EMPTY_STATE))
    logger.info_structured("AI flow intelligence state reset")
