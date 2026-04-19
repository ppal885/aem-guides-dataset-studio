"""Chat API routes - sessions, messages, streaming."""
import json
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.core.auth import AdminUser, CurrentUser, UserIdentity
from app.core.content_validation import (
    validate_authoring_jira_context,
    validate_chat_content,
    validate_chat_context,
)
from app.core.schemas_chat_authoring import (
    ChatAuthoringOutputMode,
    ChatAuthoringPattern,
    ChatAuthoringRequestPayload,
    ChatDitaGenerationOptions,
    ChatScreenshotDeliverableMode,
    ChatStyleStrictness,
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
from app.services.chat_asset_service import ensure_user_can_access_asset, read_asset_bytes, save_upload_asset
from app.services.chat_tools import get_tool_catalog
from app.services.tenant_service import get_authorized_tenant_id
from app.services.llm_service import format_llm_error_for_user

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


def _parse_form_json(value: str | None) -> dict | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON form field: {exc.msg}") from exc
    if parsed is not None and not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Context form field must decode to a JSON object")
    return parsed


def _parse_form_bool(value: str | None, *, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _parse_style_strictness(value: str | None) -> ChatStyleStrictness:
    raw = (value or "").strip().lower()
    if raw in {"low", "medium", "high"}:
        return raw  # type: ignore[return-value]
    return "medium"


def _parse_output_mode(value: str | None) -> ChatAuthoringOutputMode:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw in {"xml_only", "xml_explanation", "xml_validation", "xml_style_diff"}:
        return raw  # type: ignore[return-value]
    return "xml_validation"


def _parse_authoring_pattern(value: str | None) -> ChatAuthoringPattern:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw in {"default", "cisco_task", "cisco_reference", "auto"}:
        return raw  # type: ignore[return-value]
    return "default"


def _parse_screenshot_deliverable(value: str | None) -> ChatScreenshotDeliverableMode:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw in {"single_topic", "map_hierarchy"}:
        return raw  # type: ignore[return-value]
    return "single_topic"


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
    request: Request,
    session_id: str,
    content: str = Form(...),
    context: str | None = Form(None),
    human_prompts: str | None = Form(None),
    dita_type: str | None = Form(None),
    save_path: str | None = Form(None),
    file_name: str | None = Form(None),
    strict_validation: str | None = Form(None),
    style_strictness: str | None = Form(None),
    preserve_prolog: str | None = Form(None),
    xref_placeholders: str | None = Form(None),
    auto_ids: str | None = Form(None),
    output_mode: str | None = Form(None),
    authoring_pattern: str | None = Form(None),
    preserve_reference_doctype: str | None = Form(None),
    screenshot_deliverable: str | None = Form(None),
    jira_context: str | None = Form(None),
    image_attachment: UploadFile = File(...),
    reference_dita: UploadFile | None = File(None),
    user: UserIdentity = CurrentUser,
):
    """Send a message with screenshot/reference attachments and stream the response via SSE."""
    err = check_chat_messages_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    tenant_id = get_authorized_tenant_id(request, user)
    session = get_session(session_id, user_id=user.id, tenant_id=tenant_id, is_admin=user.is_admin)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = (content or "").strip()
    err = validate_chat_content(content)
    if err:
        raise HTTPException(status_code=400, detail=err)
    err = validate_authoring_jira_context(jira_context)
    if err:
        raise HTTPException(status_code=400, detail=err)
    jira_stripped = (jira_context or "").strip() or None
    parsed_context = _parse_form_json(context)
    err = validate_chat_context(parsed_context)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if not image_attachment:
        raise HTTPException(status_code=400, detail="image_attachment is required")

    attachments = [
        await save_upload_asset(
            session_id=session_id,
            user_id=user.id,
            kind="image",
            upload=image_attachment,
        )
    ]
    if reference_dita is not None and (reference_dita.filename or "").strip():
        attachments.append(
            await save_upload_asset(
                session_id=session_id,
                user_id=user.id,
                kind="reference_dita",
                upload=reference_dita,
            )
        )

    generation_options = ChatDitaGenerationOptions(
        dita_type=(dita_type or "").strip().lower() or None,
        save_path=(save_path or "").strip() or None,
        file_name=(file_name or "").strip() or None,
        strict_validation=_parse_form_bool(strict_validation, default=True),
        style_strictness=_parse_style_strictness(style_strictness),
        preserve_prolog=_parse_form_bool(preserve_prolog, default=False),
        xref_placeholders=_parse_form_bool(xref_placeholders, default=False),
        auto_ids=_parse_form_bool(auto_ids, default=True),
        output_mode=_parse_output_mode(output_mode),
        authoring_pattern=_parse_authoring_pattern(authoring_pattern),
        preserve_reference_doctype=_parse_form_bool(preserve_reference_doctype, default=False),
        screenshot_deliverable=_parse_screenshot_deliverable(screenshot_deliverable),
    )
    payload = ChatAuthoringRequestPayload(
        content=content,
        attachments=attachments,
        generation_options=generation_options,
        context=parsed_context,
        human_prompts=_parse_form_bool(human_prompts, default=False),
        jira_context=jira_stripped,
    )

    async def event_stream():
        try:
            async for event in chat_turn(
                session_id,
                content,
                user_id=user.id,
                context=payload.context,
                tenant_id=tenant_id,
                human_prompts=payload.human_prompts,
                attachments=payload.attachments,
                generation_options=payload.generation_options,
                jira_context=payload.jira_context,
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
    from app.db.base import SessionLocal
    from app.db.chat_models import ChatMessageFeedback

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
