"""Evidence-backed Jira learning chunks for historical QA retrieval."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_component_metadata_service import (
    canonical_component_names,
    component_filter_metadata,
)
from app.services.jira_uac_analysis_service import (
    analyze_historical_uac,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_release_scope_evidence,
    resolve_historical_uac_text,
)
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, add_documents, is_chroma_available

LEARNING_CHUNK_TYPE = "learning_behavior_chunk"
LEARNING_STRATEGY_VERSION = "jira-history-v4"
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
_NON_PRODUCT_RESOLUTION_MECHANISMS = {
    "configuration_migration",
    "documentation_only",
    "workaround",
}
_WORKAROUND_NOT_FIX_RE = re.compile(
    r"\b(?:still\s+a\s+workaround(?:\s+and\s+not\s+a\s+fix)?|"
    r"workaround\s+and\s+not\s+a\s+fix|not\s+a\s+(?:product\s+)?fix|"
    r"no\s+(?:product\s+)?code\s+changes?\s+(?:were\s+)?(?:required|made|delivered))\b",
    re.I,
)
_CONFIGURATION_MIGRATION_RE = re.compile(
    r"\b(?:"
    r"custom\s+buttons?[^.\n]{0,220}ui[_-]?config\.json[^.\n]{0,220}"
    r"(?:would\s+not\s+work|need(?:ed)?\s+to\s+be\s+ported)|"
    r"port(?:ed|ing)?[^.\n]{0,120}editor_toolbar\.(?:js|json)|"
    r"editor_toolbar\.(?:js|json)[^.\n]{0,180}"
    r"(?:both\s+(?:lock|locked)[^.\n]{0,30}(?:unlock|unlocked)|lock\s*(?:&|and)\s*unlock)"
    r")\b",
    re.I,
)
_DOCUMENTATION_CLOSURE_RE = re.compile(
    r"\b(?:"
    r"closing\s+this[^.\n]{0,180}no\s+further\s+action[^.\n]{0,180}documentation|"
    r"no\s+further\s+action[^.\n]{0,180}documentation\s+(?:will\s+be|is\s+being)\s+tracked|"
    r"documentation\s+(?:will\s+be|is\s+being)\s+tracked[^.\n]{0,160}GUIDES-\d+"
    r")\b",
    re.I,
)
_EXPLICIT_PRODUCT_FIX_RE = re.compile(
    r"\b(?:"
    r"(?:product|code)\s+(?:fix|change)\s+(?:has\s+been|was|is)\s+"
    r"(?:implemented|merged|released|delivered)|"
    r"fix\s+(?:has\s+been|was)\s+(?:implemented|merged|released|delivered)|"
    r"(?:already\s+)?fixed\s+in\s+(?:develop|development|main|master)(?:\s+branch)?|"
    r"cherry[-\s]?picked\s+(?:for|into)\s+(?:the\s+)?(?:[\w.-]+\s+)?hotfix|"
    r"verified\s+on\s+build"
    r")\b",
    re.I,
)


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _last_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


def _match_excerpt(text: str, match: re.Match[str] | None, limit: int = 500) -> str:
    if match is None:
        return ""
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    if end < 0:
        end = len(text)
    return _clean(text[start:end], limit)


def _resolution_classification(
    resolution: str,
    resolution_context: str,
) -> tuple[str, str, str]:
    """Classify how a Jira was resolved without equating ``Fixed`` to a code fix."""
    context = str(resolution_context or "")
    normalized_resolution = _clean(resolution, 120).lower()
    workaround = _last_match(_WORKAROUND_NOT_FIX_RE, context)
    migration = _last_match(_CONFIGURATION_MIGRATION_RE, context)
    documentation = _last_match(_DOCUMENTATION_CLOSURE_RE, context)
    product_fix = _last_match(_EXPLICIT_PRODUCT_FIX_RE, context)
    latest_non_product = max(
        (match.end() for match in (workaround, migration, documentation) if match is not None),
        default=-1,
    )
    if product_fix is not None and product_fix.end() > latest_non_product:
        return "product_fix", "jira_comment_product_fix", _match_excerpt(context, product_fix)

    evidence_parts: list[str] = []
    for match in (workaround, migration, documentation):
        excerpt = _match_excerpt(context, match)
        if excerpt and excerpt not in evidence_parts:
            evidence_parts.append(excerpt)
    evidence = " | ".join(evidence_parts)[:1200]
    if migration is not None:
        return "configuration_migration", "jira_comment_configuration_migration", evidence
    if workaround is not None and documentation is not None:
        return "documentation_only", "jira_comment_documentation_closure", evidence
    if workaround is not None:
        return "workaround", "jira_comment_workaround", evidence
    if normalized_resolution == "documentation complete":
        return "documentation_only", "jira_resolution_field", ""
    if normalized_resolution in _FIXED_OUTCOMES:
        return "resolution_field_only", "jira_resolution_field", ""
    return "non_fix_or_other", "jira_resolution_field", ""


def _outcome_kind(resolution: str, resolution_mechanism: str = "") -> str:
    if resolution_mechanism in _NON_PRODUCT_RESOLUTION_MECHANISMS:
        return resolution_mechanism
    if resolution_mechanism == "product_fix":
        return "implemented_fix"
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
    resolution_mechanism: str,
) -> tuple[str, bool]:
    if resolution_mechanism in _NON_PRODUCT_RESOLUTION_MECHANISMS:
        return "caution", False
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
    resolution_context: str = "",
) -> tuple[str, dict[str, Any]] | None:
    """Build one conservative historical-learning chunk without inferring missing facts."""
    resolution = _clean(resolution, 120)
    problem = _clean(problem, 1200)
    behavior_contract = _clean(behavior_contract, 1200)
    root_cause = _clean(root_cause, 900)
    qa_oracle = _clean(qa_oracle, 1000)
    root_cause_source = root_cause_source or ("jira_root_cause_field" if root_cause else "missing")
    qa_oracle_source = qa_oracle_source or ("jira_test_plan_field" if qa_oracle else "missing")
    resolution_mechanism, resolution_evidence_source, resolution_evidence = _resolution_classification(
        resolution,
        resolution_context,
    )
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
        resolution_mechanism=resolution_mechanism,
    )
    if verified_fix and resolution_mechanism == "resolution_field_only":
        resolution_mechanism = "product_fix"
    facets = [
        name
        for name, value in (
            ("problem", problem),
            ("behavior_contract", behavior_contract),
            ("resolution", resolution),
            ("root_cause", root_cause),
            ("qa_oracle", qa_oracle),
            ("resolution_evidence", resolution_evidence),
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
        f"Resolution mechanism: {resolution_mechanism}",
        f"Resolution evidence source: {resolution_evidence_source}",
        f"Resolution evidence: {resolution_evidence or 'not explicitly captured beyond the Jira resolution field'}",
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
        "historical_outcome": _outcome_kind(resolution, resolution_mechanism),
        "is_verified_fix": verified_fix,
        "evidence_facets": facets,
        "learning_strategy_version": LEARNING_STRATEGY_VERSION,
        "behavior_contract_source": behavior_contract_source,
        "behavior_contract_complete": bool(behavior_contract_complete),
        "root_cause_source": root_cause_source,
        "qa_oracle_source": qa_oracle_source,
        "resolution_mechanism": resolution_mechanism,
        "resolution_evidence_source": resolution_evidence_source,
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
    release_scope, release_scope_source = extract_release_scope_evidence(
        comment_documents=[enriched.comments_digest],
    )
    acceptance_text, acceptance_source = resolve_historical_uac_text(
        acceptance_criteria=enriched.acceptance_criteria,
        labels=enriched.labels,
        description=enriched.description,
        raw_text=enriched.raw_text,
        comment_documents=[enriched.comments_digest],
    )
    uac_analysis = analyze_historical_uac(
        jira_key=enriched.jira_key,
        acceptance_criteria=acceptance_text,
        status=enriched.status,
        resolution=enriched.resolution,
        labels=enriched.labels,
        root_cause=root_cause,
        test_evidence=qa_oracle,
        root_cause_source=root_cause_source,
        test_evidence_source=qa_oracle_source,
        release_scope_evidence=release_scope,
        release_scope_source=release_scope_source,
        acceptance_source=acceptance_source,
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
        f"jira_expected_behavior+{acceptance_source}"
        if enriched.expected_behavior.strip() and uac_contract
        else acceptance_source
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
        resolution_context=enriched.comments_digest,
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
    acceptance_text, acceptance_source = resolve_historical_uac_text(
        labels=_json_list(issue.labels),
        description=issue.description or "",
        raw_text=issue.raw_text or "",
        fallback_documents=by_type.get("acceptance_criteria_chunk", []),
        comment_documents=by_type.get("comment_chunk", []),
    )
    qa_oracle, qa_oracle_source = extract_explicit_test_evidence(
        field_value="\n".join(by_type.get("test_evidence_chunk", [])),
        comment_documents=by_type.get("comment_chunk", []),
    )
    release_scope, release_scope_source = extract_release_scope_evidence(
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
        release_scope_evidence=release_scope,
        release_scope_source=release_scope_source,
        acceptance_source=acceptance_source,
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
            f"jira_expected_behavior+{acceptance_source}"
            if expected_contract and uac_contract
            else acceptance_source
            if uac_contract
            else "jira_expected_behavior"
            if expected_contract
            else "missing"
        ),
        behavior_contract_complete=uac_analysis.contract_complete if uac_analysis is not None else bool(contract),
        root_cause_source=root_cause_source,
        qa_oracle_source=qa_oracle_source,
        resolution_context="\n".join(by_type.get("comment_chunk", [])),
    )


def _learning_chroma_metadata(
    issue: JiraEnrichedIssue,
    learning_meta: dict[str, Any],
) -> dict[str, Any]:
    components = canonical_component_names(_json_list(issue.components))
    customers = list(dict.fromkeys(
        _json_list(issue.customer_cohorts) + _json_list(issue.customer_names)
    ))
    features = _json_list(issue.affected_features)
    metadata = {
        "source_type": "jira_learning",
        "jira_key": issue.jira_key,
        "title": (issue.summary or "")[:500],
        "chunk_type": LEARNING_CHUNK_TYPE,
        "status": (issue.status or "")[:120],
        "resolution": (issue.resolution or "")[:120],
        "enrich_domain": (issue.domain or "unknown")[:120],
        "components": json.dumps(components, ensure_ascii=False)[:4000],
        "customer_names": json.dumps(customers, ensure_ascii=False)[:4000],
        "customer_cohorts": json.dumps(_json_list(issue.customer_cohorts), ensure_ascii=False)[:4000],
        "enrich_customers": json.dumps(customers, ensure_ascii=False)[:4000],
        "enrich_outputs": json.dumps(_json_list(issue.affected_outputs), ensure_ascii=False)[:4000],
        "enrich_entities": json.dumps(_json_list(issue.dita_entities), ensure_ascii=False)[:4000],
        "enrich_features": json.dumps(features, ensure_ascii=False)[:4000],
        "editor_variant": "new_editor" if "new_editor" in features else "",
        "learning_confidence": str(learning_meta["learning_confidence"]),
        "historical_outcome": str(learning_meta["historical_outcome"]),
        "is_verified_fix": bool(learning_meta["is_verified_fix"]),
        "evidence_facets": json.dumps(learning_meta["evidence_facets"], ensure_ascii=False),
        "learning_strategy_version": LEARNING_STRATEGY_VERSION,
        "behavior_contract_source": str(learning_meta["behavior_contract_source"]),
        "behavior_contract_complete": bool(learning_meta["behavior_contract_complete"]),
        "root_cause_source": str(learning_meta["root_cause_source"]),
        "qa_oracle_source": str(learning_meta["qa_oracle_source"]),
        "resolution_mechanism": str(learning_meta["resolution_mechanism"]),
        "resolution_evidence_source": str(learning_meta["resolution_evidence_source"]),
    }
    metadata.update(component_filter_metadata(components))
    return metadata


def backfill_jira_learning_chunks(
    *,
    source_type: str = "jira_csv",
    limit: int = 10_000,
    jira_keys: list[str] | None = None,
) -> dict[str, Any]:
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
        requested_keys = list(dict.fromkeys(
            str(key or "").strip().upper() for key in (jira_keys or []) if str(key or "").strip()
        ))
        if requested_keys:
            query = query.filter(JiraEnrichedIssue.jira_key.in_(requested_keys))
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
        metadatas = [
            _learning_chroma_metadata(issue, learning_meta)
            for issue, _, learning_meta in batch
        ]
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
        "requested_keys": len(requested_keys),
        "eligible_issues": len(candidates),
        "indexed_issues": indexed,
        "chunks": indexed,
        "failed_issues": len(errors),
        "errors": errors[:100],
        "confidence_counts": dict(confidence_counts),
        "outcome_counts": dict(outcome_counts),
        "strategy_version": LEARNING_STRATEGY_VERSION,
    }
