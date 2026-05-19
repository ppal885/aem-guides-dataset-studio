"""Optional LLM pass: structured QA handoff (smoke vs deep, sign-off blockers, Jira test outline)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.llm_service import generate_text, is_llm_available

_MAX_UAC_ANSWER_CHARS = 14_000
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)


def _shell(
    *,
    requested: bool,
    generated: bool,
    note: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "requested": requested,
        "generated": generated,
        "note": note,
        "regression_breadth": "",
        "smoke_checks": [],
        "deep_regression_focus": [],
        "blocking_for_signoff": [],
        "exit_criteria": [],
        "exploratory_angles": [],
        "jira_test_script": {
            "title": "",
            "preconditions": [],
            "steps": [],
            "expected_result": "",
        },
        "qa_lead_note": "",
    }
    base.update(fields)
    return base


def _trunc(s: str, n: int) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _build_user_prompt(
    en: JiraEnrichedDocument,
    *,
    uac_answer: str,
    similar_slim: list[dict[str, Any]],
    scenario_titles: list[str],
    risk_level: str,
    insufficient_similar: bool,
) -> str:
    ctx = {
        "jira_key": en.jira_key,
        "summary": _trunc(en.summary, 400),
        "domain": en.domain,
        "sub_domain": en.sub_domain or None,
        "issue_type": en.issue_type,
        "priority": en.priority,
        "status": en.status,
        "affected_outputs": list(en.affected_outputs or [])[:20],
        "dita_entities": list(en.dita_entities or [])[:25],
        "components": list(en.components or [])[:15],
        "customer_names": list(en.customer_names or [])[:10],
        "qa_risk_tags": list(en.qa_risk_tags or [])[:15],
        "missing_info_flags": list(en.missing_info or [])[:12],
        "risk_level_from_uac": risk_level or None,
        "insufficient_similar_ticket_pool": insufficient_similar,
        "must_test_scenario_titles_from_structured_pipeline": scenario_titles,
        "similar_tickets_summary": similar_slim,
        "uac_brief_markdown_excerpt": _trunc(uac_answer, _MAX_UAC_ANSWER_CHARS),
    }
    schema = """{
  "regression_breadth": "smoke" | "focused" | "full",
  "smoke_checks": ["string"],
  "deep_regression_focus": ["string"],
  "blocking_for_signoff": [{"question": "string", "owner_role": "dev" | "qa" | "pm" | "other"}],
  "exit_criteria": ["string"],
  "exploratory_angles": ["string"],
  "jira_test_script": {
    "title": "string",
    "preconditions": ["string"],
    "steps": ["string"],
    "expected_result": "string"
  },
  "qa_lead_note": "string"
}"""
    return f"""Use ONLY the JSON context below to fill this schema. Max lengths: smoke_checks ≤5, deep_regression_focus ≤5, blocking_for_signoff ≤6, exit_criteria ≤6, exploratory_angles ≤4, preconditions ≤4, steps ≤8. Each line must reference something concrete from context (entity, output, component, key, or similar jira_key) when such data exists; if the ticket is thin, say what is unknown instead of inventing customers or builds.

JSON schema (output exactly one object matching this shape):
{schema}

