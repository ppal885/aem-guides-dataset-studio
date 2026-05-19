"""Infer workflow-level customer impact from Jira enrichment (no named customer hallucination)."""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore

_CALS_RE = re.compile(r"\b(cals|table|entry|colspec)\b", re.I)
_VALIDATION_RE = re.compile(r"\b(validat|dtd|xsd|schema|jdita|well[- ]formed)\b", re.I)
_MIGRATION_RE = re.compile(r"\b(migrat|upgrade|import|convert)\b", re.I)
_LARGE_REPO_RE = re.compile(r"\b(10k|\b\d{3,}\s+topics|large\s+content|repository|bulk)\b", re.I)


def analyze_customer_impact(
    en: JiraEnrichedDocument,
    store: RequirementEvidenceStore,
) -> dict[str, Any]:
    """Rule-based workflow impact; confidence lowered when inference is heuristic."""

    eid = store.add(
        "current_jira",
        f"Ticket {en.jira_key}: domain={en.domain}, entities={en.dita_entities}, outputs={en.affected_outputs}",
        str(en.jira_key or ""),
        {"field": "enrichment_snapshot"},
    )

    text = " ".join(
        [
            en.summary or "",
            en.description or ""[:8000],
            " ".join(en.symptoms or []),
            " ".join(en.labels or []),
        ]
    ).lower()

    customers = [str(x).strip() for x in (en.customer_names or []) if str(x).strip()][:15]
    workflow_impacts: list[str] = []
    potential_risks: list[str] = []
    sensitive: list[str] = []
    confidence_note = "high" if customers else "medium"

    ents = {str(x).lower() for x in (en.dita_entities or [])}
    outs = {str(x).lower() for x in (en.affected_outputs or [])}

    if "native_pdf" in outs or "native pdf" in text:
        workflow_impacts.append(
            "Publishing pipeline / Native PDF generation may affect customer sign-off on printable deliverables."
        )
        sensitive.append("publishing_sensitive")
    if "preview" in outs or "preview" in text:
        workflow_impacts.append("Authoring-time preview expectations may differ from publish-time outputs (review cycles).")
        sensitive.append("authoring_preview")
    if "aem_sites" in outs or "sites" in outs or "sites output" in text:
        workflow_impacts.append("AEM Sites output paths affect web delivery and caching assumptions.")
        sensitive.append("sites_output")
    if "baseline" in text or "baseline" in ents:
        workflow_impacts.append("Baseline/versioning touches enterprise release and rollback workflows.")
        sensitive.append("baseline_workflow")
    if any(x in ents for x in ("conref", "keyref", "conkeyref", "keydef")) or any(x in text for x in ("conref", "keyref")):
        workflow_impacts.append("Keyref/conref resolution impacts reuse governance and link integrity across maps.")
        sensitive.append("xml_reuse")
    if "ditaval" in ents or "ditaval" in text:
        workflow_impacts.append("DITAVAL filtering affects conditional content visible to different customer profiles.")
        sensitive.append("conditional_publishing")
    if _CALS_RE.search(text) or "table" in ents:
        workflow_impacts.append(
            "CALS/table-heavy content often correlates with manufacturing or S1000D-adjacent doc sets (layout-sensitive)."
        )
        sensitive.append("table_layout")
    if _VALIDATION_RE.search(text):
        workflow_impacts.append("Strict XML or validation emphasis implies governance-heavy content pipelines.")
        sensitive.append("xml_governance")
    if _MIGRATION_RE.search(text):
        workflow_impacts.append("Migration/upgrade context implies bulk content movement and regression sensitivity.")
        sensitive.append("migration")
        confidence_note = "medium"
    if _LARGE_REPO_RE.search(text):
        potential_risks.append("Large-repository scenarios amplify blast radius for publishing or indexing defects.")
        confidence_note = "medium"

    if not customers:
        potential_risks.append(
            "No indexed customer names on ticket — workflow impact is speculative; confirm with PM or support metadata."
        )
        confidence_note = "low"

    return {
        "customer_names": customers,
        "workflow_impacts": workflow_impacts[:12],
        "potential_customer_risks": potential_risks[:8],
        "sensitive_workflows": sensitive,
        "confidence": {
            "overall": confidence_note,
            "evidence": [eid],
            "method": "rule_based_enrichment_plus_text_heuristics",
        },
    }


__all__ = ["analyze_customer_impact"]
