"""In-process counters for QA copilot observability."""

from __future__ import annotations

from collections import Counter
from typing import Any


class CopilotMetrics:
    """Tiny process-local metric accumulator suitable for tests and logs."""

    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()

    def increment(self, name: str, value: int = 1) -> None:
        self._counter[name] += value

    def snapshot(self) -> dict[str, Any]:
        return dict(self._counter)


metrics = CopilotMetrics()

