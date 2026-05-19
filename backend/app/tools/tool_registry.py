"""Dynamic tool registry for QA copilot tool calling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


ToolCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolCallable


class ToolRegistry:
    """Runtime registry that allows planner-selected tool names to resolve dynamically."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown QA copilot tool: {name}") from exc

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]


def build_default_tool_registry() -> ToolRegistry:
    from app.tools.automation_tools import generate_automation_scenarios, generate_uac_points
    from app.tools.jira_tools import detect_common_patterns, get_related_issue_details, search_jira_issues

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_jira_issues",
            description="Search indexed Jira issues using generic enterprise QA metadata, semantic, and customer-aware retrieval.",
            parameters={
                "customer": "str | None",
                "feature": "str | None",
                "issue_type": "str | None",
                "environment": "str | None",
                "editor_type": "str | None",
                "output_type": "str | None",
                "time_window_days": "int | None",
                "source_jira_key": "str | None",
                "escalation_only": "bool",
                "limit": "int",
            },
            handler=search_jira_issues,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_related_issue_details",
            description="Fetch detailed grounded chunks for selected Jira issues.",
            parameters={"issues": "list[JiraIssueSearchResult]"},
            handler=get_related_issue_details,
        )
    )
    registry.register(
        ToolDefinition(
            name="detect_common_patterns",
            description="Detect repeated historical patterns across retrieved Jira details.",
            parameters={"issue_details": "list[JiraIssueDetails]"},
            handler=detect_common_patterns,
        )
    )
    registry.register(
        ToolDefinition(
            name="generate_automation_scenarios",
            description="Generate grounded Behave automation scenarios from retrieved issue evidence.",
            parameters={
                "issue_details": "list[JiraIssueDetails]",
                "patterns": "list[CommonPattern]",
                "customer": "str | None",
                "feature": "str | None",
            },
            handler=generate_automation_scenarios,
        )
    )
    registry.register(
        ToolDefinition(
            name="generate_uac_points",
            description="Generate grounded QA/UAC discussion points from retrieved issue evidence.",
            parameters={
                "issue_details": "list[JiraIssueDetails]",
                "patterns": "list[CommonPattern]",
                "customer": "str | None",
                "feature": "str | None",
            },
            handler=generate_uac_points,
        )
    )
    return registry
