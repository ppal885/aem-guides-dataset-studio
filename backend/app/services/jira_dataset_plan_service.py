"""LLM-assisted plan: Jira issue → validated chat dataset job (recipe + caps).

The model returns JSON only (no Python). Config is merged with ``build_chat_job_base_config``
and clamped before ``normalize_dataset_job_config`` validates it.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.services.ai_executor_service import PARAM_CAPS
from app.services.dataset_job_service import normalize_dataset_job_config
from app.services.jira_generate_resolve import extract_issue_key_from_shortcut, fetch_issue_text_for_generate
from app.services.llm_service import generate_text, is_llm_available
from app.services.qa_reasoning_engine import parse_llm_json_dict

logger = get_structured_logger(__name__)

# Numeric keys the LLM may tune on the primary recipe (bounded below).
_RECIPE_NUMERIC_KEYS = frozenset(
    {
        "topic_count",
        "steps_per_task",
        "sections_per_concept",
        "entry_count",
        "depth",
        "children_per_level",
        "root_topics",
        "children_per_root",
        "map_count",
        "topicrefs_per_map",
        "keydef_count",
    }
)

# Hard ceiling for topic-like counts when PARAM_CAPS omits a key (Pydantic still caps per recipe).
_MAX_TOPIC_LIKE = 500


def _norm_jira_key(raw: str) -> str:
    return (raw or "").strip().upper()


def _merge_recipe_overrides(primary: dict[str, Any], overrides: dict[str, Any] | None) -> None:
    if not overrides or not isinstance(primary, dict):
        return
    for k, v in overrides.items():
        if k == "type":
            continue
        if k in _RECIPE_NUMERIC_KEYS and isinstance(v, (int, float)):
            iv = int(v)
            cap = PARAM_CAPS.get(k)
            if cap is not None:
                iv = min(max(iv, 1), int(cap))
            elif k == "topic_count" or k.endswith("_count"):
                iv = min(max(iv, 1), _MAX_TOPIC_LIKE)
            primary[k] = iv
        elif isinstance(v, (str, bool, list, dict)):
            primary[k] = v


def _coerce_plan_dict(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "recipe_type": str(data.get("recipe_type") or "").strip().lower(),
        "subject": str(data.get("subject") or "").strip()[:200],
        "prompt_text": str(data.get("prompt_text") or "").strip()[:4000],
        "recipe_overrides": data.get("recipe_overrides") if isinstance(data.get("recipe_overrides"), dict) else {},
        "save_runner": bool(data.get("save_runner")),
        "preset_label": str(data.get("preset_label") or "").strip()[:200],
        "rationale": str(data.get("rationale") or "").strip()[:2000],
    }
    return out


async def plan_dataset_job_from_jira_issue(
    jira_key: str,
    *,
    allowlist: frozenset[str],
) -> dict[str, Any]:
    """
    Fetch Jira text, ask LLM for JSON plan, merge into base chat job config, validate.

    Returns keys: ``ok`` (bool), ``error`` (str|None), ``jira_key``, ``recipe_type``,
    ``subject``, ``prompt_text``, ``base_config`` (dict), ``classification`` (dict),
    ``save_runner``, ``preset_label``, ``warnings`` (list).
    """
    warnings: list[str] = []
    raw = (jira_key or "").strip()
    key = extract_issue_key_from_shortcut(raw) or _norm_jira_key(raw)
    if not re.match(r"^[A-Z][A-Z0-9_]*-\d+$", key or ""):
        return {"ok": False, "error": "Invalid Jira issue key format.", "warnings": warnings}

    blob, err = fetch_issue_text_for_generate(key)
    if err:
        return {"ok": False, "error": err, "warnings": warnings}
    if not blob:
        return {"ok": False, "error": "Could not fetch Jira issue (check JIRA_* credentials).", "warnings": warnings}

    if not is_llm_available():
        return {"ok": False, "error": "LLM is not configured; cannot classify Jira for dataset generation.", "warnings": warnings}

    system = (
        "You plan a single AEM Guides Studio batch job from a Jira issue. "
        "Reply with JSON ONLY (no markdown): "
        '{"recipe_type":"<id>","subject":"<short subject>","prompt_text":"<optional extra hints>",'
        '"recipe_overrides":{...},"save_runner":true|false,"preset_label":"<short snake label or empty>",'
        '"rationale":"<one line>"}.\n'
        f"recipe_type must be one of: {', '.join(sorted(allowlist))}.\n"
        "recipe_overrides: optional numeric tweaks for the primary recipe only, keys like "
        "topic_count, steps_per_task, depth, children_per_level, entry_count, sections_per_concept. "
        "Keep sizes moderate (prefer topic_count under 80 unless the ticket clearly needs scale).\n"
        "save_runner: true if the ticket implies repeat runs, large topic sets, or bulk map generation.\n"
        "preset_label: short label for reuse (letters, digits, spaces, hyphen); empty if save_runner is false."
    )
    user = f"jira_key:{key}\n\n### Issue\n{blob[:14000]}"
    try:
        raw = await generate_text(system, user, max_tokens=700, step_name="jira_dataset_plan")
    except Exception as exc:
        logger.warning_structured("jira_dataset_plan_llm_failed", extra_fields={"error": str(exc)})
        return {"ok": False, "error": f"LLM classification failed: {exc}", "warnings": warnings}

    data = parse_llm_json_dict(raw.strip()) or {}
    if not data:
        return {"ok": False, "error": "Model did not return valid JSON for the dataset plan.", "warnings": warnings}

    plan = _coerce_plan_dict(data)
    rt = plan["recipe_type"]
    if not rt or rt not in allowlist:
        return {
            "ok": False,
            "error": f"Invalid or disallowed recipe_type from model: {rt!r}.",
            "warnings": warnings,
            "classification": plan,
        }

    from app.services.chat_tools import build_chat_job_base_config

    base = build_chat_job_base_config(rt, None)
    recipes = base.get("recipes") or []
    primary = recipes[0] if recipes and isinstance(recipes[0], dict) else {}
    if not isinstance(primary, dict):
        return {"ok": False, "error": "Internal error: no primary recipe.", "warnings": warnings}

    _merge_recipe_overrides(primary, plan.get("recipe_overrides") or {})

    try:
        normalize_dataset_job_config(dict(base))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Planned config failed validation: {exc}",
            "warnings": warnings,
            "classification": plan,
        }

    return {
        "ok": True,
        "error": None,
        "jira_key": key,
        "recipe_type": rt,
        "subject": plan["subject"],
        "prompt_text": plan["prompt_text"],
        "base_config": base,
        "classification": plan,
        "save_runner": plan["save_runner"],
        "preset_label": plan["preset_label"],
        "warnings": warnings,
    }
