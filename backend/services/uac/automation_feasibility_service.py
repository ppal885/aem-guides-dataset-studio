"""Automation feasibility for AEM Guides validation (API/UI/publishing)."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_qa_automation_rubric import recommend_layer, rubric_to_dict, score_automation_fit

from services.uac.evidence_store import RequirementEvidenceStore

_API_TERMS = (
    "referencelistener",
    "validatexml",
    "asset/update",
    "rest/api",
    "aem guides api",
)


def analyze_automation_feasibility(en: JiraEnrichedDocument, store: RequirementEvidenceStore) -> dict[str, Any]:
    eid = store.add(
        "current_jira",
        f"Automation rubric input for {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )
    blob = f"{en.summary}\n{en.description}\n{en.raw_text or ''}"[:16000]
    rubric = score_automation_fit(blob)
    layer = recommend_layer(blob, rubric)
    rd = rubric_to_dict(rubric)

    text_l = blob.lower()
    apis = [t for t in _API_TERMS if t.replace("_", "").lower() in text_l.replace("_", "").lower() or t in text_l]

    api_fit = "Strong" if rd["automation_fit"] == "Yes" and layer in ("API", "Hybrid") else rd["automation_fit"]
    ui_fit = "Strong" if "web editor" in text_l or "ui" in en.domain else "Partial"
    pub_fit = "Strong" if "native_pdf" in text_l or "publish" in text_l else "Partial"
    deterministic = "High" if rd["deterministic_expected_result"] >= 1.2 else "Medium"
    flaky = "Elevated" if rd["maintenance_risk_penalty"] >= 0.4 else "Moderate"
    artifacts: list[str] = []
    if "map" in text_l or "ditamap" in text_l:
        artifacts.append("Minimal repro DITA map + topics referenced in ticket.")
    if "baseline" in text_l:
        artifacts.append("Baseline snapshot IDs or export artifacts for before/after compare.")
    if "pdf" in text_l:
        artifacts.append("Golden PDF hash or pixel-diff baseline (if policy allows).")

    return {
        "api_automation_fit": api_fit,
        "ui_automation_fit": ui_fit,
        "publishing_validation_fit": pub_fit,
        "deterministic_validation": deterministic,
        "flaky_risk": flaky,
        "required_artifacts": artifacts[:8],
        "relevant_apis": apis[:8],
        "rubric": rd,
        "recommended_layer": layer,
        "evidence": [eid],
    }


__all__ = ["analyze_automation_feasibility"]
