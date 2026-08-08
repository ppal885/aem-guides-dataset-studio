"""Conservative Jira domain backfill for SQL and Chroma metadata."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from app.services.jira_enrichment_service import classify_domain, infer_domain_from_components
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_count,
    get_collection_records,
    is_chroma_available,
    update_document_metadatas,
)


DOMAIN_SCHEMA_VERSION = "jira-domain-v2"


def _domain_token(value: Any) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item).strip() for item in decoded if str(item).strip()]


def infer_domain_for_issue_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Infer one domain from existing metadata, exact components, or strong taxonomy evidence."""
    known_domains: set[str] = set()
    components: list[str] = []
    labels: list[str] = []
    text_parts: list[str] = []
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        domain = _domain_token(metadata.get("enrich_domain") or metadata.get("domain"))
        if domain and domain != "unknown":
            known_domains.add(domain)
        components.extend(_json_list(metadata.get("components")))
        primary = str(metadata.get("component_primary") or "").strip()
        if primary:
            components.append(primary.replace("_", " "))
        labels.extend(_json_list(metadata.get("labels")))
        for field in ("enrich_entities", "smart_dita_entities", "enrich_outputs", "smart_affected_outputs"):
            text_parts.extend(_json_list(metadata.get(field)))
        title = str(metadata.get("title") or "").strip()
        document = str(record.get("document") or "").strip()
        if title:
            text_parts.append(title)
        if document:
            text_parts.append(document[:12000])

    if len(known_domains) > 1:
        return {
            "domain": "",
            "sub_domain": "",
            "method": "conflicting_existing_domains",
            "confidence": "blocked",
            "evidence": sorted(known_domains),
        }
    if known_domains:
        return {
            "domain": next(iter(known_domains)),
            "sub_domain": "",
            "method": "existing_issue_domain",
            "confidence": "high",
            "evidence": sorted(known_domains),
        }

    component_domain = infer_domain_from_components(list(dict.fromkeys(components)))
    if component_domain:
        return {
            "domain": component_domain,
            "sub_domain": "",
            "method": "jira_component",
            "confidence": "high",
            "evidence": list(dict.fromkeys(components))[:10],
        }

    classification = classify_domain("\n".join(text_parts)[:50000], list(dict.fromkeys(labels)))
    domain = _domain_token(classification.get("domain"))
    scores = classification.get("scores") if isinstance(classification.get("scores"), dict) else {}
    hits = classification.get("hits") if isinstance(classification.get("hits"), dict) else {}
    best_score = float(scores.get(domain) or 0.0)
    best_hits = list(dict.fromkeys(str(item) for item in (hits.get(domain) or []) if str(item).strip()))
    if domain and domain != "unknown" and (best_score >= 2.5 or len(best_hits) >= 2):
        return {
            "domain": domain,
            "sub_domain": _domain_token(classification.get("sub_domain")),
            "method": "strong_taxonomy_evidence",
            "confidence": "medium",
            "evidence": best_hits[:10],
            "score": round(best_score, 3),
        }
    return {
        "domain": "",
        "sub_domain": "",
        "method": "insufficient_evidence",
        "confidence": "unresolved",
        "evidence": best_hits[:10],
        "score": round(best_score, 3),
    }


