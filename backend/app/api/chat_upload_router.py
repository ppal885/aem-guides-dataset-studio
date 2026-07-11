"""Chat file upload API endpoints (removed)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/chat", tags=["chat-upload"])

_GONE = "Chat file upload is no longer available in DITA Expert."


@router.post("/sessions/{session_id}/upload")
async def upload_file(session_id: str):
    raise HTTPException(status_code=410, detail=_GONE)


@router.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    raise HTTPException(status_code=410, detail=_GONE)


@router.get("/upload/config")
async def get_upload_config():
    raise HTTPException(status_code=410, detail=_GONE)
