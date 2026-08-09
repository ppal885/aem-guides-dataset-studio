"""Evidence-backed Jira learning chunks for historical QA retrieval."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_uac_analysis_service import (
    analyze_historical_uac,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_historical_uac_text,
)
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, add_documents, is_chroma_available

LEARNING_CHUNK_TYPE = "learning_behavior_chunk"
LEARNING_STRATEGY_VERSION = "jira-history-v1"
_FIXED_OUTCOMES = {"fixed", "done", "complete", "partially complete", "documentation complete"}
_CAUTION_OUTCOMES = {
    "duplicate",
    "won't do",
    "won't fix",
    "not a bug",
    "working as designed",
    "cannot reproduce",
    "rejected",
    "deferred",
    "canceled",
    "no longer applies",
    "question answered",
    "transfer to product",
}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _outcome_kind(resolution: str) -> str:
    normalized = _clean(resolution, 120).lower()
    if normalized in _FIXED_OUTCOMES:
        return "implemented_fix"
    if normalized == "duplicate":
        return "duplicate_reference"
    if normalized == "working as designed":
        return "expected_product_behavior"
    if normalized in _CAUTION_OUTCOMES:
        return "non_fix_decision"
    return "other_resolution"


def _learning_confidence(
    *,
    resolution: str,
    problem: str,
    behavior_contract: str,
    root_cause: str,
    qa_oracle: str,
    behavior_contract_complete: bool,
    root_cause_source: str,
    qa_oracle_source: str,
) -> tuple[str, bool]:
    fixed = _clean(resolution, 120).lower() in _FIXED_OUTCOMES
    verified = bool(
        fixed
        and problem
        and behavior_contract
        and behavior_contract_complete
        and root_cause
        and root_cause_source != "missing"
        and qa_oracle
        and qa_oracle_source != "generated_fallback"
        and qa_oracle_source != "missing"
    )
    if verified:
        return "high", True
    if fixed and problem and behavior_contract and behavior_contract_complete:
        return "medium", False
    return "caution", False


def build_learning_document(
    *,
    jira_key: str,
    summary: str,
    domain: str,
    components: list[str],
    outputs: list[str],
    entities: list[str],
    problem: str,
    behavior_contract: str,
    resolution: str,
    root_cause: str,
    qa_oracle: str,
    risks: list[str],
    behavior_contract_source: str = "jira_expected_behavior_or_uac",
    behavior_contract_complete: bool = True,
    root_cause_source: str | None = None,
    qa_oracle_source: str | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Build one conservative historical-learning chunk without inferring missing facts."""
    resolution = _clean(resolution, 120)
    problem = _clean(problem, 1200)
    behavior_contract = _clean(behavior_contract, 1200)
    root_cause = _clean(root_cause, 900)
    qa_oracle = _clean(qa_oracle, 1000)
    root_cause_source = root_cause_source or ("jira_root_cause_field" if root_cause else "missing")
    qa_oracle_source = qa_oracle_source or ("jira_test_plan_field" if qa_oracle else "missing")
    if not resolution or not (problem or behavior_contract):
        return None

    confidence, verified_fix = _learning_confidence(
        resolution=resolution,
        problem=problem,
        behavior_contract=behavior_contract,
        root_cause=root_cause,
        qa_oracle=qa_oracle,
        behavior_contract_complete=behavior_contract_complete,
        root_cause_source=root_cause_source,
        qa_oracle_source=qa_oracle_source,
    )
    facets = [
        name
        for name, value in (
            ("problem", problem),
            ("behavior_contract", behavior_contract),
            ("resolution", resolution),
            ("root_cause", root_cause),
            ("qa_oracle", qa_oracle),
        )
        if value
    ]
    scope = []
    if domain:
        scope.append(f"domain={domain}")
    if components:
        scope.append("components=" + ", ".join(components[:8]))
    if outputs:
        scope.append("outputs=" + ", ".join(outputs[:8]))
    if entities:
        scope.append("entities=" + ", ".join(entities[:10]))

    lines = [
        f"Historical Jira learning: {jira_key}",
        f"Summary: {_clean(summary, 500)}",
        f"Scope: {' | '.join(scope) if scope else 'not classified'}",
        f"Observed problem: {problem or 'not explicitly captured'}",
        f"Behavior contract: {behavior_contract or 'not explicitly captured'}",
        f"Behavior contract source: {behavior_contract_source or 'missing'}",
        f"Behavior contract complete: {str(bool(behavior_contract_complete)).lower()}",
        f"Historical outcome: {resolution}",
        f"Root cause evidence: {root_cause or 'not explicitly captured; do not infer'}",
        f"Root cause source: {root_cause_source}",
        f"QA oracle: {qa_oracle or 'not explicitly captured; validate independently'}",
        f"QA oracle source: {qa_oracle_source}",
        f"Regression risks: {', '.join(risks[:10]) if risks else 'not explicitly classified'}",
        (
            "Reuse rule: treat this as historical supporting evidence. "
            "Current Jira facts and approved UAC remain authoritative."
        ),
    ]
    metadata = {
        "learning_confidence": confidence,
        "historical_outcome": _outcome_kind(resolution),
        "is_verified_fix": verified_fix,
        "evidence_facets": facets,
        "learning_strategy_version": LEARNING_STRATEGY_VERSION,
        "behavior_contract_source": behavior_contract_source,
        "behavior_contract_complete": bool(behavior_contract_complete),
        "root_cause_source": root_cause_source,
        "qa_oracle_source": qa_oracle_source,
    }
    return "\n".join(lines)[:6000], metadata


