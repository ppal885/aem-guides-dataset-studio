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


def _is_safe_issue_key(issue_key: str) -> bool:
    """Validate issue_key for path safety (alphanumeric + hyphen)."""
    return bool(issue_key and re.match(r"^[A-Za-z0-9_-]+$", issue_key))


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

    storage = get_storage()
    safe_filename = sanitize_filename(attachment_row.filename, windows_safe=True)
    if not safe_filename or ".." in safe_filename:
        safe_filename = f"attachment_{attachment_row.id[:8]}"

    rel_path = f"jira_attachments/{attachment_row.issue_key}/{safe_filename}"
    full_path = storage.base_path / rel_path
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
