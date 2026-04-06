"""Tests for tool_observability — execution metrics collection."""
import pytest
from app.services.tool_observability import (
    ToolExecutionRecord,
    ToolObservabilityCollector,
    _truncate_for_summary,
)


class TestToolExecutionRecord:
    def test_to_dict_basic(self):
        rec = ToolExecutionRecord(
            tool_name="generate_dita",
            round_idx=0,
            latency_ms=150.5,
            success=True,
        )
        d = rec.to_dict()
        assert d["tool_name"] == "generate_dita"
        assert d["latency_ms"] == 150.5
        assert d["success"] is True
        assert "error_category" not in d  # Not included when empty

    def test_to_dict_with_error(self):
        rec = ToolExecutionRecord(
            tool_name="search_jira",
            round_idx=1,
            latency_ms=500.0,
            success=False,
            error_category="rate_limited",
            error_message="429 Too Many Requests",
            retry_count=2,
        )
        d = rec.to_dict()
        assert d["success"] is False
        assert d["error_category"] == "rate_limited"
        assert d["retry_count"] == 2

    def test_to_dict_parse_error(self):
        rec = ToolExecutionRecord(
            tool_name="create_job",
            round_idx=0,
            latency_ms=0,
            success=False,
            was_parse_error=True,
        )
        d = rec.to_dict()
        assert d["was_parse_error"] is True


class TestToolObservabilityCollector:
    def test_empty_collector(self):
        c = ToolObservabilityCollector(session_id="s1", trace_id="t1")
        assert c.tool_count == 0
        assert c.total_tool_time_ms == 0.0
        assert c.tool_failure_rate == 0.0
        assert c.tools_used == []

    def test_record_and_aggregate(self):
        c = ToolObservabilityCollector(session_id="s1")
        c.record_execution(tool_name="generate_dita", round_idx=0, latency_ms=100, success=True)
        c.record_execution(tool_name="create_job", round_idx=0, latency_ms=200, success=True)
        c.record_execution(tool_name="generate_dita", round_idx=1, latency_ms=150, success=False, error_category="timeout")

        assert c.tool_count == 3
        assert c.total_tool_time_ms == 450.0
        assert c.tools_used == ["generate_dita", "create_job"]
        assert c.tool_failure_count == 1
        assert abs(c.tool_failure_rate - 1 / 3) < 0.01
        assert c.max_round == 1

    def test_total_retries(self):
        c = ToolObservabilityCollector()
        c.record_execution(tool_name="t1", round_idx=0, latency_ms=100, success=True, retry_count=2)
        c.record_execution(tool_name="t2", round_idx=0, latency_ms=100, success=True, retry_count=1)
        assert c.total_retries == 3

    def test_parse_error_count(self):
        c = ToolObservabilityCollector()
        c.record_execution(tool_name="t1", round_idx=0, latency_ms=0, success=False, was_parse_error=True)
        c.record_execution(tool_name="t2", round_idx=0, latency_ms=100, success=True)
        assert c.parse_error_count == 1

    def test_to_summary_dict(self):
        c = ToolObservabilityCollector(session_id="s1", trace_id="t1")
        c.record_execution(tool_name="generate_dita", round_idx=0, latency_ms=100, success=True)
        summary = c.to_summary_dict()
        assert summary["session_id"] == "s1"
        assert summary["trace_id"] == "t1"
        assert summary["tool_count"] == 1
        assert len(summary["records"]) == 1
        assert "turn_elapsed_ms" in summary

    def test_emit_summary_no_error(self):
        c = ToolObservabilityCollector()
        c.record_execution(tool_name="t1", round_idx=0, latency_ms=100, success=True)
        # Should not raise
        c.emit_summary()

    def test_emit_summary_empty_does_nothing(self):
        c = ToolObservabilityCollector()
        c.emit_summary()  # Should not raise


class TestTruncateForSummary:
    def test_string_truncation(self):
        assert _truncate_for_summary("a" * 300, 200) == "a" * 200

    def test_dict_truncation(self):
        result = _truncate_for_summary({"key": "value"}, 200)
        assert "key" in result

    def test_none_returns_empty(self):
        assert _truncate_for_summary(None) == ""