def build_jira_domain_backfill_plan(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic issue-level plan and per-chunk metadata updates."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_key_chunks = 0
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        jira_key = str(metadata.get("jira_key") or "").strip().upper()
        if not jira_key:
            missing_key_chunks += 1
            continue
        grouped[jira_key].append(record)

    assignments: dict[str, dict[str, Any]] = {}
    method_counts: Counter[str] = Counter()
    pending: list[dict[str, Any]] = []
    unresolved: list[str] = []
    conflicts: list[str] = []
    for jira_key, issue_records in sorted(grouped.items()):
        inference = infer_domain_for_issue_records(issue_records)
        method_counts[str(inference["method"])] += 1
        domain = str(inference.get("domain") or "")
        if not domain:
            (conflicts if inference["method"] == "conflicting_existing_domains" else unresolved).append(jira_key)
            continue
        assignments[jira_key] = inference
        for record in issue_records:
            metadata = dict(record.get("metadata") or {})
            current = _domain_token(metadata.get("enrich_domain") or metadata.get("domain"))
            if current and current != "unknown":
                continue
            updated_metadata = dict(metadata)
            updated_metadata.update({
                "enrich_domain": domain,
                "domain_assignment_source": str(inference["method"]),
                "domain_ranking_policy": "soft_boost_only",
                "domain_schema_version": DOMAIN_SCHEMA_VERSION,
            })
            sub_domain = str(inference.get("sub_domain") or "")
            if sub_domain and not str(metadata.get("enrich_sub_domain") or "").strip():
                updated_metadata["enrich_sub_domain"] = sub_domain
            pending.append({
                "id": str(record.get("id") or ""),
                "jira_key": jira_key,
                "metadata": updated_metadata,
            })
    return {
        "unique_issue_count": len(grouped),
        "assignment_count": len(assignments),
        "assignments": assignments,
        "pending_chunk_updates": pending,
        "pending_chunk_update_count": len(pending),
        "unresolved_issue_count": len(unresolved),
        "unresolved_issue_sample": unresolved[:50],
        "conflicting_issue_count": len(conflicts),
        "conflicting_issue_sample": conflicts[:50],
        "chunks_missing_jira_key": missing_key_chunks,
        "method_distribution": dict(sorted(method_counts.items())),
    }


def _sync_assignments_to_sql(assignments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
    from app.db.session import SessionLocal

    issue_updates = 0
    chunk_updates = 0
    db = SessionLocal()
    try:
        for issue in db.query(JiraEnrichedIssue).all():
            assignment = assignments.get(str(issue.jira_key or "").upper())
            if not assignment or _domain_token(issue.domain) not in {"", "unknown"}:
                continue
            issue.domain = str(assignment["domain"])
            if not str(issue.sub_domain or "").strip() and assignment.get("sub_domain"):
                issue.sub_domain = str(assignment["sub_domain"])
            issue_updates += 1
        for chunk in db.query(JiraIssueChunk).all():
            assignment = assignments.get(str(chunk.jira_key or "").upper())
            if not assignment or _domain_token(chunk.domain) not in {"", "unknown"}:
                continue
            chunk.domain = str(assignment["domain"])
            chunk_updates += 1
        db.commit()
        return {"available": True, "issue_rows_updated": issue_updates, "chunk_rows_updated": chunk_updates}
    except Exception as exc:
        db.rollback()
        return {"available": False, "issue_rows_updated": 0, "chunk_rows_updated": 0, "error": str(exc)}
    finally:
        db.close()


def migrate_unknown_jira_domains(
    *, dry_run: bool = True, batch_size: int = 500, sync_sql: bool = True
) -> dict[str, Any]:
    """Backfill only unknown domains; never overwrite known or conflicting assignments."""
    if not is_chroma_available():
        return {"available": False, "dry_run": dry_run, "error": "ChromaDB is unavailable"}
    expected_count = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
    records = get_collection_records(CHROMA_COLLECTION_JIRA_QA, include_documents=True)
    if len(records) != expected_count:
        return {
            "available": False,
            "dry_run": dry_run,
            "collection_count": expected_count,
            "scanned_chunk_count": len(records),
            "error": "Partial Chroma scan; no domain metadata was changed.",
        }
    plan = build_jira_domain_backfill_plan(records)
    pending = [row for row in plan.pop("pending_chunk_updates") if row["id"]]
    updated = 0
    failed = 0
    if not dry_run:
        safe_batch_size = max(1, min(int(batch_size), 2000))
        for start in range(0, len(pending), safe_batch_size):
            batch = pending[start : start + safe_batch_size]
            if update_document_metadatas(
                CHROMA_COLLECTION_JIRA_QA,
                [row["id"] for row in batch],
                [row["metadata"] for row in batch],
            ):
                updated += len(batch)
            else:
                failed += len(batch)
    sql_sync = {"requested": sync_sql, "skipped": dry_run or failed > 0 or not sync_sql}
    if not dry_run and failed == 0 and sync_sql:
        sql_sync = {"requested": True, "skipped": False, **_sync_assignments_to_sql(plan["assignments"])}
    return {
        "available": True,
        "dry_run": dry_run,
        "collection_count": expected_count,
        **plan,
        "pending_chunk_update_count": len(pending),
        "updated_chunk_count": updated,
        "failed_chunk_count": failed,
        "sql_sync": sql_sync,
        "domain_policy": "soft_boost_only",
        "hard_domain_filtering": False,
        "reembedding_required": False,
        "restart_required": False,
    }
