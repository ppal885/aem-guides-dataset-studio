"""Review-center and learned-QA endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import AdminUser, CurrentUser, UserIdentity
from app.core.validation import sanitize_error_for_client
from app.db.session import get_db
from app.services.learned_qa_service import (
    approve_learned_prompt_entry,
    export_approved_learned_qa_pairs,
    index_approved_learned_qa,
    list_learned_prompt_entries,
    reject_learned_prompt_entry,
    sync_learned_qa_corpus,
)
from app.services.review_center_service import build_review_center_status
from app.services.source_review_state_service import record_source_failure, record_source_success
from app.services.tenant_service import get_authorized_tenant_id
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_OT_GITHUB,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_JIRA_QA,
    CHROMA_COLLECTION_LEARNED_QA,
)

router = APIRouter(prefix="/ai", tags=["AI Review Center"], dependencies=[CurrentUser])


def _sync_learned_qa_index(session: Session, *, force_reindex: bool = True) -> dict[str, Any]:
    stats = index_approved_learned_qa(session, force_reindex=force_reindex)
    if stats.get("errors"):
        record_source_failure(
            source_id=CHROMA_COLLECTION_LEARNED_QA,
            operation="reindex",
            error="; ".join(str(err) for err in stats.get("errors") or []),
            failed_items=list(stats.get("errors") or []),
            stats=stats,
        )
    else:
        record_source_success(
            source_id=CHROMA_COLLECTION_LEARNED_QA,
            operation="reindex",
            stats=stats,
        )
    return stats


@router.get("/review-center")
def get_review_center(
    request: Request,
    tenant_id: str = Query("default", description="Tenant for GitHub DITA review status"),
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    try:
        sync_learned_qa_corpus(session, reason="review_center")
    except Exception:
        pass
    requested_tenant = tenant_id if str(tenant_id or "").strip() not in {"", "default"} else None
    authorized_tenant_id = get_authorized_tenant_id(request, user, requested_tenant=requested_tenant)
    return build_review_center_status(session=session, tenant_id=authorized_tenant_id)


@router.get("/review-center/candidates")
def get_review_center_candidates(
    status: str | None = Query("pending_review", description="Filter candidates by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    del user
    return {
        "items": list_learned_prompt_entries(
            session,
            status=status or None,
            limit=limit,
            offset=offset,
        ),
        "status": status,
        "limit": limit,
        "offset": offset,
    }


@router.post("/review-center/candidates/{entry_id}/approve")
def approve_review_center_candidate(
    entry_id: str,
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    del user
    try:
        entry = approve_learned_prompt_entry(session, entry_id)
        index_stats = _sync_learned_qa_index(session, force_reindex=True)
        return {"entry": entry, "index_stats": index_stats}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc)) from exc


@router.post("/review-center/candidates/{entry_id}/reject")
def reject_review_center_candidate(
    entry_id: str,
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    del user
    try:
        entry = reject_learned_prompt_entry(session, entry_id)
        index_stats = _sync_learned_qa_index(session, force_reindex=True)
        return {"entry": entry, "index_stats": index_stats}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc)) from exc


@router.post("/review-center/sources/{source_id}/reindex")
async def reindex_review_center_source(
    source_id: str,
    request: Request,
    force_reindex: bool = Query(False),
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    del request
    del user
    try:
        if source_id == CHROMA_COLLECTION_AEM_GUIDES:
            from app.services.crawl_service import crawl_and_index

            stats = await asyncio.to_thread(crawl_and_index, urls=None)
            errors = list(stats.get("errors") or [])
            if errors:
                record_source_failure(
                    source_id=source_id,
                    operation="reindex",
                    error="; ".join(errors),
                    failed_items=errors,
                    stats=stats,
                )
            else:
                record_source_success(source_id=source_id, operation="reindex", stats=stats)
            return stats

        if source_id == CHROMA_COLLECTION_DITA_SPEC:
            from app.services.dita_pdf_index_service import index_dita_pdf

            stats = await asyncio.to_thread(index_dita_pdf, pdf_urls=None)
            errors = list(stats.get("errors") or [])
            if errors:
                record_source_failure(
                    source_id=source_id,
                    operation="reindex",
                    error="; ".join(errors),
                    failed_items=errors,
                    stats=stats,
                )
            else:
                record_source_success(source_id=source_id, operation="reindex", stats=stats)
            return stats

        if source_id == CHROMA_COLLECTION_DITA_OT_GITHUB:
            from app.services.dita_ot_github_rag_service import index_dita_ot_github_issues

            stats = await asyncio.to_thread(
                index_dita_ot_github_issues,
                force_reindex=force_reindex,
            )
            errors = list(stats.get("errors") or [])
            if errors:
                record_source_failure(
                    source_id=source_id,
                    operation="reindex",
                    error="; ".join(errors),
                    failed_items=errors,
                    stats=stats,
                )
            else:
                record_source_success(source_id=source_id, operation="reindex", stats=stats)
            return stats

        if source_id == CHROMA_COLLECTION_JIRA_QA:
            from app.services.jira_qa_index_service import default_jira_qa_backfill_limit, index_jira_project_incremental, resolve_jira_qa_project_key

            stats = await asyncio.to_thread(
                index_jira_project_incremental,
                resolve_jira_qa_project_key(),
                limit=default_jira_qa_backfill_limit(),
                force_reindex=force_reindex,
            )
            errors = list(stats.get("errors") or [])
            if errors:
                record_source_failure(
                    source_id=source_id,
                    operation="reindex",
                    error="; ".join(errors),
                    failed_items=errors,
                    stats=stats,
                )
            else:
                record_source_success(source_id=source_id, operation="reindex", stats=stats)
            return stats

        if source_id == CHROMA_COLLECTION_LEARNED_QA:
            return _sync_learned_qa_index(session, force_reindex=True)

        raise HTTPException(status_code=404, detail=f"Unknown source_id: {source_id}")
    except HTTPException:
        raise
    except Exception as exc:
        record_source_failure(
            source_id=source_id,
            operation="reindex",
            error=str(exc),
            failed_items=[str(exc)],
        )
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc)) from exc


@router.post("/learned-qa/seed")
def seed_reviewed_learned_qa(
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    del user
    try:
        return sync_learned_qa_corpus(
            session,
            force_seed=True,
            force_reindex=True,
            reason="manual_seed",
        )
    except Exception as exc:
        record_source_failure(
            source_id=CHROMA_COLLECTION_LEARNED_QA,
            operation="seed",
            error=str(exc),
            failed_items=[str(exc)],
        )
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc)) from exc


@router.post("/learned-qa/export")
def export_reviewed_learned_qa(
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    del user
    try:
        return export_approved_learned_qa_pairs(session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc)) from exc
