"""LLM orchestration for QA Studio: planning, generation, judge, self-correction."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from prompts import qa_studio_authoring as qa_prompts
from app.services.gqs_integration_config import (
    authoring_llm_execution_enabled,
    gqs_llm_credentials,
    llm_configured_for_authoring,
)
from app.services.gqs_openai_compatible import gqs_chat_completion_json, gqs_chat_completion_text
from app.services.llm_service import generate_json, generate_text, is_llm_available
from app.services.qa_studio_automation_validator import (
    _FRAGILE_XPATH_POSITION_RE,
    validate_automation_artifacts,
)
from app.services.qa_studio_retrieve_for_plan import (
    format_compact_plan_for_prompt,
    retrieve_for_plan,
)


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def _use_gqs_openai() -> bool:
    c = gqs_llm_credentials()
    return bool(c.get("api_key_set") and (c.get("model") or "").strip())


def llm_authoring_enabled() -> bool:
    """True when this process may call a real LLM for QA Studio plan/generate (GQS or app provider)."""
    if not authoring_llm_execution_enabled() or not llm_configured_for_authoring():
        return False
    if _use_gqs_openai():
        return True
    return is_llm_available()


async def llm_authoring_probe() -> dict[str, Any]:
    """Short reachability check for the configured authoring provider."""
    if not llm_authoring_enabled():
        return {"ok": False, "error": "LLM authoring is not enabled or credentials are incomplete."}
    try:
        if _use_gqs_openai():
            await gqs_chat_completion_text(
                system_prompt="Reply with exactly the word PONG and nothing else.",
                user_prompt="ping",
                max_tokens=8,
            )
        else:
            await generate_text(
                system_prompt="Reply with exactly the word PONG and nothing else.",
                user_prompt="ping",
                max_tokens=8,
                step_name="qa_studio_llm_probe",
            )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:800]}


async def _generate_json_for_authoring(
    *,
    system: str,
    user: str,
    max_tokens: int,
    step_name: str,
    trace_id: str | None,
    jira_key: str | None,
) -> dict[str, Any]:
    if _use_gqs_openai():
        raw = await gqs_chat_completion_json(
            system_prompt=system,
            user_prompt=user,
            max_tokens=max_tokens,
        )
        return raw if isinstance(raw, dict) else {}
    raw = await generate_json(
        system,
        user,
        max_tokens=max_tokens,
        step_name=step_name,
        trace_id=trace_id,
        jira_id=jira_key,
    )
    return raw if isinstance(raw, dict) else {}


def _deep_reasoning() -> bool:
    return _truthy(os.getenv("GQS_DEEP_REASONING")) or _truthy(os.getenv("QA_STUDIO_DEEP_REASONING"))


def _plan_max_retries() -> int:
    for key in ("GQS_PLAN_MAX_RETRIES", "QA_STUDIO_PLAN_MAX_RETRIES"):
        raw = os.getenv(key)
        if raw is not None and str(raw).strip() != "":
            try:
                return max(0, min(8, int(raw)))
            except ValueError:
                pass
    return 2


def _gen_max_retries() -> int:
    for key in ("GQS_GEN_MAX_RETRIES", "QA_STUDIO_GEN_MAX_RETRIES"):
        raw = os.getenv(key)
        if raw is not None and str(raw).strip() != "":
            try:
                return max(0, min(8, int(raw)))
            except ValueError:
                pass
    return 2


def _norm_step(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _judge_plan(plan: Any, fields: dict[str, Any]) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Planning gate: traceability, PO calls, Then coverage, fragile XPath hints in plan text."""
    critiques: list[str] = []
    structured: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return False, ["Plan root must be a JSON object."], [
            {"severity": "error", "code": "plan_not_object", "message": "LLM returned non-object JSON."}
        ]

    atr = plan.get("assertion_traceability")
    if not isinstance(atr, list) or len(atr) == 0:
        critiques.append("assertion_traceability must be a non-empty array grounded in Jira.")
        structured.append(
            {
                "severity": "error",
                "code": "missing_traceability",
                "message": "Add assertion_traceability entries for each Then.",
            }
        )
    else:
        for i, row in enumerate(atr):
            if not isinstance(row, dict):
                critiques.append(f"assertion_traceability[{i}] must be an object.")
                continue
            if not (row.get("then_step") or "").strip():
                critiques.append(f"assertion_traceability[{i}] needs then_step.")
            jq = (row.get("jira_quote") or row.get("mapped_jira_source") or "").strip()
            if not jq:
                critiques.append(f"assertion_traceability[{i}] needs jira_quote / mapped_jira_source.")

    ad = plan.get("automation_design")
    if not isinstance(ad, dict):
        critiques.append("automation_design must be an object with gherkin_outline and step_implementation.")
        structured.append(
            {
                "severity": "error",
                "code": "missing_automation_design",
                "message": "Provide automation_design.gherkin_outline and step_implementation.",
            }
        )
    else:
        outline = ad.get("gherkin_outline") or {}
        steps_impl = ad.get("step_implementation")
        if not isinstance(steps_impl, list) or len(steps_impl) == 0:
            critiques.append("automation_design.step_implementation must be a non-empty array.")
        else:
            for j, row in enumerate(steps_impl):
                if not isinstance(row, dict):
                    continue
                k = str(row.get("kind") or "").lower()
                poc = (row.get("page_object_call") or "").strip()
                if k in ("when", "then") and not poc:
                    critiques.append(
                        f"step_implementation[{j}] ({k}) must include page_object_call to a Page Object API."
                    )

        then_steps: list[str] = []
        if isinstance(outline, dict):
            raw_then = outline.get("then") or []
            if isinstance(raw_then, list):
                then_steps = [str(x) for x in raw_then if (str(x).strip())]

        trace_thens = set()
        if isinstance(atr, list):
            for row in atr:
                if isinstance(row, dict) and (row.get("then_step") or "").strip():
                    trace_thens.add(_norm_step(str(row.get("then_step"))))

        for ts in then_steps:
            n = _norm_step(ts)
            if not any(n in t or t in n for t in trace_thens if t):
                critiques.append(
                    f"Then step not mapped in assertion_traceability: {ts[:120]}"
                )

    quote = (
        (fields.get("source_quote") or fields.get("acceptance_criteria") or fields.get("expected_fixed_behavior") or "")
        .strip()
    )
    if quote:
        needle = quote[:120].lower()
        plan_blob = json.dumps(plan, ensure_ascii=False).lower()
        if needle.strip() and needle not in plan_blob:
            critiques.append(
                "Ground Plans in explicit Jira wording: quote key phrases from source_quote / AC inside assertion_traceability or summary."
            )

    fragile_hits: list[str] = []
    for blob in (
        json.dumps(plan.get("locator_and_reuse", []), ensure_ascii=False),
        json.dumps(plan.get("new_artifacts", []), ensure_ascii=False),
        json.dumps(plan.get("reuse", {}), ensure_ascii=False),
    ):
        if _FRAGILE_XPATH_POSITION_RE.search(blob):
            fragile_hits.append(blob[:200])

    if fragile_hits:
        critiques.append(
            "Locators use fragile positional XPath patterns; prefer stable role/aria/label scopes or document reuse-first."
        )
        structured.append(
            {
                "severity": "warning",
                "code": "fragile_xpath_plan",
                "message": "Strengthen locator strategy before generation.",
            }
        )

    ok = len(critiques) == 0
    return ok, critiques, structured


