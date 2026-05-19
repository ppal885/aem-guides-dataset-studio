"""Planner tool executor with observable tool-call records."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from app.core.structured_logging import get_structured_logger
from app.models.tool_models import PlannedToolCall, ToolExecutionRecord
from app.tools.tool_registry import ToolRegistry, build_default_tool_registry

logger = get_structured_logger(__name__)


def _to_plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    if isinstance(value, tuple):
        return [_to_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    return value


class ToolExecutor:
    """Executes planner-selected tools and resolves simple output placeholders."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or build_default_tool_registry()

    async def execute(self, calls: list[PlannedToolCall]) -> list[ToolExecutionRecord]:
        records: list[ToolExecutionRecord] = []
        by_name: dict[str, ToolExecutionRecord] = {}
        for call in sorted(calls, key=lambda c: c.sequence):
            start = time.perf_counter()
            args = self._resolve_args(call.arguments, by_name)
            logger.info_structured(
                "qa_copilot_tool_selected",
                extra_fields={
                    "tool": call.name,
                    "arguments": args,
                    "sequence": call.sequence,
                    "reason": call.reason,
                },
            )
            try:
                definition = self.registry.get(call.name)
                output = await definition.handler(**args)
                latency = round((time.perf_counter() - start) * 1000, 2)
                record = ToolExecutionRecord(
                    name=call.name,
                    arguments=args,
                    success=True,
                    latency_ms=latency,
                    output=_to_plain(output),
                    metadata=self._record_metadata(output),
                )
                logger.info_structured(
                    "qa_copilot_tool_completed",
                    extra_fields={
                        "tool": call.name,
                        "latency_ms": latency,
                        **record.metadata,
                    },
                )
            except Exception as exc:
                latency = round((time.perf_counter() - start) * 1000, 2)
                record = ToolExecutionRecord(
                    name=call.name,
                    arguments=args,
                    success=False,
                    latency_ms=latency,
                    error=str(exc),
                    output=None,
                )
                logger.error_structured(
                    "qa_copilot_tool_failed",
                    extra_fields={"tool": call.name, "latency_ms": latency, "error": str(exc)},
                    exc_info=True,
                )
            records.append(record)
            by_name[record.name] = record
        return records

    def _resolve_args(self, value: Any, records: dict[str, ToolExecutionRecord]) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            return self._resolve_placeholder(value[1:], records)
        if isinstance(value, dict):
            return {k: self._resolve_args(v, records) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_args(v, records) for v in value]
        return value

    def _resolve_placeholder(self, placeholder: str, records: dict[str, ToolExecutionRecord]) -> Any:
        tool_name, _, path = placeholder.partition(".")
        record = records.get(tool_name)
        if record is None:
            return None
        current: Any = record.output
        if not path or path == "output":
            return current
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part == "issue_keys":
                current = [str(x.get("issue_key") or "") for x in current if isinstance(x, dict)]
            else:
                return None
        return current

    def _record_metadata(self, output: Any) -> dict[str, Any]:
        data = _to_plain(output)
        if isinstance(data, dict):
            return {
                "retrieval_count": len(data.get("issues") or data.get("issue_details") or []),
                "semantic_fallback_used": bool(data.get("semantic_fallback_used")),
                "metadata_filter_used": bool(data.get("metadata_filter_used", True)),
            }
        return {}

