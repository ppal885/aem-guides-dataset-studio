"""Gate automation planning on observable expected behavior / AC (no invented assertions)."""

from __future__ import annotations

import re
from typing import Any


def _non_empty(s: str) -> bool:
    return bool((s or "").strip())


def extract_jira_observables(
    jira_summary: str,
    jira_description: str,
) -> dict[str, str]:
    """Lightweight field extraction from pasted Jira-style text."""
    text = f"{jira_summary}\n{jira_description}".strip()
    out: dict[str, str] = {
        "observed_bug": "",
        "reproduction_trigger": "",
        "expected_fixed_behavior": "",
        "acceptance_criteria": "",
        "source_quote": "",
        "assertion_method": "",
    }
    if not text:
        return out

    m = re.search(
        r"(?is)(?:actual|current)\s*(?:behavior|result)?\s*[:.\s]*(.+?)(?=(?:\n\s*(?:expected|acceptance|steps))|(?:\Z))",
        text,
    )
    if m:
        out["observed_bug"] = m.group(1).strip()[:8000]

    m = re.search(
        r"(?is)(?:expected|expect)\s*(?:behavior|result)?\s*[:.\s]*(.+?)(?=(?:\n\s*(?:actual|acceptance|steps))|(?:\Z))",
        text,
    )
    if m:
        out["expected_fixed_behavior"] = m.group(1).strip()[:8000]

    m = re.search(
        r"(?is)(?:acceptance|acceptance\s*criteria)\s*[:.\s]*(.+?)(?=(?:\n\s*(?:expected|actual|steps))|(?:\Z))",
        text,
    )
    if m:
        out["acceptance_criteria"] = m.group(1).strip()[:8000]

    m = re.search(
        r"(?is)(?:steps?\s*to\s*reproduce|repro\s*steps)\s*[:.\s]*(.+?)(?=(?:\n\s*(?:expected|actual|acceptance))|(?:\Z))",
        text,
    )
    if m:
        out["reproduction_trigger"] = m.group(1).strip()[:8000]

    if out["expected_fixed_behavior"] or out["acceptance_criteria"]:
        quote_src = out["acceptance_criteria"] or out["expected_fixed_behavior"]
        out["source_quote"] = quote_src[:2000]
        out["assertion_method"] = "Trace Then assertions to Jira expected/AC quote."

    return out


def plan_readiness(
    *,
    repro_steps: str,
    expected_behavior: str,
    acceptance_criteria: str,
    jira_summary: str,
    jira_description: str,
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Returns ``(blocked, blocking_questions, payload)``.
    Blocks when there is no observable expected outcome (expected behavior or AC).
    """
    extracted = extract_jira_observables(jira_summary, jira_description)
    exp = expected_behavior.strip() or extracted["expected_fixed_behavior"]
    ac = acceptance_criteria.strip() or extracted["acceptance_criteria"]
    repro = repro_steps.strip() or extracted["reproduction_trigger"]

    blocking: list[str] = []
    hints: list[str] = []

    if not _non_empty(exp) and not _non_empty(ac):
        blocking.append(
            "What concrete, observable outcome (expected behavior or acceptance criteria) proves this Jira is resolved? "
            "Add that to Jira or the form before generating assertions — do not invent Then steps from assumptions."
        )

    if not _non_empty(repro) and not _non_empty(extracted.get("observed_bug", "")):
        hints.append(
            "Add reproduction steps or an Actual/Current behavior section to strengthen scenario planning."
        )

    blocked = len(blocking) > 0
    payload = {
        **extracted,
        "expected_fixed_behavior": exp or extracted["expected_fixed_behavior"],
        "acceptance_criteria": ac or extracted["acceptance_criteria"],
        "reproduction_trigger": repro or extracted["reproduction_trigger"],
        "planning_hints": hints,
    }
    qsrc = (ac or exp or "").strip()
    if qsrc and not (payload.get("source_quote") or "").strip():
        payload["source_quote"] = qsrc[:2000]
    if qsrc and not (payload.get("assertion_method") or "").strip():
        payload["assertion_method"] = "Trace Then assertions to Jira expected/AC quote."
    return blocked, blocking, payload
