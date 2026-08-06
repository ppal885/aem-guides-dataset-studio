"""Repair missing Jira Chroma documents from authoritative SQL rows."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from app.db.session import SessionLocal
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    get_collection_records,
    is_chroma_available,
)


def _json_metadata(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)[:4000]
    return "[]"


def _metadata(issue: JiraEnrichedIssue, chunk_type: str) -> dict[str, str]:
    return {
        "source_type": str(issue.source_type or "jira"),
        "jira_key": issue.jira_key,
        "title": str(issue.summary or "")[:500],
        "chunk_type": chunk_type[:80],
        "status": str(issue.status or "")[:120],
        "resolution": str(issue.resolution or "")[:120],
        "enrich_domain": str(issue.domain or "unknown")[:120],
        "components": _json_metadata(issue.components),
        "affected_outputs": _json_metadata(issue.affected_outputs),
        "dita_entities": _json_metadata(issue.dita_entities),
        "qa_risk_tags": _json_metadata(issue.qa_risk_tags),
    }


def _fallback_chunks(issue: JiraEnrichedIssue) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    summary = str(issue.summary or "").strip()
    description = str(issue.description or issue.raw_text or "").strip()
    if summary:
        chunks.append(("summary_chunk", f"Jira {issue.jira_key}: {summary}"))
    if description:
        chunks.append(("problem_chunk", description))
    domain = str(issue.domain or "unknown").strip()
    if domain or issue.affected_features or issue.dita_entities:
        chunks.append(
            (
                "domain_entity_chunk",
                "\n".join(
                    [
                        f"Jira: {issue.jira_key}",
                        f"Domain: {domain or 'unknown'}",
                        f"Affected features: {', '.join(map(str, issue.affected_features or [])) or 'not captured'}",
                        f"DITA entities: {', '.join(map(str, issue.dita_entities or [])) or 'not captured'}",
                    ]
                ),
            )
        )
    return chunks or [("summary_chunk", f"Jira issue {issue.jira_key}")]


def build_reconciliation_rows(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> list[dict[str, Any]]:
    """Build deterministic Chroma rows from SQL chunks or safe issue fallbacks."""
    grouped_indexes: dict[str, int] = defaultdict(int)
    source = [(chunk.chunk_type, chunk.chunk_text) for chunk in chunks]
    if not source:
        source = _fallback_chunks(issue)
    rows: list[dict[str, Any]] = []
    for chunk_type, document in source:
        normalized_type = str(chunk_type or "unknown")[:80]
        index = grouped_indexes[normalized_type]
        grouped_indexes[normalized_type] += 1
        text = str(document or "").strip()
        if not text:
            continue
        rows.append(
            {
                "chunk_id": f"{issue.jira_key}::{normalized_type}::{index}",
                "document": text,
                "metadata": _metadata(issue, normalized_type),
            }
        )
    return rows


def _chroma_jira_keys() -> set[str]:
    keys: set[str] = set()
    for record in get_collection_records(CHROMA_COLLECTION_JIRA_QA):
        metadata = record.get("metadata") or {}
        key = metadata.get("jira_key") or metadata.get("issue_key") or metadata.get("key")
        if key:
            keys.add(str(key))
    return keys


def reconcile_jira_sql_chroma(*, dry_run: bool = True, limit: int = 10_000) -> dict[str, Any]:
    """Upsert SQL Jira keys absent from Chroma without deleting Chroma-only records."""
    if not is_chroma_available():
        return {"error": "ChromaDB is not available"}
    if not dry_run and not is_embedding_available():
        return {"error": "Embedding model is not available"}

    chroma_keys_before = _chroma_jira_keys()
    db = SessionLocal()
    try:
        issues = db.query(JiraEnrichedIssue).order_by(JiraEnrichedIssue.jira_key).all()
        sql_keys = {issue.jira_key for issue in issues}
        missing_keys = sorted(sql_keys - chroma_keys_before)[: max(1, min(limit, 100_000))]
        missing_issues = [issue for issue in issues if issue.jira_key in set(missing_keys)]
        chunk_rows = (
            db.query(JiraIssueChunk)
            .filter(JiraIssueChunk.jira_key.in_(missing_keys))
            .order_by(JiraIssueChunk.jira_key, JiraIssueChunk.id)
            .all()
            if missing_keys
            else []
        )
        grouped: dict[str, list[JiraIssueChunk]] = defaultdict(list)
        for chunk in chunk_rows:
            grouped[chunk.jira_key].append(chunk)
        rows = [
            row
            for issue in missing_issues
            for row in build_reconciliation_rows(issue, grouped.get(issue.jira_key, []))
        ]
        fallback_keys = [issue.jira_key for issue in missing_issues if not grouped.get(issue.jira_key)]
    finally:
        db.close()

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "sql_unique_keys": len(sql_keys),
        "chroma_unique_keys_before": len(chroma_keys_before),
        "missing_keys_before": len(sql_keys - chroma_keys_before),
        "selected_missing_keys": len(missing_keys),
        "candidate_chunks": len(rows),
        "fallback_issue_count": len(fallback_keys),
        "fallback_keys": fallback_keys,
        "chroma_only_keys_untouched": len(chroma_keys_before - sql_keys),
        "failed_batches": [],
    }
    if dry_run or not rows:
        report["indexed_chunks"] = 0
        report["remaining_missing_keys"] = len(sql_keys - chroma_keys_before)
        return report

    indexed = 0
    for start in range(0, len(rows), 48):
        batch = rows[start : start + 48]
        embeddings = embed_texts_batched([row["document"] for row in batch], batch_size=48)
        if embeddings is None:
            report["failed_batches"].append({"start": start, "reason": "embedding failed"})
            continue
        success = False
        for attempt in range(1, 4):
            success = add_documents(
                CHROMA_COLLECTION_JIRA_QA,
                [row["chunk_id"] for row in batch],
                [row["document"] for row in batch],
                [row["metadata"] for row in batch],
                [embeddings[index].tolist() for index in range(len(batch))],
            )
            if success:
                break
            if attempt < 3:
                time.sleep(0.5 * attempt)
        if success:
            indexed += len(batch)
        else:
            report["failed_batches"].append({"start": start, "reason": "Chroma upsert failed"})

    chroma_keys_after = _chroma_jira_keys()
    report.update(
        {
            "indexed_chunks": indexed,
            "chroma_unique_keys_after": len(chroma_keys_after),
            "remaining_missing_keys": len(sql_keys - chroma_keys_after),
            "remaining_missing_key_sample": sorted(sql_keys - chroma_keys_after)[:20],
        }
    )
    return report
