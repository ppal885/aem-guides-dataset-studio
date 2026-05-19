"""Semantic search adapter over the existing Jira QA Chroma retrieval service."""

from __future__ import annotations

from typing import Any

from app.rag.metadata_filtering import JiraMetadataCriteria
from app.services.jira_qa_retrieval_service import semantic_search_jira_qa


class SemanticJiraSearch:
    """Thin adapter so the copilot can swap vector backends later."""

    def search(self, query: str, criteria: JiraMetadataCriteria, *, top_k: int) -> list[dict[str, Any]]:
        customer_names = [criteria.customer] if criteria.customer else []
        affected_outputs = [criteria.output_type] if criteria.output_type else []
        dita_entities = [criteria.feature] if criteria.feature else []
        return semantic_search_jira_qa(
            query,
            top_k=top_k,
            customer=criteria.customer,
            domain=criteria.feature,
            dita_entities=dita_entities,
            affected_outputs=affected_outputs,
            customer_names=[x for x in customer_names if x],
        )

