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
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _iter_loggers() -> list[logging.Logger]:
    return [logging.getLogger(name) for name in logging.root.manager.loggerDict]


def strip_stdout_log_handlers() -> int:
    """Remove StreamHandlers bound to stdout so logs cannot corrupt MCP JSON-RPC."""
    removed = 0
    candidates = [logging.getLogger()] + _iter_loggers()
    for logger in candidates:
        for handler in list(logger.handlers):
            stream = getattr(handler, "stream", None)
            if isinstance(handler, logging.StreamHandler) and stream is sys.stdout:
                logger.removeHandler(handler)
                removed += 1
    return removed


def configure_mcp_stdio_runtime(*, log_level: str | None = None) -> None:
    """Configure process-wide logging/progress behavior for MCP stdio servers."""
    _force_mcp_stdio_env()

    level = (log_level or os.getenv("LOG_LEVEL") or "INFO").upper()
    from app.core.logging_config import setup_logging

    # Plain text to stderr keeps Rich/JSON logs off stdout and is easier to read in MCP logs.
    setup_logging(level, structured=False)
    strip_stdout_log_handlers()

    from app.core.observability import reset_observability_handler_for_mcp_stdio

    reset_observability_handler_for_mcp_stdio()
    strip_stdout_log_handlers()

    warnings.showwarning = _warn_to_stderr

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root.addHandler(handler)
        root.setLevel(getattr(logging, level, logging.INFO))


def _warn_to_stderr(message, category, filename, lineno, file=None, line=None):
    sys.stderr.write(warnings.formatwarning(message, category, filename, lineno, line))