def build_learning_chunk_from_enriched(enriched: JiraEnrichedDocument) -> dict[str, Any] | None:
    root_cause, root_cause_source = extract_explicit_root_cause_evidence(
        field_value=enriched.root_cause,
        comment_documents=[enriched.comments_digest],
    )
    qa_oracle, qa_oracle_source = extract_explicit_test_evidence(
        field_value=enriched.test_plan,
        comment_documents=[enriched.comments_digest],
    )
    uac_analysis = analyze_historical_uac(
        jira_key=enriched.jira_key,
        acceptance_criteria=enriched.acceptance_criteria,
        status=enriched.status,
        resolution=enriched.resolution,
        labels=enriched.labels,
        root_cause=root_cause,
        test_evidence=qa_oracle,
        root_cause_source=root_cause_source,
        test_evidence_source=qa_oracle_source,
    )
    uac_contract = ""
    if uac_analysis is not None:
        uac_contract = "\n".join(
            f"{clause.source_id}: {clause.text}" for clause in uac_analysis.in_scope_clauses
        )
    contract = "\n".join(
        value.strip() for value in (enriched.expected_behavior, uac_contract) if value and value.strip()
    )
    behavior_contract_complete = uac_analysis.contract_complete if uac_analysis is not None else bool(contract)
    behavior_contract_source = (
        "jira_expected_behavior+jira_acceptance_field"
        if enriched.expected_behavior.strip() and uac_contract
        else "jira_acceptance_field"
        if uac_contract
        else "jira_expected_behavior"
        if enriched.expected_behavior.strip()
        else "missing"
    )
    built = build_learning_document(
        jira_key=enriched.jira_key,
        summary=enriched.summary,
        domain=enriched.domain,
        components=list(enriched.components or []),
        outputs=list(enriched.affected_outputs or []),
        entities=list(enriched.dita_entities or []),
        problem=enriched.description,
        behavior_contract=contract,
        resolution=enriched.resolution,
        root_cause=root_cause,
        qa_oracle=qa_oracle,
        risks=list(enriched.qa_risk_tags or []),
        behavior_contract_source=behavior_contract_source,
        behavior_contract_complete=behavior_contract_complete,
        root_cause_source=root_cause_source,
        qa_oracle_source=qa_oracle_source,
    )
    if built is None:
        return None
    document, metadata = built
    return {"chunk_type": LEARNING_CHUNK_TYPE, "chunk_text": document, **metadata}


