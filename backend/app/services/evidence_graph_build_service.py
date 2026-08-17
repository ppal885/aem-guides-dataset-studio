"""Deterministic evidence graph adapters and blue/green rebuild orchestration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import os
import re
import sys
import time
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.db.dita_spec_models import DitaSpecChunk
from app.db.evidence_graph_models import (
    EvidenceGraphAssertion,
    EvidenceGraphGeneration,
    EvidenceGraphNode,
)
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.session import SessionLocal
from app.services.evidence_graph_contract import (
    EdgeSpec,
    EvidenceSpec,
    NodeSpec,
    canonical_url,
    exact_source_claim,
    extract_api_routes,
    extract_config_keys,
    extract_error_signatures,
    json_values,
    normalize_text,
    normalized_token,
    sanitize_excerpt,
    stable_digest,
    stable_key,
)
from app.services.evidence_graph_store import (
    GraphWriter,
    acquire_graph_lease,
    active_generation,
    create_generation,
    create_sync_run,
    promote_generation,
    release_graph_lease,
    update_source_checkpoint,
)
from app.services.jira_component_metadata_service import canonical_component_names
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_records_by_ids,
    get_collection_count,
    get_documents_where,
    iter_collection_records,
)


DEFAULT_GRAPH_SOURCES = ("jira", "docs", "dita")
_IMPLEMENTED_FIX_OUTCOMES = {"fixed", "done", "implemented", "completed"}
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,15}-\d+\b")
_SPECIALIZES_RE = re.compile(
    r"(?i)\b(?:specialization of|specializes|specialized from)\s+(?:the\s+)?<?([a-z][\w.-]+)>?"
)
_CONSTRAINS_RE = re.compile(
    r"(?i)\b(?:constraint of|constrains|constrained from)\s+(?:the\s+)?<?([a-z][\w.-]+)>?"
)


def _bounded_env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _jira_tenant_id() -> str:
    return normalize_text(os.getenv("EVIDENCE_GRAPH_DEFAULT_TENANT_ID", "kone")).casefold() or "kone"


def _safe_error(exc: Exception | str) -> str:
    value = f"{type(exc).__name__}: {exc}" if isinstance(exc, Exception) else str(exc)
    return sanitize_excerpt(value, max_chars=1000)[0]


def _peak_process_memory_mb() -> float | None:
    try:
        import resource

        maximum_rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return maximum_rss / (1024 * 1024) if sys.platform == "darwin" else maximum_rss / 1024
    except (ImportError, OSError, ValueError):
        try:
            import psutil

            return float(psutil.Process().memory_info().rss) / (1024 * 1024)
        except (ImportError, OSError, ValueError):
            return None


def _performance_result(started_at: float) -> dict[str, Any]:
    elapsed_seconds = round(max(0.0, time.perf_counter() - started_at), 3)
    peak_memory_mb = _peak_process_memory_mb()
    max_seconds = _bounded_env_int(
        "EVIDENCE_GRAPH_REBUILD_MAX_SECONDS",
        default=1200,
        minimum=1,
        maximum=86400,
    )
    max_memory_mb = _bounded_env_int(
        "EVIDENCE_GRAPH_REBUILD_MAX_MEMORY_MB",
        default=1536,
        minimum=64,
        maximum=1048576,
    )
    elapsed_ok = elapsed_seconds <= max_seconds
    memory_ok = peak_memory_mb is not None and peak_memory_mb <= max_memory_mb
    return {
        "elapsed_seconds": elapsed_seconds,
        "peak_memory_mb": round(peak_memory_mb, 2) if peak_memory_mb is not None else None,
        "limits": {"max_seconds": max_seconds, "max_memory_mb": max_memory_mb},
        "elapsed_ok": elapsed_ok,
        "memory_ok": memory_ok,
        "accepted": elapsed_ok and memory_ok,
    }


def _generation_source_fingerprints(
    session: Session,
    generation_id: str,
) -> dict[tuple[str, str], set[str]]:
    fingerprints: dict[tuple[str, str], set[str]] = defaultdict(set)
    for source_kind, record_id, source_hash in session.query(
        EvidenceGraphAssertion.source_kind,
        EvidenceGraphAssertion.source_record_id,
        EvidenceGraphAssertion.source_hash,
    ).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.active.is_(True),
    ):
        fingerprints[(str(source_kind), str(record_id))].add(str(source_hash))
    return fingerprints


def _reconciliation_delta(
    session: Session,
    *,
    previous_generation_id: str | None,
    generation_id: str,
) -> dict[str, Any]:
    if not previous_generation_id:
        return {
            "previous_generation_id": None,
            "added_source_records": 0,
            "changed_source_records": 0,
            "deleted_source_records": 0,
            "stale_assertions_removed": 0,
            "tombstoned_entities": 0,
        }
    previous = _generation_source_fingerprints(session, previous_generation_id)
    current = _generation_source_fingerprints(session, generation_id)
    previous_keys = set(previous)
    current_keys = set(current)
    changed = {
        key
        for key in previous_keys & current_keys
        if previous.get(key, set()) != current.get(key, set())
    }
    stale_assertions = sum(
        len(previous.get(key, set()) - current.get(key, set()))
        for key in previous_keys
    )
    previous_nodes = {
        stable_key_value
        for (stable_key_value,) in session.query(EvidenceGraphNode.stable_key).filter(
            EvidenceGraphNode.generation_id == previous_generation_id,
            EvidenceGraphNode.active.is_(True),
        )
    }
    current_nodes = {
        stable_key_value
        for (stable_key_value,) in session.query(EvidenceGraphNode.stable_key).filter(
            EvidenceGraphNode.generation_id == generation_id,
            EvidenceGraphNode.active.is_(True),
        )
    }
    return {
        "previous_generation_id": previous_generation_id,
        "added_source_records": len(current_keys - previous_keys),
        "changed_source_records": len(changed),
        "deleted_source_records": len(previous_keys - current_keys),
        "stale_assertions_removed": stale_assertions,
        "tombstoned_entities": len(previous_nodes - current_nodes),
        "sample_changed_records": [f"{kind}:{record}" for kind, record in sorted(changed)[:20]],
        "sample_deleted_records": [
            f"{kind}:{record}" for kind, record in sorted(previous_keys - current_keys)[:20]
        ],
    }


class GraphCollector:
    def __init__(self):
        self.nodes: dict[str, NodeSpec] = {}
        self.edges: dict[tuple[str, str, str], EdgeSpec] = {}

    def add_node(self, spec: NodeSpec) -> None:
        current = self.nodes.get(spec.stable_key)
        if current is None:
            self.nodes[spec.stable_key] = spec
            return
        if current.tenant_id and spec.tenant_id and current.tenant_id != spec.tenant_id:
            raise ValueError(
                f"Evidence graph node {spec.stable_key} was assigned to multiple tenants."
            )
        if spec.tenant_id is None:
            current.tenant_id = None
        current.properties = {**current.properties, **spec.properties}
        current.evidence.extend(_new_evidence(current.evidence, spec.evidence))
        if len(spec.label) > len(current.label):
            current.label = spec.label

    def add_edge(self, spec: EdgeSpec) -> None:
        key = (spec.source_key, spec.relation, spec.target_key)
        current = self.edges.get(key)
        if current is None:
            self.edges[key] = spec
            return
        if _trust_rank(spec.trust_tier) > _trust_rank(current.trust_tier):
            current.trust_tier = spec.trust_tier
        current.confidence = max(current.confidence, spec.confidence)
        current.properties = {**current.properties, **spec.properties}
        current.evidence.extend(_new_evidence(current.evidence, spec.evidence))

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()


class GraphCounter:
    """Dry-run writer that counts deterministic graph records without persistence."""

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: set[tuple[str, str, str]] = set()
        self.assertions: set[tuple[str, str, str, str]] = set()

    def write(self, nodes: Iterable[NodeSpec], edges: Iterable[EdgeSpec]) -> dict[str, int]:
        for node in nodes:
            self.nodes.add(node.stable_key)
            for evidence in node.evidence:
                self.assertions.add((node.stable_key, evidence.source_kind, evidence.source_record_id, evidence.source_hash))
        for edge in edges:
            edge_key = (edge.source_key, edge.relation, edge.target_key)
            self.edges.add(edge_key)
            for evidence in edge.evidence:
                self.assertions.add(("|".join(edge_key), evidence.source_kind, evidence.source_record_id, evidence.source_hash))
        return self.counts()

    def counts(self) -> dict[str, int]:
        return {
            "nodes_created": len(self.nodes),
            "edges_created": len(self.edges),
            "assertions_created": len(self.assertions),
        }


def _new_evidence(current: list[EvidenceSpec], incoming: list[EvidenceSpec]) -> list[EvidenceSpec]:
    existing = {
        (item.source_kind, item.source_record_id, item.source_hash, item.source_chunk_id)
        for item in current
    }
    return [
        item
        for item in incoming
        if (item.source_kind, item.source_record_id, item.source_hash, item.source_chunk_id) not in existing
    ]


def _trust_rank(value: str) -> int:
    return {"candidate": 0, "supporting": 1, "historical_verified": 2, "authoritative": 3}.get(value, -1)


def _source_hash(*values: Any) -> str:
    return "sha256:" + stable_digest(*values, length=64)


def _safe_label(value: Any, fallback: str) -> tuple[str, int]:
    clean, count = sanitize_excerpt(value, max_chars=500)
    return clean or fallback, count


def _evidence(
    *,
    source_kind: str,
    source_ref: str,
    source_record_id: str,
    source_hash: str,
    extraction_method: str,
    authority: str,
    trust_tier: str,
    excerpt: Any = "",
    source_chunk_id: str = "",
    source_updated_at: datetime | None = None,
    tenant_id: str | None = None,
) -> EvidenceSpec:
    return EvidenceSpec(
        source_kind=source_kind,
        source_ref=source_ref,
        source_record_id=source_record_id,
        source_chunk_id=source_chunk_id,
        source_hash=source_hash,
        extraction_method=extraction_method,
        authority=authority,
        trust_tier=trust_tier,
        excerpt=normalize_text(excerpt),
        tenant_id=tenant_id,
        source_updated_at=source_updated_at,
    )


def _add_entity_edge(
    collector: GraphCollector,
    *,
    source_key: str,
    node_type: str,
    value: str,
    relation: str,
    evidence: EvidenceSpec,
    trust_tier: str,
    confidence: float,
    properties: dict[str, Any] | None = None,
) -> None:
    value = normalize_text(value)
    if not value:
        return
    target_key = stable_key(node_type, value)
    collector.add_node(
        NodeSpec(
            stable_key=target_key,
            node_type=node_type,
            label=value,
            properties=properties or {},
            tenant_id=evidence.tenant_id,
            evidence=[evidence],
        )
    )
    collector.add_edge(
        EdgeSpec(
            source_key=source_key,
            relation=relation,
            target_key=target_key,
            trust_tier=trust_tier,
            confidence=confidence,
            properties=properties or {},
            evidence=[evidence],
        )
    )


def _parse_root_cause(chunks: list[JiraIssueChunk]) -> str:
    values = []
    for chunk in chunks:
        if chunk.chunk_type != "resolution_rca_chunk":
            continue
        text = normalize_text(chunk.chunk_text)
        match = re.search(r"(?i)\broot cause\s*:\s*(.+)", text)
        candidate = normalize_text(match.group(1) if match else text)
        if candidate and "not explicitly captured" not in candidate.casefold():
            values.append(candidate)
    return " ".join(values)[:2000]


def _parse_explicit_oracle(chunks: list[JiraIssueChunk]) -> str:
    values = [normalize_text(chunk.chunk_text) for chunk in chunks if chunk.chunk_type == "test_evidence_chunk"]
    return " ".join(value for value in values if value)[:2500]


def _parse_fallback_oracle(chunks: list[JiraIssueChunk]) -> str:
    for chunk in chunks:
        if chunk.chunk_type != "learning_behavior_chunk":
            continue
        match = re.search(r"(?i)\bQA oracle\s*:\s*(.+?)(?:\s+Regression risks:|$)", chunk.chunk_text)
        if not match:
            continue
        value = normalize_text(match.group(1))
        if value.casefold().startswith("verify the captured behavior contract"):
            return value
    return ""


def _build_jira_issue(collector: GraphCollector, issue: JiraEnrichedIssue, chunks: list[JiraIssueChunk]) -> dict[str, int]:
    counts = defaultdict(int)
    jira_key = normalize_text(issue.jira_key).upper()
    if not jira_key:
        return counts
    issue_key = stable_key("jira_issue", jira_key)
    label, redactions = _safe_label(issue.summary, jira_key)
    counts["redactions"] += redactions
    fingerprint = issue.source_file_hash or _source_hash(
        jira_key,
        issue.summary,
        issue.expected_behavior,
        issue.actual_behavior,
        issue.updated_at,
    )
    evidence = _evidence(
        source_kind="jira_enriched",
        source_ref=jira_key,
        source_record_id=jira_key,
        source_hash=fingerprint,
        extraction_method="structured_jira_field",
        authority="indexed_jira_snapshot",
        trust_tier="authoritative",
        excerpt=issue.summary,
        tenant_id=_jira_tenant_id(),
        source_updated_at=issue.jira_updated_at or issue.updated_at,
    )
    collector.add_node(
        NodeSpec(
            stable_key=issue_key,
            node_type="jira_issue",
            label=label,
            properties={
                "jira_key": jira_key,
                "status": normalize_text(issue.status)[:120],
                "resolution": normalize_text(issue.resolution)[:120],
                "priority": normalize_text(issue.priority)[:120],
                "issue_type": normalize_text(issue.issue_type)[:120],
                "source_type": normalize_text(issue.source_type)[:80],
                "jira_updated_at": issue.jira_updated_at.isoformat() if issue.jira_updated_at else None,
                "mutable_facts_require_live_validation": True,
            },
            tenant_id=evidence.tenant_id,
            evidence=[evidence],
        )
    )

    for customer in json_values(issue.customer_names or issue.company_names):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="customer",
            value=customer,
            relation="REPORTED_BY",
            evidence=evidence,
            trust_tier="authoritative",
            confidence=1.0,
        )
    components = canonical_component_names(json_values(issue.components))
    for component in components:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="component",
            value=component,
            relation="IN_COMPONENT",
            evidence=evidence,
            trust_tier="authoritative",
            confidence=1.0,
        )
    if not components and json_values(issue.components):
        counts["noncanonical_components"] += 1

    domain = normalize_text(issue.domain or "unknown") or "unknown"
    _add_entity_edge(
        collector,
        source_key=issue_key,
        node_type="domain",
        value=domain,
        relation="IN_DOMAIN",
        evidence=evidence,
        trust_tier="supporting",
        confidence=0.45 if domain.casefold() == "unknown" else 0.7,
        properties={"ranking_only": True},
    )
    if issue.sub_domain:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="subdomain",
            value=issue.sub_domain,
            relation="IN_SUBDOMAIN",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.65,
            properties={"ranking_only": True},
        )

    for feature in json_values(issue.affected_features):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="feature",
            value=feature,
            relation="AFFECTS_FEATURE",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.7,
        )
    for output in json_values(issue.affected_outputs):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="output",
            value=_canonical_output(output),
            relation="AFFECTS_OUTPUT",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.8,
        )
    for entity in json_values(issue.dita_entities):
        _add_dita_entity(collector, issue_key, entity, evidence, relation="MENTIONS_DITA_ENTITY")
    for symptom in json_values(issue.symptoms):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="symptom",
            value=symptom,
            relation="HAS_ACTUAL_BEHAVIOR",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.75,
            properties={"mechanism_signal": True},
        )
    for risk in json_values(issue.qa_risk_tags):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="risk",
            value=risk,
            relation="HAS_RISK",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.65,
            properties={"cannot_define_expected_behavior": True},
        )

    expected = normalize_text(issue.expected_behavior)
    actual = normalize_text(issue.actual_behavior)
    if expected:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="behavior_claim",
            value=expected,
            relation="HAS_EXPECTED_BEHAVIOR",
            evidence=_evidence(
                source_kind="jira_enriched",
                source_ref=jira_key,
                source_record_id=jira_key,
                source_hash=fingerprint,
                extraction_method="explicit_expected_behavior_field",
                authority="jira_acceptance_contract",
                trust_tier="authoritative",
                excerpt=expected,
                tenant_id=evidence.tenant_id,
                source_updated_at=issue.jira_updated_at or issue.updated_at,
            ),
            trust_tier="authoritative",
            confidence=1.0,
            properties={"claim_role": "expected_behavior"},
        )
    if actual:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="symptom",
            value=actual,
            relation="HAS_ACTUAL_BEHAVIOR",
            evidence=evidence,
            trust_tier="authoritative",
            confidence=0.95,
            properties={"claim_role": "actual_behavior", "mechanism_signal": True},
        )

    combined = "\n".join(
        [normalize_text(issue.summary), normalize_text(issue.description), expected, actual]
    )
    for signature in extract_error_signatures(combined):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="error_signature",
            value=signature,
            relation="HAS_ERROR_SIGNATURE",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.9,
            properties={"mechanism_signal": True},
        )
    for route in extract_api_routes(combined):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="api_route",
            value=route,
            relation="USES_API_ROUTE",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.9,
            properties={"mechanism_signal": True},
        )
    for key in extract_config_keys(combined):
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="config_key",
            value=key,
            relation="USES_CONFIG_KEY",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.8,
            properties={"mechanism_signal": True},
        )

    fixed = normalize_text(issue.resolution).casefold() in _IMPLEMENTED_FIX_OUTCOMES
    root_cause = _parse_root_cause(chunks)
    explicit_oracle = _parse_explicit_oracle(chunks)
    fallback_oracle = _parse_fallback_oracle(chunks)
    historical_trust = "historical_verified" if fixed and expected and root_cause and explicit_oracle else "supporting"
    if root_cause:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="root_cause",
            value=root_cause,
            relation="HAS_ROOT_CAUSE",
            evidence=_evidence(
                source_kind="jira_chunk",
                source_ref=jira_key,
                source_record_id=jira_key,
                source_hash=_source_hash(jira_key, root_cause),
                extraction_method="explicit_resolution_rca",
                authority="historical_jira_resolution",
                trust_tier=historical_trust,
                excerpt=root_cause,
                tenant_id=evidence.tenant_id,
                source_updated_at=issue.jira_updated_at or issue.updated_at,
            ),
            trust_tier=historical_trust,
            confidence=0.95 if historical_trust == "historical_verified" else 0.75,
            properties={"root_cause_source": "explicit_resolution_rca", "mechanism_signal": True},
        )
    if explicit_oracle:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="qa_oracle",
            value=explicit_oracle,
            relation="HAS_QA_ORACLE",
            evidence=_evidence(
                source_kind="jira_chunk",
                source_ref=jira_key,
                source_record_id=jira_key,
                source_hash=_source_hash(jira_key, explicit_oracle),
                extraction_method="explicit_test_evidence",
                authority="historical_jira_test_evidence",
                trust_tier=historical_trust,
                excerpt=explicit_oracle,
                tenant_id=evidence.tenant_id,
                source_updated_at=issue.jira_updated_at or issue.updated_at,
            ),
            trust_tier=historical_trust,
            confidence=0.95 if historical_trust == "historical_verified" else 0.75,
            properties={"qa_oracle_source": "explicit_test_evidence"},
        )
    elif fallback_oracle:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="qa_oracle",
            value=fallback_oracle,
            relation="HAS_QA_ORACLE",
            evidence=_evidence(
                source_kind="jira_chunk",
                source_ref=jira_key,
                source_record_id=jira_key,
                source_hash=_source_hash(jira_key, fallback_oracle),
                extraction_method="derived_contract_fallback",
                authority="derived_jira_learning",
                trust_tier="candidate",
                excerpt=fallback_oracle,
                tenant_id=evidence.tenant_id,
            ),
            trust_tier="candidate",
            confidence=0.2,
            properties={
                "qa_oracle_source": "derived_contract_fallback",
                "cannot_define_expected_behavior": True,
            },
        )
    return counts


def _jira_version_values(metadata: dict[str, Any], key: str) -> list[str]:
    return json_values(metadata.get(key))


def _canonical_release_value(value: str) -> tuple[str, str]:
    text = normalize_text(value)
    cloud = re.search(
        r"(?i)\b(20\d{2})[./ -](0?[1-9]|1[0-2])(?:[./ -]0)?(?:[ -]?(sp\d+))?\b",
        text,
    )
    if cloud:
        year, month, service_pack = cloud.groups()
        version = f"{year}.{int(month):02d}.0" + (
            f"-{service_pack.casefold()}" if service_pack else ""
        )
        return "cloud", version
    on_prem = re.search(r"(?i)\b(\d+)\.(\d+)\.(\d+)(?:[ -]?(sp\d+))?\b", text)
    if on_prem:
        major, minor, patch, service_pack = on_prem.groups()
        version = f"{int(major)}.{int(minor)}.{int(patch)}" + (
            f"-{service_pack.casefold()}" if service_pack else ""
        )
        return "on-prem", version
    return "jira", text


def _add_jira_release_edges(
    collector: GraphCollector,
    *,
    jira_node_key: str,
    values: list[str],
    relation: str,
    evidence: EvidenceSpec,
) -> None:
    for value in values:
        version = normalize_text(value)
        if not version:
            continue
        channel, canonical_version = _canonical_release_value(version)
        release_key = stable_key("release", f"{channel}:{canonical_version}")
        collector.add_node(
            NodeSpec(
                stable_key=release_key,
                node_type="release",
                label=canonical_version,
                properties={"channel": channel, "version": canonical_version, "mutable_fact": True},
                tenant_id=evidence.tenant_id,
                evidence=[evidence],
            )
        )
        collector.add_edge(
            EdgeSpec(
                source_key=jira_node_key,
                relation=relation,
                target_key=release_key,
                trust_tier="authoritative",
                confidence=1.0,
                properties={"requires_live_jira_validation": True},
                evidence=[evidence],
            )
        )


def _build_jira_chroma_record(collector: GraphCollector, record: dict[str, Any]) -> None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    jira_key = normalize_text(metadata.get("jira_key") or str(record.get("id") or "").split("::", 1)[0]).upper()
    if not jira_key or not _JIRA_KEY_RE.fullmatch(jira_key):
        return
    chunk_id = normalize_text(record.get("id"))
    document = str(record.get("document") or "")
    fingerprint = normalize_text(
        metadata.get("source_file_hash")
        or metadata.get("chunk_content_hash")
        or metadata.get("source_content_hash")
    ) or _source_hash(chunk_id, document)
    evidence = _evidence(
        source_kind="jira_chroma",
        source_ref=jira_key,
        source_record_id=jira_key,
        source_chunk_id=chunk_id,
        source_hash=fingerprint,
        extraction_method="trusted_indexed_jira_metadata",
        authority="indexed_jira_snapshot",
        trust_tier="authoritative",
        excerpt=document,
        tenant_id=_jira_tenant_id(),
    )
    issue_key = stable_key("jira_issue", jira_key)
    collector.add_node(
        NodeSpec(
            stable_key=issue_key,
            node_type="jira_issue",
            label=normalize_text(metadata.get("title")) or jira_key,
            properties={
                "jira_key": jira_key,
                "status": normalize_text(metadata.get("status"))[:120],
                "resolution": normalize_text(metadata.get("resolution"))[:120],
                "priority": normalize_text(metadata.get("priority"))[:120],
                "issue_type": normalize_text(metadata.get("issue_type"))[:120],
                "jira_updated_at": normalize_text(metadata.get("jira_updated_at") or metadata.get("updated_at"))[:80],
                "mutable_facts_require_live_validation": True,
            },
            tenant_id=evidence.tenant_id,
            evidence=[evidence],
        )
    )
    chunk_key = stable_key("source_chunk", f"{CHROMA_COLLECTION_JIRA_QA}:{chunk_id}")
    collector.add_node(
        NodeSpec(
            stable_key=chunk_key,
            node_type="source_chunk",
            label=f"{jira_key} — {normalize_text(metadata.get('chunk_type')) or 'indexed evidence'}",
            properties={
                "collection": CHROMA_COLLECTION_JIRA_QA,
                "chunk_id": chunk_id,
                "evidence_type": normalize_text(metadata.get("chunk_type"))[:120],
            },
            tenant_id=evidence.tenant_id,
            evidence=[evidence],
        )
    )
    collector.add_edge(
        EdgeSpec(
            source_key=issue_key,
            relation="HAS_CHUNK",
            target_key=chunk_key,
            trust_tier="authoritative",
            confidence=1.0,
            evidence=[evidence],
        )
    )
    _add_jira_release_edges(
        collector,
        jira_node_key=issue_key,
        values=_jira_version_values(metadata, "affected_versions"),
        relation="AFFECTS_VERSION",
        evidence=evidence,
    )
    _add_jira_release_edges(
        collector,
        jira_node_key=issue_key,
        values=_jira_version_values(metadata, "fix_versions"),
        relation="FIXED_IN_RELEASE",
        evidence=evidence,
    )

    if normalize_text(metadata.get("chunk_type")) != "learning_behavior_chunk":
        return
    try:
        from app.services.jira_retrieval_service import extract_structured_learning_evidence

        learning = extract_structured_learning_evidence(
            {"chunk_type": "learning_behavior_chunk", "document": document, "metadata": metadata}
        )
    except Exception:
        learning = {}
    reusable = bool(
        learning.get("reuse_mode") == "verified_regression_contract"
        and normalize_text(learning.get("behavior_contract"))
        and normalize_text(learning.get("root_cause"))
        and normalize_text(learning.get("qa_oracle"))
    )
    trust = "historical_verified" if reusable else "candidate"
    extraction = "verified_structured_learning" if reusable else "candidate_structured_learning"
    for field, node_type, relation, source_property in (
        ("behavior_contract", "behavior_claim", "HAS_EXPECTED_BEHAVIOR", "behavior_contract_source"),
        ("root_cause", "root_cause", "HAS_ROOT_CAUSE", "root_cause_source"),
        ("qa_oracle", "qa_oracle", "HAS_QA_ORACLE", "qa_oracle_source"),
    ):
        value = normalize_text(learning.get(field))
        if not value:
            continue
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type=node_type,
            value=value,
            relation=relation,
            evidence=_evidence(
                source_kind="jira_chroma",
                source_ref=jira_key,
                source_record_id=jira_key,
                source_chunk_id=chunk_id,
                source_hash=fingerprint,
                extraction_method=extraction,
                authority="verified_historical_jira" if reusable else "derived_jira_learning",
                trust_tier=trust,
                excerpt=value,
                tenant_id=evidence.tenant_id,
            ),
            trust_tier=trust,
            confidence=0.9 if reusable else 0.2,
            properties={
                source_property: extraction,
                "mechanism_signal": node_type in {"behavior_claim", "root_cause"},
                "cannot_define_expected_behavior": not reusable,
            },
        )
    risk = normalize_text(learning.get("regression_risks"))
    if risk:
        _add_entity_edge(
            collector,
            source_key=issue_key,
            node_type="risk",
            value=risk,
            relation="HAS_RISK",
            evidence=evidence,
            trust_tier="supporting" if reusable else "candidate",
            confidence=0.7 if reusable else 0.2,
            properties={"cannot_define_expected_behavior": True},
        )


def _canonical_output(value: str) -> str:
    token = normalized_token(value)
    aliases = {
        "pdf": "PDF",
        "pdf2": "DITA-OT PDF2",
        "native-pdf": "Native PDF",
        "html": "HTML",
        "html5": "HTML5",
        "aem-sites": "AEM Sites",
        "experience-manager-sites": "AEM Sites",
        "dita-ot": "DITA-OT",
    }
    return aliases.get(token, normalize_text(value))


def _add_dita_entity(
    collector: GraphCollector,
    source_key: str,
    entity: str,
    evidence: EvidenceSpec,
    *,
    relation: str,
) -> None:
    value = normalize_text(entity)
    if not value:
        return
    if value.startswith("@"):
        node_type = "dita_attribute"
        label = value
        key_value = value[1:]
    else:
        node_type = "dita_element"
        label = value.strip("<>")
        key_value = label
    if not key_value or " " in key_value or len(key_value) > 100:
        return
    target_key = stable_key(node_type, key_value)
    collector.add_node(
        NodeSpec(
            stable_key=target_key,
            node_type=node_type,
            label=label,
            tenant_id=evidence.tenant_id,
            evidence=[evidence],
        )
    )
    collector.add_edge(
        EdgeSpec(
            source_key=source_key,
            relation=relation,
            target_key=target_key,
            trust_tier="supporting",
            confidence=0.75,
            evidence=[evidence],
        )
    )


def _flush(writer: GraphWriter | GraphCounter, collector: GraphCollector, session: Session | None) -> None:
    if not collector.nodes and not collector.edges:
        return
    writer.write(collector.nodes.values(), collector.edges.values())
    if session is not None:
        session.commit()
    collector.clear()


def _build_jira_source(
    session: Session,
    writer: GraphWriter | GraphCounter,
    *,
    batch_size: int,
    persist: bool,
) -> dict[str, Any]:
    scanned = 0
    source_counts = defaultdict(int)
    last_id = 0
    while True:
        issues = (
            session.query(JiraEnrichedIssue)
            .filter(JiraEnrichedIssue.id > last_id)
            .order_by(JiraEnrichedIssue.id.asc())
            .limit(batch_size)
            .all()
        )
        if not issues:
            break
        keys = [issue.jira_key for issue in issues]
        grouped: dict[str, list[JiraIssueChunk]] = defaultdict(list)
        for chunk in session.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key.in_(keys)).all():
            grouped[chunk.jira_key].append(chunk)
        collector = GraphCollector()
        for issue in issues:
            counts = _build_jira_issue(collector, issue, grouped.get(issue.jira_key, []))
            for key, value in counts.items():
                source_counts[key] += value
            scanned += 1
        _flush(writer, collector, session if persist else None)
        last_id = issues[-1].id
    source_counts["sql_scanned"] = scanned
    source_counts["sql_expected"] = session.query(JiraEnrichedIssue).count()
    if scanned != source_counts["sql_expected"]:
        raise RuntimeError(
            f"Jira SQL graph scan count mismatch: scanned={scanned}, expected={source_counts['sql_expected']}"
        )

    chroma_expected = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
    chroma_scanned = 0
    collector = GraphCollector()
    for record in iter_collection_records(
        CHROMA_COLLECTION_JIRA_QA,
        include_documents=True,
        batch_size=batch_size,
    ):
        _build_jira_chroma_record(collector, record)
        chroma_scanned += 1
        if chroma_scanned % batch_size == 0:
            _flush(writer, collector, session if persist else None)
    _flush(writer, collector, session if persist else None)
    source_counts["chroma_scanned"] = chroma_scanned
    source_counts["chroma_expected"] = chroma_expected
    source_counts["scan_complete"] = (
        scanned == source_counts["sql_expected"] and chroma_scanned == chroma_expected
    )
    if not source_counts["scan_complete"]:
        raise RuntimeError(
            "Jira graph scan count mismatch: "
            f"sql={scanned}/{source_counts['sql_expected']}, chroma={chroma_scanned}/{chroma_expected}"
        )
    return dict(source_counts)


def upsert_jira_issue_into_generation(
    session: Session,
    writer: GraphWriter,
    jira_key: str,
) -> dict[str, Any]:
    """Rebuild one Jira issue from SQL and its current bounded Chroma records."""
    key = normalize_text(jira_key).upper()
    issue = session.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == key).first()
    records = get_documents_where(CHROMA_COLLECTION_JIRA_QA, {"jira_key": key}, limit=5000)
    if issue is None and not records:
        return {"found": False, "jira_key": key, "records": 0}
    collector = GraphCollector()
    if issue is not None:
        chunks = session.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == key).all()
        _build_jira_issue(collector, issue, chunks)
    for record in records:
        _build_jira_chroma_record(collector, record)
    _flush(writer, collector, session)
    return {"found": True, "jira_key": key, "records": len(records), "sql_issue": issue is not None}


def upsert_document_chunk_into_generation(
    session: Session,
    writer: GraphWriter,
    chunk_id: str,
) -> dict[str, Any]:
    records = get_collection_records_by_ids(
        CHROMA_COLLECTION_AEM_GUIDES,
        [normalize_text(chunk_id)],
        include_documents=True,
    )
    if not records:
        return {"found": False, "chunk_id": normalize_text(chunk_id)}
    collector = GraphCollector()
    counts = _build_doc_record(collector, records[0])
    _flush(writer, collector, session)
    return {"found": True, "chunk_id": normalize_text(chunk_id), **counts}


def upsert_dita_record_into_generation(
    session: Session,
    writer: GraphWriter,
    record_id: str,
) -> dict[str, Any]:
    normalized = normalize_text(record_id)
    if normalized.startswith("sql:"):
        chunk = session.get(DitaSpecChunk, normalized.removeprefix("sql:"))
        if chunk is None:
            return {"found": False, "record_id": normalized}
        collector = GraphCollector()
        _build_dita_sql_chunk(collector, chunk)
        _flush(writer, collector, session)
        return {"found": True, "record_id": normalized, "source": "sql"}
    records = get_collection_records_by_ids(
        CHROMA_COLLECTION_DITA_SPEC,
        [normalized],
        include_documents=True,
    )
    if not records:
        return {"found": False, "record_id": normalized}
    collector = GraphCollector()
    _build_dita_chroma_record(collector, records[0])
    _flush(writer, collector, session)
    return {"found": True, "record_id": normalized, "source": "chroma"}


def _release_from_url(url: str) -> tuple[str, str] | None:
    lowered = url.casefold()
    cloud = re.search(r"/(20\d{2})-releases/(\d{2})(\d{2})(?:-0)?(?:-(sp\d+))?-release/", lowered)
    if cloud:
        year, short_year, month, service_pack = cloud.groups()
        if short_year != year[-2:]:
            return None
        version = f"{year}.{int(month):02d}.0" + (f"-{service_pack}" if service_pack else "")
        return "cloud", version
    on_prem = re.search(r"/(\d)(\d)(\d)(?:-(sp\d+))?-release/", lowered)
    if on_prem:
        major, minor, patch, service_pack = on_prem.groups()
        version = f"{major}.{minor}.{patch}" + (f"-{service_pack}" if service_pack else "")
        return "on-prem", version
    legacy = re.search(r"/(\d)(\d)-release/", lowered)
    if legacy:
        return "on-prem", f"{legacy.group(1)}.{legacy.group(2)}"
    return None


def _metadata_values(metadata: dict[str, Any], *keys: str) -> list[str]:
    values = []
    for key in keys:
        values.extend(json_values(metadata.get(key)))
    return list(dict.fromkeys(value for value in values if value))


def _build_doc_record(collector: GraphCollector, record: dict[str, Any]) -> dict[str, int]:
    counts = defaultdict(int)
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    document = str(record.get("document") or "")
    chunk_id = normalize_text(record.get("id"))
    url = canonical_url(
        metadata.get("canonical_url")
        or metadata.get("source_url")
        or metadata.get("url")
        or metadata.get("source_path")
    )
    source_ref = url or normalize_text(metadata.get("source_path")) or f"chroma:{chunk_id}"
    page_key = stable_key("documentation_page", source_ref)
    chunk_key = stable_key("source_chunk", f"{CHROMA_COLLECTION_AEM_GUIDES}:{chunk_id}")
    title, redactions = _safe_label(metadata.get("title"), source_ref)
    counts["redactions"] += redactions
    source_type = normalize_text(metadata.get("source_type") or metadata.get("source_product_family"))
    official = "experience" in source_type.casefold() or "adobe" in source_type.casefold() or "experienceleague" in source_ref.casefold()
    authority = "official_experience_league" if official else "indexed_product_documentation"
    trust = "authoritative" if official else "supporting"
    fingerprint = normalize_text(metadata.get("chunk_content_hash") or metadata.get("source_content_hash")) or _source_hash(
        chunk_id, document
    )
    evidence = _evidence(
        source_kind="aem_guides_chroma",
        source_ref=source_ref,
        source_record_id=chunk_id,
        source_chunk_id=chunk_id,
        source_hash=fingerprint,
        extraction_method="indexed_document_chunk",
        authority=authority,
        trust_tier=trust,
        excerpt=document,
    )
    collector.add_node(
        NodeSpec(
            stable_key=page_key,
            node_type="documentation_page",
            label=title,
            properties={"canonical_url": url or None, "source_type": source_type, "official": official},
            evidence=[evidence],
        )
    )
    collector.add_node(
        NodeSpec(
            stable_key=chunk_key,
            node_type="source_chunk",
            label=f"{title} — {normalize_text(metadata.get('section') or metadata.get('chunk_index'))}"[:500],
            properties={
                "collection": CHROMA_COLLECTION_AEM_GUIDES,
                "chunk_id": chunk_id,
                "evidence_type": normalize_text(metadata.get("evidence_type"))[:120],
            },
            evidence=[evidence],
        )
    )
    collector.add_edge(
        EdgeSpec(
            source_key=page_key,
            relation="HAS_CHUNK",
            target_key=chunk_key,
            trust_tier=trust,
            confidence=1.0,
            evidence=[evidence],
        )
    )

    release = _release_from_url(url)
    if release:
        channel, version = release
        _add_entity_edge(
            collector,
            source_key=page_key,
            node_type="release",
            value=f"{channel}:{version}",
            relation="APPLIES_TO_RELEASE",
            evidence=evidence,
            trust_tier="authoritative",
            confidence=1.0,
            properties={"channel": channel, "version": version},
        )
    for feature in _metadata_values(metadata, "feature_areas", "feature_area"):
        _add_entity_edge(
            collector,
            source_key=page_key,
            node_type="feature",
            value=feature,
            relation="DOCUMENTS_FEATURE",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.65,
            properties={"ranking_only": True},
        )
    for output in _metadata_values(metadata, "output_contexts", "enrich_outputs"):
        _add_entity_edge(
            collector,
            source_key=page_key,
            node_type="output",
            value=_canonical_output(output),
            relation="DOCUMENTS_OUTPUT",
            evidence=evidence,
            trust_tier="supporting",
            confidence=0.7,
        )
    for entity in _metadata_values(metadata, "detected_constructs", "enrich_entities"):
        _add_dita_entity(collector, page_key, entity, evidence, relation="MENTIONS_DITA_ENTITY")

    exact_claims = _metadata_values(metadata, "workflow_cues", "expected_behavior")
    for claim in exact_claims:
        if not exact_source_claim(claim, document):
            counts["derived_claims_rejected"] += 1
            continue
        _add_entity_edge(
            collector,
            source_key=page_key,
            node_type="behavior_claim",
            value=claim,
            relation="HAS_EXPECTED_BEHAVIOR",
            evidence=_evidence(
                source_kind="aem_guides_chroma",
                source_ref=source_ref,
                source_record_id=chunk_id,
                source_chunk_id=chunk_id,
                source_hash=fingerprint,
                extraction_method="exact_source_text_containment",
                authority=authority,
                trust_tier=trust,
                excerpt=claim,
            ),
            trust_tier=trust,
            confidence=0.95 if official else 0.75,
            properties={"exact_source_text": True},
        )
    for jira_key in sorted(set(_JIRA_KEY_RE.findall(document.upper())))[:100]:
        jira_node_key = stable_key("jira_issue", jira_key)
        collector.add_node(
            NodeSpec(
                stable_key=jira_node_key,
                node_type="jira_issue",
                label=jira_key,
                properties={"jira_key": jira_key, "mutable_facts_require_live_validation": True},
            )
        )
        collector.add_edge(
            EdgeSpec(
                source_key=page_key,
                relation="MENTIONS_ISSUE",
                target_key=jira_node_key,
                trust_tier=trust,
                confidence=0.95,
                evidence=[evidence],
            )
        )
    return counts


def _build_docs_source(
    writer: GraphWriter | GraphCounter,
    *,
    batch_size: int,
    session: Session | None,
) -> dict[str, Any]:
    expected = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)
    scanned = 0
    source_counts = defaultdict(int)
    collector = GraphCollector()
    for record in iter_collection_records(
        CHROMA_COLLECTION_AEM_GUIDES,
        include_documents=True,
        batch_size=batch_size,
    ):
        counts = _build_doc_record(collector, record)
        for key, value in counts.items():
            source_counts[key] += value
        scanned += 1
        if scanned % batch_size == 0:
            _flush(writer, collector, session)
    _flush(writer, collector, session)
    source_counts.update({"scanned": scanned, "expected": expected, "scan_complete": scanned == expected})
    if scanned != expected:
        raise RuntimeError(f"Documentation graph scan count mismatch: scanned={scanned}, expected={expected}")
    return dict(source_counts)


def _structured_json(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    text = normalize_text(value)
    if not text:
        return []
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return [item.strip() for item in re.split(r"[,|]", text) if item.strip()]


def _dita_evidence(chunk: DitaSpecChunk, trust: str) -> EvidenceSpec:
    source_ref = canonical_url(chunk.source_url) or f"dita-spec:{chunk.id}"
    return _evidence(
        source_kind="dita_spec_sql",
        source_ref=source_ref,
        source_record_id=chunk.id,
        source_hash=_source_hash(chunk.id, chunk.text_content, chunk.attributes, chunk.children_elements),
        extraction_method="structured_dita_spec_field",
        authority="oasis_dita_spec" if trust == "authoritative" else "curated_dita_seed",
        trust_tier=trust,
        excerpt=chunk.text_content,
    )


def _build_dita_sql_chunk(collector: GraphCollector, chunk: DitaSpecChunk) -> None:
    element = normalize_text(chunk.element_name).strip("<>")
    if not element:
        return
    trust = "authoritative" if "oasis" in normalize_text(chunk.source_url).casefold() else "supporting"
    evidence = _dita_evidence(chunk, trust)
    element_key = stable_key("dita_element", element)
    collector.add_node(
        NodeSpec(
            stable_key=element_key,
            node_type="dita_element",
            label=f"<{element}>",
            properties={"content_type": normalize_text(chunk.content_type)[:80]},
            evidence=[evidence],
        )
    )
    chunk_key = stable_key("source_chunk", f"dita_sql:{chunk.id}")
    collector.add_node(
        NodeSpec(
            stable_key=chunk_key,
            node_type="source_chunk",
            label=f"DITA specification: {element}",
            properties={"collection": "dita_spec_sql", "chunk_id": chunk.id},
            evidence=[evidence],
        )
    )
    collector.add_edge(
        EdgeSpec(
            source_key=element_key,
            relation="HAS_CHUNK",
            target_key=chunk_key,
            trust_tier=trust,
            confidence=1.0,
            evidence=[evidence],
        )
    )

    children = _structured_json(chunk.children_elements)
    if isinstance(children, dict):
        children = list(children)
    for child in json_values(children):
        child = child.strip("<>")
        if not child or " " in child:
            continue
        child_key = stable_key("dita_element", child)
        collector.add_node(NodeSpec(stable_key=child_key, node_type="dita_element", label=f"<{child}>"))
        collector.add_edge(
            EdgeSpec(
                source_key=element_key,
                relation="ALLOWS_CHILD",
                target_key=child_key,
                trust_tier=trust,
                confidence=0.95,
                evidence=[evidence],
            )
        )
    parent = normalize_text(chunk.parent_element).strip("<>")
    if parent and " " not in parent and parent != element:
        parent_key = stable_key("dita_element", parent)
        collector.add_node(NodeSpec(stable_key=parent_key, node_type="dita_element", label=f"<{parent}>"))
        collector.add_edge(
            EdgeSpec(
                source_key=parent_key,
                relation="ALLOWS_CHILD",
                target_key=element_key,
                trust_tier=trust,
                confidence=0.9,
                evidence=[evidence],
            )
        )

    attributes = _structured_json(chunk.attributes)
    if isinstance(attributes, dict):
        attribute_items = attributes.items()
    else:
        attribute_items = ((item, "") for item in json_values(attributes))
    for attribute, description in attribute_items:
        attribute_name = normalize_text(attribute).lstrip("@").split()[0] if normalize_text(attribute) else ""
        if not attribute_name:
            continue
        attribute_key = stable_key("dita_attribute", attribute_name)
        collector.add_node(
            NodeSpec(
                stable_key=attribute_key,
                node_type="dita_attribute",
                label=f"@{attribute_name}",
                properties={"description": normalize_text(description)[:500]},
                evidence=[evidence],
            )
        )
        collector.add_edge(
            EdgeSpec(
                source_key=element_key,
                relation="HAS_ATTRIBUTE",
                target_key=attribute_key,
                trust_tier=trust,
                confidence=0.95,
                evidence=[evidence],
            )
        )

    text = normalize_text(chunk.text_content)
    for regex, relation in ((_SPECIALIZES_RE, "SPECIALIZES"), (_CONSTRAINS_RE, "CONSTRAINS")):
        for base in sorted(set(match.group(1).rstrip(".,;:") for match in regex.finditer(text))):
            if base == element:
                continue
            base_key = stable_key("dita_element", base)
            collector.add_node(NodeSpec(stable_key=base_key, node_type="dita_element", label=f"<{base}>"))
            collector.add_edge(
                EdgeSpec(
                    source_key=element_key,
                    relation=relation,
                    target_key=base_key,
                    trust_tier=trust,
                    confidence=0.85,
                    evidence=[evidence],
                )
            )


def _build_dita_chroma_record(collector: GraphCollector, record: dict[str, Any]) -> None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    document = str(record.get("document") or "")
    chunk_id = normalize_text(record.get("id"))
    element = normalize_text(metadata.get("element_name")).strip("<>")
    source_ref = canonical_url(metadata.get("source_url") or metadata.get("url")) or f"dita-chroma:{chunk_id}"
    official = "oasis" in source_ref.casefold()
    trust = "authoritative" if official else "supporting"
    evidence = _evidence(
        source_kind="dita_spec_chroma",
        source_ref=source_ref,
        source_record_id=chunk_id,
        source_chunk_id=chunk_id,
        source_hash=normalize_text(metadata.get("chunk_content_hash")) or _source_hash(chunk_id, document),
        extraction_method="indexed_dita_spec_chunk",
        authority="oasis_dita_spec" if official else "indexed_dita_spec",
        trust_tier=trust,
        excerpt=document,
    )
    chunk_key = stable_key("source_chunk", f"{CHROMA_COLLECTION_DITA_SPEC}:{chunk_id}")
    collector.add_node(
        NodeSpec(
            stable_key=chunk_key,
            node_type="source_chunk",
            label=f"DITA specification chunk {chunk_id}",
            properties={"collection": CHROMA_COLLECTION_DITA_SPEC, "chunk_id": chunk_id},
            evidence=[evidence],
        )
    )
    if element:
        element_key = stable_key("dita_element", element)
        collector.add_node(NodeSpec(stable_key=element_key, node_type="dita_element", label=f"<{element}>", evidence=[evidence]))
        collector.add_edge(
            EdgeSpec(
                source_key=element_key,
                relation="HAS_CHUNK",
                target_key=chunk_key,
                trust_tier=trust,
                confidence=1.0,
                evidence=[evidence],
            )
        )


def _build_dita_source(
    session: Session,
    writer: GraphWriter | GraphCounter,
    *,
    batch_size: int,
    persist: bool,
) -> dict[str, Any]:
    sql_expected = session.query(DitaSpecChunk).count()
    sql_scanned = 0
    collector = GraphCollector()
    for chunk in session.query(DitaSpecChunk).yield_per(batch_size):
        _build_dita_sql_chunk(collector, chunk)
        sql_scanned += 1
        if sql_scanned % batch_size == 0:
            _flush(writer, collector, session if persist else None)
    _flush(writer, collector, session if persist else None)
    if sql_scanned != sql_expected:
        raise RuntimeError(f"DITA SQL scan count mismatch: scanned={sql_scanned}, expected={sql_expected}")

    chroma_expected = get_collection_count(CHROMA_COLLECTION_DITA_SPEC)
    chroma_scanned = 0
    for record in iter_collection_records(
        CHROMA_COLLECTION_DITA_SPEC,
        include_documents=True,
        batch_size=batch_size,
    ):
        _build_dita_chroma_record(collector, record)
        chroma_scanned += 1
        if chroma_scanned % batch_size == 0:
            _flush(writer, collector, session if persist else None)
    _flush(writer, collector, session if persist else None)
    if chroma_scanned != chroma_expected:
        raise RuntimeError(
            f"DITA Chroma scan count mismatch: scanned={chroma_scanned}, expected={chroma_expected}"
        )
    return {
        "sql_scanned": sql_scanned,
        "sql_expected": sql_expected,
        "chroma_scanned": chroma_scanned,
        "chroma_expected": chroma_expected,
        "scan_complete": sql_scanned == sql_expected and chroma_scanned == chroma_expected,
    }


def rebuild_evidence_graph(
    *,
    dry_run: bool = False,
    sources: Iterable[str] | None = None,
    batch_size: int = 500,
    created_by: str | None = None,
    _lease_owner: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    selected = [normalize_text(source).casefold() for source in (sources or DEFAULT_GRAPH_SOURCES)]
    selected = list(dict.fromkeys(source for source in selected if source))
    unsupported = [source for source in selected if source not in DEFAULT_GRAPH_SOURCES]
    if unsupported:
        raise ValueError(f"Unsupported evidence graph sources: {', '.join(unsupported)}")
    if not dry_run and set(selected) != set(DEFAULT_GRAPH_SOURCES):
        missing = sorted(set(DEFAULT_GRAPH_SOURCES) - set(selected))
        return {
            "available": False,
            "valid": False,
            "dry_run": False,
            "status": "partial_apply_refused",
            "sources": {},
            "counts": {},
            "errors": [
                "Applied evidence graph rebuilds must include jira, docs, and dita; "
                f"missing sources: {', '.join(missing)}. Use --dry-run for partial source audits."
            ],
            "generation_id": None,
            "promoted": False,
            "performance": _performance_result(started_at),
        }
    page_size = max(10, min(int(batch_size or 500), 5000))
    session = SessionLocal()
    acquired_owner: str | None = None
    generation: EvidenceGraphGeneration | None = None
    sync_run = None
    source_results: dict[str, Any] = {}
    errors: list[str] = []
    try:
        if _lease_owner is None:
            acquired_owner = acquire_graph_lease(session, seconds=1800)
            if acquired_owner is None:
                return {
                    "available": True,
                    "valid": False,
                    "dry_run": dry_run,
                    "status": "lease_held",
                    "sources": {},
                    "counts": {},
                    "errors": ["Another evidence graph synchronization or rebuild holds the database lease."],
                    "generation_id": None,
                    "promoted": False,
                    "performance": _performance_result(started_at),
                }
        previous = active_generation(session)
        previous_generation_id = previous.id if previous else None
        if dry_run:
            writer: GraphWriter | GraphCounter = GraphCounter()
        else:
            generation = create_generation(
                session,
                mode="full",
                created_by=created_by,
                source_snapshot={
                    "sources": selected,
                    "batch_size": page_size,
                    "previous_generation_id": previous_generation_id,
                },
            )
            sync_run = create_sync_run(
                session,
                mode="full",
                sources=selected,
                dry_run=False,
                generation_id=generation.id,
            )
            session.commit()
            writer = GraphWriter(session, generation.id)

        for source in selected:
            try:
                if source == "jira":
                    source_results[source] = _build_jira_source(
                        session, writer, batch_size=page_size, persist=not dry_run
                    )
                elif source == "docs":
                    source_results[source] = _build_docs_source(
                        writer, batch_size=page_size, session=session if not dry_run else None
                    )
                elif source == "dita":
                    source_results[source] = _build_dita_source(
                        session, writer, batch_size=page_size, persist=not dry_run
                    )
                if not bool(source_results[source].get("scan_complete")):
                    raise RuntimeError(f"{source} source scan did not report complete coverage")
            except Exception as exc:
                errors.append(f"{source}: {_safe_error(exc)}")
                break

        counts = writer.counts() if isinstance(writer, GraphCounter) else dict(writer.counts)
        performance = _performance_result(started_at)
        if not errors and not performance["accepted"]:
            errors.append(
                "Evidence graph rebuild performance acceptance failed: "
                f"elapsed={performance['elapsed_seconds']}s, "
                f"peak_memory={performance['peak_memory_mb']}MB, limits={performance['limits']}"
            )
        result = {
            "available": not errors,
            "valid": not errors,
            "dry_run": dry_run,
            "sources": source_results,
            "counts": counts,
            "errors": errors,
            "generation_id": generation.id if generation else None,
            "promoted": False,
            "performance": performance,
            "reconciliation": {
                "previous_generation_id": previous_generation_id,
                "status": "dry_run_not_persisted" if dry_run else "pending",
            },
        }
        if dry_run:
            return result

        now = datetime.utcnow()
        generation.counts = counts
        generation.errors = errors
        generation.completed_at = now
        if errors:
            generation.status = "failed"
            sync_run.status = "failed"
            sync_run.errors = errors
            sync_run.counters = counts
            sync_run.completed_at = now
            session.commit()
            return result

        generation.status = "ready"
        sync_run.status = "validating"
        sync_run.counters = counts
        session.commit()
        reconciliation = _reconciliation_delta(
            session,
            previous_generation_id=previous_generation_id,
            generation_id=generation.id,
        )
        generation.source_snapshot = {
            **dict(generation.source_snapshot or {}),
            "reconciliation": reconciliation,
        }
        session.commit()
        audit = promote_generation(session, generation.id)
        for source, source_result in source_results.items():
            update_source_checkpoint(
                session,
                source_name=f"evidence_graph:{source}",
                generation_id=generation.id,
                counts=source_result,
                cursor={"mode": "full", "completed_at": now.isoformat()},
            )
        update_source_checkpoint(
            session,
            source_name="evidence_graph:reconciliation",
            generation_id=generation.id,
            counts=audit.get("counts") or {},
            cursor={"mode": "full", "completed_at": now.isoformat()},
        )
        sync_run.status = "succeeded"
        sync_run.completed_at = datetime.utcnow()
        session.commit()
        result["audit"] = audit
        result["reconciliation"] = reconciliation
        result["valid"] = bool(audit.get("valid"))
        result["promoted"] = bool(audit.get("valid"))
        return result
    except Exception as exc:
        session.rollback()
        safe_error = _safe_error(exc)
        if generation is not None:
            generation = session.get(EvidenceGraphGeneration, generation.id)
            if generation is not None:
                generation.status = "failed"
                generation.errors = [safe_error]
                generation.completed_at = datetime.utcnow()
            if sync_run is not None:
                sync_run = session.get(type(sync_run), sync_run.id)
                if sync_run is not None:
                    sync_run.status = "failed"
                    sync_run.errors = [safe_error]
                    sync_run.completed_at = datetime.utcnow()
            session.commit()
        return {
            "available": False,
            "valid": False,
            "dry_run": dry_run,
            "sources": source_results,
            "counts": {},
            "errors": [safe_error],
            "generation_id": generation.id if generation else None,
            "promoted": False,
            "performance": _performance_result(started_at),
        }
    finally:
        if acquired_owner:
            release_graph_lease(session, acquired_owner)
        session.close()
