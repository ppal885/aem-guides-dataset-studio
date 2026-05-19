"""Orchestration for UAC Copilot analyze API: DB → enrich → hybrid retrieval → LLM → critic → evidence gate."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.core.structured_logging import get_structured_logger
from app.db.jira_enrichment_repository import get_jira_by_key, upsert_jira_issue
from app.db.session import SessionLocal
from prompts.uac_prompt import build_uac_prompt
from app.services.jira_retrieval_service import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    JIRA_UAC_MIN_METADATA_OVERLAP,
    JIRA_UAC_MIN_STRONG_SIMILAR,
    JIRA_UAC_MINIMUM_EVIDENCE_THRESHOLD,
    MIN_FINAL_SCORE,
    MIN_METADATA_SCORE,
    MIN_VECTOR_SCORE,
    RetrievedJira,
    explain_similarity,
    retrieve_similar_jiras,
)
from app.services.jira_client import JiraClient
from app.services.jira_enrichment_service import enrich_jira
from app.services.llm_service import generate_text, is_llm_available
from services.answer_quality_service import generic_phrases_removed_between, score_answer_specificity
from app.services.uac_critic_service import critic_refine_uac_answer
from app.services.uac_evidence_gate import apply_uac_evidence_gate
from app.services import uac_critic_service as _uac_critic
from services.uac_generation_service import generate_uac_recommendations
from services.uac.anti_repetition_service import finalize_payload_with_anti_repetition
from services.uac.claim_verifier import verify_uac_claims
from services.uac.uac_decision_record_service import build_uac_decision_record
from services.uac.uac_guardrails import check_uac_guardrails
from services.uac.uac_output_validator import apply_strict_uac_validation, _sync_structured_from_top_level

from app.services.uac_ui_contract_service import build_uac_ui_contract
from services.uac.qa_handoff_service import build_qa_handoff_payload_for_response

logger = get_structured_logger(__name__)

_UAC_MAX_SCENARIOS: int = int(os.getenv("UAC_MAX_SCENARIOS", "7"))
_UAC_MAX_CLARIFICATIONS: int = int(os.getenv("UAC_MAX_CLARIFICATIONS", "5"))
_UAC_LLM_TIMEOUT_SECS: float = float(os.getenv("UAC_LLM_TIMEOUT_SECS", "120"))

_JIRA_FETCH_FIELDS = (
    "summary,description,labels,components,priority,status,created,updated,issuetype,"
    "comment"
)


def _jira_client_ready(client: JiraClient) -> bool:
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    return bool(client.base_url and has_auth)


def _safe_jira_fetch_error_message(jira_key: str, exc: Exception) -> str:
    """Convert Jira client failures into actionable, non-secret API messages."""

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else 0
        if code == 401:
            return "Jira authentication failed (401). Check JIRA_USERNAME/JIRA_PASSWORD, SSO restrictions, or use an API token if Jira requires it."
        if code == 403:
            return f"Jira permission denied (403). The configured user can authenticate but cannot browse {jira_key}."
        if code == 404:
            return f"Issue {jira_key} was not found in Jira, or JIRA_URL/JIRA_API_VERSION is wrong for this Jira instance."
        if code == 400:
            return f"Jira rejected the request (400). Check the Jira key {jira_key}, JIRA_URL, and JIRA_API_VERSION."
        return f"Jira returned HTTP {code} while fetching {jira_key}. Check Jira server status, permissions, and API version."
    if isinstance(exc, httpx.RequestError):
        return "Could not reach Jira. Check VPN/proxy/network access and JIRA_URL from the backend host."
    return "Could not fetch issue from Jira. Check JIRA_URL, credentials, and API version."


def _enriched_from_db_row(row: dict[str, Any]) -> JiraEnrichedDocument:
    def s(key: str, default: str = "") -> str:
        v = row.get(key)
        if v is None:
            return default
        return str(v)

    def lst(key: str) -> list[str]:
        v = row.get(key)
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        return []

    def ddict(key: str) -> dict[str, Any]:
        v = row.get(key)
        if v is None:
            return {}
        if isinstance(v, dict):
            return dict(v)
        return {}

    return JiraEnrichedDocument(
        jira_key=s("jira_key"),
        summary=s("summary"),
        description=s("description"),
        issue_type=s("issue_type"),
        status=s("status"),
        priority=s("priority"),
        labels=lst("labels"),
        components=lst("components"),
        customer_names=lst("customer_names"),
        customer_detection_debug=ddict("customer_detection_debug"),
        domain=s("domain") or "unknown",
        sub_domain=s("sub_domain"),
        affected_outputs=lst("affected_outputs"),
        affected_features=lst("affected_features"),
        dita_entities=lst("dita_entities"),
        symptoms=lst("symptoms"),
        expected_behavior=s("expected_behavior"),
        actual_behavior=s("actual_behavior"),
        qa_risk_tags=lst("qa_risk_tags"),
        automation_fit=s("automation_fit"),
        missing_info=lst("missing_info"),
        raw_text=s("raw_text"),
        enrichment_debug=ddict("enrichment_debug") or {"customer_detection": ddict("customer_detection_debug")},
        comments_digest="",
    )


def _load_or_fetch_enriched(jira_key: str) -> tuple[JiraEnrichedDocument, str]:
    """
    Return ``(enriched, source)`` where ``source`` is ``\"db\"`` or ``\"jira_live\"``.
    Raises ``ValueError`` if the issue is missing and cannot be fetched.
    """
    jk = jira_key.strip()
    db = SessionLocal()
    try:
        row = get_jira_by_key(db, jk)
        if row:
            logger.info_structured("uac_analyze_enriched_source", extra_fields={"jira_key": jk, "source": "db"})
            return _enriched_from_db_row(row), "db"
    finally:
        db.close()

    client = JiraClient()
    if not _jira_client_ready(client):
        raise ValueError(
            "Issue not found in local database and Jira is not configured (set JIRA_URL and credentials)."
        )
    issue = None
    try:
        issue = client.get_issue(jk, fields=_JIRA_FETCH_FIELDS)
    except Exception as exc:
        safe_msg = _safe_jira_fetch_error_message(jk, exc)
        logger.warning_structured(
            "uac_analyze_jira_fetch_failed",
            extra_fields={
                "jira_key": jk,
                "error_type": type(exc).__name__,
                "safe_message": safe_msg,
                "base_url_set": bool(client.base_url),
                "api_version": getattr(client, "_api", ""),
                "username_auth_configured": bool(client.username and client.password),
                "token_auth_configured": bool(client.email and client.api_token),
            },
            exc_info=True,
        )
        raise ValueError(safe_msg) from None
    if not issue:
        raise ValueError(f"Issue {jk} could not be loaded from Jira.")
    enriched = enrich_jira(issue)
    db = SessionLocal()
    try:
        upsert_jira_issue(db, enriched)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning_structured(
            "uac_analyze_persist_enrichment_failed",
            extra_fields={"jira_key": jk, "error": str(exc)},
        )
    finally:
        db.close()

    logger.info_structured("uac_analyze_enriched_source", extra_fields={"jira_key": jk, "source": "jira_live"})
    return enriched, "jira_live"


def _retrieval_query_text(en: JiraEnrichedDocument) -> str:
    parts = [
        en.summary or "",
        (en.description or "")[:12000],
        (en.raw_text or "")[:6000],
        " ".join(en.dita_entities or []),
        " ".join(en.affected_outputs or []),
    ]
    return "\n\n".join(p for p in parts if p.strip())


def _has_retrieval_anchors(en: JiraEnrichedDocument) -> bool:
    """Avoid vector-only similar Jira retrieval when the current ticket has no reusable UAC anchors."""

    return bool(
        (en.domain or "").strip().lower() not in {"", "unknown"}
        or (en.dita_entities or [])
        or (en.affected_outputs or [])
    )


def _collect_risk_section_drops(
    draft: str,
    en: JiraEnrichedDocument,
    similar: list[RetrievedJira],
) -> list[dict[str, str]]:
    _, sections = _uac_critic._split_sections(draft)
    chunk2 = sections.get(2, "")
    body = _uac_critic._body_without_heading(chunk2)
    bullets = [ln for ln in body.splitlines() if ln.strip().startswith("-")]
    if not bullets:
        return []
    res = apply_uac_evidence_gate(en, similar, "\n".join(bullets))
    return [{"text": d.text, "reason": d.reason} for d in res.dropped_points]


def _classification_payload(en: JiraEnrichedDocument) -> dict[str, Any]:
    return {
        "domain": en.domain,
        "sub_domain": en.sub_domain,
        "issue_type": en.issue_type,
        "status": en.status,
        "priority": en.priority,
        "customer_names": list(en.customer_names or []),
        "affected_outputs": list(en.affected_outputs or []),
        "dita_entities": list(en.dita_entities or [])[:25],
        "labels": list(en.labels or [])[:40],
        "components": list(en.components or [])[:30],
        "qa_risk_tags": list(en.qa_risk_tags or [])[:20],
    }


def _similar_payload(rows: list[RetrievedJira], enriched: JiraEnrichedDocument) -> list[dict[str, Any]]:
    cur = enriched.model_dump()
    out: list[dict[str, Any]] = []
    for r in rows:
        expl = explain_similarity(cur, r)
        out.append(
            {
                **expl,
                "title": r.title,
                "chunk_type": r.chunk_type,
                "scores": {
                    "final": r.final_score,
                    "vector": r.vector_score,
                    "keyword": r.keyword_score,
                    "metadata": r.metadata_score,
                    "confidence": r.confidence_score,
                },
                "evidence": {
                    "strong": r.strong_evidence,
                    "overlap_signals": r.evidence_overlap_signals,
                },
                "document_excerpt": (r.document or "")[:500],
            }
        )
    return out


def _retrieval_debug(en: JiraEnrichedDocument, similar: list[RetrievedJira]) -> dict[str, Any]:
    return {
        "domain": en.domain,
        "entities": list(en.dita_entities or [])[:40],
        "outputs": list(en.affected_outputs or [])[:40],
        "customers": list(en.customer_names or [])[:40],
        "extracted": {
            "domain": en.domain if en.domain != "unknown" else None,
            "sub_domain": en.sub_domain or None,
            "dita_entities": list(en.dita_entities or [])[:40],
            "affected_outputs": list(en.affected_outputs or [])[:40],
            "customer_names": list(en.customer_names or [])[:40],
            "issue_type": en.issue_type or None,
        },
        "scores": [
            {
                "jira_key": r.jira_key,
                "final": float(r.final_score),
                "vector": float(r.vector_score),
                "keyword": float(r.keyword_score),
                "metadata": float(r.metadata_score),
                "confidence": float(r.confidence_score),
            }
            for r in similar
        ],
        "thresholds": {
            "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
            "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
            "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
            "MIN_ENTITY_OVERLAP": JIRA_UAC_MIN_METADATA_OVERLAP,
        },
    }


def _structured_uac(en: JiraEnrichedDocument, similar: list[RetrievedJira], retrieval_debug: dict[str, Any]) -> dict[str, Any]:
    return generate_uac_recommendations(
        en,
        [row.model_dump() for row in similar],
        retrieval_debug,
    )


def _normalize_retrieval_debug(en: JiraEnrichedDocument, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Expose a stable debug contract for API callers while preserving the raw retrieval sink."""

    out = dict(raw or {})
    extracted = out.get("extracted") if isinstance(out.get("extracted"), dict) else {}
    extracted = {
        "domain": extracted.get("domain") or (en.domain if en.domain != "unknown" else None),
        "sub_domain": extracted.get("sub_domain") or (en.sub_domain or None),
        "dita_entities": list(extracted.get("dita_entities") or en.dita_entities or [])[:40],
        "affected_outputs": list(extracted.get("affected_outputs") or en.affected_outputs or [])[:40],
        "customer_names": list(extracted.get("customer_names") or en.customer_names or [])[:40],
        "issue_type": extracted.get("issue_type") or (en.issue_type or None),
    }
    out["extracted"] = extracted
    out.setdefault("extracted_domain", extracted["domain"])
    out.setdefault("extracted_entities", extracted["dita_entities"])
    out.setdefault("extracted_outputs", extracted["affected_outputs"])
    out.setdefault("extracted_customers", extracted["customer_names"])
    if "dropped_candidates" in out and "rejected_candidates" not in out:
        out["rejected_candidates"] = out["dropped_candidates"]
    else:
        out.setdefault("rejected_candidates", [])
    out.setdefault("candidates_before_rerank", [])
    out.setdefault("candidates_after_rerank", [])
    out.setdefault("candidates_final", [])
    return out


