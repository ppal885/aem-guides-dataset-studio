"""Aggregates review-center status for Settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.github_dita_examples_service import get_github_dita_rag_summary
from app.services.jira_index_dashboard_service import build_jira_index_status
from app.services.jira_qa_index_service import default_jira_qa_backfill_limit, resolve_jira_qa_project_key
from app.services.learned_qa_service import get_learned_qa_summary
from app.services.source_review_state_service import load_source_state, read_recent_source_failures
from app.services.tavily_search_service import get_tavily_rag_status
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_OT_GITHUB,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_JIRA_QA,
    CHROMA_COLLECTION_LEARNED_QA,
    get_collection_count,
    is_chroma_available,
)

_SOURCE_DESCRIPTIONS = {
    CHROMA_COLLECTION_AEM_GUIDES: "Experience League crawl and approved product-document examples used for AEM Guides chat grounding.",
    CHROMA_COLLECTION_DITA_SPEC: "Normative DITA spec PDFs and seed-backed spec chunks used for construct and attribute grounding.",
    CHROMA_COLLECTION_DITA_OT_GITHUB: "DITA-OT GitHub issue knowledge for publishing, transforms, and known build/runtime issues.",
    CHROMA_COLLECTION_JIRA_QA: "Indexed Jira QA issues and resolution patterns for similar ticket grounding.",
    CHROMA_COLLECTION_LEARNED_QA: "Approved senior prompt/answer pairs learned from curated seeds and accepted product usage.",
}


def _source_card(
    *,
    source_id: str,
    title: str,
    source: str,
    collection: str,
    chunk_count: int,
    candidate_backlog: int = 0,
    issue_count: int | None = None,
    last_successful_run: str | None = None,
    failed_item_count: int = 0,
    failed_items: list[str] | None = None,
    populate_via: str = "",
    last_error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "title": title,
        "description": _SOURCE_DESCRIPTIONS.get(source_id, source),
        "source": source,
        "collection": collection,
        "chunk_count": int(chunk_count or 0),
        "candidate_backlog": int(candidate_backlog or 0),
        "issue_count": issue_count,
        "last_successful_run": last_successful_run,
        "failed_item_count": int(failed_item_count or 0),
        "failed_items": list(failed_items or []),
        "populate_via": populate_via,
        "last_error": last_error,
        "extra": dict(extra or {}),
    }


def build_review_center_status(*, session: Session, tenant_id: str = "default") -> dict[str, Any]:
    chroma_ok = is_chroma_available()
    aem_count = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES) if chroma_ok else 0
    dita_count = get_collection_count(CHROMA_COLLECTION_DITA_SPEC) if chroma_ok else 0
    dita_ot_count = get_collection_count(CHROMA_COLLECTION_DITA_OT_GITHUB) if chroma_ok else 0
    jira_count = get_collection_count(CHROMA_COLLECTION_JIRA_QA) if chroma_ok else 0
    learned_count = get_collection_count(CHROMA_COLLECTION_LEARNED_QA) if chroma_ok else 0

    jira_status = build_jira_index_status(session)
    learned_summary = get_learned_qa_summary(session)
    github_dita = get_github_dita_rag_summary(tenant_id=tenant_id)
    tavily = get_tavily_rag_status()

    aem_state = load_source_state(CHROMA_COLLECTION_AEM_GUIDES)
    dita_state = load_source_state(CHROMA_COLLECTION_DITA_SPEC)
    dita_ot_state = load_source_state(CHROMA_COLLECTION_DITA_OT_GITHUB)
    jira_state = load_source_state(CHROMA_COLLECTION_JIRA_QA)
    learned_state = load_source_state(CHROMA_COLLECTION_LEARNED_QA)

    sources = [
        _source_card(
            source_id=CHROMA_COLLECTION_AEM_GUIDES,
            title="AEM Guides & Assets",
            source="Experience League crawl",
            collection=CHROMA_COLLECTION_AEM_GUIDES,
            chunk_count=aem_count,
            last_successful_run=aem_state.last_successful_run,
            failed_item_count=aem_state.failed_item_count,
            failed_items=aem_state.failed_items,
            populate_via="crawl-aem-guides",
            last_error=aem_state.last_error,
        ),
        _source_card(
            source_id=CHROMA_COLLECTION_DITA_SPEC,
            title="DITA Spec PDFs",
            source="DITA 1.2 + 1.3 Part 1 Base PDFs",
            collection=CHROMA_COLLECTION_DITA_SPEC,
            chunk_count=dita_count,
            last_successful_run=dita_state.last_successful_run,
            failed_item_count=dita_state.failed_item_count,
            failed_items=dita_state.failed_items,
            populate_via="index-dita-pdf",
            last_error=dita_state.last_error,
        ),
        _source_card(
            source_id=CHROMA_COLLECTION_DITA_OT_GITHUB,
            title="DITA OT GitHub Issues",
            source="dita-ot/dita-ot GitHub issues",
            collection=CHROMA_COLLECTION_DITA_OT_GITHUB,
            chunk_count=dita_ot_count,
            last_successful_run=dita_ot_state.last_successful_run,
            failed_item_count=dita_ot_state.failed_item_count,
            failed_items=dita_ot_state.failed_items,
            populate_via="index-dita-ot-github",
            last_error=dita_ot_state.last_error,
            extra={
                "reference_issue_count": int(github_dita.get("indexed_subtrees") or 0),
            },
        ),
        _source_card(
            source_id=CHROMA_COLLECTION_JIRA_QA,
            title="Jira QA Knowledge Base",
            source="Indexed Jira QA issues",
            collection=CHROMA_COLLECTION_JIRA_QA,
            chunk_count=jira_count,
            issue_count=int(jira_status.get("total_indexed_jira") or 0),
            last_successful_run=jira_state.last_successful_run or jira_status.get("last_sync_time"),
            failed_item_count=max(int(jira_state.failed_item_count or 0), int(jira_status.get("recent_failure_count") or 0)),
            failed_items=jira_state.failed_items or list(jira_status.get("failed_jira_keys") or [])[:10],
            populate_via="jira-rag/index",
            last_error=jira_state.last_error,
            extra={
                "project_key": resolve_jira_qa_project_key(),
                "backfill_limit": default_jira_qa_backfill_limit(),
            },
        ),
        _source_card(
            source_id=CHROMA_COLLECTION_LEARNED_QA,
            title="Learned Prompt Corpus",
            source="Curated and approved senior prompt-answer pairs",
            collection=CHROMA_COLLECTION_LEARNED_QA,
            chunk_count=learned_count,
            candidate_backlog=int(learned_summary.get("pending_review_count") or 0),
            last_successful_run=learned_state.last_successful_run or learned_summary.get("last_indexed_time"),
            failed_item_count=max(int(learned_state.failed_item_count or 0), int(learned_summary.get("failed_item_count") or 0)),
            failed_items=learned_state.failed_items or list(learned_summary.get("failed_items") or []),
            populate_via="learned-qa/seed, review-center approve, learned-qa export",
            last_error=learned_state.last_error or learned_summary.get("last_error"),
            extra={
                "approved_count": int(learned_summary.get("approved_count") or 0),
                "pending_review_count": int(learned_summary.get("pending_review_count") or 0),
                "rejected_count": int(learned_summary.get("rejected_count") or 0),
            },
        ),
    ]

    recent_failures = read_recent_source_failures(limit=50)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chroma_available": chroma_ok,
        "sources": sources,
        "candidate_counts": {
            "pending_review": int(learned_summary.get("pending_review_count") or 0),
            "approved": int(learned_summary.get("approved_count") or 0),
            "rejected": int(learned_summary.get("rejected_count") or 0),
            "total": int(learned_summary.get("total_count") or 0),
        },
        "recent_failures": recent_failures,
        "github_dita": github_dita,
        "tavily": tavily,
    }
