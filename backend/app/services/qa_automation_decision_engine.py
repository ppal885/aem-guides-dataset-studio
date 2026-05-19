"""Enterprise automation decision record built on rubric + narrative heuristics."""

from __future__ import annotations

from typing import Any

from app.services.jira_qa_automation_rubric import (
    recommend_layer,
    rubric_to_dict,
    score_automation_fit,
)


class QAAutomationDecisionEngine:
    def decide(self, issue_text: str, *, label_intel: dict[str, Any] | None = None) -> dict[str, Any]:
        li = label_intel if isinstance(label_intel, dict) else {}
        extra = ""
        if li:
            ti = " ".join(str(x) for x in (li.get("testing_implications") or []) if x)[:2500]
            ai = " ".join(str(x) for x in (li.get("automation_implications") or []) if x)[:2500]
            uac = " ".join(str(x) for x in (li.get("uac_focus_points") or []) if x)[:1500]
            extra = f"\n\n{ti}\n{ai}\n{uac}"
        rub = score_automation_fit((issue_text or "") + extra)
        rd = rubric_to_dict(rub)
        t = ((issue_text or "") + extra).lower()
        anti: list[str] = []
        if "clipboard" in t or "paste" in t:
            anti.append("Heavy clipboard/UI timing coupling")
        if "drag" in t or "animation" in t:
            anti.append("Flaky UI interaction patterns")
        if "oauth" in t or "sso" in t:
            anti.append("Auth/session coupling unsuitable for parallel CI without harness")

        flakiness = "Low"
        if rub.maintenance_risk >= 0.5 or len(anti) >= 2:
            flakiness = "High"
        elif rub.maintenance_risk >= 0.25:
            flakiness = "Medium"

        if "flaky" in t or any("flaky" in str(x).lower() for x in (li.get("automation_implications") or [])):
            anti.append("Label intelligence: flaky — expect reruns/quarantine; defer scaling UI automation.")
            if flakiness == "Low":
                flakiness = "Medium"
            elif flakiness == "Medium":
                flakiness = "High"

        layers: list[str] = []
        layer = recommend_layer((issue_text or "") + extra, rub)
        if layer:
            layers.append(layer)
        if layer != "API" and "API" not in layers:
            if "/api/" in t or "rest" in t:
                layers.append("API")
        if layer != "UI" and any(x in t for x in ("web editor", "click", "button")):
            layers.append("UI")
        layers = list(dict.fromkeys(layers)) or ["Hybrid"]

        pyramid = "Lean toward API contracts under authoring flows; add minimal UI smoke."
        if rub.fit_label == "No":
            pyramid = "Manual exploration first; automate only after oracle stabilizes."
        elif rub.stable_selectors_or_api >= 1.0:
            pyramid = "Strong API/Test-service layer candidate; UI as thin smoke."

        return {
            "decision": rub.fit_label,
            "score": rub.score_0_10,
            "recommended_layers": layers,
            "flakiness_risk": flakiness,
            "ci_feasibility": "Good" if rub.ci_headless >= 0.7 else ("Fair" if rub.ci_headless >= 0.4 else "Challenging"),
            "maintenance_cost": "High" if rub.maintenance_risk >= 0.5 else ("Medium" if rub.maintenance_risk >= 0.25 else "Low"),
            "test_pyramid_fit": pyramid,
            "recommended_strategy": (
                f"Primary layer: {layer}. Score {rub.score_0_10}/10 ({rub.fit_label}). "
                f"Regression signal {rd.get('regression_value')}, "
                f"maintenance_penalty {rd.get('maintenance_risk_penalty')}."
            )[:600],
            "anti_patterns": anti[:8],
            "rubric_detail": rd,
        }
