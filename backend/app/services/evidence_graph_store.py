"""Transactional storage, generation promotion, queueing, and audit operations."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import os
import socket
import uuid
from typing import Any, Iterable

from sqlalchemy import func, inspect, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.db.evidence_graph_models import (
    EvidenceGraphAssertion,
    EvidenceGraphEdge,
    EvidenceGraphGeneration,
    EvidenceGraphNode,
    EvidenceGraphQueryAudit,
    EvidenceGraphSourceEvent,
    EvidenceGraphSourceState,
    EvidenceGraphSyncRun,
)
from app.services.evidence_graph_contract import (
    GRAPH_SCHEMA_VERSION,
    GRAPH_STATE_KEY,
    NODE_TYPES,
    RELATIONS,
    TRUST_WEIGHTS,
    TRUST_TIERS,
    EdgeSpec,
    EvidenceSpec,
    NodeSpec,
    contains_sensitive_text,
    deterministic_id,
    sanitize_excerpt,
    sanitize_structured_properties,
)


class GraphWriter:
    """Idempotent writer for one immutable/building graph generation."""

    def __init__(self, session: Session, generation_id: str):
        self.session = session
        self.generation_id = generation_id
        self.node_ids: dict[str, str] = {}
        self.counts = Counter()

    def write(self, nodes: Iterable[NodeSpec], edges: Iterable[EdgeSpec]) -> dict[str, int]:
        node_assertions: list[tuple[NodeSpec, str]] = []
        for node in nodes:
            node_id = self._write_node(node, write_assertions=False)
            node_assertions.append((node, node_id))
        self.session.flush()
        for node, node_id in node_assertions:
            for evidence in node.evidence:
                self._write_assertion(evidence, node_id=node_id)
        self.session.flush()
        edge_assertions: list[tuple[EdgeSpec, str]] = []
        for edge in edges:
            edge_id = self._write_edge(edge, write_assertions=False)
            edge_assertions.append((edge, edge_id))
        self.session.flush()
        for edge, edge_id in edge_assertions:
            for evidence in edge.evidence:
                self._write_assertion(evidence, edge_id=edge_id)
        self.session.flush()
        return dict(self.counts)

    def _write_node(self, spec: NodeSpec, *, write_assertions: bool = True) -> str:
        label, label_redactions = sanitize_excerpt(spec.label, max_chars=500)
        properties, property_redactions = sanitize_structured_properties(
            spec.node_type,
            spec.properties,
        )
        self.counts["redactions"] += label_redactions + property_redactions
        node_id = self.node_ids.get(spec.stable_key)
        if node_id is None:
            node_id = deterministic_id(self.generation_id, "node", spec.stable_key)
            self.node_ids[spec.stable_key] = node_id
        row = self.session.get(EvidenceGraphNode, node_id)
        if row is None:
            row = EvidenceGraphNode(
                id=node_id,
                generation_id=self.generation_id,
                stable_key=spec.stable_key,
                node_type=spec.node_type,
                label=label or spec.stable_key[:500],
                properties=properties,
                visibility=spec.visibility,
                tenant_id=spec.tenant_id,
                active=True,
            )
            self.session.add(row)
            self.counts["nodes_created"] += 1
        else:
            if row.tenant_id and spec.tenant_id and row.tenant_id != spec.tenant_id:
                raise ValueError(
                    f"Evidence graph node {spec.stable_key} was assigned to multiple tenants."
                )
            row.label = label or spec.stable_key[:500]
            row.properties = {**(row.properties or {}), **properties}
            row.visibility = spec.visibility
            if spec.tenant_id is None:
                row.tenant_id = None
            row.active = True
            self.counts["nodes_updated"] += 1
        if write_assertions:
            self.session.flush()
            for evidence in spec.evidence:
                self._write_assertion(evidence, node_id=node_id)
        return node_id

    def _write_edge(self, spec: EdgeSpec, *, write_assertions: bool = True) -> str:
        properties, property_redactions = sanitize_structured_properties(
            None,
            spec.properties,
            edge=True,
        )
        self.counts["redactions"] += property_redactions
        source_id = self.node_ids.get(spec.source_key)
        target_id = self.node_ids.get(spec.target_key)
        if not source_id or not target_id:
            raise ValueError(
                f"Evidence graph edge references an unwritten node: {spec.source_key} -> {spec.target_key}"
            )
        edge_id = deterministic_id(
            self.generation_id,
            "edge",
            spec.source_key,
            spec.relation,
            spec.target_key,
        )
        row = self.session.get(EvidenceGraphEdge, edge_id)
        if row is None:
            row = EvidenceGraphEdge(
                id=edge_id,
                generation_id=self.generation_id,
                source_node_id=source_id,
                target_node_id=target_id,
                relation=spec.relation,
                trust_tier=spec.trust_tier,
                confidence=max(0.0, min(float(spec.confidence), 1.0)),
                properties=properties,
                active=True,
            )
            self.session.add(row)
            self.counts["edges_created"] += 1
        else:
            if TRUST_WEIGHTS.get(spec.trust_tier, 0.0) > TRUST_WEIGHTS.get(row.trust_tier, 0.0):
                row.trust_tier = spec.trust_tier
            row.confidence = max(
                float(row.confidence or 0.0),
                max(0.0, min(float(spec.confidence), 1.0)),
            )
            row.properties = {**(row.properties or {}), **properties}
            row.active = True
            self.counts["edges_updated"] += 1
        if write_assertions:
            self.session.flush()
            for evidence in spec.evidence:
                self._write_assertion(evidence, edge_id=edge_id)
        return edge_id

    def _write_assertion(
        self,
        evidence: EvidenceSpec,
        *,
        node_id: str | None = None,
        edge_id: str | None = None,
    ) -> None:
        excerpt, redactions = sanitize_excerpt(evidence.excerpt, max_chars=1000)
        source_ref, source_ref_redactions = sanitize_excerpt(evidence.source_ref, max_chars=1000)
        assertion_id = deterministic_id(
            self.generation_id,
            "assertion",
            node_id or "",
            edge_id or "",
            evidence.source_kind,
            evidence.source_record_id,
            evidence.source_hash,
        )
        row = self.session.get(EvidenceGraphAssertion, assertion_id)
        values = {
            "generation_id": self.generation_id,
            "node_id": node_id,
            "edge_id": edge_id,
            "source_kind": evidence.source_kind,
            "source_ref": source_ref,
            "source_record_id": evidence.source_record_id[:512],
            "source_chunk_id": (evidence.source_chunk_id or "")[:512] or None,
            "source_hash": evidence.source_hash[:80],
            "extraction_method": evidence.extraction_method[:120],
            "authority": evidence.authority[:80],
            "trust_tier": evidence.trust_tier,
            "excerpt": excerpt or None,
            "visibility": evidence.visibility,
            "tenant_id": evidence.tenant_id,
            "source_updated_at": evidence.source_updated_at,
            "active": True,
        }
        if row is None:
            self.session.add(EvidenceGraphAssertion(id=assertion_id, **values))
            self.counts["assertions_created"] += 1
        else:
            for key, value in values.items():
                setattr(row, key, value)
            self.counts["assertions_updated"] += 1
        self.counts["redactions"] += redactions + source_ref_redactions


def _assertion_spec(row: EvidenceGraphAssertion) -> EvidenceSpec:
    return EvidenceSpec(
        source_kind=row.source_kind,
        source_ref=row.source_ref,
        source_record_id=row.source_record_id,
        source_chunk_id=row.source_chunk_id or "",
        source_hash=row.source_hash,
        extraction_method=row.extraction_method,
        authority=row.authority,
        trust_tier=row.trust_tier,
        excerpt=row.excerpt or "",
        visibility=row.visibility,
        tenant_id=row.tenant_id,
        source_updated_at=row.source_updated_at,
    )


def clone_generation(
    session: Session,
    *,
    source_generation_id: str,
    target_generation_id: str,
    batch_size: int = 500,
) -> tuple[GraphWriter, dict[str, int]]:
    """Clone an audited generation in bounded batches for blue/green incremental updates."""
    page_size = max(10, min(int(batch_size or 500), 5000))
    writer = GraphWriter(session, target_generation_id)
    last_node_id = ""
    while True:
        rows = (
            session.query(EvidenceGraphNode)
            .filter(
                EvidenceGraphNode.generation_id == source_generation_id,
                EvidenceGraphNode.active.is_(True),
                EvidenceGraphNode.id > last_node_id,
            )
            .order_by(EvidenceGraphNode.id.asc())
            .limit(page_size)
            .all()
        )
        if not rows:
            break
        node_ids = [row.id for row in rows]
        assertions: dict[str, list[EvidenceSpec]] = {node_id: [] for node_id in node_ids}
        for assertion in session.query(EvidenceGraphAssertion).filter(
            EvidenceGraphAssertion.generation_id == source_generation_id,
            EvidenceGraphAssertion.active.is_(True),
            EvidenceGraphAssertion.node_id.in_(node_ids),
        ):
            assertions[assertion.node_id].append(_assertion_spec(assertion))
        writer.write(
            [
                NodeSpec(
                    stable_key=row.stable_key,
                    node_type=row.node_type,
                    label=row.label,
                    properties=dict(row.properties or {}),
                    visibility=row.visibility,
                    tenant_id=row.tenant_id,
                    evidence=assertions.get(row.id, []),
                )
                for row in rows
            ],
            [],
        )
        session.commit()
        last_node_id = rows[-1].id

    last_edge_id = ""
    node_keys = {
        row.id: row.stable_key
        for row in session.query(EvidenceGraphNode).filter(
            EvidenceGraphNode.generation_id == source_generation_id,
            EvidenceGraphNode.active.is_(True),
        )
    }
    while True:
        rows = (
            session.query(EvidenceGraphEdge)
            .filter(
                EvidenceGraphEdge.generation_id == source_generation_id,
                EvidenceGraphEdge.active.is_(True),
                EvidenceGraphEdge.id > last_edge_id,
            )
            .order_by(EvidenceGraphEdge.id.asc())
            .limit(page_size)
            .all()
        )
        if not rows:
            break
        edge_ids = [row.id for row in rows]
        assertions: dict[str, list[EvidenceSpec]] = {edge_id: [] for edge_id in edge_ids}
        for assertion in session.query(EvidenceGraphAssertion).filter(
            EvidenceGraphAssertion.generation_id == source_generation_id,
            EvidenceGraphAssertion.active.is_(True),
            EvidenceGraphAssertion.edge_id.in_(edge_ids),
        ):
            assertions[assertion.edge_id].append(_assertion_spec(assertion))
        specs = []
        for row in rows:
            source_key = node_keys.get(row.source_node_id)
            target_key = node_keys.get(row.target_node_id)
            if not source_key or not target_key:
                raise RuntimeError(f"Cannot clone dangling graph edge {row.id}.")
            specs.append(
                EdgeSpec(
                    source_key=source_key,
                    relation=row.relation,
                    target_key=target_key,
                    trust_tier=row.trust_tier,
                    confidence=row.confidence,
                    properties=dict(row.properties or {}),
                    evidence=assertions.get(row.id, []),
                )
            )
        writer.write([], specs)
        session.commit()
        last_edge_id = rows[-1].id
    return writer, dict(writer.counts)


def remove_source_record(
    session: Session,
    *,
    generation_id: str,
    source_record_id: str,
    source_kinds: Iterable[str] | None = None,
) -> dict[str, int]:
    """Remove one source record's assertions and tombstone newly unsupported graph records."""
    query = session.query(EvidenceGraphAssertion).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.source_record_id == source_record_id,
        EvidenceGraphAssertion.active.is_(True),
    )
    kinds = [str(value).strip() for value in (source_kinds or []) if str(value).strip()]
    if kinds:
        query = query.filter(EvidenceGraphAssertion.source_kind.in_(kinds))
    rows = query.all()
    edge_ids = {row.edge_id for row in rows if row.edge_id}
    node_ids = {row.node_id for row in rows if row.node_id}
    for row in rows:
        row.active = False
    session.flush()

    tombstoned_edges = 0
    for edge_id in edge_ids:
        remaining = session.query(func.count(EvidenceGraphAssertion.id)).filter(
            EvidenceGraphAssertion.edge_id == edge_id,
            EvidenceGraphAssertion.active.is_(True),
        ).scalar() or 0
        if remaining:
            continue
        edge = session.get(EvidenceGraphEdge, edge_id)
        if edge and edge.active:
            edge.active = False
            edge.properties = {**(edge.properties or {}), "tombstoned": True}
            tombstoned_edges += 1
            node_ids.update((edge.source_node_id, edge.target_node_id))
    session.flush()

    tombstoned_nodes = 0
    for node_id in node_ids:
        remaining_assertions = session.query(func.count(EvidenceGraphAssertion.id)).filter(
            EvidenceGraphAssertion.node_id == node_id,
            EvidenceGraphAssertion.active.is_(True),
        ).scalar() or 0
        remaining_edges = session.query(func.count(EvidenceGraphEdge.id)).filter(
            EvidenceGraphEdge.generation_id == generation_id,
            EvidenceGraphEdge.active.is_(True),
            or_(EvidenceGraphEdge.source_node_id == node_id, EvidenceGraphEdge.target_node_id == node_id),
        ).scalar() or 0
        if remaining_assertions or remaining_edges:
            continue
        node = session.get(EvidenceGraphNode, node_id)
        if node and node.active:
            node.active = False
            node.properties = {**(node.properties or {}), "tombstoned": True}
            tombstoned_nodes += 1
    session.flush()
    return {
        "assertions_removed": len(rows),
        "edges_tombstoned": tombstoned_edges,
        "nodes_tombstoned": tombstoned_nodes,
    }


