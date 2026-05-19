"""Output expectation and parity risk analysis (AEM Guides channels)."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore
from services.uac.uac_output_parity import build_output_parity
from services.uac_generation_service import _build_context


def analyze_output_expectations(
    en: JiraEnrichedDocument,
    similar_payload: list[dict[str, Any]],
    store: RequirementEvidenceStore,
) -> dict[str, Any]:
    eid = store.add(
        "current_jira",
        f"Output analysis for {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )
    ctx = _build_context(en.model_dump(), similar_payload, {})
    parity = build_output_parity(ctx, similar_rows=similar_payload)

    outputs_discussed = list(en.affected_outputs or [])
    parity_risks = [f"{p.get('source')} → {p.get('target')}: {p.get('risk')}" for p in parity.get("parity_pairs") or []]
    undefined: list[str] = []
    if not outputs_discussed:
        undefined.append("Affected outputs not classified — preview/native_pdf/sites expectations undefined.")
    rendering: list[str] = []
    meta_risks: list[str] = []
    blob = f"{en.summary} {en.description}".lower()
    if "metadata" in blob or "topicmeta" in blob or "metadata" in [x.lower() for x in outputs_discussed]:
        meta_risks.append("Metadata propagation to published outputs may need explicit verification per channel.")
    if "native" in blob and "pdf" in blob:
        rendering.append("Native PDF font/layout fidelity vs editor preview should be explicitly compared if customer cares.")

    pts = parity.get("validation_points") or []
    for p in pts[:4]:
        if isinstance(p, str):
            rendering.append(p)

    return {
        "outputs_discussed": outputs_discussed,
        "parity_risks": parity_risks[:10],
        "undefined_behavior": undefined,
        "rendering_risks": rendering[:8],
        "metadata_propagation_risks": meta_risks[:6],
        "evidence": [eid],
        "_parity_required": bool(parity.get("parity_required")),
    }


__all__ = ["analyze_output_expectations"]
