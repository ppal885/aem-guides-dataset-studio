"""Public Jira enrichment pipeline facade for QA/UAC intelligence.

The implementation delegates to ``app.services.jira_enrichment_service`` so the
API, indexer, tests, and scripts share one taxonomy-backed enrichment path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_enrichment_service import (  # noqa: F401
    CUSTOMER_LABEL_EXCLUDE_PATTERNS,
    classify_domain,
    detect_customers,
    detect_customers_dynamic,
    detect_customers_dynamic_with_debug,
    enrich_jira,
    enrichment_embed_prefix,
    enrichment_metadata_json,
    extract_dita_entities,
    extract_expected_actual,
)


@dataclass(slots=True)
class JiraEnrichmentPipeline:
    """Structured enrichment facade used by indexing, evals, and offline jobs."""

    def enrich_issue(self, jira_issue: dict[str, Any]) -> JiraEnrichedDocument:
        return enrich_jira(jira_issue)

    def enrich_many(self, jira_issues: Iterable[dict[str, Any]]) -> list[JiraEnrichedDocument]:
        return [self.enrich_issue(issue) for issue in jira_issues]

    def metadata_for_embedding(self, enriched: JiraEnrichedDocument) -> dict[str, str]:
        return {
            "embed_prefix": enrichment_embed_prefix(enriched),
            "enrichment_json": enrichment_metadata_json(enriched),
        }


__all__ = [
    "CUSTOMER_LABEL_EXCLUDE_PATTERNS",
    "JiraEnrichmentPipeline",
    "classify_domain",
    "detect_customers",
    "detect_customers_dynamic",
    "detect_customers_dynamic_with_debug",
    "enrich_jira",
    "enrichment_embed_prefix",
    "enrichment_metadata_json",
    "extract_dita_entities",
    "extract_expected_actual",
]
