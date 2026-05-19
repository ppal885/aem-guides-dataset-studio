"""Deterministic automation-fit rubric (0–10) from issue text heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class AutomationRubricResult:
    repeatable_steps: float
    deterministic_result: float
    stable_test_data: float
    stable_selectors_or_api: float
    ci_headless: float
    regression_value: float
    maintenance_risk: float
    net_raw: float
    score_0_10: float
    fit_label: str  # Yes | No | Partial


def _has_steps(text: str) -> bool:
    t = text.lower()
    return bool(
        re.search(r"(?:step\s*\d|repro\s*steps|steps\s+to\s+reproduce|workaround)", t)
        or "1." in text[:2000]
    )


def _deterministic_signals(text: str) -> float:
    t = text.lower()
    score = 0.0
    if any(x in t for x in ("expected", "should", "must display", "verify that")):
        score += 1.0
    if any(x in t for x in ("error message", "status code", "api returns", "json")):
        score += 1.0
    if "unclear" in t or "intermittent" in t or "random" in t:
        score -= 0.5
    return max(0.0, min(2.0, score))


def _stable_data(text: str) -> float:
    t = text.lower()
    if any(x in t for x in ("test data", "fixture", "sample map", "baseline")):
        return 1.0
    if any(x in t for x in ("customer content", "production", "pii")):
        return 0.3
    return 0.6


def _selectors_api(text: str) -> float:
    t = text.lower()
    if any(x in t for x in ("/api/", "rest", "graphql", "json response", "http")):
        return 1.0
    if any(x in t for x in ("web editor", "ui", "click", "button", "modal")):
        return 0.4
    return 0.5


def _ci_feasibility(text: str) -> float:
    t = text.lower()
    bad = any(x in t for x in ("oauth", "sso", "vpn", "license server", "physical"))
    good = any(x in t for x in ("headless", "ci", "docker", "api"))
    if bad and not good:
        return 0.2
    if good:
        return 1.0
    return 0.6


def _regression_value(text: str) -> float:
    t = text.lower()
    score = 0.0
    if any(x in t for x in ("regression", " broke ", "broken", "blocker", "critical")):
        score += 1.0
    if any(x in t for x in ("publish", "baseline", "output", "pdf", "web editor")):
        score += 1.0
    return min(2.0, score)


def _maintenance_risk(text: str) -> float:
    t = text.lower()
    risk = 0.0
    if any(x in t for x in ("clipboard", "drag and drop", "timing", "flaky", "animation")):
        risk += 0.4
    if any(x in t for x in ("odt", "word", "dynamic", "third-party")):
        risk += 0.3
    if "selector" in t or "xpath" in t:
        risk += 0.2
    return min(1.0, risk)


def score_automation_fit(issue_text: str) -> AutomationRubricResult:
    """Score from concatenated summary + description + comments blob."""
    text = issue_text or ""
    rep = 2.0 if _has_steps(text) else 0.8
    det = _deterministic_signals(text)
    data = _stable_data(text)
    sel = _selectors_api(text)
    ci = _ci_feasibility(text)
    reg = _regression_value(text)
    maint = _maintenance_risk(text)

    net = rep + det + data + sel + ci + reg - maint
    net = max(0.0, min(9.0, net))
    score_10 = round((net / 9.0) * 10.0, 2)

    if score_10 >= 6.5:
        label = "Yes"
    elif score_10 >= 3.5:
        label = "Partial"
    else:
        label = "No"

    return AutomationRubricResult(
        repeatable_steps=rep,
        deterministic_result=det,
        stable_test_data=data,
        stable_selectors_or_api=sel,
        ci_headless=ci,
        regression_value=reg,
        maintenance_risk=maint,
        net_raw=round(net, 3),
        score_0_10=score_10,
        fit_label=label,
    )


def recommend_layer(text: str, rubric: AutomationRubricResult) -> str:
    t = (text or "").lower()
    if rubric.fit_label == "No" and rubric.stable_selectors_or_api < 0.5:
        return "Manual only"
    if "/api/" in t or "rest" in t or rubric.stable_selectors_or_api >= 1.0:
        if "web editor" in t or "ui" in t:
            return "Hybrid"
        return "API"
    if "web editor" in t or "click" in t:
        return "UI"
    return "Hybrid"


def rubric_to_dict(r: AutomationRubricResult) -> dict[str, Any]:
    return {
        "repeatable_steps": r.repeatable_steps,
        "deterministic_expected_result": r.deterministic_result,
        "stable_test_data": r.stable_test_data,
        "stable_selectors_api": r.stable_selectors_or_api,
        "ci_headless_feasibility": r.ci_headless,
        "regression_value": r.regression_value,
        "maintenance_risk_penalty": r.maintenance_risk,
        "net_raw": r.net_raw,
        "score_0_10": r.score_0_10,
        "automation_fit": r.fit_label,
    }
