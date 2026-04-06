"""Extensible approval gate registry for chat tool execution.

Extends the existing _check_approval_gate() with a registry pattern that
supports multiple gate conditions for different tools.

Feature flag: CHAT_EXTENDED_APPROVAL_GATES (default False)
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ApprovalGate:
    """A single approval gate definition."""

    name: str
    tool_name: str  # Which tool this gate applies to, or "*" for all
    condition: Callable[[str, dict, dict], str]
    """
    condition(tool_name, tool_input, config) -> reason_string_or_empty
    Returns non-empty string (the reason) if approval is needed, empty string if not.
    """
    description: str = ""
    priority: int = 0  # Lower = checked first


class ApprovalGateRegistry:
    """Registry of approval gates checked before tool execution."""

    def __init__(self) -> None:
        self._gates: list[ApprovalGate] = []

    def register(self, gate: ApprovalGate) -> None:
        """Register a new approval gate."""
        self._gates.append(gate)
        self._gates.sort(key=lambda g: g.priority)

    def check_gates(
        self,
        tool_name: str,
        tool_input: dict,
        config: Optional[dict] = None,
    ) -> str:
        """Check all applicable gates for a tool call.

        Returns the first non-empty reason string, or empty string if all pass.
        """
        cfg = config or {}
        for gate in self._gates:
            if gate.tool_name != "*" and gate.tool_name != tool_name:
                continue
            reason = gate.condition(tool_name, tool_input, cfg)
            if reason:
                return reason
        return ""

    @property
    def gate_count(self) -> int:
        return len(self._gates)

    @property
    def gate_names(self) -> list[str]:
        return [g.name for g in self._gates]


# ── Built-in gate conditions ──


def _gate_large_create_job(tool_name: str, tool_input: dict, config: dict) -> str:
    """Block create_job with very large topic counts."""
    threshold = config.get("topic_threshold", 1000)
    cfg = tool_input.get("config") or {}

    # Direct topic_count in config
    topic_count = cfg.get("topic_count", 0)
    if isinstance(topic_count, (int, float)) and topic_count >= threshold:
        return (
            f"This will create a dataset with {int(topic_count)} topics "
            f"(threshold: {threshold}). Type 'yes' or 'confirm' to proceed."
        )

    # Check recipe types known to have large defaults
    recipe_type = tool_input.get("recipe_type", "")
    _LARGE_RECIPES = {
        "flat_hierarchical_dita": 5000,
        "large_scale": 2000,
        "deep_hierarchy": 1500,
        "wide_branching": 1500,
        "bulk_dita_map_topics": 5000,
        "large_root_map_1000_topics_100kb": 1000,
    }
    if recipe_type in _LARGE_RECIPES and topic_count == 0:
        default = _LARGE_RECIPES[recipe_type]
        if default >= threshold:
            return (
                f"Recipe '{recipe_type}' defaults to ~{default} topics "
                f"(threshold: {threshold}). Type 'yes' or 'confirm' to proceed."
            )

    return ""


def _gate_large_generate_dita(tool_name: str, tool_input: dict, config: dict) -> str:
    """Block generate_dita with very large text inputs."""
    threshold = config.get("generate_char_threshold", 50_000)
    text = tool_input.get("text", "")
    if isinstance(text, str) and len(text) >= threshold:
        return (
            f"The input text is {len(text):,} characters (threshold: {threshold:,}). "
            f"This will be an expensive LLM call. Type 'yes' or 'confirm' to proceed."
        )
    return ""


def _gate_multi_tool_round(tool_name: str, tool_input: dict, config: dict) -> str:
    """Block when too many tools requested in a single round.

    Note: This gate checks the tool_count_in_round config key which must be
    set by the caller (chat_service) before checking gates.
    """
    max_parallel = config.get("max_parallel_tools", 3)
    count_in_round = config.get("tool_count_in_round", 1)
    if count_in_round > max_parallel:
        return (
            f"The AI wants to call {count_in_round} tools simultaneously "
            f"(max: {max_parallel}). Type 'yes' or 'confirm' to proceed."
        )
    return ""


# ── Default registry with built-in gates ──


def create_default_registry() -> ApprovalGateRegistry:
    """Create a registry with all built-in gates."""
    registry = ApprovalGateRegistry()

    registry.register(ApprovalGate(
        name="large_create_job",
        tool_name="create_job",
        condition=_gate_large_create_job,
        description="Block dataset creation with very large topic counts",
        priority=10,
    ))

    registry.register(ApprovalGate(
        name="large_generate_dita",
        tool_name="generate_dita",
        condition=_gate_large_generate_dita,
        description="Block DITA generation with very large text inputs",
        priority=20,
    ))

    registry.register(ApprovalGate(
        name="multi_tool_round",
        tool_name="*",
        condition=_gate_multi_tool_round,
        description="Block when too many tools in a single round",
        priority=30,
    ))

    return registry


# Module-level default registry
_default_registry: Optional[ApprovalGateRegistry] = None


def get_default_registry() -> ApprovalGateRegistry:
    """Get or create the default gate registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry
