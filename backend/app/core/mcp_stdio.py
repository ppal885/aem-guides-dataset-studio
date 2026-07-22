"""MCP stdio runtime hardening for Dataset Studio.

MCP speaks JSON-RPC exclusively on stdout. Any log line, tqdm bar, or structlog
JSON event on stdout corrupts the transport (Cursor shows invalid jsonrpc errors
with keys like run_id/event/topic_count).

Call ``configure_mcp_stdio_runtime()`` once at MCP server startup, after dotenv.
"""
from __future__ import annotations

import logging
import os
import sys
import warnings


def is_mcp_stdio_mode() -> bool:
    return os.getenv("AEM_DATASET_STUDIO_MCP_STDIO", "").lower() in {"1", "true", "yes"}


def _force_mcp_stdio_env() -> None:
    """Force MCP-safe env after dotenv — do not let .env re-enable stdout noise."""
    os.environ["AEM_DATASET_STUDIO_MCP_STDIO"] = "1"
    os.environ["AEM_DATASET_STUDIO_MCP_SUPPRESS_CONSOLE_LOGS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _iter_loggers() -> list[logging.Logger]:
    return [logging.getLogger(name) for name in logging.root.manager.loggerDict]


def strip_stdio_log_handlers() -> int:
    """Remove stdout/stderr StreamHandlers so Cursor MCP stdio stays quiet."""
    removed = 0
    candidates = [logging.getLogger()] + _iter_loggers()
    for logger in candidates:
        for handler in list(logger.handlers):
            stream = getattr(handler, "stream", None)
            if isinstance(handler, logging.StreamHandler) and stream in {sys.stdout, sys.stderr}:
                logger.removeHandler(handler)
                removed += 1
    return removed


def silence_noisy_stdio_loggers() -> None:
    """Keep third-party MCP/tooling loggers from emitting INFO lines to Cursor."""
    for name in (
        "",
        "app",
        "mcp",
        "mcp.server",
        "mcp.server.lowlevel",
        "mcp.server.lowlevel.server",
        "httpx",
        "httpcore",
        "langsmith",
        "openai",
        "azure",
    ):
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)
        logger.propagate = False if name in {"mcp", "mcp.server", "mcp.server.lowlevel.server"} else logger.propagate


def configure_mcp_stdio_runtime(*, log_level: str | None = None) -> None:
    """Configure process-wide logging/progress behavior for MCP stdio servers."""
    _force_mcp_stdio_env()

    level = (log_level or os.getenv("LOG_LEVEL") or "INFO").upper()
    from app.core.logging_config import setup_logging

    # Plain text to stderr keeps Rich/JSON logs off stdout and is easier to read in MCP logs.
    setup_logging(level, structured=False)
    strip_stdio_log_handlers()
    silence_noisy_stdio_loggers()

    from app.core.observability import reset_observability_handler_for_mcp_stdio

    reset_observability_handler_for_mcp_stdio()
    strip_stdio_log_handlers()
    silence_noisy_stdio_loggers()

    warnings.showwarning = _warn_to_stderr

    root = logging.getLogger()
    root.setLevel(logging.WARNING)


def _warn_to_stderr(message, category, filename, lineno, file=None, line=None):
    sys.stderr.write(warnings.formatwarning(message, category, filename, lineno, line))
