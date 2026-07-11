"""Chat API routes - sessions, messages, streaming."""
import json
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import AdminUser, CurrentUser, UserIdentity
from app.core.content_validation import (
    validate_chat_content,
    validate_chat_context,
)
from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
)
from app.utils.api_rate_limit import check_chat_sessions_limit, check_chat_messages_limit
from app.services.chat_service import (
    branch_session_from_message,
    create_session,
    delete_all_chat_sessions,
    list_sessions,
    get_session,
    get_messages,
    delete_session,
    chat_turn,
    regenerate_last_assistant,
    update_session_title,
    update_user_message_truncate_after,
)
from app.services.chat_asset_service import ensure_user_can_access_asset, read_asset_bytes
from app.services.chat_tools import get_tool_catalog
from app.services.tenant_service import get_authorized_tenant_id
from app.services.llm_service import format_llm_error_for_user
from app.db.session import get_db
from app.services.chat_eval_dashboard_service import get_chat_eval_stats, list_chat_eval_pairs
from app.services.chat_quality_service import (
    apply_feedback_to_quality,
    get_chat_eval_breakdown,
    get_chat_eval_trends,
    promote_eval_pair_to_learned_qa,
    set_eval_pair_review_status,
)

router = APIRouter(prefix="/chat", tags=["Chat"], dependencies=[CurrentUser])


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    content: str
    context: dict | None = None  # { "issue_summary": str, "issue_key": str, "source_page": str }
    human_prompts: bool | None = None
    tool_intent: dict | None = None


class PatchSessionRequest(BaseModel):
    title: str


class PatchMessageRequest(BaseModel):
    content: str


class RegenerateRequest(BaseModel):
    context: dict | None = None
    human_prompts: bool | None = None
    #: When set, replaces persisted turn options for this regeneration only (client sends full merged object).
    generation_options: ChatDitaGenerationOptions | None = None


class BranchSessionRequest(BaseModel):
    message_id: str


def _parse_form_bool(value: str | None, *, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@router.post("/sessions", response_model=CreateSessionResponse)
def post_create_session(request: Request, user: UserIdentity = CurrentUser):
    """Create a new chat session."""
    err = check_chat_sessions_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    session_id = create_session(user_id=user.id, tenant_id=tenant_id)
    return CreateSessionResponse(session_id=session_id)


@router.get("/sessions")
def get_list_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserIdentity = CurrentUser,
):
    """List chat sessions, newest first."""
    tenant_id = get_authorized_tenant_id(request, user)
    return {"sessions": list_sessions(limit=limit, offset=offset, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)}


@router.delete("/all-sessions")
def delete_all_sessions(request: Request, user: UserIdentity = AdminUser):
    """Delete every chat session and message."""
    tenant_id = get_authorized_tenant_id(request, user)
    return {"status": "ok", "deleted": delete_all_chat_sessions(user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)}


