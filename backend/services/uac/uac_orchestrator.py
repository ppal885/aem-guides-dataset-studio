"""UAC Requirement Intelligence orchestrator — multi-source retrieval, evidence manifest, structured JSON."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.core.schemas_uac_intelligence import UacRequirementIntelligenceResponse
from app.core.structured_logging import LoggingContext, get_structured_logger
from app.services.uac_copilot_analyze_service import _load_or_fetch_enriched

from services.uac.acceptance_criteria_service import generate_acceptance_criteria
from services.uac.automation_feasibility_service import analyze_automation_feasibility
from services.uac.backward_compatibility_service import analyze_backward_compatibility
from services.uac.customer_impact_service import analyze_customer_impact
from services.uac.evidence_store import RequirementEvidenceStore
from services.uac.jira_enrichment_service import classification_from_enrichment, enrichment_to_intelligence_dict
from services.uac.multi_source_retrieval_service import retrieve_for_intelligence
from services.uac.output_expectation_service import analyze_output_expectations
from services.uac.requirement_ambiguity_service import detect_ambiguities
from services.uac.uac_discussion_service import build_discussion_questions

logger = get_structured_logger(__name__)


def run_requirement_intelligence(
    jira_key: str,
    *,
    debug: bool = False,
    include_docs: bool = True,
    max_similar_jiras: int = 8,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Synchronous pipeline: load Jira → enrich → retrieve → analyze → return JSON dict.

    Validate with ``UacRequirementIntelligenceResponse.model_validate`` at the API boundary.
    """
    cid = (correlation_id or "").strip() or str(uuid.uuid4())
    warnings: list[str] = []

    with LoggingContext(correlation_id=cid):
        logger.info_structured(
            "uac_intelligence_start",
            extra_fields={"jira_key": jira_key.strip(), "correlation_id": cid},
        )
        enriched, _source = _load_or_fetch_enriched(jira_key.strip())
        enriched = _ensure_enriched_model(enriched)

        store = RequirementEvidenceStore()
        store.add(
            "current_jira",
            f"Primary issue {enriched.jira_key}",
            str(enriched.jira_key or ""),
            {"summary": (enriched.summary or "")[:400]},
        )

        retrieval = retrieve_for_intelligence(
            enriched,
            max_similar_jiras=max_similar_jiras,
            include_docs=include_docs,
            debug=debug,
        )
        similar = list(retrieval.get("similar_jiras") or [])

        for s in similar:
            eid = store.add(
                "similar_jira",
                (s.get("why_similar") or "")[:500],
                str(s.get("jira_key") or ""),
                {"title": s.get("title"), "scores": s.get("scores")},
            )
            s["evidence_id"] = eid
            if not s.get("why_similar") and s.get("explanation"):
                expl = s.get("explanation") if isinstance(s.get("explanation"), dict) else {}
                s["why_similar"] = str(expl.get("why_similar") or "")

        for d in retrieval.get("experience_league") or []:
            eid = store.add(
                "experience_league_doc",
                (d.get("snippet") or "")[:800],
                str(d.get("url") or ""),
                {"title": d.get("title")},
            )
            d["evidence_id"] = eid

        for d in retrieval.get("dita_spec") or []:
            eid = store.add(
                "dita_ot_doc",
                (d.get("text_content") or "")[:800],
                str(d.get("source_url") or ""),
                {"element": d.get("element_name")},
            )
            d["evidence_id"] = eid

        if not similar and max_similar_jiras > 0:
            warnings.append(
                "No strong similar Jira chunks met the fusion threshold — historical regression intelligence is limited."
            )

        customer_impact = analyze_customer_impact(enriched, store)
        ambiguities = detect_ambiguities(enriched, store)
        missing_expectations: list[str] = []
        acceptance, miss_ac = generate_acceptance_criteria(enriched, store)
        missing_expectations.extend(miss_ac)

        out_exp = analyze_output_expectations(enriched, similar, store)
        parity_flag = bool(out_exp.pop("_parity_required", False))

        bc = analyze_backward_compatibility(enriched, similar, store)
        auto = analyze_automation_feasibility(enriched, store)

        pm_q, dev_q, qa_q, decisions = build_discussion_questions(enriched, ambiguities, store)

        high_amb = sum(1 for a in ambiguities if a.get("severity") == "high")
        level = "high" if high_amb >= 2 or parity_flag else "medium" if high_amb == 1 else "low"
        drivers: list[str] = []
        if high_amb:
            drivers.append(f"{high_amb} high-severity ambiguity(ies) require alignment before UAC sign-off.")
        if parity_flag:
            drivers.append("Cross-output parity flagged — divergent behavior across channels is a release risk.")
        if customer_impact.get("customer_names"):
            drivers.append("Named customers on the ticket elevate expectation-management risk.")

        doc_evidence: list[dict[str, Any]] = []
        for d in retrieval.get("experience_league") or []:
            doc_evidence.append(
                {
                    "source": "experience_league",
                    "title": d.get("title"),
                    "url": d.get("url"),
                    "snippet": d.get("snippet"),
                    "evidence_id": d.get("evidence_id"),
                    "retrieval_score_note": "semantic_chroma_aem_guides",
                }
            )
        for d in retrieval.get("dita_spec") or []:
            doc_evidence.append(
                {
                    "source": "dita_ot",
                    "title": d.get("element_name") or "dita_spec",
                    "url": d.get("source_url"),
                    "snippet": d.get("text_content"),
                    "evidence_id": d.get("evidence_id"),
                    "retrieval_score_note": "semantic_chroma_dita_spec",
                }
            )

        requirement_understanding = {
            "summary": enriched.summary or "",
            "stated_expected": (enriched.expected_behavior or "")[:2000],
            "stated_actual": (enriched.actual_behavior or "")[:2000],
            "domain_hypothesis": enriched.domain or "unknown",
            "key_entities": list(enriched.dita_entities or []),
            "key_outputs": list(enriched.affected_outputs or []),
        }

        confidence = {
            "overall": "medium" if similar else "low",
            "similar_jira_count": len(similar),
            "documentation_hits_el": len(retrieval.get("experience_league") or []),
            "documentation_hits_dita": len(retrieval.get("dita_spec") or []),
            "notes": "Low similarity or empty RAG corpora reduces confidence; statements are evidence-tagged.",
        }

        quality_score = {
            "evidence_coverage": round(min(1.0, len(store.records) / 15.0), 3),
            "clarity_of_expectations": 1.0 if (enriched.expected_behavior or "").strip() else 0.35,
            "parity_explicitness": 0.85 if parity_flag else 0.45,
        }

        auto_trim = {k: v for k, v in auto.items() if k != "rubric"}
        auto_trim["recommended_layer"] = auto.get("recommended_layer", "")

        similar_out = [
            {
                "jira_key": str(s.get("jira_key") or ""),
                "title": str(s.get("title") or ""),
                "why_similar": str(s.get("why_similar") or ""),
                "scores": s.get("scores"),
                "evidence_id": s.get("evidence_id"),
                "excerpt": str(s.get("document_excerpt") or ""),
            }
            for s in similar
        ]

        dbg: dict[str, Any] = dict(retrieval.get("debug") or {})
        if debug:
            dbg["enrichment_snapshot"] = enrichment_to_intelligence_dict(enriched)
            dbg["automation_rubric"] = auto.get("rubric")
        else:
            dbg.setdefault("note", "Set debug=true for weak similar matches, EL diagnostics, and enrichment dump.")

        payload: dict[str, Any] = {
            "jira_key": str(enriched.jira_key or ""),
            "correlation_id": cid,
            "classification": classification_from_enrichment(enriched),
            "requirement_understanding": requirement_understanding,
            "ambiguities": ambiguities,
            "missing_expectations": missing_expectations,
            "acceptance_criteria": acceptance,
            "pm_questions": pm_q,
            "dev_questions": dev_q,
            "qa_questions": qa_q,
            "cross_team_decisions": decisions,
            "customer_impact": customer_impact,
            "output_expectations": out_exp,
            "backward_compatibility": bc,
            "automation_feasibility": auto_trim,
            "similar_jira_evidence": similar_out,
            "documentation_evidence": doc_evidence,
            "risk_summary": {
                "level": level,
                "drivers": drivers[:8],
                "message": "; ".join(drivers[:3]) or "Review evidence manifest and ambiguities for residual risk.",
            },
            "confidence": confidence,
            "quality_score": quality_score,
            "warnings": warnings,
            "evidence_manifest": store.manifest(),
            "debug": dbg,
        }

        logger.info_structured(
            "uac_intelligence_done",
            extra_fields={"jira_key": enriched.jira_key, "correlation_id": cid, "evidence_count": len(store.records)},
        )
        return payload


def _ensure_enriched_model(enriched: JiraEnrichedDocument | Any) -> JiraEnrichedDocument:
    if isinstance(enriched, JiraEnrichedDocument):
        return enriched
    return JiraEnrichedDocument.model_validate(enriched)


def validate_intelligence_response(raw: dict[str, Any]) -> UacRequirementIntelligenceResponse:
    return UacRequirementIntelligenceResponse.model_validate(raw)


__all__ = ["run_requirement_intelligence", "validate_intelligence_response"]
