"""Deterministic Jira issue search for chat requests."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.structured_logging import get_structured_logger
from app.db.jira_models import JiraIssue
from app.db.session import SessionLocal
from app.services.jira_client import JiraClient
from app.services.jira_dita_fetch_service import fetch_jira_issues
from app.services.jira_similarity_service import find_similar_issues
from app.services.tenant_service import build_jira_client

logger = get_structured_logger(__name__)

_SEARCH_NOISE_PATTERN = re.compile(
    r"\b("
    r"can|could|would|will|please|you|me|the|a|an|any|all|some|of|on|in|for|to|about|around|with|that|this|these|those|"
    r"fetch|find|show|search|lookup|look\s+up|get|list|surface|pull|give|need|want|related|similar|matching|relevant|"
    r"jira|jiras|issue|issues|ticket|tickets"
    r")\b",
    re.IGNORECASE,
)
_JIRA_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

_TOPIC_ALIASES: dict[str, list[str]] = {
    "reltable": ["reltable", "reltables", "relationship table", "relationship tables"],
    "reltables": ["reltable", "reltables", "relationship table", "relationship tables"],
    "relationship table": ["reltable", "reltables", "relationship table", "relationship tables"],
    "relationship tables": ["reltable", "reltables", "relationship table", "relationship tables"],
}


def extract_jira_search_query(user_text: str) -> str:
    """Extract the actual Jira search topic from a natural-language request."""
    text = (user_text or "").strip()
    if not text:
        return ""

    explicit_issue_key = _JIRA_KEY_PATTERN.search(text)
    if explicit_issue_key:
        return explicit_issue_key.group(0)

    patterns = [
        r"\b(?:related|similar|matching|relevant)\s+(?:jiras?|issues?|tickets?)\s+(?:to|for|about)\s+(?P<query>.+)$",
        r"\b(?:fetch|find|show|search|lookup|look up|get|list|surface|pull)\s+(?:me\s+)?(?:the\s+)?(?:related\s+|similar\s+|matching\s+|relevant\s+)?(?:jiras?|issues?|tickets?)\s+(?:to|for|about)\s+(?P<query>.+)$",
        r"\b(?:which|what)\s+(?:jiras?|issues?|tickets?)\s+(?:are\s+)?(?:related|similar|matching|relevant)\s+(?:to|for|about)\s+(?P<query>.+)$",
        r"\b(?:which|what)\s+(?:jiras?|issues?|tickets?)\s+(?:mention|cover|reference|touch)\s+(?P<query>.+)$",
    ]
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            extracted = match.group("query")
            return re.sub(r"\s+", " ", extracted).strip(" ?.!,:;")

    stripped = _SEARCH_NOISE_PATTERN.sub(" ", text)
    stripped = re.sub(r"[^\w\s-]", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -")
    return stripped or text.strip(" ?.!,:;")


def expand_jira_search_terms(query: str) -> list[str]:
    """Expand the search topic into phrase and token variants for live/indexed search."""
    cleaned = re.sub(r"\s+", " ", (query or "").strip())
    if not cleaned:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        normalized = re.sub(r"\s+", " ", (value or "").strip())
        lowered = normalized.lower()
        if normalized and lowered not in seen:
            seen.add(lowered)
            terms.append(normalized)

    add_term(cleaned)
    lowered = cleaned.lower()
    alias_terms = _TOPIC_ALIASES.get(lowered)
    if alias_terms:
        for alias in alias_terms:
            add_term(alias)

    for token in re.findall(r"[A-Za-z0-9-]+", cleaned):
        add_term(token)
        if len(token) > 3 and token.lower().endswith("s"):
            add_term(token[:-1])
        elif len(token) > 3 and not token.lower().endswith("s"):
            add_term(f"{token}s")

    if " " in cleaned:
        compact = cleaned.replace(" ", "")
        if compact:
            add_term(compact)

    return terms[:8]


def build_strict_match_terms(query: str) -> list[str]:
    """Return high-confidence literal variants that must appear in matching issues."""
    cleaned = re.sub(r"\s+", " ", (query or "").strip())
    if not cleaned:
        return []

    if _JIRA_KEY_PATTERN.fullmatch(cleaned):
        return [cleaned.upper()]

    terms: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        normalized = re.sub(r"\s+", " ", (value or "").strip())
        lowered = normalized.lower()
        if normalized and lowered not in seen:
            seen.add(lowered)
            terms.append(normalized)

    add_term(cleaned)
    for alias in _TOPIC_ALIASES.get(cleaned.lower(), []):
        add_term(alias)

    if " " in cleaned:
        compact = cleaned.replace(" ", "")
        if compact:
            add_term(compact)
        if len(cleaned) > 4 and cleaned.lower().endswith("s"):
            add_term(cleaned[:-1])
    else:
        if len(cleaned) > 3 and cleaned.lower().endswith("s"):
            add_term(cleaned[:-1])
        elif len(cleaned) > 3 and not cleaned.lower().endswith("s"):
            add_term(f"{cleaned}s")

    return terms[:8]


def _escape_jql_term(term: str) -> str:
    return str(term or "").replace("\\", "\\\\").replace('"', '\\"')


def _build_live_jql(terms: list[str]) -> str:
    clauses: list[str] = []
    for term in terms[:6]:
        escaped = _escape_jql_term(term)
        if not escaped:
            continue
        clauses.append(f'(summary ~ "\\"{escaped}\\"" OR description ~ "\\"{escaped}\\"")')
    if not clauses:
        return ""
    return " OR ".join(clauses) + " ORDER BY updated DESC"


def _build_live_jql_variants(query: str, terms: list[str]) -> list[str]:
    variants: list[str] = []
    combined = _build_live_jql(terms)
    if combined:
        variants.append(combined)

    escaped_query = _escape_jql_term(query)
    if escaped_query:
        variants.append(f'text ~ "\\"{escaped_query}\\"" ORDER BY updated DESC')

    escaped_terms = [_escape_jql_term(term) for term in terms[:4] if _escape_jql_term(term)]
    if escaped_terms:
        simple_terms = " OR ".join(f'text ~ "\\"{term}\\""' for term in escaped_terms)
        variants.append(simple_terms + " ORDER BY updated DESC")

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if variant and variant not in seen:
            deduped.append(variant)
            seen.add(variant)
    return deduped


def _build_issue_url(base_url: str, issue_key: str) -> str:
    if not base_url or not issue_key:
        return ""
    return f"{base_url.rstrip('/')}/browse/{issue_key}"


def _normalize_issue(issue: dict[str, Any], *, base_url: str, source: str) -> dict[str, Any]:
    issue_key = str(issue.get("issue_key") or issue.get("key") or "").strip()
    summary = str(issue.get("summary") or "").strip()
    description = str(issue.get("description") or "").strip()
    status = str(issue.get("status") or "").strip()
    issue_type = str(issue.get("issue_type") or "").strip()
    priority = str(issue.get("priority") or "").strip()
    updated_at = issue.get("updated") or issue.get("updated_at")

    payload: dict[str, Any] = {
        "issue_key": issue_key,
        "summary": summary,
        "description": description[:500] if description else "",
        "status": status,
        "issue_type": issue_type,
        "priority": priority,
        "updated_at": str(updated_at) if updated_at else None,
        "url": _build_issue_url(base_url, issue_key),
        "source": source,
    }
    score = issue.get("score")
    if score is not None:
        payload["score"] = score
    return payload


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for issue in issues:
        issue_key = str(issue.get("issue_key") or "").strip()
        if not issue_key or issue_key in seen:
            continue
        deduped.append(issue)
        seen.add(issue_key)
    return deduped


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _term_matches_text(text: str, term: str) -> bool:
    normalized_text = _normalize_search_text(text)
    normalized_term = _normalize_search_text(term)
    if not normalized_text or not normalized_term:
        return False

    if _JIRA_KEY_PATTERN.fullmatch(normalized_term.upper()):
        return bool(re.search(rf"\b{re.escape(normalized_term.upper())}\b", text.upper()))

    pattern = re.escape(normalized_term)
    if " " in normalized_term:
        pattern = pattern.replace(r"\ ", r"\s+")
    regex = rf"(?<![\w-]){pattern}(?![\w-])"
    return bool(re.search(regex, normalized_text, re.IGNORECASE))


def _issue_match_score(issue: dict[str, Any], strict_terms: list[str]) -> int:
    if not strict_terms:
        return 0

    issue_key = str(issue.get("issue_key") or "").strip()
    summary = str(issue.get("summary") or "")
    description = str(issue.get("description") or "")
    comments_value = issue.get("comments")
    if isinstance(comments_value, list):
        comments = " ".join(
            str(item.get("body_text") or item.get("body") or "")
            for item in comments_value
            if isinstance(item, dict)
        )
    else:
        comments = str(comments_value or "")

    score = 0
    for term in strict_terms:
        upper_term = term.upper()
        if issue_key and _JIRA_KEY_PATTERN.fullmatch(upper_term) and issue_key.upper() == upper_term:
            score += 100
        if _term_matches_text(summary, term):
            score += 25
        if _term_matches_text(description, term):
            score += 10
        if _term_matches_text(comments, term):
            score += 5
    return score


def _filter_issues_for_query(issues: list[dict[str, Any]], strict_terms: list[str]) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, issue in enumerate(issues):
        score = _issue_match_score(issue, strict_terms)
        if score > 0:
            next_issue = dict(issue)
            next_issue["match_score"] = score
            scored.append((score, index, next_issue))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [issue for _, _, issue in scored]


def _search_live_jira(
    query: str,
    terms: list[str],
    *,
    client: JiraClient,
    strict_terms: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if not client.base_url or not has_auth:
        return []

    for jql in _build_live_jql_variants(query, terms or [query]):
        live_results = fetch_jira_issues(
            jql,
            max_results=max_results,
            jira_client=client,
            fetch_comments=False,
        )
        normalized = [
            _normalize_issue(issue, base_url=client.base_url, source="jira_api")
            for issue in live_results
        ]
        filtered = _filter_issues_for_query(normalized, strict_terms)
        if filtered:
            return filtered
    return []


def _score_indexed_issue(issue: JiraIssue, terms: list[str]) -> float:
    summary = (issue.summary or "").lower()
    description = (issue.description or "").lower()
    searchable = (issue.text_for_search or "").lower()
    comments = (issue.comments_json or "").lower()

    score = 0.0
    for term in terms:
        lowered = term.lower()
        if not lowered:
            continue
        if lowered in summary:
            score += 6.0 if " " in lowered else 4.0
        if lowered in description:
            score += 3.0 if " " in lowered else 2.0
        if lowered in searchable:
            score += 2.0 if " " in lowered else 1.5
        if lowered in comments:
            score += 1.0
    return score


def _search_indexed_jira(
    query: str,
    terms: list[str],
    *,
    session: Session,
    base_url: str,
    strict_terms: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    similarity_query = " ".join(terms) if terms else query
    try:
        similar = find_similar_issues(
            session,
            query_text=similarity_query,
            k=max_results,
            include_attachment_text=True,
        )
    except Exception as exc:
        logger.warning_structured(
            "Indexed Jira similarity search failed",
            extra_fields={"query": query[:120], "error": str(exc)},
        )
        similar = []

    normalized = [
        _normalize_issue(issue, base_url=base_url, source="jira_index")
        for issue in similar
    ]
    filtered_similarity = _filter_issues_for_query(normalized, strict_terms)
    if filtered_similarity:
        return filtered_similarity[:max_results]

    issues = session.query(JiraIssue).filter(JiraIssue.text_for_search.isnot(None)).all()
    scored: list[tuple[float, JiraIssue]] = []
    for issue in issues:
        score = _score_indexed_issue(issue, terms)
        if score > 0:
            scored.append((score, issue))
    scored.sort(key=lambda item: (-item[0], str(item[1].updated_at or "")), reverse=False)

    fallback_results: list[dict[str, Any]] = []
    for score, issue in scored[:max_results]:
        fallback_results.append(
            {
                "issue_key": issue.issue_key,
                "summary": issue.summary or "",
                "description": (issue.description or "")[:500],
                "status": issue.status or "",
                "issue_type": issue.issue_type or "",
                "priority": issue.priority or "",
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                "url": _build_issue_url(base_url, issue.issue_key),
                "source": "jira_index",
                "score": round(score, 2),
            }
        )
    return _filter_issues_for_query(fallback_results, strict_terms)[:max_results]


def search_related_jira_issues(
    user_text: str,
    *,
    tenant_id: str,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search real Jira issues or indexed Jira cache from a natural-language chat request."""
    query = extract_jira_search_query(user_text)
    if not query:
        return {
            "query": "",
            "issues": [],
            "source": "unavailable",
            "message": "I couldn't determine which Jira topic to search for. Please mention the feature, term, or issue key.",
        }

    terms = expand_jira_search_terms(query)
    strict_terms = build_strict_match_terms(query)
    client = build_jira_client(tenant_id)
    live_results = _search_live_jira(
        query,
        terms,
        client=client,
        strict_terms=strict_terms,
        max_results=max_results,
    )
    issues = _dedupe_issues(_filter_issues_for_query(live_results, strict_terms))
    if issues:
        return {
            "query": query,
            "search_terms": terms,
            "strict_match_terms": strict_terms,
            "issues": issues[:max_results],
            "source": "jira_api",
            "message": f"Found {len(issues[:max_results])} matching Jira issue(s) from live Jira search.",
        }

    db = SessionLocal()
    try:
        indexed_results = _search_indexed_jira(
            query,
            terms,
            session=db,
            base_url=client.base_url or "",
            strict_terms=strict_terms,
            max_results=max_results,
        )
    finally:
        db.close()

    issues = _dedupe_issues(_filter_issues_for_query(indexed_results, strict_terms))
    if issues:
        return {
            "query": query,
            "search_terms": terms,
            "strict_match_terms": strict_terms,
            "issues": issues[:max_results],
            "source": "jira_index",
            "message": f"Found {len(issues[:max_results])} matching Jira issue(s) from the indexed Jira cache.",
        }

    has_auth = (client.username and client.password) or (client.email and client.api_token)
    if client.base_url and has_auth:
        message = f"No matching Jira issues were found for `{query}`."
        source = "jira_api"
    else:
        message = (
            f"Jira search is not configured for this tenant, and I couldn't find indexed Jira issues for `{query}`."
        )
        source = "unavailable"

    return {
        "query": query,
        "search_terms": terms,
        "strict_match_terms": strict_terms,
        "issues": [],
        "source": source,
        "message": message,
    }
