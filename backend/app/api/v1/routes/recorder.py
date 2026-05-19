"""UI workflow recorder sessions — capture JSON storage, validation, redaction, planning bridge (extension-friendly)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser
from app.services.recorder_capture_service import (
    attach_session_metadata,
    create_session_from_capture,
    delete_session,
    list_sessions,
    load_session_doc,
    plan_input_from_session,
    redact_capture_document,
    save_session_doc,
    validate_capture,
)

router = APIRouter(dependencies=[CurrentUser])
evidence_router = APIRouter(dependencies=[CurrentUser])


class RecorderSessionCreate(BaseModel):
    capture: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(None, max_length=128)
    redact: bool = False


class RecorderCaptureUpdate(BaseModel):
    capture: dict[str, Any] = Field(default_factory=dict)


class RecorderAttachBody(BaseModel):
    jira_key: str | None = Field(None, max_length=50)
    authoring_job_id: str | None = Field(None, max_length=128)
    user_notes: str = ""


@router.post("/sessions")
def recorder_create_session(body: RecorderSessionCreate) -> dict[str, Any]:
    cap = body.capture
    if not isinstance(cap, dict) or not cap:
        raise HTTPException(status_code=400, detail="capture object required")
    if body.redact:
        cap = redact_capture_document({"capture": cap})["capture"]
    v = validate_capture(cap)
    if not v["ok"]:
        raise HTTPException(status_code=400, detail={"errors": v["errors"], "warnings": v["warnings"]})
    sid = create_session_from_capture(cap, session_id=body.session_id)
    return {"id": sid, "validation": v}


@router.get("/sessions")
def recorder_list_sessions(limit: int = 50) -> dict[str, Any]:
    rows = list_sessions(limit=max(1, min(limit, 200)))
    return {"sessions": rows}


@router.get("/sessions/{session_id}")
def recorder_get_session(session_id: str) -> dict[str, Any]:
    try:
        return load_session_doc(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/sessions/{session_id}")
def recorder_put_session(session_id: str, body: RecorderCaptureUpdate) -> dict[str, Any]:
    try:
        doc = load_session_doc(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    doc["capture"] = body.capture
    v = validate_capture(body.capture)
    if not v["ok"]:
        raise HTTPException(status_code=400, detail={"errors": v["errors"], "warnings": v["warnings"]})
    save_session_doc(session_id, doc)
    return {"ok": True, "validation": v}


@router.delete("/sessions/{session_id}")
def recorder_delete_session(session_id: str) -> dict[str, Any]:
    try:
        ok = delete_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@router.post("/sessions/{session_id}/validate")
def recorder_validate_session(session_id: str) -> dict[str, Any]:
    try:
        doc = load_session_doc(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    cap = doc.get("capture") if isinstance(doc.get("capture"), dict) else {}
    return validate_capture(cap)


@router.post("/sessions/{session_id}/redact")
def recorder_redact_session(session_id: str) -> dict[str, Any]:
    try:
        doc = load_session_doc(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    red = redact_capture_document(doc)
    save_session_doc(session_id, red)
    return {"ok": True, "meta": red.get("meta")}


@router.post("/sessions/{session_id}/attach")
def recorder_attach(session_id: str, body: RecorderAttachBody) -> dict[str, Any]:
    try:
        return attach_session_metadata(
            session_id,
            jira_key=body.jira_key,
            authoring_job_id=body.authoring_job_id,
            user_notes=body.user_notes,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/plan-input")
def recorder_plan_input(session_id: str) -> dict[str, Any]:
    try:
        return plan_input_from_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/screenshots")
async def recorder_upload_screenshot(
    session_id: str,
    file: UploadFile = File(...),
    step_id: str | None = None,
) -> dict[str, Any]:
    from pathlib import Path
    from shutil import copyfileobj
    import time

    try:
        from app.services.recorder_capture_service import load_session_doc, screenshots_dir

        load_session_doc(session_id)
        d = screenshots_dir(session_id)
        ext = Path(file.filename or "shot.png").suffix or ".bin"
        safe = "".join(c for c in (step_id or "step") if c.isalnum() or c in "-_")[:80]
        name = f"{safe}_{int(time.time() * 1000)}{ext}"
        dest = d / name
        with dest.open("wb") as out:
            copyfileobj(file.file, out)
        return {"ok": True, "path": str(dest.name)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@evidence_router.post("/upload-capture-json")
def evidence_upload_capture_json(body: RecorderSessionCreate) -> dict[str, Any]:
    """Alias for POST /api/v1/recorder/sessions (Chrome extension contract)."""
    return recorder_create_session(body)
