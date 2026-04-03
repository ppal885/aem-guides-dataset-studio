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

# Do not scan megabyte pastes for keys
_MAX_SHORTCUT_LEN = 2048
_MAX_URL_ONLY_LEN = 800


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


def fetch_issue_text_for_generate(issue_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch issue from configured Jira and format for _build_evidence_pack_from_text.

    Returns:
        (formatted_text, None) on success
        (None, safe_error_message) on failure (for optional UI; no stack traces)
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

    try:
        issue = client.get_issue(key)
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

    # Extract components and fix versions
    components = []
    for comp in (fields.get("components") or []):
        if isinstance(comp, dict) and comp.get("name"):
            components.append(str(comp["name"]))
    fix_versions = []
    for ver in (fields.get("fixVersions") or []):
        if isinstance(ver, dict) and ver.get("name"):
            fix_versions.append(str(ver["name"]))

    comment_lines: list[str] = []
    try:
        raw_comments = client.get_issue_comments(key)
        for c in (raw_comments or [])[:8]:
            author = (c.get("author") or "").strip()
            body = (c.get("body_text") or "").strip()
            if not body:
                continue
            body = body[:1200]
            comment_lines.append(f"[{author}]: {body}")
    except Exception as e:
        logger.debug_structured(
            "Comments fetch skipped for generate-from-text",
            extra_fields={"issue_key": key, "error": str(e)},
        )

    # Extract structured sections from description
    acceptance_criteria = _extract_section(description, r"(?:acceptance\s+criteria|ac)\s*[:\n]")
    steps_to_reproduce = _extract_section(description, r"(?:steps?\s+to\s+reproduce|reproduction\s+steps?|repro\s+steps?)\s*[:\n]")
    expected_behavior = _extract_section(description, r"(?:expected\s+(?:behavior|result|outcome))\s*[:\n]")
    actual_behavior = _extract_section(description, r"(?:actual\s+(?:behavior|result|outcome)|current\s+behavior)\s*[:\n]")
    environment = _extract_section(description, r"(?:environment|setup|config(?:uration)?)\s*[:\n]")

    parts = [
        f"Issue Key: {key}",
        f"Issue Type: {type_name}",
        f"Status: {status}",
        f"Priority: {priority}",
        f"Labels: {', '.join(str(x) for x in labels[:30])}",
    ]
    if components:
        parts.append(f"Components: {', '.join(components[:10])}")
    if fix_versions:
        parts.append(f"Fix Versions: {', '.join(fix_versions[:10])}")
    parts.extend([
        "",
        "## Issue Summary",
        summary or "(no summary)",
        "",
        "## Issue Description",
        description or "(no description)",
    ])
    if acceptance_criteria:
        parts.extend(["", "## Acceptance Criteria", acceptance_criteria])
    if steps_to_reproduce:
        parts.extend(["", "## Steps to Reproduce", steps_to_reproduce])
    if expected_behavior:
        parts.extend(["", "## Expected Behavior", expected_behavior])
    if actual_behavior:
        parts.extend(["", "## Actual Behavior", actual_behavior])
    if environment:
        parts.extend(["", "## Environment", environment])
    if comment_lines:
        parts.extend(["", "## Comments"])
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
