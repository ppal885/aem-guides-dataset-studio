"""Timing and structured logging for enterprise QA pipeline steps."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class EnterpriseQaTrace:
    session_id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)

    def step(self, name: str, **extra: Any) -> None:
        """Record elapsed ms since trace start."""
        elapsed_ms = round((time.perf_counter() - self.t0) * 1000, 2)
        row = {"name": name, "elapsed_ms": elapsed_ms, **extra}
        self.steps.append(row)
        logger.info_structured("enterprise_qa_step", extra_fields=row)

    def to_dict(self) -> dict[str, Any]:
        total = round((time.perf_counter() - self.t0) * 1000, 2)
        return {"session_id": self.session_id, "steps": self.steps, "total_latency_ms": total}
