import logging
import sys
from pathlib import Path

from app.core.mcp_stdio import configure_mcp_stdio_runtime, is_mcp_stdio_mode, strip_stdio_log_handlers


MCP_SERVER_PATH = Path(__file__).resolve().parents[2] / "mcp_server.py"


def test_is_mcp_stdio_mode_after_configure():
    configure_mcp_stdio_runtime()
    assert is_mcp_stdio_mode()


def test_configure_removes_stdout_handlers():
    logger = logging.getLogger("test.mcp_stdio")
    stdout_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(stdout_handler)
    try:
        configure_mcp_stdio_runtime()
        assert strip_stdio_log_handlers() == 0
        assert all(getattr(h, "stream", None) is not sys.stdout for h in logger.handlers)
    finally:
        logger.removeHandler(stdout_handler)


def test_observability_muted_in_mcp_stdio_mode(monkeypatch):
    monkeypatch.setenv("AEM_DATASET_STUDIO_MCP_STDIO", "1")
    monkeypatch.setenv("AEM_DATASET_STUDIO_MCP_SUPPRESS_CONSOLE_LOGS", "1")
    from app.core import observability as obs

    obs._observability_handler_configured = False
    obs.reset_observability_handler_for_mcp_stdio()
    logger = logging.getLogger("app.observability")
    assert logger.handlers == []
    obs.get_observability_logger("test").info("ignored", topic_count=1)


def test_langsmith_disabled_in_mcp_stdio_mode():
    configure_mcp_stdio_runtime()
    import os

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_test_plan_workflows_are_not_registered_as_stdio_mcp_tools():
    source = MCP_SERVER_PATH.read_text(encoding="utf-8")

    for function_name in (
        "guides_test_plan_generator",
        "test_plan_pipeline",
        "publishing_ticket_dita_qa_packet",
    ):
        assert f"@mcp.tool()\ndef {function_name}" not in source
