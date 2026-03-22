"""Jira attachment service - lazy caching and excerpt extraction."""
import re
import zipfile
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db.jira_models import JiraAttachment, JiraIssue
from app.services.jira_client import JiraClient
from app.storage import get_storage
from app.generator.generate import sanitize_filename
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

TEXT_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
)
TEXT_EXTENSIONS = (".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".html", ".htm", ".snippet", ".sample")
DITA_EXTENSIONS = (".dita", ".ditamap", ".xml")
DITA_NAMES = ("map", "topic", "keydef", "topicref", "keyref", "section", "body")
VIDEO_MIME_PREFIXES = ("video/",)
VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".wmv", ".mkv", ".ogv")
IMAGE_MIME_PREFIXES = ("image/",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp")


def _is_safe_issue_key(issue_key: str) -> bool:
    """Validate issue_key for path safety (alphanumeric + hyphen)."""
    return bool(issue_key and re.match(r"^[A-Za-z0-9_-]+$", issue_key))


def classify_attachment_kind(filename: str, mime_type: Optional[str]) -> str:
    """Classify attachment into a broad content kind."""
    suffix = Path(filename or "").suffix.lower()
    mime = (mime_type or "").lower()

    if mime.startswith(VIDEO_MIME_PREFIXES) or suffix in VIDEO_EXTENSIONS:
        return "video"
    if mime.startswith(IMAGE_MIME_PREFIXES) or suffix in IMAGE_EXTENSIONS:
        return "image"
    if mime.startswith(TEXT_MIME_PREFIXES) or suffix in TEXT_EXTENSIONS:
        return "text"
    if mime == "application/zip" or suffix == ".zip":
        return "archive"
    return "file"


def _attachment_storage_paths(issue_key: str, attachment_id: str, filename: str) -> tuple[str, Path]:
    """Resolve a safe storage location for a Jira attachment."""
    storage = get_storage()
    safe_filename = sanitize_filename(filename, windows_safe=True)
    if not safe_filename or ".." in safe_filename:
        safe_filename = f"attachment_{attachment_id[:8]}"

    safe_prefix = sanitize_filename(str(attachment_id)[:12], windows_safe=True) or "att"
    rel_path = f"jira_attachments/{issue_key}/{safe_prefix}_{safe_filename}"
    return rel_path, storage.base_path / rel_path


def cache_raw_issue_attachment(
    issue_key: str,
    attachment_id: str,
    filename: str,
    content_url: str,
    jira_client: Optional[JiraClient] = None,
) -> dict:
    """Cache a Jira attachment from raw Jira issue data."""
    if not _is_safe_issue_key(issue_key) or not content_url:
        return {"stored_path": "", "relative_path": ""}

    rel_path, full_path = _attachment_storage_paths(issue_key, attachment_id, filename)
    if full_path.exists():
        return {"stored_path": str(full_path), "relative_path": rel_path.replace("\\", "/")}

    client = jira_client or JiraClient()
    if not client.base_url:
        return {"stored_path": "", "relative_path": ""}

    try:
        content = client.download_attachment(content_url)
    except Exception as e:
        logger.warning_structured(
            "Failed to download raw Jira attachment",
            extra_fields={"issue_key": issue_key, "attachment_id": attachment_id, "error": str(e)},
        )
        return {"stored_path": "", "relative_path": ""}

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    return {"stored_path": str(full_path), "relative_path": rel_path.replace("\\", "/")}


def ensure_attachment_cached(
    session: Session,
    attachment_row: JiraAttachment,
    jira_client: Optional[JiraClient] = None,
) -> JiraAttachment:
    """Download and cache attachment if not already stored."""
    if attachment_row.stored_path and Path(attachment_row.stored_path).exists():
        return attachment_row

    if not attachment_row.jira_url:
        return attachment_row

    if not _is_safe_issue_key(attachment_row.issue_key):
        logger.warning_structured(
            "Invalid issue_key for attachment",
            extra_fields={"issue_key": attachment_row.issue_key},
        )
        return attachment_row

    client = jira_client or JiraClient()
    if not client.base_url:
        return attachment_row

    try:
        content = client.download_attachment(attachment_row.jira_url)
    except Exception as e:
        logger.warning_structured(
            "Failed to download attachment",
            extra_fields={
                "attachment_id": attachment_row.id,
                "issue_key": attachment_row.issue_key,
                "error": str(e),
            },
        )
        return attachment_row

    rel_path, full_path = _attachment_storage_paths(
        attachment_row.issue_key,
        attachment_row.id,
        attachment_row.filename,
    )
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)

    attachment_row.stored_path = str(full_path)
    session.merge(attachment_row)
    return attachment_row


def _looks_like_dita(text: str) -> bool:
    """Check if text contains DITA-like tags."""
    t = text.lower()
    return any(tag in t for tag in ("<map", "<topic", "<keydef", "<topicref", "<keyref", "<section", "<body", "<p "))


def _extract_dita_from_zip(zf: zipfile.ZipFile, max_chars_total: int = 30000) -> str:
    """Extract DITA file contents from ZIP. Returns combined content."""
    parts = []
    total = 0
    for name in zf.namelist()[:30]:
        if total >= max_chars_total:
            break
        name_lower = name.lower()
        if not any(name_lower.endswith(ext) for ext in DITA_EXTENSIONS):
            continue
        try:
            raw = zf.read(name)
            content = raw.decode("utf-8", errors="replace")
            if _looks_like_dita(content):
                chunk = content[:max_chars_total - total]
                parts.append(f"--- {name} ---\n{chunk}")
                total += len(chunk)
        except Exception:
            continue
    return "\n\n".join(parts) if parts else ""


