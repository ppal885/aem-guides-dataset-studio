from pathlib import Path


MCP_SERVER_PATH = Path(__file__).resolve().parents[2] / "mcp_server.py"


def test_test_plan_workflows_are_not_registered_as_stdio_mcp_tools():
    source = MCP_SERVER_PATH.read_text(encoding="utf-8")

    for function_name in (
        "guides_test_plan_generator",
        "test_plan_pipeline",
        "publishing_ticket_dita_qa_packet",
    ):
        assert f"@mcp.tool()\ndef {function_name}" not in source
