"""
UAC Negotiation Intelligence — structured questions by audience and severity for stronger UAC prep.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available

_AUDIENCE_PM = "product_manager"
_AUDIENCE_DEV = "developers"
_AUDIENCE_CUST = "customer"
_AUDIENCE_QA = "qa"

_GAP_AUDIENCE: dict[str, tuple[str, ...]] = {
    "missing_acceptance_criteria": (_AUDIENCE_PM,),
    "missing_expected_behavior": (_AUDIENCE_PM, _AUDIENCE_DEV),
    "missing_environment": (_AUDIENCE_QA, _AUDIENCE_DEV),
    "missing_negative_scenarios": (_AUDIENCE_QA, _AUDIENCE_DEV),
    "unclear_data_setup": (_AUDIENCE_QA, _AUDIENCE_CUST),
    "missing_validation_points": (_AUDIENCE_DEV, _AUDIENCE_QA),
}

_GAP_PM_CATEGORY: dict[str, str] = {
    "missing_acceptance_criteria": "unclear_requirements",
    "missing_expected_behavior": "unsupported_behavior",
}

_GAP_DEV_CATEGORY: dict[str, str] = {
    "missing_expected_behavior": "expected_backend_flow",
    "missing_validation_points": "api_behavior",
    "missing_negative_scenarios": "migration_concerns",
    "missing_environment": "performance_concerns",
}

_GAP_QA_CATEGORY: dict[str, str] = {
    "missing_environment": "environment_matrix",
    "missing_negative_scenarios": "edge_cases",
    "unclear_data_setup": "regression_areas",
    "missing_validation_points": "regression_areas",
}

_GAP_CUST_CATEGORY: dict[str, str] = {
    "unclear_data_setup": "exact_workflow",
    "missing_expected_behavior": "expected_behavior",
}


def _impact_to_severity(impact: str) -> str:
    i = (impact or "").strip().lower()
    if i == "high":
        return "critical"
    if i == "medium":
        return "important"
    return "optional"


def _append(
    bucket: dict[str, list[dict[str, Any]]],
    audience: str,
    *,
    category: str,
    question: str,
    severity: str,
) -> None:
    q = (question or "").strip()
    if not q or len(q) < 8:
        return
    bucket.setdefault(audience, []).append(
        {"category": category, "severity": severity, "question": q[:500]}
    )


def _rule_based_questions(
    *,
    gap_analysis: dict[str, Any],
    risk_analysis: dict[str, Any],
    labels: list[str],
    issue_type: str,
    customer_context: dict[str, Any] | str,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        _AUDIENCE_PM: [],
        _AUDIENCE_DEV: [],
        _AUDIENCE_CUST: [],
        _AUDIENCE_QA: [],
    }
    lab = " ".join(str(x).lower() for x in labels)
    risk_level = str((risk_analysis or {}).get("risk_level") or "").lower()
    risk_areas = (risk_analysis or {}).get("risk_areas") or []
    if not isinstance(risk_areas, list):
        risk_areas = []

    for g in (gap_analysis or {}).get("gaps") or []:
        if not isinstance(g, dict):
            continue
        gt = str(g.get("type") or "").strip()
        sev = _impact_to_severity(str(g.get("impact") or "medium"))
        q = str(g.get("question_to_ask") or "").strip()
        if not q:
            continue
        audiences = _GAP_AUDIENCE.get(gt, (_AUDIENCE_QA,))
        for aud in audiences:
            if aud == _AUDIENCE_PM:
                cat = _GAP_PM_CATEGORY.get(gt, "unclear_requirements")
                _append(out, _AUDIENCE_PM, category=cat, question=q, severity=sev)
            elif aud == _AUDIENCE_DEV:
                cat = _GAP_DEV_CATEGORY.get(gt, "api_behavior")
                _append(out, _AUDIENCE_DEV, category=cat, question=q, severity=sev)
            elif aud == _AUDIENCE_CUST:
                cat = _GAP_CUST_CATEGORY.get(gt, "priority_scenarios")
                _append(out, _AUDIENCE_CUST, category=cat, question=q, severity=sev)
            else:
                cat = _GAP_QA_CATEGORY.get(gt, "edge_cases")
                _append(out, _AUDIENCE_QA, category=cat, question=q, severity=sev)

    if "regression" in lab or "break" in lab:
        _append(
            out,
            _AUDIENCE_QA,
            category="regression_areas",
            question="Which prior release behaviors are frozen as 'must not regress' for this fix?",
            severity="critical" if risk_level == "high" else "important",
        )
    if "customer-escalation" in lab or "escalation" in lab:
        _append(
            out,
            _AUDIENCE_PM,
            category="rollout_expectations",
            question="What is the agreed rollout window, rollback trigger, and customer communication for this escalation?",
            severity="critical",
        )
        _append(
            out,
            _AUDIENCE_CUST,
            category="priority_scenarios",
            question="Which customer workflows are P0 for sign-off versus can follow in a dot release?",
            severity="critical",
        )
    if "publishing" in lab or "pdf" in lab or "output" in lab:
        _append(
            out,
            _AUDIENCE_DEV,
            category="api_behavior",
            question="Which publish/output code paths and presets are authoritative for this change?",
            severity="important",
        )
    if "migration" in lab or "upgrade" in lab or "baseline" in lab:
        _append(
            out,
            _AUDIENCE_PM,
            category="backward_compatibility",
            question="What backward-compatibility guarantees apply for existing customer content and maps?",
            severity="important",
        )
        _append(
            out,
            _AUDIENCE_DEV,
            category="migration_concerns",
            question="How do baselines/version compares behave for content created before this change?",
            severity="important",
        )
    if "performance" in lab or "scalability" in lab:
        _append(
            out,
            _AUDIENCE_DEV,
            category="performance_concerns",
            question="What latency/throughput or corpus-size SLOs must QA validate?",
            severity="important",
        )
    if "flaky" in lab or "automation" in lab:
        _append(
            out,
            _AUDIENCE_QA,
            category="automation_blockers",
            question="Which checks are too flaky for CI today and what stabilization is in scope before UAC?",
            severity="important",
        )

    if isinstance(customer_context, dict) and (customer_context.get("customer") or customer_context.get("escalation")):
        _append(
            out,
            _AUDIENCE_CUST,
            category="existing_workarounds",
            question="Are there customer workarounds in production we must preserve or explicitly retire?",
            severity="important",
        )

    if risk_areas:
        _append(
            out,
            _AUDIENCE_PM,
            category="unsupported_behavior",
            question=f"Product confirmation: are risk areas {', '.join(str(x) for x in risk_areas[:4])} in or out of scope for this ticket?",
            severity="important",
        )

    it = (issue_type or "").lower()
    if "story" in it or "improvement" in it:
        _append(
            out,
            _AUDIENCE_PM,
            category="out_of_scope",
            question="What is explicitly out of scope so QA does not gold-plate beyond the story?",
            severity="optional",
        )

    for k in out:
        out[k] = out[k][:14]

    return out


def _challenge_heuristics(
    *,
    context_excerpt: str,
    labels: list[str],
    risk_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    t = (context_excerpt or "").lower()
    lab = " ".join(str(x).lower() for x in labels)
    items: list[dict[str, Any]] = []

    def add(ch: str, sev: str) -> None:
        ch = ch.strip()[:400]
        if ch:
            items.append({"challenge": ch, "severity": sev})

    if "mime" in t or "content-type" in t:
        add("Challenge MIME/content-type handling: list unsupported types and expected error surfaces.", "critical")
    if "validation" not in t and "schema" not in t:
        add("Challenge missing validation logic: where should invalid DITA or payloads be rejected?", "important")
    if ("old" in t and "new" in t) or "regression" in lab:
        add("Challenge inconsistent old vs new behavior: define golden outputs for the same inputs pre/post change.", "critical")
    if "expected" not in t and "should" not in t:
        add("Challenge undefined behavior: document implicit assumptions the UI/API relies on.", "important")
    if "pdf" in t or "output" in t:
        add("Challenge unclear output expectations: pixel rules, fonts, localization, and attachments in output.", "important")
    rl = str((risk_analysis or {}).get("risk_level") or "").lower()
    if rl == "high":
        add("Challenge blast radius: what customer-visible surfaces change even when the bug is 'internal'?", "critical")

    add("Challenge observability: what logs/metrics prove the fix in prod-like conditions?", "optional")
    return items[:16]


def _empty_pack() -> dict[str, Any]:
    return {
        "questions_for_product_manager": [],
        "questions_for_developers": [],
        "questions_for_customer": [],
        "questions_for_qa": [],
        "challenge_during_uac": [],
    }


def _normalize_llm_pack(raw: dict[str, Any]) -> dict[str, Any]:
    out = _empty_pack()
    key_map = {
        "questions_for_product_manager": ("product_manager", "questions_for_product_manager", "pm"),
        "questions_for_developers": ("developers", "questions_for_developers", "engineering"),
        "questions_for_customer": ("customer", "questions_for_customer", "questions_for_customers"),
        "questions_for_qa": ("qa", "questions_for_qa"),
    }
    for target, aliases in key_map.items():
        for alias in aliases:
            rows = raw.get(alias)
            if isinstance(rows, list) and rows:
                break
        else:
            rows = []
        clean: list[dict[str, Any]] = []
        for row in rows[:16]:
            if not isinstance(row, dict):
                continue
            q = str(row.get("question") or row.get("text") or "").strip()
            if not q:
                continue
            sev = str(row.get("severity") or "important").lower()
            if sev not in {"critical", "important", "optional"}:
                sev = "important"
            cat = str(row.get("category") or row.get("topic") or "general")[:80]
            clean.append({"category": cat, "severity": sev, "question": q[:500]})
        out[target] = clean

    ch = raw.get("challenge_during_uac") or raw.get("challenges") or []
    if isinstance(ch, list):
        for row in ch[:20]:
            if isinstance(row, dict):
                pt = str(row.get("challenge") or row.get("point") or "").strip()
                sev = str(row.get("severity") or "important").lower()
                if sev not in {"critical", "important", "optional"}:
                    sev = "important"
                if pt:
                    out["challenge_during_uac"].append({"challenge": pt[:500], "severity": sev})
            elif isinstance(row, str) and row.strip():
                out["challenge_during_uac"].append({"challenge": row.strip()[:500], "severity": "important"})
    return out


def _merge_rule_and_llm(rule: dict[str, list], llm: dict[str, Any]) -> dict[str, Any]:
    merged = _empty_pack()
    for target in (
        "questions_for_product_manager",
        "questions_for_developers",
        "questions_for_customer",
        "questions_for_qa",
    ):
        aud = target.replace("questions_for_", "").replace("product_manager", "product_manager")
        if aud == "product_manager":
            rk = _AUDIENCE_PM
        elif aud == "developers":
            rk = _AUDIENCE_DEV
        elif aud == "customer":
            rk = _AUDIENCE_CUST
        else:
            rk = _AUDIENCE_QA
        seen: set[str] = set()
        for row in (rule.get(rk) or []) + (llm.get(target) or []):
            if not isinstance(row, dict):
                continue
            q = str(row.get("question") or "").strip()
            if not q:
                continue
            k = q[:120].lower()
            if k in seen:
                continue
            seen.add(k)
            merged[target].append(
                {
                    "category": str(row.get("category") or "general")[:80],
                    "severity": str(row.get("severity") or "important"),
                    "question": q[:500],
                }
            )
            if len(merged[target]) >= 14:
                break

    seen_c: set[str] = set()
    for row in llm.get("challenge_during_uac") or []:
        if isinstance(row, dict):
            c = str(row.get("challenge") or "").strip()
            if c and c[:120].lower() not in seen_c:
                seen_c.add(c[:120].lower())
                merged["challenge_during_uac"].append(
                    {"challenge": c[:500], "severity": str(row.get("severity") or "important")}
                )
    return merged


def format_uac_negotiation_markdown(bundle: dict[str, Any], *, max_chars: int = 6000) -> str:
    """Human-readable block for ``uac_points`` / executive sections."""
    lines = ["\n### UAC negotiation intelligence (by audience)\n"]
    titles = {
        "questions_for_product_manager": "Product Manager",
        "questions_for_developers": "Developers",
        "questions_for_customer": "Customer",
        "questions_for_qa": "QA",
    }
    for key, title in titles.items():
        rows = bundle.get(key) or []
        if not rows:
            continue
        lines.append(f"**{title}**")
        for row in rows[:10]:
            if not isinstance(row, dict):
                continue
            sev = row.get("severity", "important")
            q = str(row.get("question") or "").strip()
            cat = str(row.get("category") or "").strip()
            if q:
                lines.append(f"- [{sev}] ({cat}) {q}")
        lines.append("")
    ch = bundle.get("challenge_during_uac") or []
    if ch:
        lines.append("**What QA should challenge during UAC**")
        for row in ch[:10]:
            if isinstance(row, dict):
                lines.append(f"- [{row.get('severity', 'important')}] {row.get('challenge', '')}")
        lines.append("")
    text = "\n".join(lines).strip()
    return text[:max_chars]


class UACNegotiationEngine:
    """Build audience-grouped UAC questions and challenge points from Jira + copilot signals."""

    async def build(
        self,
        *,
        jira_key: str | None,
        issue_type: str,
        labels: list[str],
        customer_context: dict[str, Any] | str,
        risk_analysis: dict[str, Any],
        gap_analysis: dict[str, Any],
        context_excerpt: str = "",
    ) -> dict[str, Any]:
        rule = _rule_based_questions(
            gap_analysis=gap_analysis,
            risk_analysis=risk_analysis,
            labels=labels,
            issue_type=issue_type,
            customer_context=customer_context,
        )
        challenges = _challenge_heuristics(
            context_excerpt=context_excerpt,
            labels=labels,
            risk_analysis=risk_analysis,
        )

        llm_pack: dict[str, Any] | None = None
        if is_llm_available():
            try:
                system = (
                    "You are a senior QA lead preparing UAC negotiation. Return JSON ONLY with keys: "
                    "questions_for_product_manager, questions_for_developers, questions_for_customer, "
                    "questions_for_qa, challenge_during_uac. "
                    "Each questions_* value is an array of objects: "
                    '{"category":"short_snake","severity":"critical|important|optional","question":"one sentence"}. '
                    "Categories for PM: unclear_requirements, unsupported_behavior, out_of_scope, "
                    "backward_compatibility, rollout_expectations. "
                    "For developers: api_behavior, expected_backend_flow, feature_flags, migration_concerns, "
                    "performance_concerns. "
                    "For customer: exact_workflow, expected_behavior, existing_workarounds, priority_scenarios. "
                    "For QA: regression_areas, edge_cases, environment_matrix, automation_blockers. "
                    "challenge_during_uac is an array of {severity, challenge} covering undefined behavior, "
                    "inconsistent old/new behavior, unclear output expectations, unsupported MIME types, "
                    "missing validation logic where grounded in evidence. "
                    "Max 5 items per questions_* array, max 8 challenges. No markdown, no prose outside JSON."
                )
                cust_blob = (
                    json.dumps(customer_context, ensure_ascii=False)
                    if isinstance(customer_context, dict)
                    else str(customer_context)
                )[:2000]
                user = (
                    f"jira_key:{jira_key or 'n/a'}\nissue_type:{issue_type}\nlabels:{json.dumps(labels)[:800]}\n"
                    f"customer_context:{cust_blob}\n"
                    f"risk:{json.dumps(risk_analysis, ensure_ascii=False)[:3500]}\n"
                    f"gaps:{json.dumps(gap_analysis, ensure_ascii=False)[:4500]}\n"
                    f"context_excerpt:{(context_excerpt or '')[:6000]}"
                )
                raw_txt = await generate_text(system, user, max_tokens=1200, step_name="jira_uac_negotiation")
                raw_txt = raw_txt.strip()
                if raw_txt.startswith("```"):
                    raw_txt = re.sub(r"^```(?:json)?\s*", "", raw_txt)
                    raw_txt = re.sub(r"\s*```$", "", raw_txt)
                parsed = json.loads(raw_txt)
                if isinstance(parsed, dict):
                    llm_pack = _normalize_llm_pack(parsed)
            except Exception:
                llm_pack = None

        if llm_pack:
            merged = _merge_rule_and_llm(rule, llm_pack)
        else:
            merged = _empty_pack()
            merged["questions_for_product_manager"] = rule.get(_AUDIENCE_PM) or []
            merged["questions_for_developers"] = rule.get(_AUDIENCE_DEV) or []
            merged["questions_for_customer"] = rule.get(_AUDIENCE_CUST) or []
            merged["questions_for_qa"] = rule.get(_AUDIENCE_QA) or []

        seen_ch = {c["challenge"][:100].lower() for c in merged.get("challenge_during_uac") or []}
        for c in challenges:
            k = c["challenge"][:100].lower()
            if k not in seen_ch:
                seen_ch.add(k)
                merged.setdefault("challenge_during_uac", []).append(c)

        return merged