def extract_excerpt(path: Path, mime_type: Optional[str], max_chars: int = 12000) -> str:
    """Extract text excerpt from file based on mime type. DITA/XML get full content (up to max_chars)."""
    if not path.exists() or not path.is_file():
        return ""

    mime = (mime_type or "").lower()
    suffix = path.suffix.lower()

    try:
        if mime.startswith("text/") or mime in (
            "application/json",
            "application/xml",
            "application/yaml",
            "application/x-yaml",
        ) or suffix in TEXT_EXTENSIONS:
            content = path.read_text(encoding="utf-8", errors="replace")
            return content[:max_chars]

        if suffix in DITA_EXTENSIONS:
            content = path.read_text(encoding="utf-8", errors="replace")
            if _looks_like_dita(content):
                return content[:max_chars]
            return content[:max_chars]

        if mime == "application/zip" or suffix == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                dita_content = _extract_dita_from_zip(zf, max_chars_total=max_chars)
                if dita_content:
                    return dita_content
                names = zf.namelist()[:50]
            return "\n".join(names)

        return ""
    except Exception as e:
        logger.debug_structured(
            "Could not extract excerpt",
            extra_fields={"path": str(path), "error": str(e)},
        )
        return ""


def enrich_attachments_with_excerpts(
    session: Session,
    issue_key: str,
    max_files: int = 2,
    jira_client: Optional[JiraClient] = None,
) -> list[dict]:
    """Get attachments for issue, cache smallest ones, add excerpts. Store text_search_blob."""
    issue = session.query(JiraIssue).filter(JiraIssue.issue_key == issue_key).first()
    issue_summary = (issue.summary or "") if issue else ""

    attachments = (
        session.query(JiraAttachment)
        .filter(JiraAttachment.issue_key == issue_key)
        .order_by(JiraAttachment.size_bytes.asc().nullslast())
        .limit(max_files)
        .all()
    )

    result = []
    for att in attachments:
        att = ensure_attachment_cached(session, att, jira_client)
        excerpt = ""
        if att.stored_path:
            excerpt = extract_excerpt(Path(att.stored_path), att.mime_type)
            if excerpt and not att.text_excerpt:
                att.text_excerpt = excerpt[:12000]
                session.merge(att)

        text_search_blob = " ".join(filter(None, [att.filename or "", excerpt or "", issue_summary]))
        if text_search_blob and text_search_blob != (att.text_search_blob or ""):
            att.text_search_blob = text_search_blob[:50000]
            session.merge(att)

        full_content = ""
        if excerpt and _looks_like_dita(excerpt):
            suffix = Path(att.filename or "").suffix.lower()
            if suffix in DITA_EXTENSIONS:
                full_content = excerpt[:12000]
            elif suffix == ".zip" or (att.mime_type or "").lower() == "application/zip":
                full_content = excerpt[:30000]
            elif suffix in (".snippet", ".sample", ".txt"):
                full_content = excerpt[:12000]

        result.append({
            "filename": att.filename,
            "mime_type": att.mime_type,
            "size_bytes": att.size_bytes,
            "excerpt": excerpt[:5000] if excerpt else "",
            "full_content": full_content,
        })

    return result


def normalize_issue_attachments(
    issue_key: str,
    raw_attachments: list[dict] | None,
    jira_client: Optional[JiraClient] = None,
    *,
    download_media: bool = False,
    max_downloads: int = 3,
) -> list[dict]:
    """Normalize raw Jira attachment metadata and optionally cache media files."""
    normalized: list[dict] = []
    downloaded = 0

    for raw in raw_attachments or []:
        if not isinstance(raw, dict):
            continue

        attachment_id = str(raw.get("id") or "")
        filename = str(raw.get("filename") or "attachment")
        mime_type = str(raw.get("mimeType") or "")
        kind = classify_attachment_kind(filename, mime_type)
        content_url = str(raw.get("content") or "")
        thumbnail_url = str(raw.get("thumbnail") or "")
        stored_path = ""
        relative_path = ""

        should_download = download_media and kind in {"video", "image"} and downloaded < max_downloads
        if should_download:
            cached = cache_raw_issue_attachment(
                issue_key=issue_key,
                attachment_id=attachment_id or filename,
                filename=filename,
                content_url=content_url,
                jira_client=jira_client,
            )
            stored_path = str(cached.get("stored_path") or "")
            relative_path = str(cached.get("relative_path") or "")
            if stored_path:
                downloaded += 1

        normalized.append(
            {
                "id": attachment_id,
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": raw.get("size"),
                "jira_url": content_url,
                "thumbnail_url": thumbnail_url,
                "kind": kind,
                "is_video": kind == "video",
                "is_image": kind == "image",
                "stored_path": stored_path,
                "relative_path": relative_path,
            }
        )

    return normalized


def summarize_issue_attachments(attachments: list[dict] | None, max_items: int = 4) -> str:
    """Create a compact prompt-friendly summary of issue attachments."""
    lines: list[str] = []
    for att in (attachments or [])[:max_items]:
        filename = str(att.get("filename") or "attachment")
        kind = str(att.get("kind") or "file")
        mime_type = str(att.get("mime_type") or "")
        relative_path = str(att.get("relative_path") or "")

        details = [kind]
        if mime_type:
            details.append(mime_type)
        if relative_path:
            details.append(f"cached path: {relative_path}")

        line = f"- {filename} ({', '.join(details)})"
        if att.get("is_video") and relative_path:
            line += " Include this video with a DITA <object> element when it supports the topic."
        lines.append(line)

    return "\n".join(lines)
