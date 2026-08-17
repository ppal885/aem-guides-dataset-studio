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
from app.services import evidence_graph_sync_service as sync_service
from app.services.evidence_graph_contract import EvidenceSpec, NodeSpec
from app.services.evidence_graph_store import (
    GraphWriter,
    active_generation,
    create_generation,
    enqueue_source_event,
    promote_generation,
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


def _factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sync-graph.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=GRAPH_TABLES)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _evidence(record_id, *, kind="aem_guides_chroma", source_hash=None):
    return EvidenceSpec(
        source_kind=kind,
        source_ref=f"https://example.test/{record_id}",
        source_record_id=record_id,
        source_chunk_id=record_id,
        source_hash=source_hash or f"sha256:{record_id}",
        extraction_method="exact_fixture",
        authority="official_fixture",
        trust_tier="authoritative",
        excerpt=f"Evidence {record_id}",
    )


def _build_active(Session, records=("chunk-keep", "chunk-delete")):
    session = Session()
    generation = create_generation(session)
    writer = GraphWriter(session, generation.id)
    writer.write(
        [
            NodeSpec(
                stable_key=f"doc:{record_id}",
                node_type="documentation_page",
                label=f"Document {record_id}",
                properties={"canonical_url": f"https://example.test/{record_id}", "official": True},
                evidence=[_evidence(record_id)],
            )
            for record_id in records
        ],
        [],
    )
    generation_id = generation.id
    promote_generation(session, generation.id)
    session.commit()
    session.close()
    return generation_id


def _install(monkeypatch, Session):
    monkeypatch.setattr(sync_service, "SessionLocal", Session)
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "true")


def test_incremental_event_clones_audits_and_promotes(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    base_id = _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-new",
        source_hash="sha256:new",
    )
    session.commit()
    session.close()

    def apply_event(_session, writer, source_event):
        writer.write(
            [
                NodeSpec(
                    stable_key="doc:chunk-new",
                    node_type="documentation_page",
                    label="New document",
                    properties={"canonical_url": "https://example.test/chunk-new", "official": True},
                    evidence=[_evidence("chunk-new", source_hash=source_event.source_hash)],
                )
            ],
            [],
        )
        return {"source": "docs", "record_id": "chunk-new", "found": True}

    monkeypatch.setattr(sync_service, "_apply_event", apply_event)
    result = sync_service.drain_evidence_graph_events(max_events=10, batch_size=10)

    assert result["success"] is True
    assert result["base_generation_id"] == base_id
    assert result["generation_id"] != base_id
    check = Session()
    assert active_generation(check).id == result["generation_id"]
    assert check.get(EvidenceGraphSourceEvent, event_id).status == "completed"
    assert check.query(EvidenceGraphNode).filter_by(
        generation_id=result["generation_id"], stable_key="doc:chunk-new", active=True
    ).count() == 1
    assert check.get(EvidenceGraphGeneration, base_id).status == "retired"
    check.close()


def test_delete_event_tombstones_source_and_keeps_valid_generation(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    base_id = _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-delete",
        source_hash="sha256:delete",
        event_type="delete",
    )
    session.commit()
    session.close()

    result = sync_service.drain_evidence_graph_events(max_events=10, batch_size=10)

    assert result["success"] is True
    assert result["base_generation_id"] == base_id
    check = Session()
    active_id = active_generation(check).id
    deleted = check.query(EvidenceGraphNode).filter_by(
        generation_id=active_id,
        stable_key="doc:chunk-delete",
    ).one()
    kept = check.query(EvidenceGraphNode).filter_by(
        generation_id=active_id,
        stable_key="doc:chunk-keep",
    ).one()
    assert deleted.active is False
    assert kept.active is True
    assert check.get(EvidenceGraphSourceEvent, event_id).status == "completed"
    check.close()


def test_jira_chunk_delete_rebuilds_issue_when_other_source_evidence_remains(monkeypatch):
    calls = []
    monkeypatch.setattr(
        sync_service,
        "remove_source_record",
        lambda session, **kwargs: calls.append(("remove", kwargs)) or {"assertions_removed": 2},
    )
    monkeypatch.setattr(
        sync_service,
        "upsert_jira_issue_into_generation",
        lambda session, writer, record_id: calls.append(("upsert", record_id))
        or {"found": True, "record_id": record_id},
    )
    event = EvidenceGraphSourceEvent(
        id="event-jira-delete",
        source_kind="jira",
        source_record_id="GUIDES-100",
        source_hash="sha256:delete",
        event_type="delete",
        status="pending",
    )

    result = sync_service._apply_event(object(), type("Writer", (), {"generation_id": "g1"})(), event)

    assert [entry[0] for entry in calls] == ["remove", "upsert"]
    assert result["found"] is True
    assert "deleted" not in result


def test_dita_chroma_event_does_not_remove_same_id_sql_assertions(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        sync_service,
        "remove_source_record",
        lambda session, **kwargs: captured.update(kwargs) or {"assertions_removed": 1},
    )
    monkeypatch.setattr(
        sync_service,
        "upsert_dita_record_into_generation",
        lambda session, writer, record_id: {"found": True, "record_id": record_id},
    )
    event = EvidenceGraphSourceEvent(
        id="event-dita-chroma",
        source_kind="dita",
        source_record_id="shared-chunk-id",
        source_hash="sha256:update",
        event_type="upsert",
        status="pending",
    )

    result = sync_service._apply_event(object(), type("Writer", (), {"generation_id": "g1"})(), event)

    assert result["found"] is True
    assert captured["source_record_id"] == "shared-chunk-id"
    assert captured["source_kinds"] == ("dita_spec_chroma",)