def create_generation(
    session: Session,
    *,
    mode: str = "full",
    created_by: str | None = None,
    source_snapshot: dict | None = None,
) -> EvidenceGraphGeneration:
    generation = EvidenceGraphGeneration(
        id=str(uuid.uuid4()),
        schema_version=GRAPH_SCHEMA_VERSION,
        status="building",
        mode=mode,
        source_snapshot=source_snapshot or {},
        counts={},
        errors=[],
        created_by=created_by,
    )
    session.add(generation)
    session.flush()
    return generation


def create_sync_run(
    session: Session,
    *,
    mode: str,
    sources: list[str],
    dry_run: bool,
    generation_id: str | None = None,
) -> EvidenceGraphSyncRun:
    row = EvidenceGraphSyncRun(
        id=str(uuid.uuid4()),
        generation_id=generation_id,
        mode=mode,
        status="running",
        sources=sources,
        dry_run=dry_run,
        counters={},
        errors=[],
    )
    session.add(row)
    session.flush()
    return row


def active_generation(session: Session) -> EvidenceGraphGeneration | None:
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    if not state or not state.active_generation_id:
        return None
    generation = session.get(EvidenceGraphGeneration, state.active_generation_id)
    if generation and generation.status == "active":
        return generation
    return None


def generation_integrity_manifest(
    session: Session,
    generation_id: str,
    *,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Return a deterministic streaming digest without loading the generation into memory."""
    digest = hashlib.sha256()
    integrity_key = os.getenv("EVIDENCE_GRAPH_INTEGRITY_KEY", "").encode("utf-8", errors="strict")
    seal = hmac.new(integrity_key, digestmod=hashlib.sha256) if integrity_key else None
    counts = {"nodes": 0, "edges": 0, "assertions": 0}

    def update(kind: str, values: tuple[Any, ...]) -> None:
        payload = json.dumps(
            [kind, *values],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        encoded = payload.encode("utf-8", errors="strict") + b"\n"
        digest.update(encoded)
        if seal is not None:
            seal.update(encoded)

    node_rows = (
        session.query(
            EvidenceGraphNode.id,
            EvidenceGraphNode.stable_key,
            EvidenceGraphNode.node_type,
            EvidenceGraphNode.label,
            EvidenceGraphNode.properties,
            EvidenceGraphNode.visibility,
            EvidenceGraphNode.tenant_id,
            EvidenceGraphNode.active,
        )
        .filter(EvidenceGraphNode.generation_id == generation_id)
        .order_by(EvidenceGraphNode.id.asc())
        .yield_per(max(10, int(batch_size or 500)))
    )
    for row in node_rows:
        update("node", tuple(row))
        counts["nodes"] += 1

    edge_rows = (
        session.query(
            EvidenceGraphEdge.id,
            EvidenceGraphEdge.source_node_id,
            EvidenceGraphEdge.relation,
            EvidenceGraphEdge.target_node_id,
            EvidenceGraphEdge.trust_tier,
            EvidenceGraphEdge.confidence,
            EvidenceGraphEdge.properties,
            EvidenceGraphEdge.active,
        )
        .filter(EvidenceGraphEdge.generation_id == generation_id)
        .order_by(EvidenceGraphEdge.id.asc())
        .yield_per(max(10, int(batch_size or 500)))
    )
    for row in edge_rows:
        update("edge", tuple(row))
        counts["edges"] += 1

    assertion_rows = (
        session.query(
            EvidenceGraphAssertion.id,
            EvidenceGraphAssertion.node_id,
            EvidenceGraphAssertion.edge_id,
            EvidenceGraphAssertion.source_kind,
            EvidenceGraphAssertion.source_ref,
            EvidenceGraphAssertion.source_record_id,
            EvidenceGraphAssertion.source_chunk_id,
            EvidenceGraphAssertion.source_hash,
            EvidenceGraphAssertion.extraction_method,
            EvidenceGraphAssertion.authority,
            EvidenceGraphAssertion.trust_tier,
            EvidenceGraphAssertion.excerpt,
            EvidenceGraphAssertion.visibility,
            EvidenceGraphAssertion.tenant_id,
            EvidenceGraphAssertion.source_updated_at,
            EvidenceGraphAssertion.active,
        )
        .filter(EvidenceGraphAssertion.generation_id == generation_id)
        .order_by(EvidenceGraphAssertion.id.asc())
        .yield_per(max(10, int(batch_size or 500)))
    )
    for row in assertion_rows:
        update("assertion", tuple(row))
        counts["assertions"] += 1

    manifest = {
        "algorithm": "sha256",
        "sha256": digest.hexdigest(),
        "counts": counts,
        "schema_version": GRAPH_SCHEMA_VERSION,
        "sealed": seal is not None,
    }
    if seal is not None:
        manifest["hmac_sha256"] = seal.hexdigest()
        manifest["hmac_key_id"] = os.getenv("EVIDENCE_GRAPH_INTEGRITY_KEY_ID", "default")[:80]
    return manifest


def audit_generation(session: Session, generation_id: str) -> dict:
    generation = session.get(EvidenceGraphGeneration, generation_id)
    if generation is None:
        return {"valid": False, "errors": ["Generation does not exist."], "generation_id": generation_id}

    node_count = session.query(func.count(EvidenceGraphNode.id)).filter(
        EvidenceGraphNode.generation_id == generation_id,
        EvidenceGraphNode.active.is_(True),
    ).scalar() or 0
    edge_count = session.query(func.count(EvidenceGraphEdge.id)).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
    ).scalar() or 0
    assertion_count = session.query(func.count(EvidenceGraphAssertion.id)).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.active.is_(True),
    ).scalar() or 0

    unsupported_nodes = session.query(func.count(EvidenceGraphNode.id)).filter(
        EvidenceGraphNode.generation_id == generation_id,
        ~EvidenceGraphNode.node_type.in_(NODE_TYPES),
    ).scalar() or 0
    unsupported_edges = session.query(func.count(EvidenceGraphEdge.id)).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        ~EvidenceGraphEdge.relation.in_(RELATIONS),
    ).scalar() or 0
    unsupported_trust = session.query(func.count(EvidenceGraphEdge.id)).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        ~EvidenceGraphEdge.trust_tier.in_(TRUST_TIERS),
    ).scalar() or 0
    unsupported_assertion_trust = session.query(func.count(EvidenceGraphAssertion.id)).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        ~EvidenceGraphAssertion.trust_tier.in_(TRUST_TIERS),
    ).scalar() or 0

    proven_edge_ids = session.query(EvidenceGraphAssertion.edge_id).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.edge_id.isnot(None),
        EvidenceGraphAssertion.active.is_(True),
    )
    unproven_edges = session.query(func.count(EvidenceGraphEdge.id)).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
        ~EvidenceGraphEdge.id.in_(proven_edge_ids),
    ).scalar() or 0

    proven_node_ids = session.query(EvidenceGraphAssertion.node_id).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.node_id.isnot(None),
        EvidenceGraphAssertion.active.is_(True),
    )
    proven_edge_source_ids = session.query(EvidenceGraphEdge.source_node_id).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
        EvidenceGraphEdge.id.in_(proven_edge_ids),
    )
    proven_edge_target_ids = session.query(EvidenceGraphEdge.target_node_id).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
        EvidenceGraphEdge.id.in_(proven_edge_ids),
    )
    unproven_nodes = session.query(func.count(EvidenceGraphNode.id)).filter(
        EvidenceGraphNode.generation_id == generation_id,
        EvidenceGraphNode.active.is_(True),
        ~EvidenceGraphNode.id.in_(proven_node_ids),
        ~EvidenceGraphNode.id.in_(proven_edge_source_ids),
        ~EvidenceGraphNode.id.in_(proven_edge_target_ids),
    ).scalar() or 0

    source_node = aliased(EvidenceGraphNode)
    target_node = aliased(EvidenceGraphNode)
    dangling_edges = (
        session.query(func.count(EvidenceGraphEdge.id))
        .outerjoin(source_node, EvidenceGraphEdge.source_node_id == source_node.id)
        .outerjoin(target_node, EvidenceGraphEdge.target_node_id == target_node.id)
        .filter(
            EvidenceGraphEdge.generation_id == generation_id,
            EvidenceGraphEdge.active.is_(True),
            or_(
                source_node.id.is_(None),
                target_node.id.is_(None),
                source_node.generation_id != generation_id,
                target_node.generation_id != generation_id,
                source_node.active.is_(False),
                target_node.active.is_(False),
            ),
        )
        .scalar()
        or 0
    )

    sensitive_labels = 0
    sensitive_stable_keys = 0
    sensitive_properties = 0
    for stable_key_value, label, properties in session.query(
        EvidenceGraphNode.stable_key,
        EvidenceGraphNode.label,
        EvidenceGraphNode.properties,
    ).filter(
        EvidenceGraphNode.generation_id == generation_id
    ).yield_per(500):
        sensitive_labels += int(contains_sensitive_text(label))
        sensitive_stable_keys += int(contains_sensitive_text(stable_key_value))
        sensitive_properties += int(contains_sensitive_text(properties))
    sensitive_excerpts = 0
    sensitive_source_identifiers = 0
    for excerpt, source_ref, source_record_id, source_chunk_id in session.query(
        EvidenceGraphAssertion.excerpt,
        EvidenceGraphAssertion.source_ref,
        EvidenceGraphAssertion.source_record_id,
        EvidenceGraphAssertion.source_chunk_id,
    ).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
    ).yield_per(500):
        sensitive_excerpts += int(contains_sensitive_text(excerpt))
        sensitive_source_identifiers += int(
            any(
                contains_sensitive_text(value)
                for value in (source_ref, source_record_id, source_chunk_id)
            )
        )

    errors = []
    if node_count == 0:
        errors.append("Generation has no nodes.")
    if unsupported_nodes:
        errors.append(f"Unsupported node types: {unsupported_nodes}")
    if unsupported_edges:
        errors.append(f"Unsupported edge relations: {unsupported_edges}")
    if unsupported_trust:
        errors.append(f"Unsupported trust tiers: {unsupported_trust}")
    if unsupported_assertion_trust:
        errors.append(f"Assertions with unsupported trust tiers: {unsupported_assertion_trust}")
    if unproven_nodes:
        errors.append(f"Nodes without direct or relationship evidence assertions: {unproven_nodes}")
    if unproven_edges:
        errors.append(f"Edges without evidence assertions: {unproven_edges}")
    if dangling_edges:
        errors.append(f"Active edges with inactive or foreign-generation endpoints: {dangling_edges}")
    if any(
        (
            sensitive_labels,
            sensitive_stable_keys,
            sensitive_properties,
            sensitive_excerpts,
            sensitive_source_identifiers,
        )
    ):
        errors.append(
            "Sensitive text audit failed: "
            f"labels={sensitive_labels}, stable_keys={sensitive_stable_keys}, "
            f"properties={sensitive_properties}, excerpts={sensitive_excerpts}, "
            f"source_identifiers={sensitive_source_identifiers}"
        )

    integrity = generation_integrity_manifest(session, generation_id)
    expected_integrity = (
        (generation.source_snapshot or {}).get("integrity")
        if isinstance(generation.source_snapshot, dict)
        else None
    )
    if expected_integrity and expected_integrity.get("sha256") != integrity["sha256"]:
        errors.append("Generation integrity digest does not match the promoted manifest.")
    if expected_integrity and expected_integrity.get("sealed"):
        if not integrity.get("sealed"):
            errors.append("Generation integrity HMAC cannot be verified because its key is unavailable.")
        elif expected_integrity.get("hmac_sha256") != integrity.get("hmac_sha256"):
            errors.append("Generation integrity HMAC does not match the promoted manifest.")
        elif expected_integrity.get("hmac_key_id") != integrity.get("hmac_key_id"):
            errors.append("Generation integrity HMAC key ID does not match the promoted manifest.")

    node_types = dict(
        session.query(EvidenceGraphNode.node_type, func.count(EvidenceGraphNode.id))
        .filter(EvidenceGraphNode.generation_id == generation_id)
        .group_by(EvidenceGraphNode.node_type)
        .all()
    )
    relations = dict(
        session.query(EvidenceGraphEdge.relation, func.count(EvidenceGraphEdge.id))
        .filter(EvidenceGraphEdge.generation_id == generation_id)
        .group_by(EvidenceGraphEdge.relation)
        .all()
    )
    return {
        "valid": not errors,
        "generation_id": generation_id,
        "schema_version": generation.schema_version,
        "counts": {"nodes": node_count, "edges": edge_count, "assertions": assertion_count},
        "node_types": node_types,
        "relations": relations,
        "edges_without_assertions": unproven_edges,
        "nodes_without_assertions": unproven_nodes,
        "dangling_edges": dangling_edges,
        "sensitive_labels": sensitive_labels,
        "sensitive_stable_keys": sensitive_stable_keys,
        "sensitive_properties": sensitive_properties,
        "sensitive_excerpts": sensitive_excerpts,
        "sensitive_source_identifiers": sensitive_source_identifiers,
        "integrity": integrity,
        "integrity_verified": bool(
            expected_integrity
            and expected_integrity.get("sha256") == integrity["sha256"]
            and (
                not expected_integrity.get("sealed")
                or (
                    integrity.get("sealed")
                    and expected_integrity.get("hmac_sha256") == integrity.get("hmac_sha256")
                    and expected_integrity.get("hmac_key_id") == integrity.get("hmac_key_id")
                )
            )
        ),
        "errors": errors,
    }


def promote_generation(session: Session, generation_id: str) -> dict:
    audit = audit_generation(session, generation_id)
    if not audit["valid"]:
        raise ValueError("Evidence graph generation failed audit: " + "; ".join(audit["errors"]))
    generation = session.get(EvidenceGraphGeneration, generation_id)
    now = datetime.utcnow()
    current = active_generation(session)
    if current and current.id != generation_id:
        current.status = "retired"
    generation.status = "active"
    generation.promoted_at = now
    generation.completed_at = generation.completed_at or now
    generation.counts = audit["counts"]
    snapshot = dict(generation.source_snapshot or {})
    snapshot["integrity"] = audit["integrity"]
    generation.source_snapshot = snapshot
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    if state is None:
        state = EvidenceGraphSourceState(source_name=GRAPH_STATE_KEY, cursor={}, counts={})
        session.add(state)
    state.active_generation_id = generation_id
    state.counts = audit["counts"]
    state.last_success_at = now
    state.last_error = None
    session.flush()
    retired = (
        session.query(EvidenceGraphGeneration)
        .filter(EvidenceGraphGeneration.status == "retired")
        .order_by(EvidenceGraphGeneration.promoted_at.desc(), EvidenceGraphGeneration.created_at.desc())
        .all()
    )
    for obsolete in retired[1:]:
        session.delete(obsolete)
    session.flush()
    return audit


def rollback_generation(session: Session) -> dict:
    current = active_generation(session)
    candidate = (
        session.query(EvidenceGraphGeneration)
        .filter(EvidenceGraphGeneration.status == "retired")
        .order_by(EvidenceGraphGeneration.promoted_at.desc(), EvidenceGraphGeneration.created_at.desc())
        .first()
    )
    if candidate is None:
        raise ValueError("No retired evidence graph generation is available for rollback.")
    audit = audit_generation(session, candidate.id)
    if not audit.get("valid"):
        raise ValueError(
            "Retired evidence graph generation failed integrity audit: "
            + "; ".join(audit.get("errors") or [])
        )
    if current:
        current.status = "retired"
    candidate.status = "active"
    candidate.promoted_at = datetime.utcnow()
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    if state is None:
        state = EvidenceGraphSourceState(source_name=GRAPH_STATE_KEY, cursor={}, counts={})
        session.add(state)
    state.active_generation_id = candidate.id
    state.counts = candidate.counts or {}
    state.last_success_at = datetime.utcnow()
    session.flush()
    return {"rolled_back": True, "from_generation": current.id if current else None, "active_generation": candidate.id}


def query_audit_summary(session: Session, *, hours: int = 24, limit: int = 10000) -> dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(hours=max(1, min(int(hours or 24), 24 * 30)))
    rows = (
        session.query(
            EvidenceGraphQueryAudit.duration_ms,
            EvidenceGraphQueryAudit.cache_hit,
            EvidenceGraphQueryAudit.status,
            EvidenceGraphQueryAudit.influence_mode,
            EvidenceGraphQueryAudit.created_at,
        )
        .filter(EvidenceGraphQueryAudit.created_at >= cutoff)
        .order_by(EvidenceGraphQueryAudit.created_at.desc())
        .limit(max(1, min(int(limit or 10000), 50000)))
        .all()
    )
    durations = sorted(max(0, int(row.duration_ms or 0)) for row in rows)
    count = len(rows)
    percentile_index = max(0, math.ceil(count * 0.95) - 1) if count else 0
    status_counts = Counter(str(row.status or "unknown") for row in rows)
    influence_counts = Counter(str(row.influence_mode or "unknown") for row in rows)
    return {
        "window_hours": max(1, min(int(hours or 24), 24 * 30)),
        "query_count": count,
        "p95_duration_ms": durations[percentile_index] if durations else None,
        "cache_hit_rate": round(sum(bool(row.cache_hit) for row in rows) / count, 4) if count else None,
        "status_counts": dict(sorted(status_counts.items())),
        "influence_mode_counts": dict(sorted(influence_counts.items())),
        "last_query_at": rows[0].created_at.isoformat() if rows else None,
    }


def _privacy_audit_digest(purpose: str, value: str) -> str:
    secret = (
        os.getenv("EVIDENCE_GRAPH_AUDIT_HASH_KEY")
        or os.getenv("TENANT_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or "local-development-only"
    )
    payload = f"{purpose}\0{value}".encode("utf-8", errors="strict")
    return hmac.new(secret.encode("utf-8", errors="strict"), payload, hashlib.sha256).hexdigest()


def record_query_audit(
    session: Session,
    *,
    generation_id: str | None,
    tenant_id: str,
    actor_id: str,
    query: str,
    selectors: dict[str, Any],
    influence_mode: str,
    status: str,
    duration_ms: int,
    cache_hit: bool,
    path_count: int,
    leaf_count: int,
    cross_customer_detail_count: int,
    cross_customer_aggregate_count: int,
    warning_count: int,
) -> str:
    row = EvidenceGraphQueryAudit(
        id=str(uuid.uuid4()),
        generation_id=generation_id,
        tenant_id=(tenant_id or "kone")[:120],
        actor_hash=_privacy_audit_digest("actor", actor_id or "system"),
        query_hash=_privacy_audit_digest("query", query),
        selector_hash=_privacy_audit_digest(
            "selectors",
            json.dumps(selectors or {}, ensure_ascii=False, sort_keys=True, default=str),
        ),
        influence_mode=(influence_mode or "interactive")[:30],
        status=(status or "unknown")[:30],
        duration_ms=max(0, int(duration_ms or 0)),
        cache_hit=bool(cache_hit),
        path_count=max(0, int(path_count or 0)),
        leaf_count=max(0, int(leaf_count or 0)),
        cross_customer_detail_count=max(0, int(cross_customer_detail_count or 0)),
        cross_customer_aggregate_count=max(0, int(cross_customer_aggregate_count or 0)),
        warning_count=max(0, int(warning_count or 0)),
    )
    session.add(row)
    session.flush()
    return row.id


def graph_status(session: Session) -> dict:
    enabled = os.getenv("EVIDENCE_GRAPH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    bind = session.get_bind()
    required_tables = {
        EvidenceGraphGeneration.__tablename__,
        EvidenceGraphNode.__tablename__,
        EvidenceGraphEdge.__tablename__,
        EvidenceGraphAssertion.__tablename__,
        EvidenceGraphSourceEvent.__tablename__,
        EvidenceGraphSourceState.__tablename__,
        EvidenceGraphQueryAudit.__tablename__,
    }
    existing_tables = set(inspect(bind).get_table_names())
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        warning = "Evidence graph migration is not applied; missing tables: " + ", ".join(missing_tables)
        return {
            "enabled": enabled,
            "status": "unavailable" if enabled else "disabled",
            "schema_ready": False,
            "schema_version": GRAPH_SCHEMA_VERSION,
            "active_generation_id": None,
            "generation_created_at": None,
            "generation_promoted_at": None,
            "counts": {},
            "pending_events": 0,
            "oldest_pending_event_at": None,
            "incremental_sync_lag_seconds": 0,
            "failed_events": 0,
            "last_success_at": None,
            "source_coverage": {},
            "source_checkpoints": {},
            "reconciliation_age_seconds": None,
            "integrity": {},
            "query_health": {},
            "degraded_reasons": [warning],
            "warnings": [warning],
        }
    generation = active_generation(session)
    pending_events = session.query(func.count(EvidenceGraphSourceEvent.id)).filter(
        EvidenceGraphSourceEvent.status.in_(("pending", "retry"))
    ).scalar() or 0
    oldest_pending_event_at = session.query(func.min(EvidenceGraphSourceEvent.created_at)).filter(
        EvidenceGraphSourceEvent.status.in_(("pending", "retry"))
    ).scalar()
    incremental_sync_lag_seconds = (
        max(0, int((datetime.utcnow() - oldest_pending_event_at).total_seconds()))
        if oldest_pending_event_at
        else 0
    )
    failed_events = session.query(func.count(EvidenceGraphSourceEvent.id)).filter(
        EvidenceGraphSourceEvent.status == "failed"
    ).scalar() or 0
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    status = "ready" if enabled and generation else "disabled" if not enabled else "unavailable"
    warnings = []
    if enabled and generation is None:
        warnings.append("No active evidence graph generation has been promoted.")
    if generation and generation.schema_version != GRAPH_SCHEMA_VERSION:
        status = "degraded" if enabled else status
        warnings.append(
            f"Active graph schema is {generation.schema_version}; rebuild with {GRAPH_SCHEMA_VERSION}."
        )
    if failed_events:
        status = "degraded" if generation else status
        warnings.append(f"{failed_events} graph source events exhausted retries.")
    if incremental_sync_lag_seconds > 15 * 60:
        status = "degraded" if generation else status
        warnings.append(
            f"Evidence graph incremental synchronization lag is {incremental_sync_lag_seconds} seconds."
        )
    source_coverage = {}
    if generation:
        source_coverage = {
            source_kind: count
            for source_kind, count in (
                session.query(EvidenceGraphAssertion.source_kind, func.count(EvidenceGraphAssertion.id))
                .filter(
                    EvidenceGraphAssertion.generation_id == generation.id,
                    EvidenceGraphAssertion.active.is_(True),
                )
                .group_by(EvidenceGraphAssertion.source_kind)
                .all()
            )
        }
    source_checkpoints = {}
    for row in session.query(EvidenceGraphSourceState).filter(
        EvidenceGraphSourceState.source_name != GRAPH_STATE_KEY
    ):
        safe_error = sanitize_excerpt(row.last_error or "", max_chars=1000)[0] or None
        source_checkpoints[row.source_name] = {
            "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
            "counts": row.counts or {},
            "last_error": safe_error,
        }
        if row.last_error:
            status = "degraded" if generation else status
            warnings.append(f"{row.source_name} checkpoint reports: {safe_error}")
    reconciliation = session.get(EvidenceGraphSourceState, "evidence_graph:reconciliation")
    reconciliation_age_seconds = None
    if reconciliation and reconciliation.last_success_at:
        reconciliation_age_seconds = max(
            0,
            int((datetime.utcnow() - reconciliation.last_success_at).total_seconds()),
        )
        if reconciliation_age_seconds > 26 * 60 * 60:
            status = "degraded" if generation else status
            warnings.append("Evidence graph reconciliation is older than 26 hours.")
    elif generation:
        status = "degraded"
        warnings.append("No successful evidence graph reconciliation checkpoint is recorded.")
    query_health = query_audit_summary(session)
    if (
        query_health.get("query_count", 0) >= 5
        and int(query_health.get("p95_duration_ms") or 0) > 1500
    ):
        status = "degraded" if generation else status
        warnings.append(
            f"Evidence graph query p95 is {query_health['p95_duration_ms']} ms, above the 1500 ms SLO."
        )
    integrity = (
        (generation.source_snapshot or {}).get("integrity")
        if generation and isinstance(generation.source_snapshot, dict)
        else None
    )
    return {
        "enabled": enabled,
        "status": status,
        "schema_ready": True,
        "schema_version": GRAPH_SCHEMA_VERSION,
        "active_generation_id": generation.id if generation else None,
        "generation_created_at": generation.created_at.isoformat() if generation else None,
        "generation_promoted_at": generation.promoted_at.isoformat() if generation and generation.promoted_at else None,
        "counts": (generation.counts if generation else {}) or {},
        "pending_events": pending_events,
        "oldest_pending_event_at": (
            oldest_pending_event_at.isoformat() if oldest_pending_event_at else None
        ),
        "incremental_sync_lag_seconds": incremental_sync_lag_seconds,
        "failed_events": failed_events,
        "last_success_at": state.last_success_at.isoformat() if state and state.last_success_at else None,
        "source_coverage": source_coverage,
        "source_checkpoints": source_checkpoints,
        "reconciliation_age_seconds": reconciliation_age_seconds,
        "integrity": integrity or {},
        "query_health": query_health,
        "degraded_reasons": warnings,
        "warnings": warnings,
    }


def update_source_checkpoint(
    session: Session,
    *,
    source_name: str,
    generation_id: str | None,
    counts: dict | None = None,
    cursor: dict | None = None,
    error: str | None = None,
) -> None:
    row = session.get(EvidenceGraphSourceState, source_name)
    if row is None:
        row = EvidenceGraphSourceState(source_name=source_name, cursor={}, counts={})
        session.add(row)
    row.active_generation_id = generation_id
    row.counts = counts or {}
    if cursor is not None:
        row.cursor = cursor
    row.last_error = sanitize_excerpt(error or "", max_chars=1000)[0] or None
    if error is None:
        row.last_success_at = datetime.utcnow()
    session.flush()


def enqueue_source_event(
    session: Session,
    *,
    source_kind: str,
    source_record_id: str,
    source_hash: str,
    event_type: str = "upsert",
) -> str:
    event_id = deterministic_id(source_kind, source_record_id, event_type, source_hash)
    row = next(
        (
            pending
            for pending in session.new
            if isinstance(pending, EvidenceGraphSourceEvent) and pending.id == event_id
        ),
        None,
    )
    if row is None:
        row = session.get(EvidenceGraphSourceEvent, event_id)
    if row is None:
        row = EvidenceGraphSourceEvent(
            id=event_id,
            source_kind=source_kind,
            source_record_id=source_record_id,
            event_type=event_type,
            source_hash=source_hash,
            status="pending",
            attempts=0,
        )
        session.add(row)
    elif row.status in {"failed", "completed"}:
        row.status = "pending"
        row.attempts = 0
        row.next_attempt_at = None
        row.last_error = None
        row.completed_at = None
    return event_id


def list_source_events(
    session: Session,
    *,
    status: str | None = None,
    source_kind: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = session.query(EvidenceGraphSourceEvent)
    if status:
        query = query.filter(EvidenceGraphSourceEvent.status == status)
    if source_kind:
        query = query.filter(EvidenceGraphSourceEvent.source_kind == source_kind)
    rows = (
        query.order_by(EvidenceGraphSourceEvent.created_at.asc(), EvidenceGraphSourceEvent.id.asc())
        .limit(max(1, min(int(limit or 100), 1000)))
        .all()
    )
    return [
        {
            "id": row.id,
            "source_kind": row.source_kind,
            "source_record_id": row.source_record_id,
            "event_type": row.event_type,
            "source_hash": row.source_hash,
            "status": row.status,
            "attempts": row.attempts,
            "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
            "last_error": sanitize_excerpt(row.last_error or "", max_chars=1000)[0] or None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    ]


def replay_source_events(
    session: Session,
    *,
    event_ids: Iterable[str] | None = None,
    source_kind: str | None = None,
) -> dict[str, Any]:
    identifiers = [str(value).strip() for value in (event_ids or []) if str(value).strip()]
    query = session.query(EvidenceGraphSourceEvent).filter(
        EvidenceGraphSourceEvent.status == "failed"
    )
    if identifiers:
        query = query.filter(EvidenceGraphSourceEvent.id.in_(identifiers))
    if source_kind:
        query = query.filter(EvidenceGraphSourceEvent.source_kind == source_kind)
    rows = query.all()
    for row in rows:
        row.status = "pending"
        row.attempts = 0
        row.next_attempt_at = None
        row.last_error = None
        row.completed_at = None
    session.flush()
    return {
        "replayed": len(rows),
        "event_ids": sorted(row.id for row in rows),
        "source_kind": source_kind or None,
    }


def _lease_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def acquire_graph_lease(session: Session, *, seconds: int = 900) -> str | None:
    now = datetime.utcnow()
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    if state is None:
        try:
            session.add(EvidenceGraphSourceState(source_name=GRAPH_STATE_KEY, cursor={}, counts={}))
            session.commit()
        except IntegrityError:
            session.rollback()
    owner = _lease_owner()
    updated = (
        session.query(EvidenceGraphSourceState)
        .filter(
            EvidenceGraphSourceState.source_name == GRAPH_STATE_KEY,
            or_(
                EvidenceGraphSourceState.lease_owner.is_(None),
                EvidenceGraphSourceState.lease_expires_at.is_(None),
                EvidenceGraphSourceState.lease_expires_at <= now,
            ),
        )
        .update(
            {
                EvidenceGraphSourceState.lease_owner: owner,
                EvidenceGraphSourceState.lease_expires_at: now + timedelta(seconds=max(30, int(seconds))),
            },
            synchronize_session=False,
        )
    )
    session.commit()
    return owner if updated == 1 else None


def renew_graph_lease(session: Session, owner: str, *, seconds: int = 900) -> bool:
    updated = (
        session.query(EvidenceGraphSourceState)
        .filter(
            EvidenceGraphSourceState.source_name == GRAPH_STATE_KEY,
            EvidenceGraphSourceState.lease_owner == owner,
        )
        .update(
            {
                EvidenceGraphSourceState.lease_expires_at: datetime.utcnow()
                + timedelta(seconds=max(30, int(seconds))),
            },
            synchronize_session=False,
        )
    )
    session.commit()
    return updated == 1


def release_graph_lease(session: Session, owner: str) -> None:
    state = session.get(EvidenceGraphSourceState, GRAPH_STATE_KEY)
    if state and state.lease_owner == owner:
        state.lease_owner = None
        state.lease_expires_at = None
        session.commit()