Context (ground truth for grounding):
```json
{json.dumps(ctx, ensure_ascii=False, indent=2)}
```
"""


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_blocking(raw_list: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw_list, list):
        return out
    for item in raw_list[:6]:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or "").strip()
        if not q:
            continue
        role = str(item.get("owner_role") or "other").strip().lower()
        if role not in ("dev", "qa", "pm", "other"):
            role = "other"
        out.append({"question": q, "owner_role": role})
    return out


def _normalize_script(raw: Any) -> dict[str, Any]:
    empty = {"title": "", "preconditions": [], "steps": [], "expected_result": ""}
    if not isinstance(raw, dict):
        return empty
    pre = [str(x).strip() for x in (raw.get("preconditions") or []) if str(x).strip()][:4]
    steps = [str(x).strip() for x in (raw.get("steps") or []) if str(x).strip()][:8]
    exp = str(raw.get("expected_result") or "").strip()
    title = str(raw.get("title") or "").strip()
    return {
        "title": _trunc(title, 200),
        "preconditions": pre,
        "steps": steps,
        "expected_result": _trunc(exp, 1200),
    }


def _normalize_plan(raw: dict[str, Any]) -> dict[str, Any]:
    breadth = str(raw.get("regression_breadth") or "").strip().lower()
    if breadth not in ("smoke", "focused", "full"):
        breadth = ""

    smoke = [_trunc(str(x).strip(), 400) for x in (raw.get("smoke_checks") or []) if str(x).strip()][:5]
    deep = [_trunc(str(x).strip(), 400) for x in (raw.get("deep_regression_focus") or []) if str(x).strip()][:5]
    exit_c = [_trunc(str(x).strip(), 400) for x in (raw.get("exit_criteria") or []) if str(x).strip()][:6]
    exploratory = [_trunc(str(x).strip(), 400) for x in (raw.get("exploratory_angles") or []) if str(x).strip()][:4]
    note = _trunc(str(raw.get("qa_lead_note") or "").strip(), 2000)

    return {
        "regression_breadth": breadth,
        "smoke_checks": smoke,
        "deep_regression_focus": deep,
        "blocking_for_signoff": _normalize_blocking(raw.get("blocking_for_signoff")),
        "exit_criteria": exit_c,
        "exploratory_angles": exploratory,
        "jira_test_script": _normalize_script(raw.get("jira_test_script")),
        "qa_lead_note": note,
    }


async def build_qa_handoff_payload_for_response(
    *,
    enriched: JiraEnrichedDocument,
    uac_answer: str,
    similar_jiras: list[dict[str, Any]],
    must_test_scenarios: list[dict[str, Any]],
    risk_summary: dict[str, Any],
    insufficient_similar: bool,
    include_qa_handoff: bool,
) -> dict[str, Any]:
    """
    Build ``payload["qa_handoff"]`` for UAC analyze.

    When ``include_qa_handoff`` is False, returns a shell with ``requested=False`` (no LLM call).
    """
    if not include_qa_handoff:
        return _shell(requested=False, generated=False, note=None)

    if not is_llm_available():
        return _shell(
            requested=True,
            generated=False,
            note="LLM is not configured; set API keys for your LLM_PROVIDER.",
        )

    similar_slim: list[dict[str, Any]] = []
    for row in similar_jiras[:8]:
        if not isinstance(row, dict):
            continue
        jk = str(row.get("jira_key") or "").strip()
        if not jk:
            continue
        similar_slim.append(
            {
                "jira_key": jk,
                "title": _trunc(str(row.get("title") or row.get("summary") or ""), 200),
                "why": _trunc(str(row.get("why_similar") or row.get("why_relevant") or ""), 400),
            }
        )

    scenario_titles: list[str] = []
    for row in must_test_scenarios[:7]:
        if isinstance(row, dict):
            t = str(row.get("scenario") or "").strip()
            if t:
                scenario_titles.append(_trunc(t, 320))

    risk = risk_summary if isinstance(risk_summary, dict) else {}
    risk_level = str(risk.get("level") or "").strip()

    user_prompt = _build_user_prompt(
        enriched,
        uac_answer=uac_answer,
        similar_slim=similar_slim,
        scenario_titles=scenario_titles,
        risk_level=risk_level,
        insufficient_similar=insufficient_similar,
    )
    system = (
        "You are a staff QA engineer for Adobe Experience Manager Guides. "
        "Output a single JSON object only—no markdown fences, no commentary before or after. "
        "Ground strings in the provided context; use short imperative lines suitable for Jira checklists. "
        "Do not invent customer names, builds, URLs, or ticket keys absent from context."
    )

    try:
        raw_text = (await generate_text(system, user_prompt, max_tokens=3500, step_name="uac_qa_handoff")).strip()
    except Exception:
        return _shell(requested=True, generated=False, note="QA handoff LLM call failed.")

    parsed = _parse_llm_json(raw_text) or _parse_llm_json(raw_text.replace("```", ""))
    if not parsed:
        return _shell(requested=True, generated=False, note="QA handoff response was not valid JSON.")

    normalized = _normalize_plan(parsed)
    merged = _shell(requested=True, generated=True, note=None, **normalized)
    return merged


__all__ = ["build_qa_handoff_payload_for_response"]
