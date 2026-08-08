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
from app.services import evidence_graph_build_service as build_service
from app.services.evidence_graph_contract import EvidenceSpec, NodeSpec
from app.services.evidence_graph_store import (
    acquire_graph_lease,
    active_generation,
    release_graph_lease,
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
        f"sqlite:///{tmp_path / 'rebuild-graph.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=GRAPH_TABLES)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _source_builder(source_name):
    def build(writer, *, persist_session=None):
        evidence = EvidenceSpec(
            source_kind=f"{source_name}_fixture",
            source_ref=f"fixture:{source_name}",
            source_record_id=f"{source_name}-record",
            source_hash=f"sha256:{source_name}",
            extraction_method="deterministic_fixture",
            authority="official_fixture",
            trust_tier="authoritative",
            excerpt=f"{source_name} evidence",
        )
        writer.write(
            [
                NodeSpec(
                    stable_key=f"feature:{source_name}",
                    node_type="feature",
                    label=f"{source_name} feature",
                    evidence=[evidence],
                )
            ],
            [],
        )
        if persist_session is not None:
            persist_session.commit()
        return {"scan_complete": True, "scanned": 1, "expected": 1}

    return build


def _install_successful_sources(monkeypatch):
    jira = _source_builder("jira")
    docs = _source_builder("docs")
    dita = _source_builder("dita")
    monkeypatch.setattr(
        build_service,
        "_build_jira_source",
        lambda session, writer, **_kwargs: jira(writer, persist_session=session),
    )
    monkeypatch.setattr(
        build_service,
        "_build_docs_source",
        lambda writer, session, **_kwargs: docs(writer, persist_session=session),
    )
    monkeypatch.setattr(
        build_service,
        "_build_dita_source",
        lambda session, writer, **_kwargs: dita(writer, persist_session=session),
    )


def test_full_rebuild_promotes_only_complete_audited_generation(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)

    result = build_service.rebuild_evidence_graph(dry_run=False, batch_size=500)

    assert result["valid"] is True
    assert result["promoted"] is True
    assert result["performance"]["accepted"] is True
    assert all(source["scan_complete"] for source in result["sources"].values())
    session = Session()
    assert active_generation(session).id == result["generation_id"]
    reconciliation = session.get(EvidenceGraphSourceState, "evidence_graph:reconciliation")
    assert reconciliation.last_success_at is not None
    assert reconciliation.active_generation_id == result["generation_id"]
    assert session.query(EvidenceGraphSyncRun).filter_by(status="succeeded").count() == 1
    session.close()


def test_incomplete_source_scan_is_failed_and_never_promoted(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)
    monkeypatch.setattr(
        build_service,
        "_build_docs_source",
        lambda *_args, **_kwargs: {"scan_complete": False, "scanned": 42100, "expected": 42198},
    )

    result = build_service.rebuild_evidence_graph(dry_run=False)

    assert result["valid"] is False
    assert result["promoted"] is False
    assert any("did not report complete coverage" in error for error in result["errors"])
    session = Session()
    assert active_generation(session) is None
    assert session.get(EvidenceGraphGeneration, result["generation_id"]).status == "failed"
    session.close()


def test_dry_run_does_not_persist_generation(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)

    result = build_service.rebuild_evidence_graph(dry_run=True)

    assert result["valid"] is True
    assert result["generation_id"] is None
    assert result["promoted"] is False
    session = Session()
    assert session.query(EvidenceGraphGeneration).count() == 0
    session.close()


def test_performance_acceptance_failure_prevents_promotion(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)
    monkeypatch.setattr(
        build_service,
        "_performance_result",
        lambda _started: {
            "elapsed_seconds": 1201.0,
            "peak_memory_mb": 1600.0,
            "limits": {"max_seconds": 1200, "max_memory_mb": 1536},
            "elapsed_ok": False,
            "memory_ok": False,
            "accepted": False,
        },
    )

    result = build_service.rebuild_evidence_graph(dry_run=False)

    assert result["valid"] is False
    assert result["promoted"] is False
    assert any("performance acceptance failed" in error for error in result["errors"])
    session = Session()
    assert active_generation(session) is None
    session.close()


def test_full_reconciliation_reports_deleted_and_tombstoned_sources(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)
    first = build_service.rebuild_evidence_graph(dry_run=False)
    assert first["promoted"] is True

    changed_docs = _source_builder("docs-v2")
    monkeypatch.setattr(
        build_service,
        "_build_docs_source",
        lambda writer, session, **_kwargs: changed_docs(writer, persist_session=session),
    )
    second = build_service.rebuild_evidence_graph(dry_run=False)

    assert second["promoted"] is True
    assert second["reconciliation"]["previous_generation_id"] == first["generation_id"]
    assert second["reconciliation"]["added_source_records"] == 1
    assert second["reconciliation"]["deleted_source_records"] == 1
    assert second["reconciliation"]["stale_assertions_removed"] >= 1
    assert second["reconciliation"]["tombstoned_entities"] >= 1


def test_full_rebuild_respects_existing_database_lease(monkeypatch, tmp_path):
    Session = _factory(tmp_path)
    monkeypatch.setattr(build_service, "SessionLocal", Session)
    _install_successful_sources(monkeypatch)
    session = Session()
    owner = acquire_graph_lease(session, seconds=120)
    assert owner

    result = build_service.rebuild_evidence_graph(dry_run=False)

    assert result["valid"] is False
    assert result["status"] == "lease_held"
    assert result["generation_id"] is None
    release_graph_lease(session, owner)
    session.close()


def test_applied_rebuild_refuses_partial_source_set():
    result = build_service.rebuild_evidence_graph(
        dry_run=False,
        sources=["docs"],
    )

    assert result["valid"] is False
    assert result["status"] == "partial_apply_refused"
    assert result["generation_id"] is None
    assert result["promoted"] is False
    assert "jira" in result["errors"][0]
    assert "dita" in result["errors"][0]
