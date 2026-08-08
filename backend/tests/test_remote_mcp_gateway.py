from fastapi.testclient import TestClient

from app.core.auth import UserIdentity
from app.main import app


def test_remote_mcp_info_and_health():
    client = TestClient(app)

    info = client.get("/mcp", headers={"Authorization": "Bearer test-token"})
    assert info.status_code == 200
    assert info.json()["status"] == "ok"
    assert "guides_test_plan_generator" not in info.json()["tools"]

    health = client.get("/mcp/health", headers={"Authorization": "Bearer test-token"})
    assert health.status_code == 200
    assert health.json()["status"] == "alive"


def test_remote_mcp_initialize_and_tools_list():
    client = TestClient(app)

    init_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert init_response.status_code == 200
    assert init_response.json()["result"]["serverInfo"]["name"] == "aem-guides-dataset-studio"

    tools_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert tools_response.status_code == 200
    tool_names = [tool["name"] for tool in tools_response.json()["result"]["tools"]]
    assert "ask_dita_expert" in tool_names
    assert "guides_test_plan_generator" not in tool_names
    assert "generate_dita_ot_output" in tool_names
    assert "upload_mcp_generated_data_to_aem" in tool_names
    assert "upload_dataset_to_aem" in tool_names
    assert "audit_jira_corpus" in tool_names
    assert "audit_knowledge_corpora" in tool_names
    jira_tool = next(
        tool for tool in tools_response.json()["result"]["tools"] if tool["name"] == "search_jira_history"
    )
    assert jira_tool["inputSchema"]["properties"]["component"]["enum"] == [
        "",
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ]
    graph_tool = next(
        tool for tool in tools_response.json()["result"]["tools"] if tool["name"] == "query_test_evidence_graph"
    )
    assert graph_tool["inputSchema"]["required"] == ["query"]
    assert graph_tool["inputSchema"]["properties"]["max_depth"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 2,
        "default": 2,
    }
    assert graph_tool["inputSchema"]["properties"]["top_k"]["maximum"] == 25
    assert graph_tool["inputSchema"]["properties"]["max_paths"]["maximum"] == 50


def test_remote_mcp_jira_corpus_audit_tool(monkeypatch):
    from app.api.routes import remote_mcp

    monkeypatch.setattr(
        "app.services.jira_corpus_audit_service.audit_jira_corpus",
        lambda **kwargs: {"available": True, "totals": {"unique_issue_count": 7}, "options": kwargs},
    )

    result = remote_mcp._audit_jira_corpus({
        "duplicate_sample_limit": 5,
        "top_components_per_customer": 3,
    })

    assert result["totals"]["unique_issue_count"] == 7
    assert result["options"] == {"duplicate_sample_limit": 5, "top_components_per_customer": 3}


def test_remote_mcp_knowledge_corpus_audit_tool(monkeypatch):
    from app.api.routes import remote_mcp

    monkeypatch.setattr(
        "app.services.knowledge_corpus_audit_service.audit_knowledge_corpora",
        lambda **kwargs: {"available": True, "summary": {"knowledge_gap_count": 4}, "options": kwargs},
    )

    result = remote_mcp._audit_knowledge_corpora({"duplicate_sample_limit": 500})

    assert result["summary"]["knowledge_gap_count"] == 4
    assert result["options"] == {"duplicate_sample_limit": 100}


def test_jira_history_rejects_noncanonical_component_before_search():
    from app.api.routes import remote_mcp

    result = remote_mcp._search_jira_history(
        {"query": "save failure", "component": "Platform and Integration"}
    )

    assert result == {
        "error": "Unsupported Jira component.",
        "component": "Platform and Integration",
        "allowed_components": [
            "Editor",
            "Authoring",
            "Publishing",
            "Platform",
            "Schematron",
            "Integration",
        ],
    }


def test_rag_status_reports_invalid_jira_project_without_failing(monkeypatch):
    from app.api.routes import remote_mcp

    monkeypatch.setattr(
        "app.services.jira_sync_cursor_service.resolve_sync_project_key",
        lambda: (_ for _ in ()).throw(ValueError("invalid Jira project")),
    )
    monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: False)
    monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: True)

    result = remote_mcp._check_rag_status({})

    cursor = result["jira_corpus_coverage"]["incremental_sync_cursor"]
    assert result["status"] == "ok"
    assert cursor["valid"] is False
    assert cursor["health"]["missing_or_invalid_fields"] == ["project_key"]
    assert cursor["health"]["configuration_error"] == "invalid Jira project"


def test_graph_query_enforces_tenant_and_aggregates_for_regular_user(monkeypatch):
    from app.api.routes import remote_mcp

    captured = {}
    monkeypatch.setattr(
        "app.services.evidence_graph_query_service.query_test_evidence_graph",
        lambda query, **kwargs: captured.update({"query": query, **kwargs}) or {"available": True},
    )
    user = UserIdentity(
        id="writer",
        roles=["writer"],
        allowed_tenants=["kone"],
    )

    result = remote_mcp._query_test_evidence_graph(
        {
            "query": "xref publishing",
            "tenant_id": "kone",
            "component": "Editor",
            "include_cross_customer": True,
        },
        user,
    )

    assert result == {"available": True}
    assert captured["tenant_id"] == "kone"
    assert captured["allow_cross_customer_details"] is False
    assert captured["include_cross_customer"] is True
    assert captured["actor_id"] == "writer"
    assert captured["influence_mode"] == "interactive"


def test_graph_query_allows_ticket_details_for_knowledge_reader(monkeypatch):
    from app.api.routes import remote_mcp

    captured = {}
    monkeypatch.setattr(
        "app.services.evidence_graph_query_service.query_test_evidence_graph",
        lambda query, **kwargs: captured.update({"query": query, **kwargs}) or {"available": True},
    )
    user = UserIdentity(
        id="reader",
        roles=["knowledge_reader"],
        allowed_tenants=["kone"],
    )

    remote_mcp._query_test_evidence_graph({"query": "xref", "tenant_id": "kone"}, user)

    assert captured["allow_cross_customer_details"] is True
    assert captured["actor_id"] == "reader"
    assert captured["influence_mode"] == "interactive"


def test_graph_query_rejects_unauthorized_tenant():
    from fastapi import HTTPException
    from app.api.routes import remote_mcp

    user = UserIdentity(id="writer", roles=["writer"], allowed_tenants=["kone"])
    try:
        remote_mcp._query_test_evidence_graph(
            {"query": "xref", "tenant_id": "other"},
            user,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Unauthorized tenant was accepted")
