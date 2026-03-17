"""
Observability: structlog-style structured logging for DITA generation and LLM flows.

Usage:
    from app.core.observability import get_observability_logger
    log = get_observability_logger()
    log.info("dita_generation_started", run_id=run_id, session_id=session_id, topic_count=n)
"""
import logging
import sys
from typing import Any, Optional

import structlog

# Shared processors for structlog
_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]

# Configure structlog: stdlib integration with JSON output
structlog.configure(
    processors=_SHARED_PROCESSORS + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Formatter for observability loggers: outputs JSON
_observability_formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=_SHARED_PROCESSORS,
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.JSONRenderer(),
    ],
)

_observability_handler_configured = False


def _ensure_observability_handler() -> None:
    """Ensure app.observability logger has JSON handler."""
    global _observability_handler_configured
    if _observability_handler_configured:
        return
    _observability_handler_configured = True
    obs_logger = logging.getLogger("app.observability")
    if not obs_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_observability_formatter)
        obs_logger.addHandler(handler)
        obs_logger.setLevel(logging.INFO)
        obs_logger.propagate = False


def get_observability_logger(name: str = "observability") -> structlog.stdlib.BoundLogger:
    """
    Get a structlog-style logger for observability events.
    Use kwargs for structured fields: log.info("event_name", key=value, ...)
    """
    _ensure_observability_handler()
    return structlog.get_logger(f"app.observability.{name}")
