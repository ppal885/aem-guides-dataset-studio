"""Chat API routes - sessions, messages, streaming."""
import json
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import CurrentUser, UserIdentity
from app.core.content_validation import validate_chat_content, validate_chat_context
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
from app.services.tenant_service import get_tenant_id_from_request
from app.services.llm_service import format_llm_error_for_user

router = APIRouter(prefix="/chat", tags=["Chat"])


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    content: str
    context: dict | None = None  # { "issue_summary": str, "issue_key": str, "source_page": str }
    human_prompts: bool | None = None


class PatchSessionRequest(BaseModel):
    title: str


class PatchMessageRequest(BaseModel):
    content: str


class RegenerateRequest(BaseModel):
    context: dict | None = None
    human_prompts: bool | None = None


class BranchSessionRequest(BaseModel):
    message_id: str


@router.post("/sessions", response_model=CreateSessionResponse)
def post_create_session(request: Request):
    """Create a new chat session."""
    err = check_chat_sessions_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    session_id = create_session()
    return CreateSessionResponse(session_id=session_id)


@router.get("/sessions")
def get_list_sessions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List chat sessions, newest first."""
    return {"sessions": list_sessions(limit=limit, offset=offset)}


@router.delete("/all-sessions")
def delete_all_sessions():
    """Delete every chat session and message."""
    return {"status": "ok", "deleted": delete_all_chat_sessions()}


@router.get("/sessions/{session_id}")
def get_session_by_id(session_id: str):
    """Get session and its messages."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_messages(session_id)
    return {"session": session, "messages": messages}


@router.delete("/sessions/{session_id}")
def delete_session_by_id(session_id: str):
    """Delete a chat session and its messages."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


@router.patch("/sessions/{session_id}")
def patch_session_by_id(session_id: str, body: PatchSessionRequest):
    """Rename a chat session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = update_session_title(session_id, body.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": updated}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """Get messages for a session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_messages(session_id, limit=limit)
    return {"messages": messages}


@router.patch("/sessions/{session_id}/messages/{message_id}")
def patch_session_message(session_id: str, message_id: str, body: PatchMessageRequest):
    """Edit a user message in place and remove all later messages."""
    content = (body.content or "").strip()
    err = validate_chat_content(content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    try:
        messages = update_user_message_truncate_after(session_id, message_id, content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"messages": messages}


@router.post("/sessions/{session_id}/branches")
def post_branch_session(request: Request, session_id: str, body: BranchSessionRequest):
    """Create a new session from the history before a user message being edited."""
    err = check_chat_sessions_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    try:
        session, messages = branch_session_from_message(session_id, body.message_id)
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
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = (body.content or "").strip()
    err = validate_chat_content(content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    err = validate_chat_context(body.context)
    if err:
        raise HTTPException(status_code=400, detail=err)

    tenant_id = get_tenant_id_from_request(request)

    async def event_stream():
        try:
            async for event in chat_turn(
                session_id,
                content,
                user_id=user.id,
                context=body.context,
                tenant_id=tenant_id,
                human_prompts=body.human_prompts,
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
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    err = validate_chat_context(body.context)
    if err:
        raise HTTPException(status_code=400, detail=err)

    tenant_id = get_tenant_id_from_request(request)

    async def event_stream():
        try:
            async for event in regenerate_last_assistant(
                session_id,
                user_id=user.id,
                context=body.context,
                tenant_id=tenant_id,
                human_prompts=body.human_prompts,
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
):
    """Submit thumbs up/down feedback on an assistant message."""
    from uuid import uuid4
    from app.db.base import SessionLocal
    from app.db.chat_models import ChatMessageFeedback

    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")

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
        db.commit()
        return {"status": "ok", "id": fb.id}
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
