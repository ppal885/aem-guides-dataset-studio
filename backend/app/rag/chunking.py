"""Semantic chunking helpers for Jira issue records."""

from __future__ import annotations

from typing import Any


SEMANTIC_JIRA_SECTIONS = (
    "summary",
    "root_cause",
    "comments_summary",
    "qa_notes",
    "automation_notes",
    "resolution",
    "linked_issue_patterns",
)


def semantic_jira_chunks(issue: dict[str, Any]) -> list[dict[str, Any]]:
    """Chunk a normalized Jira dict by semantic section rather than fixed windows."""

    chunks: list[dict[str, Any]] = []
    issue_key = str(issue.get("issue_key") or issue.get("key") or "").strip()
    for section in SEMANTIC_JIRA_SECTIONS:
        text = str(issue.get(section) or "").strip()
        if not text:
            continue
        chunks.append(
            {
                "issue_key": issue_key,
                "chunk_type": section,
                "document": text,
                "metadata": {"jira_key": issue_key, "chunk_type": section},
            }
        )
    return chunks