def _chunk_body(document: str) -> str:
    text = str(document or "").strip()
    if "\n\n" in text:
        return text.split("\n\n", 1)[1].strip()
    return text


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _learning_from_sql(issue: JiraEnrichedIssue, chunks: list[JiraIssueChunk]) -> tuple[str, dict[str, Any]] | None:
    by_type: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        by_type[chunk.chunk_type].append(_chunk_body(chunk.chunk_text))
    resolution_text = "\n".join(by_type.get("resolution_rca_chunk", []))
    root_cause_field = ""
    if "Root cause:" in resolution_text:
        root_cause_field = resolution_text.split("Root cause:", 1)[1].strip()
    root_cause, root_cause_source = extract_explicit_root_cause_evidence(
        field_value=root_cause_field,
        comment_documents=by_type.get("comment_chunk", []),
    )
    acceptance_text = extract_historical_uac_text(
        description=issue.description or "",
        raw_text=issue.raw_text or "",
        fallback_documents=by_type.get("acceptance_criteria_chunk", []),
    )
    qa_oracle, qa_oracle_source = extract_explicit_test_evidence(
        field_value="\n".join(by_type.get("test_evidence_chunk", [])),
        comment_documents=by_type.get("comment_chunk", []),
    )
    uac_analysis = analyze_historical_uac(
        jira_key=issue.jira_key,
        acceptance_criteria=acceptance_text,
        status=issue.status or "",
        resolution=issue.resolution or "",
        labels=_json_list(issue.labels),
        root_cause=root_cause,
        test_evidence=qa_oracle,
        root_cause_source=root_cause_source,
        test_evidence_source=qa_oracle_source,
    )
    uac_contract = ""
    if uac_analysis is not None:
        uac_contract = "\n".join(
            f"{clause.source_id}: {clause.text}" for clause in uac_analysis.in_scope_clauses
        )
    expected_contract = "\n".join(by_type.get("expected_actual_chunk", []))
    contract = "\n".join(value for value in (expected_contract, uac_contract) if value.strip())
    problem = "\n".join(by_type.get("problem_chunk", [])[:2]) or (issue.description or "")
    return build_learning_document(
        jira_key=issue.jira_key,
        summary=issue.summary or "",
        domain=issue.domain or "unknown",
        components=_json_list(issue.components),
        outputs=_json_list(issue.affected_outputs),
        entities=_json_list(issue.dita_entities),
        problem=problem,
        behavior_contract=contract,
        resolution=issue.resolution or "",
        root_cause=root_cause,
        qa_oracle=qa_oracle,
        risks=_json_list(issue.qa_risk_tags),
        behavior_contract_source=(
            "jira_expected_behavior+jira_acceptance_field"
            if expected_contract and uac_contract
            else "jira_acceptance_field"
            if uac_contract
            else "jira_expected_behavior"
            if expected_contract
            else "missing"
        ),
        behavior_contract_complete=uac_analysis.contract_complete if uac_analysis is not None else bool(contract),
        root_cause_source=root_cause_source,
        qa_oracle_source=qa_oracle_source,
    )


