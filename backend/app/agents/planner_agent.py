"""Planner agent for enterprise QA copilot tool selection."""

from __future__ import annotations

import re
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.models.tool_models import ExtractedEntities, PlannedToolCall, PlannerResult
from app.prompts.planner_prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE
from app.services.llm_service import generate_json, is_llm_available
from app.services.metadata_service import MetadataService
from app.tools.tool_registry import ToolRegistry, build_default_tool_registry

logger = get_structured_logger(__name__)


class PlannerAgent:
    """Extract entities and create a retrieval-first tool plan."""

    def __init__(
        self,
        metadata_service: MetadataService | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.metadata_service = metadata_service or MetadataService()
        self.registry = registry or build_default_tool_registry()

    async def plan(self, message: str, *, limit: int = 10) -> PlannerResult:
        rule_entities = self.metadata_service.extract_entities(message)
        if is_llm_available():
            try:
                llm_plan = await self._llm_plan(message, rule_entities, limit=limit)
                if llm_plan.tool_calls:
                    return llm_plan
            except Exception as exc:
                logger.warning_structured(
                    "qa_copilot_llm_planner_fallback",
                    extra_fields={"error": str(exc)},
                )
        return self._rule_plan(rule_entities, limit=limit)

    async def _llm_plan(self, message: str, rule_entities: ExtractedEntities, *, limit: int) -> PlannerResult:
        payload = await generate_json(
            PLANNER_SYSTEM_PROMPT,
            PLANNER_USER_TEMPLATE.format(message=message),
            max_tokens=1600,
            step_name="qa_copilot_planner",
        )
        raw_entities = payload.get("entities") if isinstance(payload, dict) else {}
        entities = self._merge_entities(message, rule_entities, raw_entities)
        raw_calls = payload.get("tool_calls") if isinstance(payload, dict) else []
        calls = []
        for idx, raw in enumerate(raw_calls or [], start=1):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if name not in {tool["name"] for tool in self.registry.list_tools()}:
                continue
            calls.append(
                PlannedToolCall(
                    sequence=int(raw.get("sequence") or idx),
                    name=name,
                    arguments=dict(raw.get("arguments") or {}),
                    reason=str(raw.get("reason") or "LLM selected this tool."),
                    depends_on=[str(x) for x in raw.get("depends_on") or []],
                )
            )
        if not calls:
            return self._rule_plan(entities, limit=limit)
        if calls[0].name == "search_jira_issues":
            calls[0].arguments = {
                **calls[0].arguments,
                "customer": entities.customer,
                "feature": entities.feature,
                "issue_type": entities.issue_type,
                "environment": entities.environment,
                "editor_type": entities.editor_type,
                "output_type": entities.output_type,
                "time_window_days": entities.time_window_days,
                "source_jira_key": entities.source_jira_key,
                "escalation_only": entities.escalation_only,
                "limit": limit,
            }
        return PlannerResult(
            entities=entities,
            tool_calls=calls,
            fallback_strategy=[
                "If customer metadata is missing, retry feature-level semantic retrieval and mark semantic fallback.",
                "If no grounded issues return, suppress Jira-key-specific scenarios and state no grounded matches.",
            ],
            planner_path="llm",
        )

    def _merge_entities(
        self,
        message: str,
        rule_entities: ExtractedEntities,
        raw_entities: Any,
    ) -> ExtractedEntities:
        merged = rule_entities.model_dump()
        if not isinstance(raw_entities, dict):
            return rule_entities

        for key, value in raw_entities.items():
            if self._is_empty_entity_value(value):
                continue
            if key == "customer" and not self._value_is_grounded_in_query(value, message):
                logger.warning_structured(
                    "qa_copilot_rejected_ungrounded_planner_customer",
                    extra_fields={"llm_customer": value, "rule_customer": rule_entities.customer},
                )
                continue
            if key == "source_jira_key" and not self._value_is_grounded_in_query(value, message):
                logger.warning_structured(
                    "qa_copilot_rejected_ungrounded_source_jira_key",
                    extra_fields={"llm_source_jira_key": value, "rule_source_jira_key": rule_entities.source_jira_key},
                )
                continue
            if key == "escalation_only" and rule_entities.escalation_only and value is False:
                continue
            if key == "confidence":
                try:
                    if float(value) < rule_entities.confidence:
                        continue
                except (TypeError, ValueError):
                    continue
            merged[key] = value
        return ExtractedEntities.model_validate(merged)

    @staticmethod
    def _is_empty_entity_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    @staticmethod
    def _value_is_grounded_in_query(value: Any, message: str) -> bool:
        candidate = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
        query = re.sub(r"[^a-z0-9]+", " ", message.lower()).strip()
        if not candidate:
            return False
        if candidate in query:
            return True
        tokens = [token for token in candidate.split() if len(token) >= 3]
        return bool(tokens) and all(token in query.split() for token in tokens)

    def _rule_plan(self, entities: ExtractedEntities, *, limit: int) -> PlannerResult:
        calls = [
            PlannedToolCall(
                sequence=1,
                name="search_jira_issues",
                arguments={
                    "customer": entities.customer,
                    "feature": entities.feature,
                    "issue_type": entities.issue_type,
                    "environment": entities.environment,
                    "editor_type": entities.editor_type,
                    "output_type": entities.output_type,
                    "time_window_days": entities.time_window_days,
                    "source_jira_key": entities.source_jira_key,
                    "escalation_only": entities.escalation_only,
                    "limit": limit,
                },
                reason="Retrieve grounded historical Jira issues before analysis.",
            ),
            PlannedToolCall(
                sequence=2,
                name="get_related_issue_details",
                arguments={"issues": "$search_jira_issues.issues"},
                depends_on=["search_jira_issues"],
                reason="Fetch detailed evidence chunks for selected issues.",
            ),
            PlannedToolCall(
                sequence=3,
                name="detect_common_patterns",
                arguments={"issue_details": "$get_related_issue_details.issue_details"},
                depends_on=["get_related_issue_details"],
                reason="Identify repeated historical failure and regression patterns.",
            ),
            PlannedToolCall(
                sequence=4,
                name="generate_automation_scenarios",
                arguments={
                    "issue_details": "$get_related_issue_details.issue_details",
                    "patterns": "$detect_common_patterns.patterns",
                    "customer": entities.customer,
                    "feature": entities.feature,
                },
                depends_on=["get_related_issue_details", "detect_common_patterns"],
                reason="Generate grounded Behave scenarios only after Jira evidence is available.",
            ),
            PlannedToolCall(
                sequence=5,
                name="generate_uac_points",
                arguments={
                    "issue_details": "$get_related_issue_details.issue_details",
                    "patterns": "$detect_common_patterns.patterns",
                    "customer": entities.customer,
                    "feature": entities.feature,
                },
                depends_on=["get_related_issue_details", "detect_common_patterns"],
                reason="Produce QA/UAC discussion points tied to retrieved evidence.",
            ),
        ]
        return PlannerResult(
            entities=entities,
            tool_calls=calls,
            fallback_strategy=[
                "Strict metadata filter first: customer, feature, issue_type, environment.",
                "Semantic fallback: if strict metadata returns zero candidates but semantic feature matches exist, mark fallback.",
                "Grounding guardrail: if no issues are retrieved, do not invent Jira keys, customers, environments, or fixes.",
            ],
            planner_path="rules",
        )
