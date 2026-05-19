"""Public smart Jira chunking facade for QA/UAC RAG indexing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_chunking_service import (  # noqa: F401
    SMART_JIRA_CHUNK_TYPES,
    build_comments_digest,
    build_smart_chroma_chunks,
    create_jira_chunks,
    smart_chunks_to_chroma_rows,
)


@dataclass(slots=True)
class JiraSmartChunkingService:
    """Build semantic Jira chunks before embedding."""

    def create_chunks(self, enriched_doc: JiraEnrichedDocument) -> list[dict[str, Any]]:
        return create_jira_chunks(enriched_doc)

    def create_chroma_rows(
        self,
        issue_key: str,
        issue_dict: dict[str, Any],
        enriched_doc: JiraEnrichedDocument,
        comments: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        return build_smart_chroma_chunks(
            issue_key,
            issue_dict,
            enriched=enriched_doc,
            comments=comments or [],
        )


__all__ = [
    "SMART_JIRA_CHUNK_TYPES",
    "JiraSmartChunkingService",
    "build_comments_digest",
    "build_smart_chroma_chunks",
    "create_jira_chunks",
    "smart_chunks_to_chroma_rows",
]
