"""
Jira hybrid retrieval (metadata + keyword overlap + vector + rerank + diversity).

Implementation lives in ``app.services.jira_retrieval_service``; this module re-exports
so callers can use ``from services.jira_retrieval_service import ...`` when ``backend``
is the first entry on ``sys.path`` (see ``run_local.py``).
"""

from __future__ import annotations

from app.services.jira_retrieval_service import (  # noqa: F401
    RetrievedJira,
    explain_similarity,
    extract_hybrid_filters_from_issue_rows,
    retrieve_similar_jiras,
    retrieve_similar_jiras_debug,
    retrieved_to_legacy_hit,
)

__all__ = [
    "RetrievedJira",
    "explain_similarity",
    "extract_hybrid_filters_from_issue_rows",
    "retrieve_similar_jiras",
    "retrieve_similar_jiras_debug",
    "retrieved_to_legacy_hit",
]
