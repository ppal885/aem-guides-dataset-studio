"""End-to-end QA copilot orchestration agent."""

from __future__ import annotations

from typing import Any

from app.models.jira_models import AutomationFit, AutomationScenario, CommonPattern, JiraIssueSearchResult, UacPoint
from app.models.response_models import QaCopilotChatResponse
from app.observability.metrics import metrics
from app.observability.tracing import CopilotTrace
from app.services.response_grounding_service import ResponseGroundingService
from app.services.tool_executor import ToolExecutor
from app.agents.planner_agent import PlannerAgent


class QACopilotAgent:
    """Planner/executor/composer for the enterprise QA copilot."""

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        executor: ToolExecutor | None = None,
        grounding: ResponseGroundingService | None = None,
    ) -> None:
        self.planner = planner or PlannerAgent()
        self.executor = executor or ToolExecutor()
        self.grounding = grounding or ResponseGroundingService()

    async def run(self, message: str, *, limit: int = 10, include_debug: bool = False) -> QaCopilotChatResponse:
        trace = CopilotTrace()
        metrics.increment("qa_copilot_requests")
        trace.step("planner_start")
        plan = await self.planner.plan(message, limit=limit)
        trace.step("planner_done", planner_path=plan.planner_path, tool_count=len(plan.tool_calls))

        records = await self.executor.execute(plan.tool_calls)
        trace.step("tools_done", executed=len(records), failed=sum(1 for r in records if not r.success))

        issues = self._models_from_tool(records, "search_jira_issues", "issues", JiraIssueSearchResult)
        patterns = self._models_from_tool(records, "detect_common_patterns", "patterns", CommonPattern)
        scenarios = self._models_from_tool(records, "generate_automation_scenarios", "automation_scenarios", AutomationScenario)
        uac_points = self._models_from_tool(records, "generate_uac_points", "uac_points", UacPoint)
        automation_fit = self._automation_fit(records)
        search_output = self._tool_output(records, "search_jira_issues")
        semantic_fallback_used = bool(search_output.get("semantic_fallback_used")) if isinstance(search_output, dict) else False
        metadata_filter_used = bool(search_output.get("metadata_filter_used", True)) if isinstance(search_output, dict) else True

        final_response, grounding = self.grounding.compose(
            entities=plan.entities,
            issues=issues,
            patterns=patterns,
            scenarios=scenarios,
            uac_points=uac_points,
            automation_fit=automation_fit,
            semantic_fallback_used=semantic_fallback_used,
            metadata_filter_used=metadata_filter_used,
        )
        trace.step("grounded_response_done", grounded_issue_count=len(grounding.grounded_issue_keys))
        debug = {
            "planner": plan.model_dump(),
            "search_debug": search_output.get("debug") if isinstance(search_output, dict) else {},
        } if include_debug else None

        return QaCopilotChatResponse(
            query=message,
            entities=plan.entities,
            tool_calls=records,
            retrieved_issues=issues,
            patterns=patterns,
            automation_scenarios=scenarios,
            uac_points=uac_points,
            automation_fit=automation_fit,
            final_response=final_response,
            grounding=grounding,
            observability=trace.to_dict(),
            debug=debug,
        )

    def _tool_output(self, records: list[Any], name: str) -> Any:
        for record in records:
            if record.name == name and record.success:
                return record.output
        return {}

    def _models_from_tool(self, records: list[Any], tool: str, key: str, model_cls: type) -> list[Any]:
        output = self._tool_output(records, tool)
        if not isinstance(output, dict):
            return []
        rows = output.get(key) or []
        return [model_cls.model_validate(row) for row in rows if isinstance(row, dict)]

    def _automation_fit(self, records: list[Any]) -> AutomationFit | None:
        output = self._tool_output(records, "generate_automation_scenarios")
        if isinstance(output, dict) and isinstance(output.get("automation_fit"), dict):
            return AutomationFit.model_validate(output["automation_fit"])
        return None

