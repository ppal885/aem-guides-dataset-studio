"""Jira retrieval and pattern-analysis tools for QA copilot."""

from __future__ import annotations

from typing import Any

from app.models.jira_models import JiraIssueDetails, JiraIssueSearchResult
from app.services.retrieval_service import QaCopilotRetrievalService


async def search_jira_issues(
    customer: str | None,
    feature: str | None,
    issue_type: str | None = None,
    environment: str | None = None,
    editor_type: str | None = None,
    output_type: str | None = None,
    time_window_days: int | None = None,
    source_jira_key: str | None = None,
    escalation_only: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    service = QaCopilotRetrievalService()
    issues, retrieval = service.search_jira_issues(
        customer=customer,
        feature=feature,
        issue_type=issue_type,
        environment=environment,
        editor_type=editor_type,
        output_type=output_type,
        time_window_days=time_window_days,
        source_jira_key=source_jira_key,
        escalation_only=escalation_only,
        limit=limit,
    )
    return {
        "issues": [issue.model_dump() for issue in issues],
        "semantic_fallback_used": retrieval.semantic_fallback_used,
        "metadata_filter_used": retrieval.metadata_filter_used,
        "debug": retrieval.debug,
    }


async def get_related_issue_details(issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    service = QaCopilotRetrievalService()
    parsed = [JiraIssueSearchResult.model_validate(item) for item in (issues or [])]
    details = service.get_related_issue_details(parsed)
    return {"issue_details": [detail.model_dump() for detail in details]}


async def detect_common_patterns(issue_details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    service = QaCopilotRetrievalService()
    parsed = [JiraIssueDetails.model_validate(item) for item in (issue_details or [])]
    patterns = service.detect_common_patterns(parsed)
    return {"patterns": [pattern.model_dump() for pattern in patterns]}
