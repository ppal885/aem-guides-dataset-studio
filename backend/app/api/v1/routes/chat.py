"""Chat API routes - sessions, messages, streaming."""
import json
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.content_validation import validate_chat_content, validate_chat_context
from app.db.session import get_db
from app.utils.api_rate_limit import check_chat_sessions_limit, check_chat_messages_limit
from app.services.chat_service import (
    branch_session_from_message,
    create_session,
    list_sessions,
    get_session,
    get_messages,
    delete_session,
    chat_turn,
)
from app.services.tenant_service import get_tenant_id_from_request
from app.services.llm_service import format_llm_error_for_user

router = APIRouter(prefix="/chat", tags=["Chat"])


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    content: str
    context: dict | None = None  # { "issue_summary": str, "issue_key": str, "source_page": str }


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
async def post_send_message(request: Request, session_id: str, body: SendMessageRequest):
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
            async for event in chat_turn(session_id, content, context=body.context, tenant_id=tenant_id):
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
