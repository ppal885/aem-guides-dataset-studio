"""Detect requirement ambiguities for UAC alignment (evidence-cited)."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore


def _e(en: JiraEnrichedDocument, store: RequirementEvidenceStore) -> str:
    return store.add(
        "current_jira",
        f"Ambiguity scan fields for {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )


def detect_ambiguities(en: JiraEnrichedDocument, store: RequirementEvidenceStore) -> list[dict[str, Any]]:
    eid = _e(en, store)
    items: list[dict[str, Any]] = []
    exp = (en.expected_behavior or "").strip()
    act = (en.actual_behavior or "").strip()
    outs = list(en.affected_outputs or [])
    ents = list(en.dita_entities or [])

    if not exp:
        items.append(
            {
                "ambiguity": "Expected behavior is not stated explicitly in enrichment fields.",
                "why_it_matters": "PM/QA cannot sign off without agreed expected results per output.",
                "affected_area": "acceptance",
                "who_should_clarify": "pm",
                "severity": "high",
                "evidence": [eid],
            }
        )
    if not outs:
        items.append(
            {
                "ambiguity": "Affected AEM Guides outputs are not classified (preview, Native PDF, Sites, etc.).",
                "why_it_matters": "Output-specific validation and parity expectations stay undefined.",
                "affected_area": "outputs",
                "who_should_clarify": "pm",
                "severity": "medium",
                "evidence": [eid],
            }
        )
    if not ents and (en.description or "")[:400].strip():
        items.append(
            {
                "ambiguity": "No DITA/AEM entities extracted — technical scope may be under-specified.",
                "why_it_matters": "Engineering and tech comm may interpret scope differently.",
                "affected_area": "authoring_model",
                "who_should_clarify": "cross_team",
                "severity": "medium",
                "evidence": [eid],
            }
        )
    if "parity" in (en.summary or "").lower() or "parity" in (en.description or "").lower():
        if len(outs) < 2:
            items.append(
                {
                    "ambiguity": "Parity is mentioned but fewer than two outputs are enumerated for comparison.",
                    "why_it_matters": "Cross-output parity cannot be tested without explicit output pairings.",
                    "affected_area": "parity",
                    "who_should_clarify": "qa",
                    "severity": "high",
                    "evidence": [eid],
                }
            )
    if "migration" in (en.description or "").lower() or "migration" in (en.summary or "").lower():
        items.append(
            {
                "ambiguity": "Migration context detected but backward compatibility targets are not enumerated.",
                "why_it_matters": "Customers may depend on prior artifact shapes or publish flows.",
                "affected_area": "backward_compatibility",
                "who_should_clarify": "dev",
                "severity": "medium",
                "evidence": [eid],
            }
        )

    return items[:15]


__all__ = ["detect_ambiguities"]
