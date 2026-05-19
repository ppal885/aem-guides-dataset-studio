"""Hybrid search pipeline for customer-aware historical Jira retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.metadata_filtering import JiraMetadataCriteria, matches_metadata
from app.rag.reranker import EnterpriseQaReranker
from app.rag.semantic_search import SemanticJiraSearch


@dataclass
class HybridSearchOutput:
    hits: list[dict[str, Any]]
    semantic_fallback_used: bool
    metadata_filter_used: bool
    debug: dict[str, Any] = field(default_factory=dict)


class HybridJiraSearch:
    """Metadata-aware semantic retrieval with relaxed semantic fallback."""

    def __init__(
        self,
        semantic_search: SemanticJiraSearch | None = None,
        reranker: EnterpriseQaReranker | None = None,
    ) -> None:
        self.semantic_search = semantic_search or SemanticJiraSearch()
        self.reranker = reranker or EnterpriseQaReranker()

    def search(self, criteria: JiraMetadataCriteria, *, limit: int = 10) -> HybridSearchOutput:
        query = criteria.query_text() or "AEM Guides Jira QA issue"
        expanded_k = max(limit * 4, 20)
        candidates = self.semantic_search.search(query, criteria, top_k=expanded_k)
        strict = [
            hit
            for hit in candidates
            if matches_metadata(criteria, hit.get("metadata") or {}, str(hit.get("document") or ""))
        ]
        fallback_used = False
        selected = strict
        fallback_reason = ""
        if not selected and candidates:
            fallback_used = True
            fallback_reason = "metadata_filter_returned_zero_candidates"
            relaxed = JiraMetadataCriteria(
                customer=None,
                feature=criteria.feature,
                issue_type=criteria.issue_type,
                environment=criteria.environment,
                editor_type=criteria.editor_type,
                output_type=criteria.output_type,
                time_window_days=criteria.time_window_days,
                source_jira_key=criteria.source_jira_key,
                escalation_only=criteria.escalation_only,
            )
            selected = [
                hit
                for hit in candidates
                if matches_metadata(relaxed, hit.get("metadata") or {}, str(hit.get("document") or ""))
            ] or candidates
        if not selected and not candidates:
            fallback_reason = "no_semantic_candidates"

        ranked = self.reranker.rerank(selected, criteria)[:limit]
        return HybridSearchOutput(
            hits=ranked,
            semantic_fallback_used=fallback_used,
            metadata_filter_used=True,
            debug={
                "query": query,
                "candidate_count": len(candidates),
                "strict_metadata_count": len(strict),
                "selected_count": len(ranked),
                "fallback_reason": fallback_reason,
            },
        )
