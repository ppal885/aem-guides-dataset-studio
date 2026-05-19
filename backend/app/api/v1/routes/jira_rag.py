"""Jira QA RAG REST API."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, UserIdentity
from app.services.jira_qa_automation_rubric import (
    recommend_layer,
    rubric_to_dict,
    score_automation_fit,
)
from app.services.jira_qa_index_service import (
    index_jira_project_backfill,
    index_jira_project_incremental,
    index_jql_to_chroma,
)
from app.services.jira_qa_retrieval_service import (
    build_signal_text_for_issue,
    get_chunks_for_jira_key,
    related_tickets_for_issue,
)
from app.services.jira_qa_synthesis_service import (
    build_related_tickets_payload,
    generate_suggested_questions,
    pack_chunk_context,
    synthesize_answer_for_intent,
)
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count
from app.db.session import SessionLocal
from app.db.jira_enrichment_repository import search_jira_kb
from app.db.jira_enrichment_models import JiraEnrichedIssue

router = APIRouter(tags=["jira-rag"])

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def _validate_key(key: str) -> str:
    k = (key or "").strip().upper()
    if not _JIRA_KEY_RE.match(k):
        raise HTTPException(status_code=400, detail="Invalid jira_key format")
    return k


class JiraRagIndexRequest(BaseModel):
    """Index Jira into ``jira_qa`` Chroma. Use ``sync_mode`` for project-scoped backfill/incremental JQL."""

    jql: str = Field("", max_length=8000)
    limit: int | None = Field(None, ge=1)
    force_reindex: bool = False
    sync_mode: Literal["none", "backfill", "incremental"] = "none"
    project_key: str | None = Field(None, max_length=32)
    persist_sync_state: bool = False
    sync_state_id: str | None = Field(None, max_length=120)


class BodyHint(BaseModel):
    hint: Optional[str] = Field(None, max_length=4000)


@router.post("/index")
async def jira_rag_index(
    body: JiraRagIndexRequest,
    user: UserIdentity = CurrentUser,
):
    del user
    mode = body.sync_mode
    pk = (body.project_key or "").strip()
    lim = body.limit
    if mode == "backfill":
        if not pk:
            raise HTTPException(status_code=400, detail="project_key is required when sync_mode is backfill")
        return index_jira_project_backfill(
            pk,
            limit=lim,
            force_reindex=body.force_reindex,
            sync_state_id=body.sync_state_id,
        )
    if mode == "incremental":
        if not pk:
            raise HTTPException(status_code=400, detail="project_key is required when sync_mode is incremental")
        return index_jira_project_incremental(
            pk,
            limit=lim,
            force_reindex=body.force_reindex,
            sync_state_id=body.sync_state_id,
        )

    jql = body.jql.strip()
    if not jql:
        raise HTTPException(status_code=400, detail="jql is required when sync_mode is none")
    sid = (body.sync_state_id or "").strip() or None
    return index_jql_to_chroma(
        jql,
        limit=lim,
        force_reindex=body.force_reindex,
        persist_sync_state=body.persist_sync_state,
        sync_state_id=sid,
    )


@router.get("/kb/search")
def jira_kb_search(
    q: Optional[str] = None,
    domain: Optional[str] = None,
    output: Optional[str] = None,
    entity: Optional[str] = None,
    issue_type: Optional[str] = None,
    limit: int = 100,
    user: UserIdentity = CurrentUser,
):
    """Search the indexed Jira knowledge base by keyword and/or metadata filters."""
    del user
    limit = max(1, min(limit, 500))
    db = SessionLocal()
    try:
        results = search_jira_kb(
            db,
            q=q or None,
            domain=domain or None,
            output=output or None,
            entity=entity or None,
            issue_type=issue_type or None,
            limit=limit,
        )
    finally:
        db.close()
    return {"total": len(results), "results": results}


@router.get("/kb/domains")
def jira_kb_domains(user: UserIdentity = CurrentUser):
    """List all distinct domains and their ticket counts in the indexed knowledge base."""
    del user
    db = SessionLocal()
    try:
        from sqlalchemy import func
        rows = (
            db.query(JiraEnrichedIssue.domain, func.count(JiraEnrichedIssue.id).label("count"))
            .group_by(JiraEnrichedIssue.domain)
            .order_by(func.count(JiraEnrichedIssue.id).desc())
            .all()
        )
        total = db.query(JiraEnrichedIssue).count()
    finally:
        db.close()
    return {
        "total_indexed": total,
        "domains": [{"domain": r[0] or "unknown", "count": r[1]} for r in rows],
    }


@router.get("/status/chunks")
def jira_rag_chunk_status(user: UserIdentity = CurrentUser):
    del user
    return {
        "collection": CHROMA_COLLECTION_JIRA_QA,
        "chunk_count": get_collection_count(CHROMA_COLLECTION_JIRA_QA),
    }


@router.get("/{jira_key}/related")
async def jira_rag_related(
    jira_key: str,
    top_k: int = 10,
    customer: Optional[str] = None,
    user: UserIdentity = CurrentUser,
):
    del user
    jk = _validate_key(jira_key)
    hits, _sig = related_tickets_for_issue(jk, top_k=top_k, customer=customer)
    base_ctx = build_signal_text_for_issue(jk)
    related = await build_related_tickets_payload(
        jk, top_k=top_k, customer=customer, hits=hits, base_context=base_ctx
    )
    return {"base_jira": jk, "related_tickets": related}


@router.get("/{jira_key}/summary")
async def jira_rag_summary(
    jira_key: str,
    user: UserIdentity = CurrentUser,
):
    del user
    jk = _validate_key(jira_key)
    ctx = pack_chunk_context(get_chunks_for_jira_key(jk))
    answer = await synthesize_answer_for_intent(
        intent="ticket_summary",
        jira_key=jk,
        user_message=f"Summarize ticket {jk}",
        context_blob=ctx,
    )
    sug = await generate_suggested_questions(
        jira_key=jk,
        user_message="summary",
        answer_preview=answer,
        intent="ticket_summary",
    )
    return {"jira_key": jk, "answer": answer, "suggested_questions": sug}


async def _scoped_post(
    jira_key: str,
    intent: str,
    user_message: str,
    *,
    extra_blob: str = "",
) -> dict[str, Any]:
    jk = _validate_key(jira_key)
    ctx = pack_chunk_context(get_chunks_for_jira_key(jk)) + extra_blob
    answer = await synthesize_answer_for_intent(
        intent=intent,
        jira_key=jk,
        user_message=user_message,
        context_blob=ctx,
    )
    sug = await generate_suggested_questions(
        jira_key=jk,
        user_message=user_message,
        answer_preview=answer,
        intent=intent,
    )
    return {"jira_key": jk, "intent": intent, "answer": answer, "suggested_questions": sug}


@router.post("/{jira_key}/testing-scope")
async def jira_rag_testing_scope(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    hint = body.hint if body else None
    return await _scoped_post(
        jira_key,
        "testing_scope",
        hint or "What should be tested for this ticket?",
    )


@router.post("/{jira_key}/uac-points")
async def jira_rag_uac(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    hint = body.hint if body else None
    return await _scoped_post(jira_key, "uac_discussion", hint or "UAC discussion points")


@router.post("/{jira_key}/automation-fit")
async def jira_rag_automation_fit(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    jk = _validate_key(jira_key)
    ctx = pack_chunk_context(get_chunks_for_jira_key(jk))
    rub = score_automation_fit(ctx)
    extra = f"\n### Rubric JSON\n{json.dumps(rubric_to_dict(rub))}\nRecommended layer: {recommend_layer(ctx, rub)}"
    answer = await synthesize_answer_for_intent(
        intent="automation_fit",
        jira_key=jk,
        user_message=(body.hint if body else None) or "Is this automation fit?",
        context_blob=ctx + extra,
    )
    sug = await generate_suggested_questions(
        jira_key=jk,
        user_message="automation-fit",
        answer_preview=answer,
        intent="automation_fit",
    )
    rd = rubric_to_dict(rub)
    rd["recommended_layer"] = recommend_layer(ctx, rub)
    return {
        "jira_key": jk,
        "intent": "automation_fit",
        "rubric": rd,
        "answer": answer,
        "suggested_questions": sug,
    }


@router.post("/{jira_key}/test-cases")
async def jira_rag_test_cases(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    hint = body.hint if body else None
    return await _scoped_post(jira_key, "test_case_generation", hint or "Generate test cases")


@router.post("/{jira_key}/test-ticket-draft")
async def jira_rag_test_ticket(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    hint = body.hint if body else None
    return await _scoped_post(
        jira_key,
        "test_ticket_creation",
        hint or "Create a test ticket draft",
    )


@router.post("/{jira_key}/gherkin-scenarios")
async def jira_rag_gherkin(
    jira_key: str,
    body: BodyHint | None = None,
    user: UserIdentity = CurrentUser,
):
    del user
    hint = body.hint if body else None
    return await _scoped_post(
        jira_key,
        "gherkin_generation",
        hint or "Generate Behave/Gherkin scenarios",
    )
