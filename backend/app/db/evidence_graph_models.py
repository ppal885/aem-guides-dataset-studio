"""Portable SQLAlchemy models for the production evidence knowledge graph."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.base import Base


class EvidenceGraphGeneration(Base):
    __tablename__ = "evidence_graph_generations"

    id = Column(String(36), primary_key=True)
    schema_version = Column(String(40), nullable=False)
    status = Column(String(30), nullable=False, index=True)
    mode = Column(String(30), nullable=False, default="full")
    source_snapshot = Column(JSON, nullable=False, default=dict)
    counts = Column(JSON, nullable=False, default=dict)
    errors = Column(JSON, nullable=False, default=list)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    promoted_at = Column(DateTime, nullable=True, index=True)


class EvidenceGraphNode(Base):
    __tablename__ = "evidence_graph_nodes"
    __table_args__ = (
        UniqueConstraint("generation_id", "stable_key", name="uq_evidence_graph_node_key"),
        Index("ix_evidence_graph_node_type_generation", "generation_id", "node_type"),
        Index("ix_evidence_graph_node_visibility", "generation_id", "visibility", "tenant_id"),
    )

    id = Column(String(36), primary_key=True)
    generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stable_key = Column(String(512), nullable=False)
    node_type = Column(String(80), nullable=False)
    label = Column(String(500), nullable=False)
    properties = Column(JSON, nullable=False, default=dict)
    visibility = Column(String(30), nullable=False, default="internal")
    tenant_id = Column(String(120), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EvidenceGraphEdge(Base):
    __tablename__ = "evidence_graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "generation_id",
            "source_node_id",
            "relation",
            "target_node_id",
            name="uq_evidence_graph_edge_path",
        ),
        Index("ix_evidence_graph_edge_out", "generation_id", "source_node_id", "relation"),
        Index("ix_evidence_graph_edge_in", "generation_id", "target_node_id", "relation"),
        Index("ix_evidence_graph_edge_trust", "generation_id", "trust_tier"),
    )

    id = Column(String(36), primary_key=True)
    generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id = Column(
        String(36),
        ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id = Column(
        String(36),
        ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation = Column(String(80), nullable=False)
    trust_tier = Column(String(40), nullable=False, default="supporting")
    confidence = Column(Float, nullable=False, default=0.5)
    properties = Column(JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EvidenceGraphAssertion(Base):
    __tablename__ = "evidence_graph_assertions"
    __table_args__ = (
        CheckConstraint(
            "(node_id IS NOT NULL AND edge_id IS NULL) OR "
            "(node_id IS NULL AND edge_id IS NOT NULL)",
            name="ck_evidence_graph_assertion_target",
        ),
        UniqueConstraint(
            "generation_id",
            "node_id",
            "edge_id",
            "source_kind",
            "source_record_id",
            "source_hash",
            name="uq_evidence_graph_assertion_source",
        ),
        Index("ix_evidence_graph_assertion_node", "generation_id", "node_id"),
        Index("ix_evidence_graph_assertion_edge", "generation_id", "edge_id"),
        Index("ix_evidence_graph_assertion_trust", "generation_id", "trust_tier"),
    )

    id = Column(String(36), primary_key=True)
    generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(
        String(36),
        ForeignKey("evidence_graph_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    edge_id = Column(
        String(36),
        ForeignKey("evidence_graph_edges.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_kind = Column(String(80), nullable=False)
    source_ref = Column(String(1000), nullable=False)
    source_record_id = Column(String(512), nullable=False)
    source_chunk_id = Column(String(512), nullable=True)
    source_hash = Column(String(80), nullable=False)
    extraction_method = Column(String(120), nullable=False)
    authority = Column(String(80), nullable=False)
    trust_tier = Column(String(40), nullable=False)
    excerpt = Column(Text, nullable=True)
    visibility = Column(String(30), nullable=False, default="internal")
    tenant_id = Column(String(120), nullable=True)
    source_updated_at = Column(DateTime, nullable=True)
    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    active = Column(Boolean, nullable=False, default=True)


class EvidenceGraphSourceEvent(Base):
    __tablename__ = "evidence_graph_source_events"
    __table_args__ = (
        UniqueConstraint(
            "source_kind",
            "source_record_id",
            "event_type",
            "source_hash",
            name="uq_evidence_graph_source_event",
        ),
        Index("ix_evidence_graph_event_queue", "status", "next_attempt_at", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    source_kind = Column(String(80), nullable=False)
    source_record_id = Column(String(512), nullable=False)
    event_type = Column(String(30), nullable=False, default="upsert")
    source_hash = Column(String(80), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class EvidenceGraphSourceState(Base):
    __tablename__ = "evidence_graph_source_state"

    source_name = Column(String(120), primary_key=True)
    active_generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cursor = Column(JSON, nullable=False, default=dict)
    counts = Column(JSON, nullable=False, default=dict)
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    lease_owner = Column(String(120), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EvidenceGraphSyncRun(Base):
    __tablename__ = "evidence_graph_sync_runs"
    __table_args__ = (Index("ix_evidence_graph_sync_run_status", "status", "started_at"),)

    id = Column(String(36), primary_key=True)
    generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mode = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    dry_run = Column(Boolean, nullable=False, default=False)
    counters = Column(JSON, nullable=False, default=dict)
    errors = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class EvidenceGraphQueryAudit(Base):
    __tablename__ = "evidence_graph_query_audits"
    __table_args__ = (
        Index("ix_evidence_graph_query_audit_created", "created_at"),
        Index("ix_evidence_graph_query_audit_tenant", "tenant_id", "created_at"),
        Index("ix_evidence_graph_query_audit_status", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    generation_id = Column(
        String(36),
        ForeignKey("evidence_graph_generations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id = Column(String(120), nullable=False)
    actor_hash = Column(String(64), nullable=False)
    query_hash = Column(String(64), nullable=False)
    selector_hash = Column(String(64), nullable=False)
    influence_mode = Column(String(30), nullable=False, default="interactive")
    status = Column(String(30), nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    path_count = Column(Integer, nullable=False, default=0)
    leaf_count = Column(Integer, nullable=False, default=0)
    cross_customer_detail_count = Column(Integer, nullable=False, default=0)
    cross_customer_aggregate_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