def test_failed_incremental_event_never_promotes_and_exhausts_retry(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    base_id = _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-fail",
        source_hash="sha256:fail",
    )
    session.commit()
    session.close()
    monkeypatch.setattr(
        sync_service,
        "_apply_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("adapter failure password=secret qa@example.com")
        ),
    )

    result = sync_service.drain_evidence_graph_events(max_retries=1, batch_size=10)

    assert result["success"] is False
    assert "adapter failure" in result["error"]
    check = Session()
    assert active_generation(check).id == base_id
    event_row = check.get(EvidenceGraphSourceEvent, event_id)
    assert event_row.status == "failed"
    assert event_row.attempts == 1
    assert "password=secret" not in event_row.last_error
    assert "qa@example.com" not in event_row.last_error
    failed_generation = check.get(EvidenceGraphGeneration, result["generation_id"])
    assert failed_generation.status == "failed"
    assert check.query(EvidenceGraphSyncRun).filter_by(status="failed").count() == 1
    check.close()

    repeated = sync_service.drain_evidence_graph_events(max_events=10, batch_size=10)
    assert repeated["success"] is False
    assert repeated["status"] == "failed_events_pending"
    assert repeated["failed_events"] == 1


def test_events_for_same_record_are_coalesced_and_all_acknowledged(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    ids = [
        enqueue_source_event(
            session,
            source_kind="docs",
            source_record_id="chunk-same",
            source_hash=f"sha256:{suffix}",
        )
        for suffix in ("old", "new")
    ]
    session.commit()
    session.close()
    calls = []

    def apply_event(_session, writer, source_event):
        calls.append(source_event.source_hash)
        writer.write(
            [
                NodeSpec(
                    stable_key="doc:chunk-same",
                    node_type="documentation_page",
                    label="Coalesced document",
                    properties={"canonical_url": "https://example.test/chunk-same", "official": True},
                    evidence=[_evidence("chunk-same", source_hash=source_event.source_hash)],
                )
            ],
            [],
        )
        return {"found": True}

    monkeypatch.setattr(sync_service, "_apply_event", apply_event)
    result = sync_service.drain_evidence_graph_events(max_events=10, batch_size=10)

    assert result["success"] is True
    assert len(calls) == 1
    check = Session()
    assert {check.get(EvidenceGraphSourceEvent, event_id).status for event_id in ids} == {"completed"}
    check.close()


def test_reconciliation_acknowledges_events_only_after_successful_promotion(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-reconcile",
        source_hash="sha256:reconcile",
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        sync_service,
        "rebuild_evidence_graph",
        lambda **_kwargs: {"valid": False, "promoted": False, "errors": ["partial scan"]},
    )
    failed = sync_service.reconcile_evidence_graph()
    assert failed["valid"] is False
    check = Session()
    assert check.get(EvidenceGraphSourceEvent, event_id).status == "pending"
    check.get(EvidenceGraphSourceEvent, event_id).status = "failed"
    check.commit()
    check.close()

    monkeypatch.setattr(
        sync_service,
        "rebuild_evidence_graph",
        lambda **_kwargs: {"valid": True, "promoted": True, "errors": []},
    )
    succeeded = sync_service.reconcile_evidence_graph()
    assert succeeded["valid"] is True
    check = Session()
    assert check.get(EvidenceGraphSourceEvent, event_id).status == "completed"
    check.close()


def test_reconciliation_keeps_events_created_during_scan_pending(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    _build_active(Session)
    _install(monkeypatch, Session)
    during_scan_event_id = None

    def rebuild(**_kwargs):
        nonlocal during_scan_event_id
        writer = Session()
        during_scan_event_id = enqueue_source_event(
            writer,
            source_kind="docs",
            source_record_id="changed-during-reconciliation",
            source_hash="sha256:during",
        )
        writer.commit()
        writer.close()
        return {"valid": True, "promoted": True, "errors": []}

    monkeypatch.setattr(sync_service, "rebuild_evidence_graph", rebuild)

    result = sync_service.reconcile_evidence_graph()

    assert result["valid"] is True
    check = Session()
    assert check.get(EvidenceGraphSourceEvent, during_scan_event_id).status == "pending"
    check.close()


def test_incremental_sync_never_promotes_after_lease_loss(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    base_id = _build_active(Session)
    _install(monkeypatch, Session)
    session = Session()
    event_id = enqueue_source_event(
        session,
        source_kind="docs",
        source_record_id="chunk-lease-loss",
        source_hash="sha256:lease-loss",
    )
    session.commit()
    session.close()
    monkeypatch.setattr(sync_service, "renew_graph_lease", lambda *_args, **_kwargs: False)

    result = sync_service.drain_evidence_graph_events(max_retries=2, batch_size=10)

    assert result["success"] is False
    assert "lease was lost" in result["error"]
    check = Session()
    assert active_generation(check).id == base_id
    assert check.get(EvidenceGraphSourceEvent, event_id).status == "retry"
    failed_generation = check.get(EvidenceGraphGeneration, result["generation_id"])
    assert failed_generation.status == "failed"
    check.close()
