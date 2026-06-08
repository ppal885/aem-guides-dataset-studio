"""
Resolve Jira issue key / browse URL into full issue text for generate-from-text (chat ZIP flow).

Only uses configured JIRA_BASE_URL + auth — never fetches arbitrary user URLs (SSRF-safe).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from app.core.structured_logging import get_structured_logger
from app.services.jira_client import JiraClient, extract_description_from_issue

logger = get_structured_logger(__name__)

# Whole-message issue key (Jira style: PROJECT-123)
_SINGLE_ISSUE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
# /browse/PROJ-123 in URL path
_BROWSE_PATH = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)", re.IGNORECASE)
# Query params sometimes used by Jira UIs
_QUERY_KEY = re.compile(
    r"(?:^|[?&])(?:selectedIssue|issueKey|issue_key)=([A-Za-z][A-Za-z0-9_]*-\d+)",
    re.IGNORECASE,
)
_EMBEDDED_ISSUE_KEY = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*-\d+)\b")
_EMBEDDED_GENERATION_VERB = re.compile(
    r"\b(generate|create|build|make|draft|prepare|produce|write|convert|turn)\b",
    re.IGNORECASE,
)
_EMBEDDED_GENERATION_OBJECT = re.compile(
    r"\b(data|dita|xml|topic|topics|map|ditamap|bundle|zip|content|docs?|documentation)\b",
    re.IGNORECASE,
)
_EMBEDDED_NON_GENERATION_PATTERN = re.compile(
    r"^\s*(what|how|why|where|when|who|is|are|can|could|would|should|do|does)\b|"
    r"^\s*(find|search|show|lookup|look\s+up|status|comment|discussion|related|similar|history|"
    r"explain|define|compare)\b",
    re.IGNORECASE,
)

# Do not scan megabyte pastes for keys
_MAX_SHORTCUT_LEN = 2048
_MAX_URL_ONLY_LEN = 800
_MAX_EMBEDDED_GENERATION_LEN = 400


def _normalize_issue_key(key: str) -> str:
    return (key or "").strip().upper()


def _issue_key_safe_for_api(key: str) -> bool:
    """Strict key shape for Jira REST path segment (no injection)."""
    return bool(key and re.match(r"^[A-Z][A-Z0-9_]*-\d+$", key))


def is_jira_shortcut_input(text: str) -> bool:
    """
    True if the user message is only an issue key or a short URL line we should try to resolve.
    Long pastes are never treated as shortcuts (avoid false positives).
    """
    t = (text or "").strip()
    if not t or len(t) > _MAX_SHORTCUT_LEN:
        return False
    if _SINGLE_ISSUE_KEY.match(t):
        return True
    if t.startswith("http") and len(t) <= _MAX_URL_ONLY_LEN:
        if _BROWSE_PATH.search(t) or _QUERY_KEY.search(t):
            return True
    return False


def extract_issue_key_from_shortcut(text: str) -> Optional[str]:
    """Extract issue key from shortcut input; None if ambiguous or missing."""
    t = (text or "").strip()
    if not t or len(t) > _MAX_SHORTCUT_LEN:
        return None
    m = _SINGLE_ISSUE_KEY.match(t)
    if m:
        return _normalize_issue_key(m.group(0))
    if t.startswith("http"):
        m2 = _BROWSE_PATH.search(t)
        if m2:
            return _normalize_issue_key(m2.group(1))
        m3 = _QUERY_KEY.search(t)
        if m3:
            return _normalize_issue_key(m3.group(1))
    return None


def extract_issue_key_from_generation_request(text: str) -> Optional[str]:
    """Extract a Jira issue key from a short generation-style request.

    Supports plain Jira shortcuts such as ``GUIDES-123`` and short imperative
    requests like ``Create data for GUIDES-123`` without treating search or
    question phrasing as generation.
    """
    t = (text or "").strip()
    if not t or len(t) > _MAX_EMBEDDED_GENERATION_LEN:
        return None

    shortcut = extract_issue_key_from_shortcut(t)
    if shortcut:
        return shortcut

    matches = [m.group(1) for m in _EMBEDDED_ISSUE_KEY.finditer(t)]
    if len(matches) != 1:
        return None
    if "?" in t:
        return None
    if not _EMBEDDED_GENERATION_VERB.search(t):
        return None
    if _EMBEDDED_NON_GENERATION_PATTERN.search(t):
        return None
    if not (
        _EMBEDDED_GENERATION_OBJECT.search(t)
        or re.search(rf"\b(?:for|from)\s+{re.escape(matches[0])}\b", t, re.IGNORECASE)
    ):
        return None
    return _normalize_issue_key(matches[0])


def _jira_client_ready(client: JiraClient) -> bool:
    if not (client.base_url or "").strip():
        return False
    return bool(
        (client.username and client.password)
        or (client.email and client.api_token)
    )


def _extract_section(text: str, heading_pattern: str, max_chars: int = 3000) -> str:
    """Extract a section from description text following a heading pattern.

    Returns the text between the matched heading and the next heading (or end).
    """
    m = re.search(heading_pattern, text, re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    # Find the next heading-like line (## or h3. or ALLCAPS followed by colon/newline)
    next_heading = re.search(
        r"\n(?:##\s|h[1-6]\.\s|(?:Steps?\s+to|Expected|Actual|Acceptance|Environment|Comments?)\s)",
        text[start:],
        re.IGNORECASE,
    )
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()[:max_chars]


_TEXT_ATTACHMENT_EXTENSIONS = frozenset(
    ".txt .log .xml .dita .ditamap .json .yaml .yml .md .csv .html .htm .xhtml .snippet .sample .cfg .properties".split()
)
_IMAGE_ATTACHMENT_EXTENSIONS = frozenset(".png .jpg .jpeg .gif .webp .svg .bmp .tiff .tif".split())
_MAX_ATTACHMENT_BYTES = 80_000  # read up to ~80 KB per text attachment
_MAX_ATTACHMENTS = 5            # read up to 5 attachments per issue


def _read_attachment_text(client: JiraClient, att: dict) -> str:
    """Download a Jira attachment and return its text content (empty if binary/too large)."""
    content_url = att.get("content") or att.get("url") or ""
    filename = (att.get("filename") or "").lower()
    mime = (att.get("mimeType") or att.get("mime_type") or "").lower()
    size = int(att.get("size") or 0)

    # Only read text-readable files; skip huge files
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    is_text = (
        ext in _TEXT_ATTACHMENT_EXTENSIONS
        or mime.startswith("text/")
        or mime in ("application/json", "application/xml", "application/yaml", "application/x-yaml")
    )
    if not is_text:
        return ""
    if size > _MAX_ATTACHMENT_BYTES * 2:
        return f"[File too large to inline: {att.get('filename')} ({size // 1024} KB)]"

    if not content_url:
        return ""
    try:
        raw = client._download(content_url)
        return raw[:_MAX_ATTACHMENT_BYTES].decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug_structured(
            "Attachment download failed",
            extra_fields={"filename": att.get("filename"), "error": str(e)},
        )
        return ""


def fetch_issue_text_for_generate(issue_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch a Jira issue with full context for DITA dataset generation.

    Reads:
    - Issue metadata (key, type, status, priority, labels, components, fix versions)
    - Full description with all structured sections (steps to reproduce, expected/actual, environment)
    - All comments (up to 20, full text up to 2000 chars each)
    - Text/DITA/log attachments (up to 5 files, up to 80 KB each)
    - Attachment list with names/types for non-text files

    Returns:
        (formatted_text, None) on success
        (None, safe_error_message) on failure
    """
    key = _normalize_issue_key(issue_key)
    if not _issue_key_safe_for_api(key):
        return None, "Invalid issue key format."

    client = JiraClient()
    if not _jira_client_ready(client):
        logger.info_structured(
            "Jira shortcut skipped: client not configured",
            extra_fields={"issue_key": key},
        )
        return None, None

    # Fetch with attachment field included
    try:
        path = f"/rest/api/{client._api}/issue/{key}?fields=summary,description,labels,priority,status,issuetype,components,fixVersions,attachment,comment"
        issue = client._request("GET", path)
    except Exception as e:
        logger.warning_structured(
            "Jira fetch failed for generate-from-text",
            extra_fields={"issue_key": key, "error": str(e)},
        )
        return None, sanitize_error_for_generate(e)

    fields = issue.get("fields", {}) or {}
    summary = (fields.get("summary") or "").strip()
    description = (extract_description_from_issue(issue) or "").strip()
    labels = fields.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    priority = ""
    pr = fields.get("priority")
    if isinstance(pr, dict) and pr.get("name"):
        priority = str(pr["name"])
    status = ""
    st = fields.get("status")
    if isinstance(st, dict) and st.get("name"):
        status = str(st["name"])
    issuetype = fields.get("issuetype")
    type_name = str(issuetype.get("name", "")) if isinstance(issuetype, dict) else ""

    components = [str(c["name"]) for c in (fields.get("components") or []) if isinstance(c, dict) and c.get("name")]
    fix_versions = [str(v["name"]) for v in (fields.get("fixVersions") or []) if isinstance(v, dict) and v.get("name")]

    # --- Comments: fetch up to 20, full body up to 2000 chars ---
    comment_lines: list[str] = []
    try:
        # Try embedded comment field first (avoids a second API call)
        embedded = fields.get("comment") or {}
        raw_comments = embedded.get("comments") or []
        if not raw_comments:
            raw_comments = client.get_issue_comments(key)
        from app.services.jira_client import _adf_to_plain_text as _adf
        for c in (raw_comments or [])[:20]:
            author = ""
            a = c.get("author") or c.get("updateAuthor") or {}
            if isinstance(a, dict):
                author = a.get("displayName") or a.get("name") or ""
            body_raw = c.get("body") or c.get("body_text") or ""
            if isinstance(body_raw, dict):
                body = _adf(body_raw)
            else:
                body = str(body_raw)
            body = body.strip()[:2000]
            if not body:
                continue
            created = str(c.get("created") or "")[:10]
            comment_lines.append(f"[{author or 'Unknown'} | {created}]: {body}")
    except Exception as e:
        logger.debug_structured(
            "Comments fetch skipped",
            extra_fields={"issue_key": key, "error": str(e)},
        )

    # --- Attachments: read text files, list others ---
    attachment_text_parts: list[str] = []
    attachment_list_parts: list[str] = []
    raw_attachments = fields.get("attachment") or []
    if isinstance(raw_attachments, list):
        # Sort: text/DITA first, then images, then others — read text ones first
        def _att_sort_key(a: dict) -> int:
            ext = "." + (a.get("filename") or "").lower().rsplit(".", 1)[-1]
            if ext in _TEXT_ATTACHMENT_EXTENSIONS:
                return 0
            if ext in _IMAGE_ATTACHMENT_EXTENSIONS:
                return 1
            return 2

        sorted_atts = sorted(raw_attachments, key=_att_sort_key)
        text_read = 0
        for att in sorted_atts[:20]:
            fname = att.get("filename") or "unknown"
            mime = att.get("mimeType") or ""
            size = int(att.get("size") or 0)
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""

            is_text_file = ext in _TEXT_ATTACHMENT_EXTENSIONS or mime.startswith("text/") or "xml" in mime
            is_image = ext in _IMAGE_ATTACHMENT_EXTENSIONS or mime.startswith("image/")

            if is_text_file and text_read < _MAX_ATTACHMENTS:
                content = _read_attachment_text(client, att)
                if content:
                    attachment_text_parts.append(
                        f"### Attachment: {fname} ({size // 1024 or 1} KB)\n{content}"
                    )
                    text_read += 1
                else:
                    attachment_list_parts.append(f"- {fname} ({mime}, {size // 1024 or 1} KB)")
            elif is_image:
                attachment_list_parts.append(f"- [Image] {fname} ({mime}, {size // 1024 or 1} KB)")
            else:
                attachment_list_parts.append(f"- {fname} ({mime}, {size // 1024 or 1} KB)")

    # --- Extract structured sections from description ---
    acceptance_criteria = _extract_section(description, r"(?:acceptance\s+criteria|ac)\s*[:\n]")
    steps_to_reproduce = _extract_section(description, r"(?:steps?\s+to\s+reproduce|reproduction\s+steps?|repro\s+steps?|how\s+to\s+reproduce)\s*[:\n]")
    expected_behavior = _extract_section(description, r"(?:expected\s+(?:behavior|result|outcome|output))\s*[:\n]")
    actual_behavior = _extract_section(description, r"(?:actual\s+(?:behavior|result|outcome|output)|current\s+behavior|actual\s+output)\s*[:\n]")
    environment = _extract_section(description, r"(?:environment|setup|config(?:uration)?|version|build)\s*[:\n]")
    notes = _extract_section(description, r"(?:additional\s+(?:notes?|info(?:rmation)?)|notes?|remarks?)\s*[:\n]")

    # --- Assemble the full context block ---
    parts = [
        f"Issue Key: {key}",
        f"Issue Type: {type_name}",
        f"Status: {status}",
        f"Priority: {priority}",
        f"Labels: {', '.join(str(x) for x in labels[:30]) or '(none)'}",
    ]
    if components:
        parts.append(f"Components: {', '.join(components[:10])}")
    if fix_versions:
        parts.append(f"Fix Versions: {', '.join(fix_versions[:10])}")

    parts.extend(["", "## Issue Summary", summary or "(no summary)", "", "## Issue Description"])
    # If we extracted structured sections, show the description without them to avoid duplication
    clean_description = description
    for pattern in [
        r"(?:steps?\s+to\s+reproduce|reproduction\s+steps?|repro\s+steps?).*",
        r"(?:expected\s+(?:behavior|result|outcome)).*",
        r"(?:actual\s+(?:behavior|result|outcome)|current\s+behavior).*",
        r"(?:environment|setup|config(?:uration)?).*",
        r"(?:acceptance\s+criteria|ac)\s*:.*",
    ]:
        pass  # keep full description — sections are also shown separately for emphasis
    parts.append(clean_description or "(no description)")

    if steps_to_reproduce:
        parts.extend(["", "## Steps to Reproduce", steps_to_reproduce])
    if expected_behavior:
        parts.extend(["", "## Expected Behavior", expected_behavior])
    if actual_behavior:
        parts.extend(["", "## Actual Behavior", actual_behavior])
    if environment:
        parts.extend(["", "## Environment", environment])
    if acceptance_criteria:
        parts.extend(["", "## Acceptance Criteria", acceptance_criteria])
    if notes:
        parts.extend(["", "## Additional Notes", notes])

    if attachment_list_parts or attachment_text_parts:
        parts.extend(["", "## Attachments"])
        if attachment_list_parts:
            parts.extend(attachment_list_parts)
        if attachment_text_parts:
            parts.extend(["", "### Attachment Contents"])
            parts.extend(attachment_text_parts)

    if comment_lines:
        parts.extend(["", f"## Comments ({len(comment_lines)})"])
        parts.extend(comment_lines)

    return "\n".join(parts), None