def backfill_jira_learning_chunks(*, source_type: str = "jira_csv", limit: int = 10_000) -> dict[str, Any]:
    """Build and upsert one learning chunk per eligible resolved Jira issue."""
    if not is_chroma_available():
        return {"error": "ChromaDB is not available", "indexed_issues": 0, "chunks": 0}
    if not is_embedding_available():
        return {"error": "Embedding model is not available", "indexed_issues": 0, "chunks": 0}

    db = SessionLocal()
    try:
        query = db.query(JiraEnrichedIssue)
        if source_type:
            query = query.filter(JiraEnrichedIssue.source_type == source_type)
        issues = query.order_by(JiraEnrichedIssue.jira_key).limit(max(1, min(limit, 100_000))).all()
        keys = [issue.jira_key for issue in issues]
        chunk_rows = db.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key.in_(keys)).all() if keys else []
        grouped: dict[str, list[JiraIssueChunk]] = defaultdict(list)
        for chunk in chunk_rows:
            grouped[chunk.jira_key].append(chunk)

        candidates: list[tuple[JiraEnrichedIssue, str, dict[str, Any]]] = []
        confidence_counts: dict[str, int] = defaultdict(int)
        outcome_counts: dict[str, int] = defaultdict(int)
        for issue in issues:
            built = _learning_from_sql(issue, grouped.get(issue.jira_key, []))
            if built is None:
                continue
            document, learning_meta = built
            confidence_counts[str(learning_meta["learning_confidence"])] += 1
            outcome_counts[str(learning_meta["historical_outcome"])] += 1
            candidates.append((issue, document, learning_meta))
    finally:
        db.close()

    indexed = 0
    errors: list[str] = []
    for start in range(0, len(candidates), 64):
        batch = candidates[start : start + 64]
        documents = [document for _, document, _ in batch]
        embeddings = embed_texts_batched(documents, batch_size=64)
        if embeddings is None:
            errors.extend(f"{issue.jira_key}: embedding failed" for issue, _, _ in batch)
            continue
        ids = [f"{issue.jira_key}::{LEARNING_CHUNK_TYPE}::0" for issue, _, _ in batch]
        metadatas = []
        for issue, _, learning_meta in batch:
            metadatas.append(
                {
                    "source_type": "jira_learning",
                    "jira_key": issue.jira_key,
                    "title": (issue.summary or "")[:500],
                    "chunk_type": LEARNING_CHUNK_TYPE,
                    "status": (issue.status or "")[:120],
                    "resolution": (issue.resolution or "")[:120],
                    "enrich_domain": (issue.domain or "unknown")[:120],
                    "components": json.dumps(_json_list(issue.components), ensure_ascii=False)[:4000],
                    "enrich_outputs": json.dumps(_json_list(issue.affected_outputs), ensure_ascii=False)[:4000],
                    "enrich_entities": json.dumps(_json_list(issue.dita_entities), ensure_ascii=False)[:4000],
                    "learning_confidence": str(learning_meta["learning_confidence"]),
                    "historical_outcome": str(learning_meta["historical_outcome"]),
                    "is_verified_fix": bool(learning_meta["is_verified_fix"]),
                    "evidence_facets": json.dumps(learning_meta["evidence_facets"], ensure_ascii=False),
                    "learning_strategy_version": LEARNING_STRATEGY_VERSION,
                    "behavior_contract_source": str(learning_meta["behavior_contract_source"]),
                    "behavior_contract_complete": bool(learning_meta["behavior_contract_complete"]),
                    "root_cause_source": str(learning_meta["root_cause_source"]),
                    "qa_oracle_source": str(learning_meta["qa_oracle_source"]),
                }
            )
        vectors = [embeddings[index].tolist() for index in range(len(batch))]
        stored = False
        for attempt in range(1, 4):
            stored = add_documents(CHROMA_COLLECTION_JIRA_QA, ids, documents, metadatas, vectors)
            if stored:
                break
            if attempt < 3:
                time.sleep(0.5 * attempt)
        if not stored:
            errors.extend(f"{issue.jira_key}: Chroma upsert failed" for issue, _, _ in batch)
            continue

        db = SessionLocal()
        try:
            for issue, document, learning_meta in batch:
                db.query(JiraIssueChunk).filter(
                    JiraIssueChunk.jira_key == issue.jira_key,
                    JiraIssueChunk.chunk_type == LEARNING_CHUNK_TYPE,
                ).delete(synchronize_session=False)
                db.add(
                    JiraIssueChunk(
                        jira_key=issue.jira_key,
                        chunk_type=LEARNING_CHUNK_TYPE,
                        chunk_text=document,
                        domain=issue.domain or "unknown",
                        customer_names=_json_list(issue.customer_names),
                        affected_outputs=_json_list(issue.affected_outputs),
                        dita_entities=_json_list(issue.dita_entities),
                        embedding=None,
                        created_at=datetime.utcnow(),
                    )
                )
            db.commit()
            indexed += len(batch)
        except Exception as exc:
            db.rollback()
            errors.extend(f"{issue.jira_key}: SQL persistence failed: {exc}" for issue, _, _ in batch)
        finally:
            db.close()

    return {
        "source_type": source_type,
        "eligible_issues": len(candidates),
        "indexed_issues": indexed,
        "chunks": indexed,
        "failed_issues": len(errors),
        "errors": errors[:100],
        "confidence_counts": dict(confidence_counts),
        "outcome_counts": dict(outcome_counts),
        "strategy_version": LEARNING_STRATEGY_VERSION,
    }
