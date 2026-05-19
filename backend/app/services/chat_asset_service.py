from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.schemas_chat_authoring import ChatAttachmentRef
from app.core.structured_logging import get_structured_logger
from app.services.chat_authoring_governance import sha256_hex_bytes, store_asset_content_sha256, strict_image_magic_bytes
from app.storage import get_storage

logger = get_structured_logger(__name__)

_CHAT_ASSET_ROOT = "chat_assets"
_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _validate_raster_image_bytes(content: bytes) -> None:
    """Reject non-image payloads when strict magic-byte checks are enabled (enterprise upload safety)."""
    if not strict_image_magic_bytes():
        return
    if len(content) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is too small or empty")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    if content.startswith(b"\xff\xd8\xff"):
        return
    if content.startswith((b"GIF87a", b"GIF89a")):
        return
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="File is not a supported raster image (PNG, JPEG, GIF, or WebP)",
    )


def _assets_root() -> Path:
    root = get_storage().base_path / _CHAT_ASSET_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(value: str, fallback: str) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("-", (value or "").strip()).strip(".-")
    return cleaned or fallback


def _infer_mime_type(filename: str, provided: str | None = None) -> str:
    if provided:
        candidate = provided.strip()
        if candidate:
            return candidate
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _asset_dir(asset_id: str) -> Path:
    return _assets_root() / asset_id


def _asset_metadata_path(asset_id: str) -> Path:
    return _asset_dir(asset_id) / "metadata.json"


def _asset_payload_path(asset_id: str, filename: str) -> Path:
    return _asset_dir(asset_id) / filename


def _asset_url(asset_id: str) -> str:
    return f"/api/v1/chat/assets/{asset_id}"


def _load_metadata(asset_id: str) -> dict[str, Any] | None:
    path = _asset_metadata_path(asset_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning_structured(
            "Failed to read chat asset metadata",
            extra_fields={"asset_id": asset_id, "path": str(path)},
            exc_info=True,
        )
        return None


def _write_asset_metadata(asset_id: str, payload: dict[str, Any]) -> None:
    asset_root = _asset_dir(asset_id)
    asset_root.mkdir(parents=True, exist_ok=True)
    _asset_metadata_path(asset_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def save_upload_asset(
    *,
    session_id: str,
    user_id: str,
    kind: str,
    upload: UploadFile,
) -> ChatAttachmentRef:
    filename = _safe_filename(upload.filename or f"{kind}.bin", f"{kind}.bin")
    mime_type = _infer_mime_type(filename, upload.content_type)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{filename} is empty")
    if len(content) > _MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{filename} exceeds the {int(_MAX_ATTACHMENT_BYTES / (1024 * 1024))} MB attachment limit",
        )

    if kind == "image":
        _validate_raster_image_bytes(content)

    asset_id = str(uuid4())
    asset_root = _asset_dir(asset_id)
    asset_root.mkdir(parents=True, exist_ok=True)
    payload_path = _asset_payload_path(asset_id, filename)
    payload_path.write_bytes(content)
    preview = ""
    if kind == "reference_dita":
        preview = content.decode("utf-8", errors="ignore")[:1500]
    metadata = {
        "asset_id": asset_id,
        "session_id": session_id,
        "user_id": user_id,
        "kind": kind,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "payload_path": str(payload_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content_preview": preview,
    }
    if store_asset_content_sha256():
        metadata["content_sha256"] = sha256_hex_bytes(content)
    _write_asset_metadata(asset_id, metadata)
    logger.info_structured(
        "Saved chat upload asset",
        extra_fields={
            "event": "chat_asset_upload_stored",
            "asset_id": asset_id,
            "session_id": session_id,
            "user_id": user_id,
            "kind": kind,
            "filename": filename,
            "size_bytes": len(content),
            "content_sha256_logged": bool(metadata.get("content_sha256")),
        },
    )
    return ChatAttachmentRef(
        asset_id=asset_id,
        kind=kind,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        url=_asset_url(asset_id),
        storage_path=str(payload_path),
        content_preview=preview or None,
    )


def save_text_asset(
    *,
    session_id: str,
    user_id: str,
    kind: str,
    filename: str,
    content: str,
    mime_type: str = "application/xml",
) -> ChatAttachmentRef:
    asset_id = str(uuid4())
    safe_name = _safe_filename(filename, "generated-topic.dita")
    asset_root = _asset_dir(asset_id)
    asset_root.mkdir(parents=True, exist_ok=True)
    payload_path = _asset_payload_path(asset_id, safe_name)
    payload_path.write_text(content, encoding="utf-8")
    metadata = {
        "asset_id": asset_id,
        "session_id": session_id,
        "user_id": user_id,
        "kind": kind,
        "filename": safe_name,
        "mime_type": mime_type,
        "size_bytes": payload_path.stat().st_size,
        "payload_path": str(payload_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content_preview": content[:1500],
    }
    _write_asset_metadata(asset_id, metadata)
    logger.info_structured(
        "Saved chat text asset",
        extra_fields={
            "asset_id": asset_id,
            "session_id": session_id,
            "user_id": user_id,
            "kind": kind,
            "filename": safe_name,
        },
    )
    return ChatAttachmentRef(
        asset_id=asset_id,
        kind=kind,
        filename=safe_name,
        mime_type=mime_type,
        size_bytes=payload_path.stat().st_size,
        url=_asset_url(asset_id),
        storage_path=str(payload_path),
        content_preview=content[:1500] or None,
    )


def get_asset_metadata(asset_id: str) -> dict[str, Any] | None:
    return _load_metadata(asset_id)


def read_asset_bytes(asset_id: str) -> tuple[bytes, dict[str, Any]]:
    metadata = _load_metadata(asset_id)
    if not metadata:
        raise FileNotFoundError(asset_id)
    payload_path = Path(str(metadata.get("payload_path") or ""))
    if not payload_path.exists():
        raise FileNotFoundError(asset_id)
    return payload_path.read_bytes(), metadata


def ensure_user_can_access_asset(asset_id: str, user_id: str) -> dict[str, Any]:
    metadata = _load_metadata(asset_id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    owner = str(metadata.get("user_id") or "").strip()
    if owner and owner != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return metadata