def sanitize_error_for_generate(exc: Exception) -> str:
    """Short, non-sensitive message for chat tool result."""
    msg = str(exc).lower()
    if "404" in msg:
        return "Jira returned 404 for this issue. Check the key and API version (JIRA_API_VERSION=2 for some servers)."
    if "401" in msg or "403" in msg:
        return "Jira authentication failed. Check JIRA_BASE_URL and credentials in server .env."
    return "Could not fetch this issue from Jira. Paste the full issue text, or verify Jira configuration."


def resolve_text_for_generate_from_text(body_text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    If input is a Jira shortcut and Jira is configured, replace with fetched issue text.

    Returns:
        (text_for_pipeline, jira_id_for_bundle_or_none, optional_warning)
        jira_id_for_bundle is real PROJECT-123 when fetch succeeded; else None (caller uses TEXT-...).
    """
    raw = (body_text or "").strip()
    if not is_jira_shortcut_input(raw):
        key = extract_issue_key_from_generation_request(raw)
        if not key:
            return body_text, None, None
        formatted, err = fetch_issue_text_for_generate(key)
        if formatted:
            return f"{formatted}\n\n## Generation Request\n{raw}", key, None
        if err:
            return body_text, None, err
        return body_text, None, None

    key = extract_issue_key_from_shortcut(raw)
    if not key:
        return body_text, None, None

    formatted, err = fetch_issue_text_for_generate(key)
    if formatted:
        return formatted, key, None

    if err:
        return body_text, None, err

    # Not configured: keep original shortcut as text (LLM still sees key/URL)
    return body_text, None, None
