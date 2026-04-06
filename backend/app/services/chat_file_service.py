"""Chat file upload service — stores user-uploaded files for use in DITA generation."""
import os
import shutil
from pathlib import Path
from uuid import uuid4
from typing import Optional
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger("chat_file_service")

# Session-scoped upload directory
UPLOAD_BASE = Path(os.getenv("CHAT_UPLOAD_DIR", "data/chat_uploads"))
MAX_FILE_SIZE_MB = int(os.getenv("CHAT_MAX_FILE_SIZE_MB", "10"))
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf", ".xml", ".dita", ".ditamap"}


def get_session_upload_dir(session_id: str) -> Path:
    """Get or create the upload directory for a session."""
    dir_path = UPLOAD_BASE / session_id
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def save_uploaded_file(session_id: str, filename: str, content: bytes) -> dict:
    """Save an uploaded file and return metadata."""
    # Validate
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {"error": f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}

    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return {"error": f"File too large ({size_mb:.1f}MB). Max: {MAX_FILE_SIZE_MB}MB"}

    # Save with unique prefix to avoid collisions
    safe_name = Path(filename).name  # strip any path components
    file_id = str(uuid4())[:8]
    stored_name = f"{file_id}_{safe_name}"

    upload_dir = get_session_upload_dir(session_id)
    file_path = upload_dir / stored_name
    file_path.write_bytes(content)

    is_image = ext in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}

    logger.info_structured(
        "File uploaded",
        extra_fields={"session_id": session_id, "filename": safe_name, "size_mb": round(size_mb, 2), "is_image": is_image},
    )

    return {
        "file_id": file_id,
        "filename": safe_name,
        "stored_name": stored_name,
        "path": str(file_path),
        "size_bytes": len(content),
        "is_image": is_image,
        "extension": ext,
    }


def list_session_files(session_id: str) -> list[dict]:
    """List all uploaded files for a session."""
    upload_dir = UPLOAD_BASE / session_id
    if not upload_dir.exists():
        return []
    files = []
    for f in sorted(upload_dir.iterdir()):
        if f.is_file():
            ext = f.suffix.lower()
            files.append({
                "filename": "_".join(f.name.split("_")[1:]) if "_" in f.name else f.name,
                "stored_name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "is_image": ext in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"},
                "extension": ext,
            })
    return files


def cleanup_session_files(session_id: str) -> None:
    """Remove all uploaded files for a session."""
    upload_dir = UPLOAD_BASE / session_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