def _compact_plan_for_generation(plan: dict[str, Any]) -> dict[str, Any]:
    """Preserve fields the generator must keep (additive keys allowed)."""
    keys = (
        "jira_analysis",
        "assertion_traceability",
        "automation_design",
        "framework_compliance",
        "summary",
        "phases",
        "prerequisite_gates",
        "reuse",
        "locator_and_reuse",
        "new_artifacts",
    )
    extra = (
        "ui_snapshot_matches",
        "ui_reference_matches",
        "playbook_matches",
        "dom_pattern_matches",
        "page_object_matches",
        "assertion_source_matches",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in plan and plan[k] is not None:
            out[k] = plan[k]
    for k in extra:
        if k in plan and plan[k] is not None:
            out[k] = plan[k]
    return out


def _validate_generated(
    generated: Any,
    user_payload: dict[str, Any],
) -> tuple[bool, list[str], list[str], list[dict[str, Any]]]:
    """Generation gate: schema sanity + automation validator."""
    issues: list[dict[str, Any]] = []
    if not isinstance(generated, dict):
        return False, ["Generated root must be a JSON object."], [], issues

    feature = str(generated.get("feature_text") or "")
    steps = str(generated.get("step_defs_text") or "")
    po = str(generated.get("page_object_proposals_text") or "")

    if not feature.strip() or not steps.strip():
        m = "feature_text and step_defs_text must be non-empty."
        issues.append({"severity": "error", "code": "empty_artifact", "message": m})
        return False, [m], [], issues

    jira_summary = str(user_payload.get("jira_summary") or "")
    jira_description = str(user_payload.get("jira_description") or "")
    jira_raw = str(user_payload.get("jira_raw") or "")
    repro = str(user_payload.get("repro_steps") or "")
    exp = str(user_payload.get("expected_behavior") or "")
    ac = str(user_payload.get("acceptance_criteria") or "")

    r = validate_automation_artifacts(
        feature_text=feature,
        step_defs_text=steps,
        page_object_text=po,
        jira_summary=jira_summary,
        jira_description=jira_description,
        jira_raw=jira_raw,
        repro_steps=repro,
        expected_behavior=exp,
        acceptance_criteria=ac,
    )
    for err in r.errors:
        issues.append({"severity": "error", "code": "validator", "message": err})
    for w in r.warnings:
        issues.append({"severity": "warning", "code": "validator", "message": w})

    if "TODO" in steps or "FIXME" in steps:
        w = "Placeholder markers (TODO/FIXME) in step_defs_text should be resolved."
        r.warnings.append(w)
        issues.append({"severity": "warning", "code": "placeholder", "message": w})

    return r.ok, r.errors, r.warnings, issues


async def _senior_reasoning_block(jira_blob: str) -> str | None:
    if not _deep_reasoning():
        return None
    if _use_gqs_openai():
        try:
            text = await gqs_chat_completion_text(
                system_prompt=qa_prompts.REASONING_SYSTEM,
                user_prompt=f"## Context\n{jira_blob[:12000]}",
                max_tokens=1200,
            )
            return (text or "").strip() or None
        except Exception:
            return None
    if not is_llm_available():
        return None
    try:
        text = await generate_text(
            system_prompt=qa_prompts.REASONING_SYSTEM,
            user_prompt=f"## Context\n{jira_blob[:12000]}",
            max_tokens=1200,
            step_name="qa_studio_reasoning",
        )
        return (text or "").strip() or None
    except Exception:
        return None


async def _plan_with_self_correction(
    *,
    jira_blob: str,
    grounding_digest: str,
    fields: dict[str, Any],
    max_retries: int,
    trace_id: str | None,
    jira_key: str | None,
) -> tuple[dict[str, Any], int, bool, list[str], list[dict[str, Any]]]:
    critiques: list[str] = []
    structured_all: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    system = qa_prompts.COMPACT_PLAN_SYSTEM
    for attempt in range(max_retries + 1):
        feedback = "\n".join(f"- {c}" for c in critiques) if critiques else "(none — first attempt)"
        user = qa_prompts.build_plan_user_prompt(
            jira_blob=jira_blob,
            grounding_digest=grounding_digest,
            validation_feedback=feedback,
        )
        raw = await _generate_json_for_authoring(
            system=system,
            user=user,
            max_tokens=4096,
            step_name="qa_studio_plan",
            trace_id=trace_id,
            jira_key=jira_key,
        )
        last = raw if isinstance(raw, dict) else {}
        ok, new_critiques, issues = _judge_plan(last, fields)
        structured_all.extend(issues)
        if ok:
            return last, attempt, True, [], structured_all
        critiques = new_critiques
    return last, max_retries, False, critiques, structured_all


async def _generate_with_self_correction(
    *,
    compact_plan: dict[str, Any],
    grounding_digest: str,
    user_payload: dict[str, Any],
    max_retries: int,
    trace_id: str | None,
    jira_key: str | None,
) -> tuple[dict[str, Any], int, bool, list[str], list[dict[str, Any]]]:
    critiques: list[str] = []
    structured_all: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    system = qa_prompts.COMPACT_GEN_SYSTEM
    compact_json = format_compact_plan_for_prompt(compact_plan)
    for attempt in range(max_retries + 1):
        feedback = "\n".join(f"- {c}" for c in critiques) if critiques else "(none)"
        user = qa_prompts.build_gen_user_prompt(
            compact_plan_json=compact_json,
            grounding_digest=grounding_digest,
            validation_feedback=feedback,
        )
        raw = await _generate_json_for_authoring(
            system=system,
            user=user,
            max_tokens=8192,
            step_name="qa_studio_generate",
            trace_id=trace_id,
            jira_key=jira_key,
        )
        last = raw if isinstance(raw, dict) else {}
        ok, errs, warns, issues = _validate_generated(last, user_payload)
        structured_all.extend(issues)
        if ok:
            return last, attempt, True, [], structured_all
        critiques = list(errs) + [f"warning: {w}" for w in warns]
    return last, max_retries, False, critiques, structured_all


def _build_jira_blob(
    *,
    jira_key: str | None,
    jira_summary: str,
    jira_description: str,
    jira_raw: str,
    repro_steps: str,
    expected_behavior: str,
    acceptance_criteria: str,
    target_area: str,
    manual_notes: str,
    fields: dict[str, Any],
) -> str:
    parts = [
        f"jira_key: {jira_key or ''}",
        f"summary: {jira_summary}",
        f"description: {jira_description}",
        f"raw_excerpt: {jira_raw[:6000]}",
        f"repro_steps: {repro_steps}",
        f"expected_behavior: {expected_behavior or fields.get('expected_fixed_behavior', '')}",
        f"acceptance_criteria: {acceptance_criteria or fields.get('acceptance_criteria', '')}",
        f"source_quote (assertions must trace here): {fields.get('source_quote', '')}",
        f"target_area: {target_area}",
        f"manual_notes: {manual_notes}",
    ]
    return "\n".join(parts)


async def run_llm_planning(
    *,
    jira_key: str | None,
    jira_summary: str,
    jira_description: str,
    jira_raw: str,
    repro_steps: str,
    expected_behavior: str,
    acceptance_criteria: str,
    target_area: str,
    manual_notes: str,
    fields: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Full LLM planning with optional senior reasoning and self-correction."""
    out: dict[str, Any] = {
        "plan_draft": None,
        "senior_qa_reasoning": None,
        "rag_grounding": {},
        "planning_self_correction_attempts": 0,
        "plan_judge_ok": False,
        "plan_judge_critiques": [],
        "planning_structured_issues": [],
        "llm_planning_error": None,
    }
    if not _use_gqs_openai() and not is_llm_available():
        out["llm_planning_error"] = (
            "LLM is not configured — use the same provider as AI chat (see LLM_PROVIDER / ANTHROPIC_* / OPENAI_* in .env), "
            "or set GQS_LLM_API_KEY + GQS_LLM_MODEL for OpenAI-compatible gateways only."
        )
        return out

    retrieval = retrieve_for_plan(
        fields=fields,
        jira_summary=jira_summary,
        jira_description=jira_description,
        jira_raw=jira_raw,
        repro_steps=repro_steps,
        target_area=target_area,
        manual_notes=manual_notes,
        jira_key=jira_key,
    )
    jira_blob = _build_jira_blob(
        jira_key=jira_key,
        jira_summary=jira_summary,
        jira_description=jira_description,
        jira_raw=jira_raw,
        repro_steps=repro_steps,
        expected_behavior=expected_behavior,
        acceptance_criteria=acceptance_criteria,
        target_area=target_area,
        manual_notes=manual_notes,
        fields=fields,
    )
    reasoning = await _senior_reasoning_block(jira_blob)
    out["senior_qa_reasoning"] = reasoning
    if reasoning:
        jira_blob = (
            f"{jira_blob}\n\n## Senior QA reasoning (analysis pass — treat as authoritative for risks/prereqs/stability)\n"
            f"{reasoning}\n"
        )
    out["rag_grounding"] = {
        "retrieval_query_excerpt": retrieval.get("retrieval_query_excerpt"),
        "jira_similar": retrieval.get("jira_similar"),
        "digest_json": retrieval.get("digest_json"),
    }

    try:
        plan, last_attempt_idx, judge_ok, leftover_critiques, structured = await _plan_with_self_correction(
            jira_blob=jira_blob,
            grounding_digest=str(retrieval.get("grounding_digest") or ""),
            fields=fields,
            max_retries=_plan_max_retries(),
            trace_id=trace_id,
            jira_key=(jira_key or "").strip() or None,
        )
        out["plan_draft"] = plan
        out["planning_self_correction_attempts"] = last_attempt_idx + 1
        out["plan_judge_ok"] = judge_ok
        out["plan_judge_critiques"] = leftover_critiques if not judge_ok else []
        out["planning_structured_issues"] = structured
        if reasoning and isinstance(plan, dict):
            plan.setdefault("framework_compliance", {})
            fc = plan["framework_compliance"]
            if isinstance(fc, dict):
                notes = fc.get("notes")
                if not isinstance(notes, list):
                    notes = []
                notes.append("Senior QA reasoning was supplied in API field senior_qa_reasoning.")
                fc["notes"] = notes
    except Exception as e:
        out["llm_planning_error"] = str(e)[:2000]
    return out


async def run_llm_generation(
    *,
    plan: dict[str, Any],
    jira_key: str | None,
    jira_summary: str,
    jira_description: str,
    jira_raw: str,
    repro_steps: str,
    expected_behavior: str,
    acceptance_criteria: str,
    target_area: str,
    manual_notes: str,
    fields: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate feature/steps/PO proposals from a compacted plan."""
    out: dict[str, Any] = {
        "generated": None,
        "compact_plan": {},
        "generation_self_correction_attempts": 0,
        "validation_warnings": [],
        "validation_errors": [],
        "generation_structured_issues": [],
        "generation_ok": False,
        "llm_generation_error": None,
    }
    if not _use_gqs_openai() and not is_llm_available():
        out["llm_generation_error"] = (
            "LLM is not configured — use the same provider as AI chat, or GQS_LLM_API_KEY + GQS_LLM_MODEL for a separate gateway."
        )
        return out

    compact = _compact_plan_for_generation(plan)
    out["compact_plan"] = compact
    retrieval = retrieve_for_plan(
        fields=fields,
        jira_summary=jira_summary,
        jira_description=jira_description,
        jira_raw=jira_raw,
        repro_steps=repro_steps,
        target_area=target_area,
        manual_notes=manual_notes,
        jira_key=jira_key,
    )
    user_payload = {
        "jira_summary": jira_summary,
        "jira_description": jira_description,
        "jira_raw": jira_raw,
        "repro_steps": repro_steps,
        "expected_behavior": expected_behavior,
        "acceptance_criteria": acceptance_criteria,
    }
    try:
        gen, last_attempt_idx, gen_ok, leftover, structured = await _generate_with_self_correction(
            compact_plan=compact,
            grounding_digest=str(retrieval.get("grounding_digest") or ""),
            user_payload=user_payload,
            max_retries=_gen_max_retries(),
            trace_id=trace_id,
            jira_key=(jira_key or "").strip() or None,
        )
        out["generated"] = gen
        out["generation_self_correction_attempts"] = last_attempt_idx + 1
        ok, errs, warns, issues = _validate_generated(gen, user_payload)
        out["generation_ok"] = gen_ok and ok
        out["validation_errors"] = errs
        out["validation_warnings"] = warns
        extra_left = [
            {"severity": "error", "code": "leftover_critique", "message": c}
            for c in leftover
            if gen_ok is False
        ]
        out["generation_structured_issues"] = structured + extra_left
    except Exception as e:
        out["llm_generation_error"] = str(e)[:2000]
    return out
