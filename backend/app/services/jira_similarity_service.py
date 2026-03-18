"""Jira similarity service - embedding or lexical search over indexed issues.

Uses embedding similarity when USE_JIRA_EMBEDDING=true and model loads.
Falls back to lexical matching with component boost and minimum score threshold.
"""
import json
import os
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.db.jira_models import JiraIssue, JiraAttachment
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

USE_JIRA_EMBEDDING = os.getenv("USE_JIRA_EMBEDDING", "true").lower() in ("true", "1", "yes")
MIN_LEXICAL_SCORE = float(os.getenv("AI_SIMILAR_ISSUES_MIN_SCORE", "4.0"))
COMPONENT_BOOST = float(os.getenv("AI_SIMILAR_ISSUES_COMPONENT_BOOST", "3.0"))

DITA_BOOST_TERMS = {
    "conref": 2.0,
    "keyref": 2.0,
    "ditamap": 1.5,
    "ditaval": 1.5,
    "dita": 1.2,
    "topicref": 1.5,
    "keydef": 1.5,
    "keyscope": 1.5,
}


def _parse_components(components_json: Optional[str]) -> set[str]:
    """Parse components from JSON string to set of lowercase names."""
    if not components_json or not components_json.strip():
        return set()
    try:
        data = json.loads(components_json)
        if isinstance(data, list):
            return {str(c).lower().strip() for c in data if c}
        return set()
    except (json.JSONDecodeError, TypeError):
        return set()


def _tokenize(text: str) -> list[str]:
    """Extract searchable tokens from text."""
    if not text or not isinstance(text, str):
        return []
    text = re.sub(r"[^\w\s-]", " ", text.lower())
    tokens = [t for t in text.split() if len(t) >= 2]
    return list(set(tokens))


def _issue_to_result(issue: JiraIssue, score: float) -> dict:
    """Build result dict from JiraIssue."""
    return {
        "issue_key": issue.issue_key,
        "summary": issue.summary,
        "description": (issue.description or "")[:500],
        "issue_type": issue.issue_type,
        "status": issue.status,
        "priority": issue.priority,
        "components_json": issue.components_json,
        "labels_json": issue.labels_json,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "score": round(score, 2),
    }


def _find_similar_embedding(
    session: Session,
    query_text: str,
    k: int,
    filters: Optional[dict],
    exclude_issue_key: Optional[str],
    primary_components: Optional[set[str]],
) -> Optional[list[dict]]:
    """Find similar issues using embedding similarity.
    Uses pre-indexed embedding_json when available; otherwise embeds all issues on-the-fly.
    Returns None on failure."""
    try:
        from app.services.embedding_service import embed_query, embed_texts, is_embedding_available
        import numpy as np
    except ImportError:
        return None
    if not is_embedding_available():
        return None

    query = session.query(JiraIssue).filter(JiraIssue.text_for_search.isnot(None))
    if exclude_issue_key:
        query = query.filter(JiraIssue.issue_key != exclude_issue_key)
    if filters and filters.get("project"):
        prefix = str(filters["project"]).upper()
        query = query.filter(JiraIssue.issue_key.like(f"{prefix}-%"))

    issues = query.all()
    if not issues:
        return []

    q_vec = embed_query(query_text)
    if q_vec is None:
        return None

    # Prefer pre-indexed embeddings when all issues have them
    use_preindexed = all(getattr(i, "embedding_json", None) for i in issues)
    if use_preindexed:
        i_vecs = []
        valid_issues = []
        for i in issues:
            try:
                emb = json.loads(i.embedding_json)
                i_vecs.append(emb)
                valid_issues.append(i)
            except (json.JSONDecodeError, TypeError):
                pass
        if valid_issues and len(i_vecs) == len(valid_issues):
            i_vecs = np.array(i_vecs, dtype=np.float32)
            q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-9)
            scores = np.dot(i_vecs, q_norm)
            if primary_components:
                for idx, issue in enumerate(valid_issues):
                    comps = _parse_components(issue.components_json)
                    if comps & primary_components:
                        scores[idx] += COMPONENT_BOOST
            indexed = list(zip(scores, valid_issues))
            indexed.sort(key=lambda x: -x[0])
            return [_issue_to_result(issue, float(score)) for score, issue in indexed[:k]]

    # Fallback: embed all issues on-the-fly
    texts = [i.text_for_search or i.summary or "" for i in issues]
    i_vecs = embed_texts(texts)
    if i_vecs is None:
        return None

    q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-9)
    scores = np.dot(i_vecs, q_norm)

    if primary_components:
        for idx, issue in enumerate(issues):
            comps = _parse_components(issue.components_json)
            if comps & primary_components:
                scores[idx] += COMPONENT_BOOST

    indexed = list(zip(scores, issues))
    indexed.sort(key=lambda x: -x[0])
    return [_issue_to_result(issue, float(score)) for score, issue in indexed[:k]]


def find_similar_issues(
    session: Session,
    query_text: str,
    k: int = 5,
    filters: Optional[dict] = None,
    exclude_issue_key: Optional[str] = None,
    include_attachment_text: bool = True,
    primary_components_json: Optional[str] = None,
) -> list[dict]:
    """
    Find similar issues using embedding (when available) or lexical matching.
    Applies component boost and minimum score threshold for relevance.
    """
    if not query_text or not query_text.strip():
        return []

    primary_components = _parse_components(primary_components_json) if primary_components_json else None

    if USE_JIRA_EMBEDDING:
        results = _find_similar_embedding(
            session, query_text, k, filters, exclude_issue_key, primary_components
        )
        if results is not None:
            return results
        logger.debug("Jira embedding unavailable, using lexical fallback")

    tokens = _tokenize(query_text)
    if not tokens:
        return []

    query = session.query(JiraIssue).filter(JiraIssue.text_for_search.isnot(None))
    if exclude_issue_key:
        query = query.filter(JiraIssue.issue_key != exclude_issue_key)

    if filters and filters.get("project"):
        prefix = str(filters["project"]).upper()
        query = query.filter(JiraIssue.issue_key.like(f"{prefix}-%"))

    all_issues = query.all()
    att_by_issue = {}
    if include_attachment_text and all_issues:
        issue_keys = [i.issue_key for i in all_issues]
        for a in session.query(JiraAttachment).filter(
            JiraAttachment.issue_key.in_(issue_keys),
            JiraAttachment.text_search_blob.isnot(None),
        ).all():
            att_by_issue.setdefault(a.issue_key, []).append(a.text_search_blob or "")

    scored = []
    for issue in all_issues:
        text = (issue.text_for_search or "").lower()
        if include_attachment_text:
            blobs = att_by_issue.get(issue.issue_key, [])
            text += " " + " ".join(blobs).lower()
        score = 0.0
        for token in tokens:
            if token in text:
                score += 1.0
                if token in DITA_BOOST_TERMS:
                    score += DITA_BOOST_TERMS[token] - 1.0
        if primary_components:
            comps = _parse_components(issue.components_json)
            if comps & primary_components:
                score += COMPONENT_BOOST
        if score >= MIN_LEXICAL_SCORE:
            scored.append((score, issue))

    scored.sort(key=lambda x: -x[0])
    return [_issue_to_result(issue, score) for score, issue in scored[:k]]
