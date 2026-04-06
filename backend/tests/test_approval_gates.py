"""Tests for approval_gates — extensible gate registry."""
import pytest
from app.services.approval_gates import (
    ApprovalGate,
    ApprovalGateRegistry,
    create_default_registry,
    get_default_registry,
)


class TestApprovalGateRegistry:
    def test_empty_registry(self):
        reg = ApprovalGateRegistry()
        assert reg.gate_count == 0
        assert reg.check_gates("any_tool", {}) == ""

    def test_register_and_check(self):
        reg = ApprovalGateRegistry()
        reg.register(ApprovalGate(
            name="test_gate",
            tool_name="my_tool",
            condition=lambda name, inp, cfg: "blocked" if inp.get("block") else "",
        ))
        assert reg.check_gates("my_tool", {"block": True}) == "blocked"
        assert reg.check_gates("my_tool", {"block": False}) == ""
        assert reg.check_gates("other_tool", {"block": True}) == ""

    def test_wildcard_gate(self):
        reg = ApprovalGateRegistry()
        reg.register(ApprovalGate(
            name="global_gate",
            tool_name="*",
            condition=lambda name, inp, cfg: "all blocked" if cfg.get("block_all") else "",
        ))
        assert reg.check_gates("any_tool", {}, {"block_all": True}) == "all blocked"
        assert reg.check_gates("other", {}, {}) == ""

    def test_priority_ordering(self):
        reg = ApprovalGateRegistry()
        reg.register(ApprovalGate(
            name="low_priority",
            tool_name="*",
            condition=lambda n, i, c: "low",
            priority=20,
        ))
        reg.register(ApprovalGate(
            name="high_priority",
            tool_name="*",
            condition=lambda n, i, c: "high",
            priority=10,
        ))
        # Should return the first matching (highest priority = lowest number)
        assert reg.check_gates("tool", {}) == "high"


class TestDefaultGates:
    def test_large_create_job_triggers(self):
        reg = create_default_registry()
        config = {"topic_threshold": 1000}
        result = reg.check_gates(
            "create_job",
            {"recipe_type": "task_topics", "config": {"topic_count": 5000}},
            config,
        )
        assert "5000" in result
        assert "threshold" in result.lower()

    def test_small_create_job_passes(self):
        reg = create_default_registry()
        config = {"topic_threshold": 1000}
        result = reg.check_gates(
            "create_job",
            {"recipe_type": "task_topics", "config": {"topic_count": 50}},
            config,
        )
        assert result == ""

    def test_large_recipe_default_triggers(self):
        reg = create_default_registry()
        config = {"topic_threshold": 1000}
        result = reg.check_gates(
            "create_job",
            {"recipe_type": "flat_hierarchical_dita"},
            config,
        )
        assert result != ""  # Should trigger because default is 5000

    def test_large_generate_dita_triggers(self):
        reg = create_default_registry()
        config = {"generate_char_threshold": 100}
        result = reg.check_gates(
            "generate_dita",
            {"text": "x" * 200},
            config,
        )
        assert "200" in result

    def test_small_generate_dita_passes(self):
        reg = create_default_registry()
        config = {"generate_char_threshold": 50000}
        result = reg.check_gates(
            "generate_dita",
            {"text": "short text"},
            config,
        )
        assert result == ""

    def test_multi_tool_triggers(self):
        reg = create_default_registry()
        config = {"max_parallel_tools": 2, "tool_count_in_round": 5}
        result = reg.check_gates("any_tool", {}, config)
        assert "5 tools" in result

    def test_multi_tool_within_limit(self):
        reg = create_default_registry()
        config = {"max_parallel_tools": 3, "tool_count_in_round": 2}
        result = reg.check_gates("any_tool", {}, config)
        assert result == ""

    def test_default_registry_singleton(self):
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_unrelated_tool_passes(self):
        reg = create_default_registry()
        result = reg.check_gates("lookup_dita_spec", {"query": "topicref"}, {})
        assert result == ""
