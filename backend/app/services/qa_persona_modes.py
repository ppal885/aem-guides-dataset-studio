"""
QA Persona Modes — shift copilot tone and priorities (Senior QA, Automation Architect, etc.).
"""

from __future__ import annotations

import re
from typing import Final

# Internal slug -> display label (API / UI)
PERSONA_LABELS: Final[dict[str, str]] = {
    "senior_qa": "Senior QA",
    "automation_architect": "Automation Architect",
    "release_qa": "Release QA",
    "exploratory_tester": "Exploratory Tester",
    "performance_qa": "Performance QA",
    "customer_escalation_qa": "Customer Escalation QA",
}

_DEFAULT_SLUG = "senior_qa"

# Normalized lookup: underscores and multiple spaces collapsed
_ALIAS_TO_SLUG: Final[dict[str, str]] = {
    "seniorqa": "senior_qa",
    "senior_qa": "senior_qa",
    "senior qa": "senior_qa",
    "automationarchitect": "automation_architect",
    "automation_architect": "automation_architect",
    "automation architect": "automation_architect",
    "releaseqa": "release_qa",
    "release_qa": "release_qa",
    "release qa": "release_qa",
    "exploratorytester": "exploratory_tester",
    "exploratory_tester": "exploratory_tester",
    "exploratory tester": "exploratory_tester",
    "performanceqa": "performance_qa",
    "performance_qa": "performance_qa",
    "performance qa": "performance_qa",
    "customerescalationqa": "customer_escalation_qa",
    "customer_escalation_qa": "customer_escalation_qa",
    "customer escalation qa": "customer_escalation_qa",
    "escalation": "customer_escalation_qa",
    "customer escalation": "customer_escalation_qa",
}


def _norm_key(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[\s_]+", " ", s)
    return s.strip()


def normalize_persona_mode(raw: str | None) -> str:
    """Return internal slug; unknown values fall back to Senior QA."""
    if not raw or not str(raw).strip():
        return _DEFAULT_SLUG
    key = _norm_key(str(raw))
    key_compact = re.sub(r"\s+", "", key)
    if key_compact in _ALIAS_TO_SLUG:
        return _ALIAS_TO_SLUG[key_compact]
    if key in _ALIAS_TO_SLUG:
        return _ALIAS_TO_SLUG[key]
    # Substring hints
    if "automation" in key and "architect" in key:
        return "automation_architect"
    if key.startswith("release") and "qa" in key_compact:
        return "release_qa"
    if "exploratory" in key:
        return "exploratory_tester"
    if "performance" in key:
        return "performance_qa"
    if "escalation" in key or ("customer" in key and "qa" in key_compact):
        return "customer_escalation_qa"
    if "senior" in key:
        return "senior_qa"
    return _DEFAULT_SLUG


def persona_label(slug: str) -> str:
    return PERSONA_LABELS.get(slug, PERSONA_LABELS[_DEFAULT_SLUG])


_COPILOT_SECTIONS: Final[dict[str, str]] = {
    "senior_qa": (
        "Persona: Senior QA — balance depth vs delivery. Emphasize risk-based prioritization, "
        "clear oracles, evidence-backed statements, and cross-functional alignment (PM/Dev/Support)."
    ),
    "automation_architect": (
        "Persona: Automation Architect — prioritize framework fit (UI vs API vs hybrid), CI stability, "
        "flakiness drivers, testability hooks, contract checks, and maintainable layering. Call out "
        "where UI automation is high-cost vs API-first coverage."
    ),
    "release_qa": (
        "Persona: Release QA — prioritize regression blast radius, release blockers, suite prioritization "
        "and rerun strategy, compatibility across AEM/Guides versions, and sign-off gates vs timeboxed smoke."
    ),
    "exploratory_tester": (
        "Persona: Exploratory Tester — prioritize charters, heuristics, session-based findings, "
        "tours (claims/configuration/variables), and defect clustering; distinguish surfaced issues from evidence gaps."
    ),
    "performance_qa": (
        "Persona: Performance QA — prioritize scale (large maps/topics), latency/throughput signals, "
        "resource limits, soak/stability, publish pipeline cost, and profiling/metrics to capture during repro."
    ),
    "customer_escalation_qa": (
        "Persona: Customer Escalation QA — prioritize customer-visible pain, exact reproduction fidelity, "
        "workaround impact on validation, urgency and comms cadence, and data parity with customer corpus "
        "(anonymized where needed)."
    ),
}


_EXTRA_INSTRUCTIONS: Final[dict[str, str]] = {
    "senior_qa": (
        "Answer as a Senior QA: structured, pragmatic, and risk-ranked; tie recommendations to evidence; "
        "flag assumptions explicitly."
    ),
    "automation_architect": (
        "Answer as an Automation Architect: lead with framework/CI fit, flakiness risks, and API-vs-UI split; "
        "propose stable seams (contracts, services) before heavy UI flows."
    ),
    "release_qa": (
        "Answer as Release QA: foreground regression risk, candidate release blockers, and which suites "
        "to run first vs defer; relate to enterprise failure/coverage signals when present."
    ),
    "exploratory_tester": (
        "Answer as an Exploratory Tester: use exploratory framing (missions, risks, varied data), "
        "without replacing missing acceptance criteria—surface surprises and follow-up probes."
    ),
    "performance_qa": (
        "Answer as Performance QA: call out load shape, dataset size, warm vs cold paths, and what metrics "
        "would prove the fix; avoid claiming numbers not in evidence."
    ),
    "customer_escalation_qa": (
        "Answer as Customer Escalation QA: stress reproducibility, customer impact, workaround side-effects, "
        "and time-critical validation; keep tone factual and escalation-ready."
    ),
}


def build_persona_copilot_section(slug: str) -> str:
    return _COPILOT_SECTIONS.get(slug, _COPILOT_SECTIONS[_DEFAULT_SLUG])


def build_persona_extra_instructions(slug: str) -> str:
    return _EXTRA_INSTRUCTIONS.get(slug, _EXTRA_INSTRUCTIONS[_DEFAULT_SLUG])
