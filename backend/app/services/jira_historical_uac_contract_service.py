"""Batch reconstruction of deterministic historical UAC contracts from SQL."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from app.core.logging_config import get_logger
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.session import SessionLocal
from app.services.jira_uac_analysis_service import historical_uac_contract_dict
from app.services.jira_uac_backfill_service import analyze_sql_uac_issue


logger = get_logger(__name__)

_CONTRACT_SOURCE_CHUNK_TYPES = {
    "acceptance_criteria_chunk",
    "resolution_rca_chunk",
    "test_evidence_chunk",
    "comment_chunk",
}


def load_historical_uac_contracts(
    jira_keys: list[str] | tuple[str, ...] | set[str],
    *,
    session_factory: Callable[[], Any] = SessionLocal,
) -> dict[str, dict[str, Any]]:
    """Load complete contracts in two bounded SQL queries, one per source table."""
    keys = sorted({str(key or "").strip().upper() for key in jira_keys if str(key or "").strip()})
    if not keys:
        return {}

    session = session_factory()
    try:
        issues = (
            session.query(JiraEnrichedIssue)
            .filter(JiraEnrichedIssue.jira_key.in_(keys))
            .order_by(JiraEnrichedIssue.jira_key)
            .all()
        )
        chunks = (
            session.query(JiraIssueChunk)
            .filter(
                JiraIssueChunk.jira_key.in_(keys),
                JiraIssueChunk.chunk_type.in_(_CONTRACT_SOURCE_CHUNK_TYPES),
            )
            .order_by(JiraIssueChunk.jira_key, JiraIssueChunk.id)
            .all()
        )
        chunks_by_key: dict[str, list[JiraIssueChunk]] = defaultdict(list)
        for chunk in chunks:
            chunks_by_key[str(chunk.jira_key or "").upper()].append(chunk)

        contracts: dict[str, dict[str, Any]] = {}
        for issue in issues:
            key = str(issue.jira_key or "").upper()
            analyzed = analyze_sql_uac_issue(issue, chunks_by_key.get(key, []))
            if analyzed is None:
                continue
            analysis, acceptance_criteria, root_cause, test_evidence = analyzed
            contract = historical_uac_contract_dict(
                analysis,
                acceptance_criteria=acceptance_criteria,
                root_cause=root_cause,
                test_evidence=test_evidence,
            )
            contract["source_freshness"] = {
                "jira_updated_at": issue.jira_updated_at.isoformat() if issue.jira_updated_at else "",
                "indexed_at": issue.indexed_at.isoformat() if issue.indexed_at else "",
                "mutable_fields_verified_live": False,
                "status": "historical_snapshot",
            }
            contracts[key] = contract
        return contracts
    except Exception as exc:  # noqa: BLE001 - retrieval must degrade without hiding the reason
        logger.warning("Historical UAC contract reconstruction unavailable: %s", exc)
        return {}
    finally:
        session.close()
