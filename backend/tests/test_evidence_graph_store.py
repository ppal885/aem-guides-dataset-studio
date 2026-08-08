from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
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
from app.services.evidence_graph_contract import EdgeSpec, EvidenceSpec, NodeSpec
from app.services.evidence_graph_store import (
    GraphWriter,
    acquire_graph_lease,
    active_generation,
    audit_generation,
    create_generation,
    enqueue_source_event,
    graph_status,
    list_source_events,
    promote_generation,
    query_audit_summary,
    record_query_audit,
    release_graph_lease,
    remove_source_record,
    renew_graph_lease,
    replay_source_events,
    rollback_generation,
    update_source_checkpoint,
)


GRAPH_TABLES = [
    EvidenceGraphGeneration.__table__,
    EvidenceGraphNode.__table__,
    EvidenceGraphEdge.__table__,
    EvidenceGraphAssertion.__table__,
    EvidenceGraphSourceEvent.__table__,
    EvidenceGraphSourceState.__table__,
    EvidenceGraphSyncRun.__table__,
    EvidenceGraphQueryAudit.__table__,
]


def _session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'evidence-graph.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=GRAPH_TABLES)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _evidence(source_record_id="GUIDES-1", *, excerpt="Verified source text"):
    return EvidenceSpec(
        source_kind="jira_enriched",
        source_ref=source_record_id,
        source_record_id=source_record_id,
        source_hash="sha256:source",
        extraction_method="structured_jira_field",
        authority="indexed_jira_snapshot",
        trust_tier="authoritative",
        excerpt=excerpt,
    )


def _write_minimum_graph(session, generation_id, *, source_record_id="GUIDES-1"):
    evidence = _evidence(source_record_id)
    writer = GraphWriter(session, generation_id)
    writer.write(
        [
            NodeSpec(
                stable_key=f"jira:{source_record_id}",
                node_type="jira_issue",
                label=f"{source_record_id} issue",
                properties={"jira_key": source_record_id, "forbidden": "discard me"},
                evidence=[evidence],
            ),
            NodeSpec(
                stable_key="root-cause:shared",
                node_type="root_cause",
                label="Shared serializer defect",
                properties={"mechanism_signal": True},
            ),
        ],
        [
            EdgeSpec(
                source_key=f"jira:{source_record_id}",
                relation="HAS_ROOT_CAUSE",
                target_key="root-cause:shared",
                trust_tier="historical_verified",
                confidence=0.95,
                properties={"root_cause_source": "explicit_resolution_rca", "raw_text": "discard"},
                evidence=[evidence],
            )
        ],
    )
    session.flush()
    return writer