@router.get("/sessions/{session_id}")
def get_session_by_id(session_id: str, request: Request, user: UserIdentity = CurrentUser):
    """Get session and its messages."""
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_messages(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    return {"session": session, "messages": messages}


@router.delete("/sessions/{session_id}")
def delete_session_by_id(session_id: str, request: Request, user: UserIdentity = CurrentUser):
    """Delete a chat session and its messages."""
    tenant_id = get_authorized_tenant_id(request, user)
    if not delete_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


@router.patch("/sessions/{session_id}")
def patch_session_by_id(session_id: str, body: PatchSessionRequest, request: Request, user: UserIdentity = CurrentUser):
    """Rename a chat session."""
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = update_session_title(session_id, body.title, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": updated}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    request: Request,
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    user: UserIdentity = CurrentUser,
):
    """Get messages for a session."""
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_messages(session_id, limit=limit, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    return {"messages": messages}


@router.post("/sessions/{session_id}/messages/authoring")
async def post_send_authoring_message(
    session_id: str,
    user: UserIdentity = CurrentUser,
):
    """Screenshot attachment authoring was removed; use text chat and /generate_dita instead."""
    raise HTTPException(
        status_code=410,
        detail=(
            "Screenshot-to-DITA authoring is no longer available. "
            "Use AI Chat with /generate_dita, /review_dita, or /fix_dita, or paste XML in the composer."
        ),
    )


@router.patch("/sessions/{session_id}/messages/{message_id}")
def patch_session_message(
    session_id: str,
    message_id: str,
    body: PatchMessageRequest,
    request: Request,
    user: UserIdentity = CurrentUser,
):
    """Edit a user message in place and remove all later messages."""
    content = (body.content or "").strip()
    err = validate_chat_content(content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    try:
        messages = update_user_message_truncate_after(
            session_id,
            message_id,
            content,
            user_id=user.id,
            tenant_id=tenant_id,
            is_admin=user.is_admin,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"messages": messages}


@router.post("/sessions/{session_id}/branches")
def post_branch_session(request: Request, session_id: str, body: BranchSessionRequest, user: UserIdentity = CurrentUser):
    """Create a new session from the history before a user message being edited."""
    err = check_chat_sessions_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    try:
        session, messages = branch_session_from_message(
            session_id,
            body.message_id,
            user_id=user.id,
            tenant_id=tenant_id,
            is_admin=user.is_admin,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session, "messages": messages}


@router.post("/sessions/{session_id}/messages")
async def post_send_message(
    request: Request,
    session_id: str,
    body: SendMessageRequest,
    user: UserIdentity = CurrentUser,
):
    """Send a message and stream the response via SSE."""
    err = check_chat_messages_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = (body.content or "").strip()
    err = validate_chat_content(content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    err = validate_chat_context(body.context)
    if err:
        raise HTTPException(status_code=400, detail=err)

    async def event_stream():
        try:
            async for event in chat_turn(
                session_id,
                content,
                user_id=user.id,
                context=body.context,
                tenant_id=tenant_id,
                human_prompts=body.human_prompts,
                tool_intent=body.tool_intent,
            ):
                line = json.dumps(event) + "\n"
                yield f"data: {line}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': format_llm_error_for_user(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/regenerate")
async def post_regenerate(
    request: Request,
    session_id: str,
    body: RegenerateRequest,
    user: UserIdentity = CurrentUser,
):
    """Regenerate the latest assistant reply from the most recent user message."""
    err = check_chat_messages_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    err = validate_chat_context(body.context)
    if err:
        raise HTTPException(status_code=400, detail=err)

    async def event_stream():
        try:
            async for event in regenerate_last_assistant(
                session_id,
                user_id=user.id,
                context=body.context,
                tenant_id=tenant_id,
                human_prompts=body.human_prompts,
                generation_options=body.generation_options,
            ):
                line = json.dumps(event) + "\n"
                yield f"data: {line}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': format_llm_error_for_user(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class FeedbackRequest(BaseModel):
    rating: str  # "up" | "down"
    comment: str | None = None


@router.post("/sessions/{session_id}/messages/{message_id}/feedback")
def post_message_feedback(
    session_id: str,
    message_id: str,
    body: FeedbackRequest,
    request: Request,
    user: UserIdentity = CurrentUser,
):
    """Submit thumbs up/down feedback on an assistant message."""
    from uuid import uuid4
    from app.db.session import SessionLocal
    from app.db.chat_models import ChatMessageFeedback
    from app.services.learned_qa_service import (
        capture_learned_candidate_from_chat_feedback,
        capture_rejected_learned_from_chat_feedback,
    )

    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")

    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db = SessionLocal()
    try:
        fb = ChatMessageFeedback(
            id=str(uuid4()),
            message_id=message_id,
            session_id=session_id,
            rating=body.rating,
            correction_text=body.comment,
            auto_detected=False,
        )
        db.add(fb)
        apply_feedback_to_quality(
            db,
            message_id=message_id,
            rating=body.rating,
            correction_text=body.comment,
        )
        db.commit()
        learned_capture = capture_learned_candidate_from_chat_feedback(
            db,
            session_id=session_id,
            message_id=message_id,
            rating=body.rating,
        )
        rejected_capture = capture_rejected_learned_from_chat_feedback(
            db,
            session_id=session_id,
            message_id=message_id,
            rating=body.rating,
        )
        return {
            "status": "ok",
            "id": fb.id,
            "learned_capture": learned_capture,
            "rejected_capture": rejected_capture,
        }
    finally:
        db.close()


@router.get("/suggested-prompts")
def get_suggested_prompts():
    """Return starter prompts shown when chat is empty."""
    return {
        "prompts": [
            {"title": "DITA Elements", "text": "What is the difference between conref, conkeyref, and keyref?", "icon": "code"},
            {"title": "Generate DITA", "text": "Generate a task topic for configuring PDF output in AEM Guides", "icon": "file-plus"},
            {"title": "Native PDF", "text": "How do I customize Native PDF templates in AEM Guides?", "icon": "file-text"},
            {"title": "Map Structure", "text": "Explain DITA map cascading and chunk attributes with examples", "icon": "layers"},
            {"title": "Output Presets", "text": "What are the output preset types in AEM Guides and when to use each?", "icon": "settings"},
            {"title": "Review XML", "text": "Review this DITA XML for best practices and common mistakes", "icon": "check-circle"},
            {"title": "Tables", "text": "What is the difference between choicetable, simpletable, and table in DITA?", "icon": "table"},
            {"title": "Translation", "text": "How does the translation workflow work in AEM Guides?", "icon": "globe"},
        ]
    }


@router.get("/eval/stats")
def get_chat_eval_dashboard_stats(
    request: Request,
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    """Aggregate counts for the chat evaluation dashboard."""
    tenant_id = get_authorized_tenant_id(request, user)
    return get_chat_eval_stats(
        session,
        user_id=user.id,
        tenant_id=tenant_id,
        is_admin=user.is_admin,
    )


@router.get("/eval/pairs")
def get_chat_eval_dashboard_pairs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="Filter by question, answer, or session title"),
    rating: str | None = Query(None, description="Filter by feedback: up, down, or none"),
    weak_only: bool = Query(False, description="Only weak/abstain answers (quality < 60)"),
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    """List stored user question + assistant answer pairs for evaluation review."""
    if rating is not None and rating not in {"", "up", "down", "none"}:
        raise HTTPException(status_code=400, detail="rating must be up, down, none, or omitted")
    tenant_id = get_authorized_tenant_id(request, user)
    return list_chat_eval_pairs(
        session,
        user_id=user.id,
        tenant_id=tenant_id,
        is_admin=user.is_admin,
        limit=limit,
        offset=offset,
        search=search,
        rating=rating or None,
        weak_only=weak_only,
    )


class EvalReviewRequest(BaseModel):
    status: str  # pass | fail | needs_seed


@router.get("/eval/trends")
def get_chat_eval_dashboard_trends(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    """Time series of answer volume and quality for the eval dashboard."""
    tenant_id = get_authorized_tenant_id(request, user)
    return get_chat_eval_trends(
        session,
        user_id=user.id,
        tenant_id=tenant_id,
        is_admin=user.is_admin,
        days=days,
    )


@router.get("/eval/breakdown")
def get_chat_eval_dashboard_breakdown(
    request: Request,
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    """Breakdown charts data: grounding status, domain, ratings, confidence buckets."""
    tenant_id = get_authorized_tenant_id(request, user)
    return get_chat_eval_breakdown(
        session,
        user_id=user.id,
        tenant_id=tenant_id,
        is_admin=user.is_admin,
    )


@router.post("/eval/pairs/{message_id}/review")
def post_chat_eval_pair_review(
    message_id: str,
    body: EvalReviewRequest,
    request: Request,
    session: Session = Depends(get_db),
    user: UserIdentity = AdminUser,
):
    """Mark an eval pair as pass, fail, or needs_seed."""
    tenant_id = get_authorized_tenant_id(request, user)
    try:
        return set_eval_pair_review_status(
            session,
            message_id=message_id,
            review_status=body.status,
            user_id=user.id,
            tenant_id=tenant_id,
            is_admin=user.is_admin,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/eval/pairs/{message_id}/promote")
def post_chat_eval_pair_promote(
    message_id: str,
    request: Request,
    session: Session = Depends(get_db),
    user: UserIdentity = CurrentUser,
):
    """Promote a strong Q&A pair to the learned QA review queue."""
    tenant_id = get_authorized_tenant_id(request, user)
    try:
        return promote_eval_pair_to_learned_qa(
            session,
            message_id=message_id,
            user_id=user.id,
            tenant_id=tenant_id,
            is_admin=user.is_admin,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tools")
def get_chat_tools():
    """Return the chat tool catalog used by the slash-command palette."""
    return {"tools": get_tool_catalog()}


@router.get("/assets/{asset_id}")
def get_chat_asset(asset_id: str, request: Request, user: UserIdentity = CurrentUser):
    """Serve a stored chat attachment or generated XML artifact."""
    metadata = ensure_user_can_access_asset(asset_id, user.id)
    payload, _ = read_asset_bytes(asset_id)
    filename = str(metadata.get("filename") or asset_id)
    mime_type = str(metadata.get("mime_type") or "application/octet-stream")
    download = _parse_form_bool(request.query_params.get("download"), default=False)
    disposition = "attachment" if download else "inline"
    return Response(
        content=payload,
        media_type=mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
