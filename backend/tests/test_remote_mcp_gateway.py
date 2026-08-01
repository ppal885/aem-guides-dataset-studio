from fastapi.testclient import TestClient

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
