from fastapi.testclient import TestClient

from app.main import app


def test_admin_graph_status_and_audit_routes(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        "app.services.evidence_graph_store.graph_status",
        lambda _session: {"status": "ready", "active_generation_id": "generation-1"},
    )
    monkeypatch.setattr(
        "app.services.evidence_graph_store.active_generation",
        lambda _session: type("Generation", (), {"id": "generation-1"})(),
    )
    monkeypatch.setattr(
        "app.services.evidence_graph_store.audit_generation",
        lambda _session, generation_id: {"valid": True, "generation_id": generation_id},
    )

    status = client.get(
        "/api/v1/admin/evidence-graph/status",
        headers={"Authorization": "Bearer test-token"},
    )
    audit = client.get(
        "/api/v1/admin/evidence-graph/audit",
        headers={"Authorization": "Bearer test-token"},
    )

    assert status.status_code == 200
    assert status.json()["active_generation_id"] == "generation-1"
    assert audit.status_code == 200
    assert audit.json() == {"valid": True, "generation_id": "generation-1"}


def test_admin_rebuild_sync_and_rollback_routes(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        "app.services.evidence_graph_build_service.rebuild_evidence_graph",
        lambda **kwargs: {"valid": True, "promoted": not kwargs["dry_run"], "options": kwargs},
    )
    monkeypatch.setattr(
        "app.services.evidence_graph_sync_service.drain_evidence_graph_events",
        lambda **kwargs: {"success": True, "status": "succeeded", "options": kwargs},
    )
    monkeypatch.setattr(
        "app.services.evidence_graph_store.rollback_generation",
        lambda _session: {"rolled_back": True, "active_generation": "generation-0"},
    )
    headers = {"Authorization": "Bearer test-token"}

    rebuild = client.post(
        "/api/v1/admin/evidence-graph/rebuild",
        headers=headers,
        json={"dry_run": True, "sources": ["jira", "docs", "dita"], "batch_size": 500},
    )
    sync = client.post(
        "/api/v1/admin/evidence-graph/sync",
        headers=headers,
        json={"max_events": 100, "max_retries": 3, "batch_size": 500},
    )
    rollback = client.post(
        "/api/v1/admin/evidence-graph/rollback",
        headers=headers,
    )

    assert rebuild.status_code == 200
    assert rebuild.json()["options"]["created_by"] == "test-user-1"
    assert sync.status_code == 200
    assert sync.json()["options"]["max_events"] == 100
    assert rollback.status_code == 200
    assert rollback.json()["rolled_back"] is True


def test_admin_graph_mutations_require_admin(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        '{"reader-token":{"id":"reader","roles":["knowledge_reader"],"allowed_tenants":["kone"]}}',
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/evidence-graph/sync",
        headers={"Authorization": "Bearer reader-token"},
        json={},
    )

    assert response.status_code == 403


def test_admin_can_inspect_and_replay_failed_graph_events(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        "app.services.evidence_graph_store.list_source_events",
        lambda _session, **kwargs: [
            {"id": "event-1", "status": kwargs["status"], "source_kind": "docs"}
        ],
    )
    monkeypatch.setattr(
        "app.services.evidence_graph_store.replay_source_events",
        lambda _session, **kwargs: {"replayed": 1, "event_ids": kwargs["event_ids"]},
    )
    headers = {"Authorization": "Bearer test-token"}

    listed = client.get(
        "/api/v1/admin/evidence-graph/events?status=failed&limit=10",
        headers=headers,
    )
    unsafe = client.post(
        "/api/v1/admin/evidence-graph/events/replay",
        headers=headers,
        json={},
    )
    replayed = client.post(
        "/api/v1/admin/evidence-graph/events/replay",
        headers=headers,
        json={"event_ids": ["event-1"]},
    )

    assert listed.status_code == 200
    assert listed.json()["events"][0]["id"] == "event-1"
    assert unsafe.status_code == 400
    assert replayed.status_code == 200
    assert replayed.json()["event_ids"] == ["event-1"]
