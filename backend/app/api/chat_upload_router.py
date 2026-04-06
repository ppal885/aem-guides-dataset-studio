"""Chat file upload API endpoints."""
from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from app.services.chat_file_service import save_uploaded_file, list_session_files, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

router = APIRouter(prefix="/api/v1/chat", tags=["chat-upload"])


@router.post("/sessions/{session_id}/upload")
async def upload_file(session_id: str, file: UploadFile = File(...)):
    """Upload a file to a chat session."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    result = save_uploaded_file(session_id, file.filename, content)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    """List all uploaded files for a session."""
    return {"files": list_session_files(session_id)}


@router.get("/upload/config")
async def get_upload_config():
    """Return upload configuration for the frontend."""
    return {
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    }