def test_writer_is_idempotent_redacts_and_whitelists_properties(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    evidence = _evidence(
        excerpt="Contact qa@example.com with password=hunter2 and [~accountid:abc]"
    )
    writer = GraphWriter(session, generation.id)
    nodes = [
        NodeSpec(
            stable_key="jira:GUIDES-1",
            node_type="jira_issue",
            label="Failure reported by qa@example.com",
            properties={
                "jira_key": "GUIDES-1",
                "status": "Owned by qa@example.com",
                "description": "full Jira text must not persist",
            },
            evidence=[evidence],
        ),
        NodeSpec(
            stable_key="root-cause:shared",
            node_type="root_cause",
            label="Serializer defect",
        ),
    ]
    edges = [
        EdgeSpec(
            source_key="jira:GUIDES-1",
            relation="HAS_ROOT_CAUSE",
            target_key="root-cause:shared",
            trust_tier="historical_verified",
            confidence=2.0,
            properties={"root_cause_source": "explicit_resolution_rca", "raw_text": "discard"},
            evidence=[evidence],
        )
    ]

    writer.write(nodes, edges)
    writer.write(nodes, edges)
    session.commit()

    assert session.query(EvidenceGraphNode).count() == 2
    assert session.query(EvidenceGraphEdge).count() == 1
    assert session.query(EvidenceGraphAssertion).count() == 2
    jira_node = session.query(EvidenceGraphNode).filter_by(stable_key="jira:GUIDES-1").one()
    assert jira_node.label == "Failure reported by [redacted-email]"
    assert jira_node.properties == {
        "jira_key": "GUIDES-1",
        "status": "Owned by [redacted-email]",
    }
    edge = session.query(EvidenceGraphEdge).one()
    assert edge.confidence == 1.0
    assert edge.properties == {"root_cause_source": "explicit_resolution_rca"}
    assert "hunter2" not in " ".join(
        assertion.excerpt or "" for assertion in session.query(EvidenceGraphAssertion)
    )
    assert audit_generation(session, generation.id)["valid"] is True
    session.close()


def test_relationship_keeps_strongest_trust_across_multiple_sources(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    authoritative = _evidence("GUIDES-1")
    candidate = EvidenceSpec(
        source_kind="jira_chunk",
        source_ref="GUIDES-2",
        source_record_id="GUIDES-2",
        source_hash="sha256:candidate",
        extraction_method="derived_metadata",
        authority="indexed_jira_snapshot",
        trust_tier="candidate",
        excerpt="Candidate relationship",
    )
    writer = GraphWriter(session, generation.id)
    nodes = [
        NodeSpec(
            stable_key="jira:GUIDES-1",
            node_type="jira_issue",
            label="Issue",
            evidence=[authoritative],
        ),
        NodeSpec(
            stable_key="root-cause:shared",
            node_type="root_cause",
            label="Serializer",
            evidence=[authoritative],
        ),
    ]
    writer.write(
        nodes,
        [
            EdgeSpec(
                source_key="jira:GUIDES-1",
                relation="HAS_ROOT_CAUSE",
                target_key="root-cause:shared",
                trust_tier="historical_verified",
                confidence=0.95,
                evidence=[authoritative],
            )
        ],
    )
    writer.write(
        nodes,
        [
            EdgeSpec(
                source_key="jira:GUIDES-1",
                relation="HAS_ROOT_CAUSE",
                target_key="root-cause:shared",
                trust_tier="candidate",
                confidence=0.2,
                evidence=[candidate],
            )
        ],
    )
    session.commit()

    edge = session.query(EvidenceGraphEdge).one()
    assert edge.trust_tier == "historical_verified"
    assert edge.confidence == 0.95
    assert session.query(EvidenceGraphAssertion).filter_by(edge_id=edge.id).count() == 2
    session.close()


def test_audit_rejects_edges_and_orphan_nodes_without_assertions(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    writer = GraphWriter(session, generation.id)
    writer.write(
        [
            NodeSpec(stable_key="jira:GUIDES-2", node_type="jira_issue", label="Issue"),
            NodeSpec(stable_key="component:editor", node_type="component", label="Editor"),
            NodeSpec(stable_key="risk:orphan", node_type="risk", label="Orphan risk"),
        ],
        [
            EdgeSpec(
                source_key="jira:GUIDES-2",
                relation="IN_COMPONENT",
                target_key="component:editor",
                trust_tier="supporting",
                confidence=0.5,
            )
        ],
    )
    session.commit()

    audit = audit_generation(session, generation.id)

    assert audit["valid"] is False
    assert audit["edges_without_assertions"] == 1
    assert audit["nodes_without_assertions"] == 3
    session.close()


def test_promote_blue_green_rollback_and_retention(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    first = create_generation(session)
    _write_minimum_graph(session, first.id, source_record_id="GUIDES-10")
    promote_generation(session, first.id)
    session.commit()

    second = create_generation(session)
    _write_minimum_graph(session, second.id, source_record_id="GUIDES-11")
    promote_generation(session, second.id)
    session.commit()

    assert active_generation(session).id == second.id
    assert session.get(EvidenceGraphGeneration, first.id).status == "retired"

    result = rollback_generation(session)
    session.commit()

    assert result["from_generation"] == second.id
    assert result["active_generation"] == first.id
    assert active_generation(session).id == first.id
    session.close()


def test_remove_source_record_tombstones_unsupported_records(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    _write_minimum_graph(session, generation.id, source_record_id="GUIDES-20")
    session.commit()

    result = remove_source_record(
        session,
        generation_id=generation.id,
        source_record_id="GUIDES-20",
    )
    session.commit()

    assert result == {
        "assertions_removed": 2,
        "edges_tombstoned": 1,
        "nodes_tombstoned": 2,
    }
    assert session.query(EvidenceGraphNode).filter_by(active=True).count() == 0
    assert session.query(EvidenceGraphEdge).filter_by(active=True).count() == 0
    session.close()


def test_event_upsert_is_idempotent_and_failed_event_can_be_requeued(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    first = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-1",
        source_hash="sha256:one",
    )
    second = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-1",
        source_hash="sha256:one",
    )
    session.commit()
    assert first == second
    assert session.query(EvidenceGraphSourceEvent).count() == 1

    event_row = session.get(EvidenceGraphSourceEvent, first)
    event_row.status = "failed"
    event_row.attempts = 5
    session.commit()
    enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-1",
        source_hash="sha256:one",
    )
    session.commit()
    assert event_row.status == "pending"
    assert event_row.attempts == 0

    event_row.status = "completed"
    event_row.completed_at = datetime.utcnow()
    session.commit()
    enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-1",
        source_hash="sha256:one",
    )
    session.commit()
    assert event_row.status == "pending"
    assert event_row.completed_at is None
    session.close()


def test_sqlite_lease_prevents_concurrent_worker(tmp_path):
    Session = _session_factory(tmp_path)
    first = Session()
    second = Session()

    first_owner = acquire_graph_lease(first, seconds=60)
    assert first_owner
    assert acquire_graph_lease(second, seconds=60) is None

    release_graph_lease(first, first_owner)
    second_owner = acquire_graph_lease(second, seconds=60)
    assert second_owner
    release_graph_lease(second, second_owner)
    first.close()
    second.close()


def test_status_degrades_for_sync_lag_and_stale_reconciliation(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    _write_minimum_graph(session, generation.id, source_record_id="GUIDES-30")
    promote_generation(session, generation.id)
    update_source_checkpoint(
        session,
        source_name="evidence_graph:reconciliation",
        generation_id=generation.id,
        counts={"nodes": 2},
        cursor={"mode": "full"},
    )
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="late-chunk",
        source_hash="sha256:late",
    )
    session.flush()
    session.get(EvidenceGraphSourceEvent, event_id).created_at = datetime.utcnow() - timedelta(minutes=16)
    session.get(EvidenceGraphSourceState, "evidence_graph:reconciliation").last_success_at = (
        datetime.utcnow() - timedelta(hours=27)
    )
    session.commit()
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "true")

    status = graph_status(session)

    assert status["status"] == "degraded"
    assert status["incremental_sync_lag_seconds"] >= 16 * 60 - 1
    assert status["reconciliation_age_seconds"] >= 27 * 60 * 60 - 1
    assert any("incremental synchronization lag" in reason for reason in status["degraded_reasons"])
    assert any("older than 26 hours" in reason for reason in status["degraded_reasons"])
    session.close()


def test_promoted_generation_integrity_detects_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_INTEGRITY_KEY", "test-integrity-secret")
    monkeypatch.setenv("EVIDENCE_GRAPH_INTEGRITY_KEY_ID", "test-key")
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    _write_minimum_graph(session, generation.id)
    promote_generation(session, generation.id)
    session.commit()

    first_audit = audit_generation(session, generation.id)
    assert first_audit["valid"] is True
    assert first_audit["integrity_verified"] is True
    assert first_audit["integrity"]["sealed"] is True
    assert first_audit["integrity"]["hmac_key_id"] == "test-key"

    monkeypatch.delenv("EVIDENCE_GRAPH_INTEGRITY_KEY")
    missing_key = audit_generation(session, generation.id)
    assert missing_key["valid"] is False
    assert any("key is unavailable" in error for error in missing_key["errors"])
    monkeypatch.setenv("EVIDENCE_GRAPH_INTEGRITY_KEY", "test-integrity-secret")

    node = session.query(EvidenceGraphNode).filter_by(generation_id=generation.id).first()
    node.label = "tampered label"
    session.commit()
    tampered = audit_generation(session, generation.id)

    assert tampered["valid"] is False
    assert tampered["integrity_verified"] is False
    assert any("integrity digest" in error for error in tampered["errors"])
    session.close()


def test_rollback_refuses_tampered_retired_generation(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    first = create_generation(session)
    _write_minimum_graph(session, first.id, source_record_id="GUIDES-40")
    promote_generation(session, first.id)
    second = create_generation(session)
    _write_minimum_graph(session, second.id, source_record_id="GUIDES-41")
    promote_generation(session, second.id)
    session.commit()

    retired_node = session.query(EvidenceGraphNode).filter_by(generation_id=first.id).first()
    retired_node.label = "tampered retired generation"
    session.commit()

    with pytest.raises(ValueError, match="integrity audit"):
        rollback_generation(session)
    assert active_generation(session).id == second.id
    session.close()


def test_query_audit_is_privacy_safe_and_status_reports_latency(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    _write_minimum_graph(session, generation.id, source_record_id="GUIDES-50")
    promote_generation(session, generation.id)
    for index in range(5):
        record_query_audit(
            session,
            generation_id=generation.id,
            tenant_id="kone",
            actor_id="qa.user@example.com",
            query="customer secret xref query",
            selectors={"jira_key": "GUIDES-50", "customer": "KONE"},
            influence_mode="shadow",
            status="ready",
            duration_ms=1600 + index,
            cache_hit=index > 0,
            path_count=2,
            leaf_count=3,
            cross_customer_detail_count=0,
            cross_customer_aggregate_count=1,
            warning_count=0,
        )
    session.commit()
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "true")

    row = session.query(EvidenceGraphQueryAudit).first()
    assert row.query_hash != "customer secret xref query"
    assert row.actor_hash != "qa.user@example.com"
    assert not hasattr(row, "query")
    summary = query_audit_summary(session)
    assert summary["query_count"] == 5
    assert summary["p95_duration_ms"] == 1604
    assert summary["cache_hit_rate"] == 0.8
    status = graph_status(session)
    assert status["status"] == "degraded"
    assert any("p95" in warning for warning in status["warnings"])
    session.close()


def test_failed_events_can_be_inspected_and_explicitly_replayed(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-dead-letter",
        source_hash="sha256:dead-letter",
    )
    session.flush()
    event = session.get(EvidenceGraphSourceEvent, event_id)
    event.status = "failed"
    event.attempts = 5
    event.last_error = "password=secret failed for qa@example.com"
    session.commit()

    listed = list_source_events(session, status="failed")
    assert listed[0]["id"] == event_id
    assert "password=secret" not in listed[0]["last_error"]
    assert "qa@example.com" not in listed[0]["last_error"]
    replayed = replay_source_events(session, event_ids=[event_id])
    session.commit()

    assert replayed["event_ids"] == [event_id]
    assert event.status == "pending"
    assert event.attempts == 0
    assert event.last_error is None
    session.close()


def test_graph_lease_can_be_renewed_only_by_owner(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    owner = acquire_graph_lease(session, seconds=60)
    state = session.query(EvidenceGraphSourceState).filter_by(lease_owner=owner).one()
    first_expiry = state.lease_expires_at

    assert owner
    assert renew_graph_lease(session, "wrong-owner", seconds=120) is False
    assert renew_graph_lease(session, owner, seconds=120) is True
    session.refresh(state)
    assert state.lease_expires_at > first_expiry
    release_graph_lease(session, owner)
    session.close()


def test_status_requires_phase_b_graph_schema_rebuild(tmp_path, monkeypatch):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    _write_minimum_graph(session, generation.id, source_record_id="GUIDES-60")
    promote_generation(session, generation.id)
    generation.schema_version = "evidence-graph-v1"
    session.commit()
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "true")

    status = graph_status(session)

    assert status["status"] == "degraded"
    assert any("rebuild with evidence-graph-v2" in warning for warning in status["warnings"])
    session.close()


def test_source_checkpoint_sanitizes_error_before_storage(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()

    update_source_checkpoint(
        session,
        source_name="evidence_graph:docs",
        generation_id=None,
        error="password=secret failed for qa@example.com",
    )
    session.commit()

    stored = session.get(EvidenceGraphSourceState, "evidence_graph:docs").last_error
    assert "password=secret" not in stored
    assert "qa@example.com" not in stored
    session.close()


def test_graph_writer_rejects_cross_tenant_stable_key_collision(tmp_path):
    Session = _session_factory(tmp_path)
    session = Session()
    generation = create_generation(session)
    writer = GraphWriter(session, generation.id)
    key = "customer:shared"
    writer.write(
        [NodeSpec(stable_key=key, node_type="customer", label="Shared", tenant_id="kone")],
        [],
    )

    with pytest.raises(ValueError, match="multiple tenants"):
        writer.write(
            [NodeSpec(stable_key=key, node_type="customer", label="Shared", tenant_id="other")],
            [],
        )
    session.rollback()
    session.close()