def _quality_payload(
    answer: str,
    enriched: JiraEnrichedDocument,
    similar_payload: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    quality = score_answer_specificity(answer, enriched.model_dump(), similar_payload)
    return int(quality.get("score", 0)), quality


def _uac_response(
    *,
    jira_key: str,
    enriched: JiraEnrichedDocument,
    similar: list[RetrievedJira],
    uac_answer: str,
    structured_uac: dict[str, Any],
    retrieval_debug: dict[str, Any],
    quality_score: int | None,
    answer_quality: dict[str, Any] | None = None,
    regeneration_used: bool = False,
    generic_phrases_removed: list[str] | None = None,
    dropped_generic_points: list[dict[str, Any]] | None = None,
    insufficient_similar_evidence: bool = False,
) -> dict[str, Any]:
    """Backward-compatible API payload plus top-level structured UAC fields."""

    similar_payload = _similar_payload(similar, enriched)
    payload: dict[str, Any] = {
        "jira_key": jira_key,
        "classification": structured_uac.get("classification") or _classification_payload(enriched),
        "risk_summary": structured_uac.get("risk_summary") or {},
        "similar_jiras": similar_payload,
        "structured_similar_jiras": structured_uac.get("similar_jiras") or [],
        "must_test_scenarios": structured_uac.get("must_test_scenarios") or [],
        "missing_clarifications": structured_uac.get("missing_clarifications") or [],
        "automation_fit": structured_uac.get("automation_fit") or {},
        "evidence_summary": structured_uac.get("evidence_summary") or {},
        "confidence": structured_uac.get("confidence") or {},
        "output_parity": structured_uac.get("output_parity")
        or {"parity_required": False, "parity_pairs": [], "validation_points": []},
        "uac_answer": uac_answer,
        "structured_uac": structured_uac,
        "quality_score": quality_score,
        "regeneration_used": regeneration_used,
        "generic_phrases_removed": list(generic_phrases_removed or []),
        "dropped_generic_points": list(dropped_generic_points or []),
        "insufficient_similar_evidence": insufficient_similar_evidence,
        "retrieval_debug": _normalize_retrieval_debug(enriched, retrieval_debug),
    }
    if answer_quality is not None:
        payload["answer_quality"] = answer_quality
    return payload


def _format_structured_uac_markdown(payload: dict[str, Any]) -> str:
    """Compact legacy Markdown rendering for clients that still read ``uac_answer``."""

    cls = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    risk = payload.get("risk_summary") if isinstance(payload.get("risk_summary"), dict) else {}
    lines: list[str] = [
        "### 1. Jira Classification",
        f"- **Domain:** {cls.get('domain') or 'unknown'}",
        f"- **Request Type:** {cls.get('issue_type') or 'Insufficient evidence from indexed Jira data.'}",
        f"- **Customer:** {', '.join(cls.get('customer_names') or []) or 'Insufficient evidence from indexed Jira data.'}",
        f"- **Affected Output:** {', '.join(cls.get('affected_outputs') or []) or 'Insufficient evidence from indexed Jira data.'}",
        f"- **Key DITA/AEM Entities:** {', '.join(cls.get('dita_entities') or []) or 'Insufficient evidence from indexed Jira data.'}",
        f"- **Risk Level:** {risk.get('level') or 'Insufficient evidence from indexed Jira data'}",
        "",
        "### 2. Why This Jira Is Risky",
    ]
    drivers = risk.get("drivers") if isinstance(risk.get("drivers"), list) else []
    lines.extend([f"- {d}" for d in drivers] or ["- Insufficient evidence from indexed Jira data."])
    lines.extend(["", "### 3. Similar Historical Tickets"])
    similar = payload.get("similar_jiras") if isinstance(payload.get("similar_jiras"), list) else []
    if similar:
        for row in similar[:5]:
            lines.extend(
                [
                    f"**{row.get('jira_key')}**",
                    f"- **Similarity reason:** {row.get('why_relevant') or 'Matched by retrieval evidence.'}",
                    "- **What we learned from it:** Reuse only the overlapped entity/output risk, not the full historical scope.",
                ]
            )
    else:
        lines.append("Insufficient evidence from indexed Jira data.")
    lines.extend(["", "### 4. Must-Test Scenarios"])
    scenarios = payload.get("must_test_scenarios") if isinstance(payload.get("must_test_scenarios"), list) else []
    if scenarios:
        for sc in scenarios[:_UAC_MAX_SCENARIOS]:
            lines.extend(
                [
                    "```",
                    f"Scenario: {sc.get('scenario')}",
                    f"Why: {sc.get('why')}",
                    f"Evidence: {sc.get('evidence')}",
                    f"Test Layer: {sc.get('test_layer')}",
                    f"Priority: {sc.get('priority') or ''}",
                    "```",
                ]
            )
    else:
        lines.append("Insufficient evidence from indexed Jira data.")
    lines.extend(["", "### 5. Missing Clarifications for UAC"])
    clarifications = payload.get("missing_clarifications") if isinstance(payload.get("missing_clarifications"), list) else []
    lines.extend([f"- {q.get('question')}" for q in clarifications[:_UAC_MAX_CLARIFICATIONS]] or ["- Insufficient evidence from indexed Jira data."])
    fit = payload.get("automation_fit") if isinstance(payload.get("automation_fit"), dict) else {}
    lines.extend(
        [
            "",
            "### 6. Automation Fit",
            f"- **Fit:** {fit.get('fit') or 'Partial'}",
            f"- **Best Layer:** {fit.get('primary_test_layer') or 'Manual'}",
            f"- **Reason:** {fit.get('framework') or 'Insufficient evidence from indexed Jira data.'}",
            f"- **Suggested test name:** {str(cls.get('jira_key') or 'jira').lower().replace('-', '_')}_uac",
        ]
    )
    return "\n".join(lines).strip()




async def _finalize_uac_payload(
    payload: dict[str, Any],
    enriched: JiraEnrichedDocument,
    *,
    lenient_validation: bool,
    debug: bool = False,
    include_qa_handoff: bool = False,
) -> dict[str, Any]:
    finalize_payload_with_anti_repetition(
        payload,
        enriched,
        lenient=lenient_validation,
        format_markdown_fn=_format_structured_uac_markdown,
    )
    if not (lenient_validation and payload.get("insufficient_similar_evidence")):
        cv = verify_uac_claims(
            payload,
            {"enriched_jira": enriched, "similar_jiras": payload.get("similar_jiras") or []},
            refresh_markdown=True,
            format_markdown_fn=_format_structured_uac_markdown,
        )
        verified = cv["verified_response"]
        for k, v in verified.items():
            payload[k] = v
        payload["claim_verification"] = {
            "dropped_claims": cv["dropped_claims"],
            "downgraded_claims": cv["downgraded_claims"],
            "unsupported_claims": cv["unsupported_claims"],
        }
        _sync_structured_from_top_level(payload)
    out = await apply_strict_uac_validation(
        payload,
        enriched=enriched,
        lenient=lenient_validation,
        format_markdown_fn=_format_structured_uac_markdown,
    )
    out["uac_decision_record"] = build_uac_decision_record(out, enriched)
    out["uac_guardrails"] = check_uac_guardrails(out, enriched)
    out["qa_handoff"] = await build_qa_handoff_payload_for_response(
        enriched=enriched,
        uac_answer=str(out.get("uac_answer") or ""),
        similar_jiras=list(out.get("similar_jiras") or []),
        must_test_scenarios=list(out.get("must_test_scenarios") or []),
        risk_summary=out.get("risk_summary") if isinstance(out.get("risk_summary"), dict) else {},
        insufficient_similar=bool(out.get("insufficient_similar_evidence")),
        include_qa_handoff=include_qa_handoff,
    )
    out["uac_ui"] = build_uac_ui_contract(out, debug=debug)
    return out


async def run_uac_analyze(
    jira_key: str,
    *,
    include_similar: bool = True,
    max_similar: int = 8,
    debug: bool = False,
    include_qa_handoff: bool = False,
) -> dict[str, Any]:
    """
    Full UAC analyze pipeline. Returns a JSON-serializable dict (no stack traces).
    """
    jk = jira_key.strip()
    logger.info_structured(
        "uac_analyze_start",
        extra_fields={
            "jira_key": jk,
            "include_similar": include_similar,
            "max_similar": max_similar,
            "debug": debug,
            "include_qa_handoff": include_qa_handoff,
        },
    )

    enriched, _source = _load_or_fetch_enriched(jk)

    similar: list[RetrievedJira] = []
    retrieval_sink: dict[str, Any] = {}
    can_retrieve_similar = include_similar and max_similar > 0
    if can_retrieve_similar:
        qtext = _retrieval_query_text(enriched)
        eff_domain = enriched.domain if enriched.domain != "unknown" else None
        similar = retrieve_similar_jiras(
            qtext,
            domain=eff_domain,
            dita_entities=list(enriched.dita_entities or []),
            affected_outputs=list(enriched.affected_outputs or []),
            customer_names=list(enriched.customer_names or []),
            limit=max(1, min(max_similar, 24)),
            exclude_jira_key=jk,
            base_labels=list(enriched.labels or []),
            base_components=list(enriched.components or []),
            retrieval_debug_sink=retrieval_sink if debug else None,
        )
        if debug:
            retrieval_sink.setdefault("uac_effective_domain_for_retrieval", eff_domain)
            retrieval_sink["classification_snapshot"] = _classification_payload(enriched)
        logger.info_structured(
            "uac_analyze_retrieval",
            extra_fields={"jira_key": jk, "similar_count": len(similar), "debug": debug},
        )
    elif debug:
        retrieval_sink = {
            "retrieval_query": {
                "text_preview": _retrieval_query_text(enriched)[:3000],
                "char_length": len(_retrieval_query_text(enriched)),
            },
            "extracted": {
                "domain_passed_to_retrieval": enriched.domain if enriched.domain != "unknown" else None,
                "dita_entities": list(enriched.dita_entities or []),
                "affected_outputs": list(enriched.affected_outputs or []),
                "customer_names": list(enriched.customer_names or []),
                "exclude_jira_key": jk,
            },
            "note": (
                "Similar-ticket retrieval was not run because current Jira lacks domain/entity/output anchors."
                if include_similar and max_similar > 0
                else "Similar-ticket retrieval was not run (include_similar=false or max_similar=0)."
            ),
            "classification_snapshot": _classification_payload(enriched),
        }

    def _retrieval_out() -> dict[str, Any]:
        if debug and retrieval_sink:
            return dict(retrieval_sink)
        return _retrieval_debug(enriched, similar)

    try:
        structured_uac = _structured_uac(enriched, similar, _retrieval_out())
    except Exception as exc:
        logger.warning_structured(
            "uac_structured_uac_failed",
            extra_fields={"jira_key": jk, "error": str(exc)},
            exc_info=True,
        )
        structured_uac = {}

    insufficient_similar_evidence = bool(
        include_similar and max_similar > 0 and len(similar) < JIRA_UAC_MIN_STRONG_SIMILAR
    )
    if insufficient_similar_evidence:
        msg = INSUFFICIENT_EVIDENCE_MESSAGE
        logger.info_structured(
            "uac_analyze_insufficient_similar_evidence",
            extra_fields={
                "jira_key": jk,
                "strong_similar_returned": len(similar),
                "required_strong_similar": JIRA_UAC_MIN_STRONG_SIMILAR,
                "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
                "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
                "MIN_FINAL_SCORE": JIRA_UAC_MINIMUM_EVIDENCE_THRESHOLD,
                "MIN_ENTITY_OVERLAP": JIRA_UAC_MIN_METADATA_OVERLAP,
            },
        )
        ins_pl = _uac_response(
            jira_key=jk,
            enriched=enriched,
            similar=similar,
            uac_answer=msg,
            structured_uac=structured_uac,
            retrieval_debug=_retrieval_out(),
            quality_score=0,
            answer_quality={
                "score": 0,
                "generic_phrases_found": [],
                "missing_specificity": [msg],
                "recommendation": "reject",
            },
            insufficient_similar_evidence=True,
        )
        return await _finalize_uac_payload(
            ins_pl,
            enriched,
            lenient_validation=True,
            debug=debug,
            include_qa_handoff=include_qa_handoff,
        )

    current_for_score = enriched.model_dump()
    similar_for_score = _similar_payload(similar, enriched)
    prompt = build_uac_prompt(enriched, similar)

    if not is_llm_available():
        logger.warning_structured("uac_analyze_llm_off", extra_fields={"jira_key": jk})
        fallback_answer = _format_structured_uac_markdown(structured_uac)
        fallback_similar = _similar_payload(similar, enriched)
        fallback_score, fallback_quality = _quality_payload(fallback_answer, enriched, fallback_similar)
        off_pl = _uac_response(
            jira_key=jk,
            enriched=enriched,
            similar=similar,
            uac_answer=fallback_answer,
            structured_uac=structured_uac,
            retrieval_debug=_retrieval_out(),
            quality_score=fallback_score,
            answer_quality=fallback_quality,
        )
        return await _finalize_uac_payload(
            off_pl,
            enriched,
            lenient_validation=False,
            debug=debug,
            include_qa_handoff=include_qa_handoff,
        )

    system = (
        "You are a senior QA analyst for Adobe Experience Manager Guides. "
        "Follow the user instructions exactly and output only the required Markdown sections. "
        "Write so another QA can defend sign-off: name concrete outputs, entities, or keys from evidence in scenarios and risk drivers."
    )
    regeneration_used = False
    try:
        draft = (
            await asyncio.wait_for(
                generate_text(system, prompt, max_tokens=8000, step_name="uac_copilot_analyze"),
                timeout=_UAC_LLM_TIMEOUT_SECS,
            )
        ).strip()
        first_quality = score_answer_specificity(draft, current_for_score, similar_for_score)
        if int(first_quality.get("score", 0)) < 70:
            strict_prompt = build_uac_prompt(enriched, similar, strict_specificity=True)
            draft = (
                await asyncio.wait_for(
                    generate_text(
                        system,
                        strict_prompt,
                        max_tokens=8000,
                        step_name="uac_copilot_analyze_specificity_retry",
                    ),
                    timeout=_UAC_LLM_TIMEOUT_SECS,
                )
            ).strip()
            regeneration_used = True
    except Exception as exc:
        logger.error_structured(
            "uac_analyze_llm_failed",
            extra_fields={"jira_key": jk, "error": str(exc)},
            exc_info=True,
        )
        fallback_answer = _format_structured_uac_markdown(structured_uac)
        fallback_similar = _similar_payload(similar, enriched)
        fallback_score, fallback_quality = _quality_payload(fallback_answer, enriched, fallback_similar)
        fb_pl = _uac_response(
            jira_key=jk,
            enriched=enriched,
            similar=similar,
            uac_answer=fallback_answer,
            structured_uac=structured_uac,
            retrieval_debug=_retrieval_out(),
            quality_score=fallback_score,
            answer_quality=fallback_quality,
        )
        return await _finalize_uac_payload(
            fb_pl,
            enriched,
            lenient_validation=False,
            debug=debug,
            include_qa_handoff=include_qa_handoff,
        )

    dropped = _collect_risk_section_drops(draft, enriched, similar)

    try:
        refined = critic_refine_uac_answer(enriched, similar, draft)
    except Exception as exc:
        logger.error_structured(
            "uac_analyze_critic_failed",
            extra_fields={"jira_key": jk, "error": str(exc)},
            exc_info=True,
        )
        refined = draft

    answer_quality_final = score_answer_specificity(refined, current_for_score, similar_for_score)
    phrases_removed = generic_phrases_removed_between(draft, refined)
    quality_score = int(answer_quality_final.get("score", 0))

    logger.info_structured(
        "uac_analyze_done",
        extra_fields={
            "jira_key": jk,
            "draft_chars": len(draft),
            "refined_chars": len(refined),
            "dropped_points": len(dropped),
            "quality_score": quality_score,
            "answer_quality_recommendation": answer_quality_final.get("recommendation"),
            "regeneration_used": regeneration_used,
            "generic_phrases_removed_count": len(phrases_removed),
        },
    )

    ok_pl = _uac_response(
        jira_key=jk,
        enriched=enriched,
        similar=similar,
        uac_answer=refined,
        structured_uac=structured_uac,
        retrieval_debug=_retrieval_out(),
        quality_score=quality_score,
        answer_quality=answer_quality_final,
        regeneration_used=regeneration_used,
        generic_phrases_removed=phrases_removed,
        dropped_generic_points=dropped,
    )
    return await _finalize_uac_payload(
        ok_pl,
        enriched,
        lenient_validation=False,
        debug=debug,
        include_qa_handoff=include_qa_handoff,
    )
