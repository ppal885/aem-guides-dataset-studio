"""Paginated reconciliation for deterministic historical Jira UAC chunks."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_chunking_service import smart_chunks_to_chroma_rows
from app.services.jira_uac_analysis_service import (
    HISTORICAL_UAC_CHUNK_TYPES,
    UAC_SCHEMA_VERSION,
    HistoricalUacAnalysis,
    analyze_historical_uac,
    build_historical_uac_chunks,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_release_scope_evidence,
    resolve_historical_uac_text,
)
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    delete_documents,
    get_documents_where,
    is_chroma_available,
)


_SOURCE_CHUNK_TYPES = {
    "acceptance_criteria_chunk",
    "resolution_rca_chunk",
    "test_evidence_chunk",
    "comment_chunk",
}
_EXACT_UAC_SOURCE_TYPES = frozenset({"jira_api", "jira_csv"})
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.I)


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def _archive_values(issue: JiraEnrichedIssue, key: str) -> list[str]:
    archive = issue.evidence_archive if isinstance(issue.evidence_archive, dict) else {}
    values = archive.get(key) if isinstance(archive, dict) else []
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _uac_provenance_status(issue: JiraEnrichedIssue) -> tuple[bool, str]:
    source_type = str(issue.source_type or "").strip().casefold()
    if source_type not in _EXACT_UAC_SOURCE_TYPES:
        return False, "source_is_not_jira_csv_or_jira_api"
    if source_type == "jira_api":
        return True, "jira_api"

    hashes = [str(issue.source_file_hash or "").strip()]
    hashes.extend(_json_list(issue.source_file_hashes))
    provenance = issue.import_provenance if isinstance(issue.import_provenance, list) else []
    hashes.extend(
        str(entry.get("file_hash") or "").strip()
        for entry in provenance
        if isinstance(entry, dict)
    )
    if any(_SHA256_RE.fullmatch(value) for value in hashes if value):
        return True, "jira_csv_hash_verified"
    return False, "jira_csv_hash_missing"


def has_indexable_exact_uac_provenance(issue: JiraEnrichedIssue) -> bool:
    """Return whether exact historical UAC text came from Jira API or a hashed CSV."""

    return _uac_provenance_status(issue)[0]


def _chunk_body(document: str) -> str:
    text = str(document or "").strip()
    if "\n\n" in text:
        text = text.split("\n\n", 1)[1].strip()
    return text


def _acceptance_criteria_from_sql(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[str, str]:
    archived_acceptance = _archive_values(issue, "acceptance_criteria")
    return resolve_historical_uac_text(
        acceptance_criteria=archived_acceptance[-1] if archived_acceptance else "",
        labels=_json_list(issue.labels),
        description=issue.description or "",
        raw_text=issue.raw_text or "",
        fallback_documents=[
            chunk.chunk_text for chunk in chunks if chunk.chunk_type == "acceptance_criteria_chunk"
        ],
        comment_documents=[
            chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"
        ]
        + _archive_values(issue, "comments"),
    )


def _root_cause_from_chunks(chunks: list[JiraIssueChunk]) -> tuple[str, str]:
    field_value = ""
    for chunk in chunks:
        if chunk.chunk_type != "resolution_rca_chunk":
            continue
        body = _chunk_body(chunk.chunk_text)
        if "Root cause:" in body:
            field_value = body.split("Root cause:", 1)[1].strip()
            break
    return extract_explicit_root_cause_evidence(
        field_value=field_value,
        comment_documents=[chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
    )


def _root_cause_from_issue(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[str, str]:
    archived = _archive_values(issue, "root_causes")
    if archived:
        return extract_explicit_root_cause_evidence(
            field_value=archived[-1],
            comment_documents=_archive_values(issue, "comments")
            + [chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
        )
    return _root_cause_from_chunks(chunks)


def _test_evidence_from_chunks(chunks: list[JiraIssueChunk]) -> tuple[str, str]:
    bodies = []
    for chunk in chunks:
        if chunk.chunk_type != "test_evidence_chunk":
            continue
        body = _chunk_body(chunk.chunk_text)
        if body.casefold().startswith("test plan and evidence:"):
            body = body.split(":", 1)[1].strip()
        if body:
            bodies.append(body)
    return extract_explicit_test_evidence(
        field_value="\n".join(bodies).strip(),
        comment_documents=[chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
    )


def _test_evidence_from_issue(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[str, str]:
    archived = _archive_values(issue, "test_plans")
    if archived:
        return extract_explicit_test_evidence(
            field_value=archived[-1],
            comment_documents=_archive_values(issue, "comments")
            + [chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
        )
    return _test_evidence_from_chunks(chunks)


def _release_scope_from_chunks(chunks: list[JiraIssueChunk]) -> tuple[str, str]:
    return extract_release_scope_evidence(
        comment_documents=[chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
    )


def _release_scope_from_issue(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[str, str]:
    archived_comments = _archive_values(issue, "comments")
    if archived_comments:
        return extract_release_scope_evidence(
            comment_documents=archived_comments
            + [chunk.chunk_text for chunk in chunks if chunk.chunk_type == "comment_chunk"],
        )
    return _release_scope_from_chunks(chunks)


def analyze_sql_uac_issue(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[HistoricalUacAnalysis, str, str, str] | None:
    if not has_indexable_exact_uac_provenance(issue):
        return None
    acceptance_criteria, acceptance_source = _acceptance_criteria_from_sql(issue, chunks)
    if not acceptance_criteria:
        return None
    root_cause, root_cause_source = _root_cause_from_issue(issue, chunks)
    test_evidence, test_evidence_source = _test_evidence_from_issue(issue, chunks)
    release_scope, release_scope_source = _release_scope_from_issue(issue, chunks)
    analysis = analyze_historical_uac(
        jira_key=issue.jira_key,
        acceptance_criteria=acceptance_criteria,
        status=issue.status or "",
        resolution=issue.resolution or "",
        labels=_json_list(issue.labels),
        root_cause=root_cause,
        test_evidence=test_evidence,
        root_cause_source=root_cause_source,
        test_evidence_source=test_evidence_source,
        release_scope_evidence=release_scope,
        release_scope_source=release_scope_source,
        acceptance_source=acceptance_source,
    )
    if analysis is None:
        return None
    return analysis, acceptance_criteria, root_cause, test_evidence


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _enriched_from_sql(
    issue: JiraEnrichedIssue,
    *,
    acceptance_criteria: str,
    root_cause: str,
    test_evidence: str,
) -> JiraEnrichedDocument:
    return JiraEnrichedDocument(
        jira_key=issue.jira_key,
        summary=issue.summary or "",
        description=issue.description or "",
        issue_type=issue.issue_type or "",
        status=issue.status or "",
        priority=issue.priority or "",
        resolution=issue.resolution or "",
        jira_updated_at=_iso(issue.jira_updated_at),
        source_type=issue.source_type or "jira_csv",
        source_file_hash=issue.source_file_hash or "",
        labels=_json_list(issue.labels),
        components=_json_list(issue.components),
        customer_names=_json_list(issue.customer_names),
        domain=issue.domain or "unknown",
        sub_domain=issue.sub_domain or "",
        affected_outputs=_json_list(issue.affected_outputs),
        affected_features=_json_list(issue.affected_features),
        dita_entities=_json_list(issue.dita_entities),
        symptoms=_json_list(issue.symptoms),
        expected_behavior=issue.expected_behavior or "",
        actual_behavior=issue.actual_behavior or "",
        qa_risk_tags=_json_list(issue.qa_risk_tags),
        automation_fit=issue.automation_fit or "",
        missing_info=_json_list(issue.missing_info),
        raw_text=issue.raw_text or "",
        customer_detection_debug=issue.customer_detection_debug or {},
        acceptance_criteria=acceptance_criteria,
        root_cause=root_cause,
        test_plan=test_evidence,
    )


def _issue_dict(issue: JiraEnrichedIssue) -> dict[str, Any]:
    return {
        "key": issue.jira_key,
        "fields": {
            "summary": issue.summary or "",
            "issuetype": {"name": issue.issue_type or ""},
            "status": {"name": issue.status or ""},
            "priority": {"name": issue.priority or ""},
            "labels": _json_list(issue.labels),
            "components": [{"name": value} for value in _json_list(issue.components)],
            "updated": _iso(issue.jira_updated_at),
            "_csv_resolution": issue.resolution or "",
            "_source_type": issue.source_type or "jira_csv",
            "_source_file_hash": issue.source_file_hash or "",
        },
    }


def build_sql_uac_rows(
    issue: JiraEnrichedIssue,
    chunks: list[JiraIssueChunk],
) -> tuple[HistoricalUacAnalysis, list[dict[str, Any]]] | None:
    analyzed = analyze_sql_uac_issue(issue, chunks)
    if analyzed is None:
        return None
    analysis, acceptance_criteria, root_cause, test_evidence = analyzed
    enriched = _enriched_from_sql(
        issue,
        acceptance_criteria=acceptance_criteria,
        root_cause=root_cause,
        test_evidence=test_evidence,
    )
    smart_chunks = build_historical_uac_chunks(analysis)
    rows = smart_chunks_to_chroma_rows(issue.jira_key, _issue_dict(issue), enriched, smart_chunks)
    return analysis, rows


def _persist_sql_chunks(issue: JiraEnrichedIssue, rows: list[dict[str, Any]]) -> None:
    db = SessionLocal()
    try:
        db.query(JiraIssueChunk).filter(
            JiraIssueChunk.jira_key == issue.jira_key,
            JiraIssueChunk.chunk_type.in_(tuple(HISTORICAL_UAC_CHUNK_TYPES)),
        ).delete(synchronize_session=False)
        now = datetime.utcnow()
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            db.add(
                JiraIssueChunk(
                    jira_key=issue.jira_key,
                    chunk_type=str(metadata.get("chunk_type") or "unknown")[:80],
                    chunk_text=str(row.get("document") or ""),
                    domain=issue.domain or "unknown",
                    customer_names=_json_list(issue.customer_names),
                    affected_outputs=_json_list(issue.affected_outputs),
                    dita_entities=_json_list(issue.dita_entities),
                    embedding=None,
                    created_at=now,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _upsert_chroma_rows(rows: list[dict[str, Any]]) -> bool:
    documents = [str(row["document"]) for row in rows]
    embeddings = embed_texts_batched(documents, batch_size=64)
    if embeddings is None:
        return False
    ids = [str(row["chunk_id"]) for row in rows]
    metadatas = [
        {
            key: value
            for key, value in row["metadata"].items()
            if isinstance(value, (str, int, float, bool))
        }
        for row in rows
    ]
    vectors = [embeddings[index].tolist() for index in range(len(rows))]
    for attempt in range(1, 4):
        if add_documents(CHROMA_COLLECTION_JIRA_QA, ids, documents, metadatas, vectors):
            return True
        if attempt < 3:
            time.sleep(0.5 * attempt)
    return False


def _existing_uac_ids(jira_key: str) -> set[str]:
    rows = get_documents_where(CHROMA_COLLECTION_JIRA_QA, {"jira_key": jira_key}, limit=500)
    return {
        str(row.get("id") or "")
        for row in rows
        if str((row.get("metadata") or {}).get("chunk_type") or "") in HISTORICAL_UAC_CHUNK_TYPES
        and row.get("id")
    }


def backfill_historical_uac_chunks(
    *,
    source_type: str = "jira_csv",
    limit: int = 100_000,
    page_size: int = 200,
    closed_only: bool = True,
    dry_run: bool = True,
    jira_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not dry_run and not is_chroma_available():
        return {"available": False, "valid": False, "error": "ChromaDB is not available"}
    if not dry_run and not is_embedding_available():
        return {"available": False, "valid": False, "error": "Embedding model is not available"}

    capped_limit = max(1, min(int(limit), 500_000))
    capped_page_size = max(1, min(int(page_size), 1000))
    requested_keys = tuple(
        dict.fromkeys(
            str(key or "").strip().upper()
            for key in (jira_keys or [])
            if str(key or "").strip()
        )
    )
    if len(requested_keys) > 10_000:
        return {
            "available": True,
            "valid": False,
            "dry_run": bool(dry_run),
            "error": "Historical UAC key filter exceeds 10,000 issues",
        }
    last_id = 0
    exhausted = False
    scanned = 0
    analyzed_count = 0
    planned_chunks = 0
    indexed_issues = 0
    indexed_chunks = 0
    stale_deleted = 0
    errors: list[str] = []
    reuse_tiers: Counter[str] = Counter()
    dimensions: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    unresolved_clause_count = 0
    contradiction_count = 0
    performance_issue_count = 0
    performance_complete_count = 0
    contract_complete_count = 0
    source_truncated_count = 0
    in_scope_clause_count = 0
    out_of_scope_clause_count = 0
    reference_clause_count = 0
    context_clause_count = 0
    explicit_root_cause_count = 0
    explicit_test_evidence_count = 0
    source_authorities: Counter[str] = Counter()
    source_origins: Counter[str] = Counter()
    skipped_provenance: Counter[str] = Counter()

    while analyzed_count < capped_limit:
        db = SessionLocal()
        try:
            query = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.id > last_id)
            if source_type:
                query = query.filter(JiraEnrichedIssue.source_type == source_type)
            if requested_keys:
                query = query.filter(JiraEnrichedIssue.jira_key.in_(requested_keys))
            issues = query.order_by(JiraEnrichedIssue.id).limit(capped_page_size).all()
            if not issues:
                exhausted = True
                break
            last_id = max(int(issue.id) for issue in issues)
            keys = [issue.jira_key for issue in issues]
            source_chunks = (
                db.query(JiraIssueChunk)
                .filter(
                    JiraIssueChunk.jira_key.in_(keys),
                    JiraIssueChunk.chunk_type.in_(tuple(_SOURCE_CHUNK_TYPES)),
                )
                .all()
            )
        finally:
            db.close()

        grouped: dict[str, list[JiraIssueChunk]] = defaultdict(list)
        for chunk in source_chunks:
            grouped[chunk.jira_key].append(chunk)

        for issue in issues:
            scanned += 1
            provenance_ok, provenance_reason = _uac_provenance_status(issue)
            if not provenance_ok:
                skipped_provenance[provenance_reason] += 1
                continue
            built = build_sql_uac_rows(issue, grouped.get(issue.jira_key, []))
            if built is None:
                continue
            analysis, rows = built
            if closed_only and not analysis.issue_closed:
                continue
            if analyzed_count >= capped_limit:
                break
            analyzed_count += 1
            planned_chunks += len(rows)
            reuse_tiers[analysis.reuse_tier] += 1
            source_authorities[analysis.source_authority] += 1
            source_origins[analysis.source_origin] += 1
            outcome_counts[analysis.historical_outcome] += 1
            dimensions.update(analysis.dimensions)
            contract_complete_count += int(analysis.contract_complete)
            source_truncated_count += int(analysis.source_truncated)
            in_scope_clause_count += len(analysis.in_scope_clauses)
            out_of_scope_clause_count += len(analysis.out_of_scope_clauses)
            reference_clause_count += len(analysis.reference_clauses)
            context_clause_count += len(analysis.context_clauses)
            explicit_root_cause_count += int(analysis.explicit_root_cause)
            explicit_test_evidence_count += int(analysis.explicit_test_evidence)
            unresolved_clause_count += len(analysis.unresolved_clauses)
            contradiction_count += len(analysis.contradictions)
            performance_issue_count += int(analysis.performance_matters)
            performance_complete_count += int(analysis.performance_contract_complete)
            if dry_run:
                continue
            old_ids = _existing_uac_ids(issue.jira_key)
            if not _upsert_chroma_rows(rows):
                errors.append(f"{issue.jira_key}: UAC Chroma upsert failed")
                continue
            try:
                _persist_sql_chunks(issue, rows)
            except Exception as exc:
                errors.append(f"{issue.jira_key}: UAC SQL persistence failed: {exc}")
                continue
            new_ids = {str(row["chunk_id"]) for row in rows}
            stale_ids = sorted(old_ids - new_ids)
            if stale_ids:
                if delete_documents(CHROMA_COLLECTION_JIRA_QA, stale_ids):
                    stale_deleted += len(stale_ids)
                else:
                    errors.append(f"{issue.jira_key}: stale UAC chunk cleanup failed")
                    continue
            indexed_issues += 1
            indexed_chunks += len(rows)

    limit_reached = analyzed_count >= capped_limit and not exhausted
    scan_complete = exhausted and not limit_reached
    valid = scan_complete and not errors
    return {
        "available": True,
        "valid": valid,
        "dry_run": bool(dry_run),
        "applied": not dry_run and indexed_issues > 0,
        "schema_version": UAC_SCHEMA_VERSION,
        "source_type": source_type,
        "jira_key_filter_count": len(requested_keys),
        "closed_only": bool(closed_only),
        "scan_complete": scan_complete,
        "limit_reached": limit_reached,
        "issues_scanned": scanned,
        "issues_with_uac": analyzed_count,
        "planned_chunks": planned_chunks,
        "indexed_issues": indexed_issues,
        "indexed_chunks": indexed_chunks,
        "stale_chunks_deleted": stale_deleted,
        "contract_complete": contract_complete_count,
        "contract_incomplete": analyzed_count - contract_complete_count,
        "source_truncated": source_truncated_count,
        "in_scope_clauses": in_scope_clause_count,
        "out_of_scope_clauses": out_of_scope_clause_count,
        "reference_clauses": reference_clause_count,
        "context_clauses": context_clause_count,
        "unresolved_clauses": unresolved_clause_count,
        "contradictions": contradiction_count,
        "explicit_root_cause": explicit_root_cause_count,
        "explicit_test_evidence": explicit_test_evidence_count,
        "performance_issues": performance_issue_count,
        "performance_contracts_complete": performance_complete_count,
        "source_authorities": dict(sorted(source_authorities.items())),
        "source_origins": dict(sorted(source_origins.items())),
        "skipped_untrusted_provenance": sum(skipped_provenance.values()),
        "skipped_provenance_reasons": dict(sorted(skipped_provenance.items())),
        "reuse_tiers": dict(sorted(reuse_tiers.items())),
        "historical_outcomes": dict(sorted(outcome_counts.items())),
        "dimensions": dict(sorted(dimensions.items())),
        "errors_count": len(errors),
        "errors": errors[:100],
    }
