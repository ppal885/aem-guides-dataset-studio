"""Structured Jira Intelligence Engine for QA/UAC workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira, retrieve_similar_jiras, retrieve_similar_jiras_debug
from services.uac_generation_service import generate_uac_recommendations


@dataclass(slots=True)
class JiraIntelligenceRequest:
    """Input contract for offline and API-facing Jira intelligence flows."""

    enriched_jira: JiraEnrichedDocument
    include_similar: bool = True
    max_similar: int = 8
    debug: bool = False
    exclude_jira_key: str | None = None


def build_retrieval_query(enriched: JiraEnrichedDocument) -> str:
    """High-signal retrieval text; avoids over-weighting boilerplate."""

    parts = [
        enriched.summary or "",
        (enriched.description or "")[:12000],
        " ".join(enriched.dita_entities or []),
        " ".join(enriched.affected_outputs or []),
        " ".join(enriched.components or []),
        " ".join(enriched.customer_names or []),
        " ".join(enriched.qa_risk_tags or []),
    ]
    return "\n\n".join(p for p in parts if str(p).strip())


class JiraIntelligenceEngine:
    """Orchestrates enrichment output, hybrid retrieval, and grounded UAC generation."""

    def retrieve_similar(self, request: JiraIntelligenceRequest) -> tuple[list[RetrievedJira], dict[str, Any]]:
        if not request.include_similar or request.max_similar <= 0:
            return [], {"note": "similar Jira retrieval skipped"}

        enriched = request.enriched_jira
        query = build_retrieval_query(enriched)
        common_kwargs = {
            "query_text": query,
            "domain": enriched.domain if enriched.domain != "unknown" else None,
            "sub_domain": enriched.sub_domain or None,
            "dita_entities": list(enriched.dita_entities or []),
            "affected_outputs": list(enriched.affected_outputs or []),
            "customer_names": list(enriched.customer_names or []),
            "issue_type": enriched.issue_type or None,
            "base_labels": list(enriched.labels or []),
            "base_components": list(enriched.components or []),
            "exclude_jira_key": request.exclude_jira_key or enriched.jira_key,
            "limit": max(1, min(request.max_similar, 24)),
        }
        if request.debug:
            payload = retrieve_similar_jiras_debug(**common_kwargs)
            rows = [RetrievedJira.model_validate(row) for row in payload.get("results") or []]
            return rows, dict(payload.get("debug") or {})

        rows = retrieve_similar_jiras(**common_kwargs)
        return rows, {
            "retrieval_query": {"text_preview": query[:3000], "char_length": len(query)},
            "result_count": len(rows),
        }

    def build_uac(self, request: JiraIntelligenceRequest) -> dict[str, Any]:
        similar, debug = self.retrieve_similar(request)
        structured = generate_uac_recommendations(
            request.enriched_jira,
            [row.model_dump() for row in similar],
            debug,
        )
        return {
            "classification": structured["classification"],
            "similar_jiras": structured["similar_jiras"],
            "structured_uac": structured,
            "retrieval_debug": debug,
        }


__all__ = [
    "JiraIntelligenceEngine",
    "JiraIntelligenceRequest",
    "build_retrieval_query",
]
