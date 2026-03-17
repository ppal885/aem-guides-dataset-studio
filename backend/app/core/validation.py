"""
Input validation and error sanitization for API safety.
"""
import re
from typing import Optional

JIRA_KEY_MAX_LEN = 50


def validate_jira_id(jira_id: str) -> Optional[str]:
    """
    Validate Jira issue key. Returns error message if invalid, None if valid.
    Accepts PROJECT-123 format; also accepts TEXT-{run_id} for generate-from-text (paste) flow.
    """
    if not jira_id or not isinstance(jira_id, str):
        return "jira_id is required"
    jira_id = jira_id.strip()
    if len(jira_id) > JIRA_KEY_MAX_LEN:
        return f"jira_id must be at most {JIRA_KEY_MAX_LEN} characters"
    # Synthetic format for generate-from-text (paste Jira, no real Jira ID)
    if jira_id.startswith("TEXT-") and len(jira_id) > 5:
        suffix = jira_id[5:]
        if re.match(r"^[a-zA-Z0-9]+$", suffix):
            return None
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9\-]*\d+$", jira_id):
        return "jira_id must match format PROJECT-123 (e.g. DXML-42)"
    return None


def sanitize_error_for_client(error: Exception, include_detail: bool = False) -> str:
    """
    Return a safe error message for API responses.
    Avoids exposing internal paths, stack traces, or sensitive data.
    """
    msg = str(error)
    if include_detail:
        return msg[:500]
    # Jira 404: corporate Jira often needs JIRA_API_VERSION=2
    if "404" in msg and ("rest/api" in msg.lower() or "jira" in msg.lower()):
        return (
            "Jira returned 404. For corporate/on-prem Jira (e.g. jira.corp.adobe.com), "
            "set JIRA_API_VERSION=2 in .env. Also verify JIRA_BASE_URL, JIRA_USERNAME, JIRA_PASSWORD."
        )
    # Generic message for unknown errors; preserve known safe errors
    safe_prefixes = ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "jira_id", "Issue ", "Validation error")
    if any(msg.startswith(p) for p in safe_prefixes):
        return msg[:500]
    # Don't expose internal details
    if "Traceback" in msg or "File \"" in msg or "line " in msg.lower():
        return "An internal error occurred. Check server logs for details."
    if len(msg) > 200:
        return msg[:200] + "..."
    return msg


JQL_MAX_LEN = 500
JQL_BLOCKED_PATTERNS = (r";", r"--", r"/\*", r"\*/")


def validate_jql(jql: str) -> Optional[str]:
    """
    Validate JQL for search/index. Returns error message if invalid, None if valid.
    Blocks dangerous characters to reduce injection risk.
    """
    if not jql or not isinstance(jql, str):
        return "jql is required"
    jql = jql.strip()
    if len(jql) > JQL_MAX_LEN:
        return f"jql must be at most {JQL_MAX_LEN} characters"
    for pattern in JQL_BLOCKED_PATTERNS:
        if re.search(pattern, jql):
            return "jql contains invalid characters"
    return None
