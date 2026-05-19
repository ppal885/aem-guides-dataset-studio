"""Lightweight tracing for QA copilot agent and tool execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class CopilotTrace:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    steps: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)

    def step(self, name: str, **extra: Any) -> None:
        elapsed_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        row = {"name": name, "elapsed_ms": elapsed_ms, **extra}
        self.steps.append(row)
        logger.info_structured("qa_copilot_step", extra_fields={"trace_id": self.trace_id, **row})

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "steps": self.steps,
            "total_latency_ms": round((time.perf_counter() - self.started_at) * 1000, 2),
        }

