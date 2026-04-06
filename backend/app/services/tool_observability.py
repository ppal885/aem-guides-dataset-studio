"""Tool execution observability — structured metrics for the agentic tool loop.

Collects per-tool execution records during a chat turn and emits a summary
via structured logging when the turn completes.

Feature flag: CHAT_TOOL_OBSERVABILITY (default True)
"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger("chat_tools_obs")


@dataclass
class ToolExecutionRecord:
    """Single tool execution record within a chat turn."""

    tool_name: str
    round_idx: int
    latency_ms: float = 0.0
    success: bool = True
    error_category: str = ""  # From ToolErrorCategory if available
    error_message: str = ""
    retry_count: int = 0
    was_parse_error: bool = False
    input_summary: str = ""  # First 200 chars of input
    output_summary: str = ""  # First 200 chars of output

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "tool_name": self.tool_name,
            "round_idx": self.round_idx,
            "latency_ms": round(self.latency_ms, 1),
            "success": self.success,
        }
        if self.error_category:
            d["error_category"] = self.error_category
        if self.error_message:
            d["error_message"] = self.error_message[:200]
        if self.retry_count > 0:
            d["retry_count"] = self.retry_count
        if self.was_parse_error:
            d["was_parse_error"] = True
        if self.input_summary:
            d["input_summary"] = self.input_summary
        if self.output_summary:
            d["output_summary"] = self.output_summary
        return d


@dataclass
class ToolObservabilityCollector:
    """Collects tool execution records for one chat turn."""

    session_id: str = ""
    trace_id: str = ""
    records: list[ToolExecutionRecord] = field(default_factory=list)
    _turn_start: float = field(default_factory=time.monotonic)

    def record_execution(
        self,
        *,
        tool_name: str,
        round_idx: int,
        latency_ms: float,
        success: bool,
        error_category: str = "",
        error_message: str = "",
        retry_count: int = 0,
        was_parse_error: bool = False,
        input_summary: str = "",
        output_summary: str = "",
    ) -> ToolExecutionRecord:
        """Record a single tool execution."""
        rec = ToolExecutionRecord(
            tool_name=tool_name,
            round_idx=round_idx,
            latency_ms=latency_ms,
            success=success,
            error_category=error_category,
            error_message=error_message,
            retry_count=retry_count,
            was_parse_error=was_parse_error,
            input_summary=input_summary[:200] if input_summary else "",
            output_summary=output_summary[:200] if output_summary else "",
        )
        self.records.append(rec)
        return rec

    # ── Computed properties ──

    @property
    def total_tool_time_ms(self) -> float:
        """Total time spent in tool execution across all records."""
        return sum(r.latency_ms for r in self.records)

    @property
    def tool_count(self) -> int:
        """Total number of tool executions."""
        return len(self.records)

    @property
    def tools_used(self) -> list[str]:
        """Unique tool names used in this turn, in order of first use."""
        seen: set[str] = set()
        result: list[str] = []
        for r in self.records:
            if r.tool_name not in seen:
                seen.add(r.tool_name)
                result.append(r.tool_name)
        return result

    @property
    def tool_failure_count(self) -> int:
        """Number of failed tool executions."""
        return sum(1 for r in self.records if not r.success)

    @property
    def tool_failure_rate(self) -> float:
        """Fraction of tool executions that failed (0.0-1.0)."""
        if not self.records:
            return 0.0
        return self.tool_failure_count / len(self.records)

    @property
    def total_retries(self) -> int:
        """Total retry attempts across all records."""
        return sum(r.retry_count for r in self.records)

    @property
    def max_round(self) -> int:
        """Highest round index seen."""
        if not self.records:
            return 0
        return max(r.round_idx for r in self.records)

    @property
    def parse_error_count(self) -> int:
        """Number of tool calls with parse errors."""
        return sum(1 for r in self.records if r.was_parse_error)

    # ── Summary output ──

    def to_summary_dict(self) -> dict[str, Any]:
        """Generate a summary dict for logging or SSE emission."""
        turn_elapsed_ms = (time.monotonic() - self._turn_start) * 1000
        return {
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "tool_count": self.tool_count,
            "tools_used": self.tools_used,
            "total_tool_time_ms": round(self.total_tool_time_ms, 1),
            "turn_elapsed_ms": round(turn_elapsed_ms, 1),
            "tool_failure_count": self.tool_failure_count,
            "tool_failure_rate": round(self.tool_failure_rate, 3),
            "total_retries": self.total_retries,
            "max_round": self.max_round,
            "parse_error_count": self.parse_error_count,
            "records": [r.to_dict() for r in self.records],
        }

    def emit_summary(self) -> None:
        """Emit the turn summary to structured logging."""
        if not self.records:
            return
        summary = self.to_summary_dict()
        # Remove per-record details for the summary log line
        log_summary = {k: v for k, v in summary.items() if k != "records"}
        logger.info_structured(
            "Chat tool turn summary",
            extra_fields=log_summary,
        )
        # Log individual failures at warning level
        for rec in self.records:
            if not rec.success:
                logger.warning(
                    f"Tool execution failed: {rec.tool_name} round={rec.round_idx} "
                    f"error={rec.error_category or 'unknown'} retries={rec.retry_count}",
                )


class ToolTimer:
    """Context manager for timing tool execution."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ToolTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        self.elapsed_ms = (time.monotonic() - self._start) * 1000


def _truncate_for_summary(obj: Any, max_len: int = 200) -> str:
    """Create a truncated string summary of a tool input/output."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj[:max_len]
    if isinstance(obj, dict):
        # Compact representation
        try:
            import json
            s = json.dumps(obj, ensure_ascii=False, default=str)
            return s[:max_len]
        except (TypeError, ValueError):
            return str(obj)[:max_len]
    return str(obj)[:max_len]
