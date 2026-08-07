"""Shared customer-token sanitizer.

Jira labels leak process/status tags (Triaged, Bugs, Uac_done, Won't_automate,
Plan_2611, 5.1.2_sp_guides, ID, Name, Org, ...) into the customer_names the
enrichment derives from labels. Those pollute customer matching, cross-customer
ranking, and any customer display in the jira_qa RAG.

This module is the single source of truth used at:
- ingestion (jira_qa_chunking_service / jira_chunking_service) so re-indexed
  chunks store clean customer tokens, and
- query/ranking time (jira_retrieval_service, remote_mcp search_jira_history) so
  already-indexed polluted chunks are cleaned on read without a re-index.
"""

from __future__ import annotations

import re

# Exact (lowercased, apostrophe-normalized) non-customer tokens.
CUSTOMER_TOKEN_DENY_EXACT = {
    "automated", "bugs", "triaged", "groomed", "id", "name", "org", "ims", "also",
    "uac_done", "uac_not_required", "uac_check", "won't_automate", "wont_automate",
    "not_automated", "loc_tested", "loc", "doc_required", "features", "context",
    "information", "impact", "managed", "services", "service", "support", "production",
    "cert", "environment", "har", "td", "severity", "subzero", "urgent", "break",
    "sr", "sla3", "shift_left_guides", "elite", "elite3", "deleting", "not", "segment",
    "bookmarks", "contents", "table", "reviewed", "resolved", "open", "closed",
}
# Prefixes of non-customer tokens (release trains, plan tags, investigation ids...).
CUSTOMER_TOKEN_DENY_PREFIX = (
    "plan_", "cxps", "fluffyjaws", "guides_", "productmay", "elevate", "must_fix",
    "5.", "4.", "3.", "2609", "2611", "2606", "2601", "guid-", "guides-",
)
_VERSIONISH_RE = re.compile(r"^[0-9._-]+$")


def is_customer_token(token: str) -> bool:
    """True if the token looks like a real customer, not a leaked Jira label."""
    s = str(token or "").strip()
    if not s:
        return False
    low = s.lower().replace("’", "'")  # normalize curly apostrophe
    if low in CUSTOMER_TOKEN_DENY_EXACT:
        return False
    if any(low.startswith(p) for p in CUSTOMER_TOKEN_DENY_PREFIX):
        return False
    if _VERSIONISH_RE.match(low):
        return False
    return True


def clean_customer_tokens(tokens: list[str]) -> list[str]:
    """Drop leaked-label tokens, preserving order and de-duplicating."""
    out: list[str] = []
    for t in tokens or []:
        s = str(t or "").strip()
        if is_customer_token(s) and s not in out:
            out.append(s)
    return out
