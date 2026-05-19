"""Tests for enterprise Tool Calling + RAG QA Copilot."""

from __future__ import annotations

import asyncio
import json

from app.agents.planner_agent import PlannerAgent
from app.models.jira_models import AutomationFit, JiraIssueDetails
from app.models.tool_models import PlannedToolCall
from app.prompts.planner_prompts import PLANNER_SYSTEM_PROMPT
from app.rag.hybrid_search import HybridJiraSearch
from app.rag.metadata_filtering import JiraMetadataCriteria, matches_metadata
from app.services.metadata_service import MetadataService
from app.services.response_grounding_service import ResponseGroundingService
from app.services.retrieval_service import QaCopilotRetrievalService
from app.services.tool_executor import ToolExecutor
from app.tools.automation_tools import generate_automation_scenarios
from app.tools.tool_registry import ToolDefinition, ToolRegistry


def test_dynamic_customer_and_domain_extraction_examples() -> None:
    svc = MetadataService()
    examples = {
        "Cisco ke conref related bugs batao": ("Cisco", "conref", "Bug"),
        "Topcon ke ditaval issues batao": ("Topcon", "ditaval", "Bug"),
        "Swift ke publishing regressions batao": ("Swift", "publishing", "Bug"),
        "ABS ke keyref related tickets batao": ("ABS", "keyref", None),
        "Hyundai ke baseline bugs batao": ("Hyundai", "baseline", "Bug"),
        "Apex Future ke image handling tickets batao": ("Apex Future", "image handling", None),
        "customer Northwind Labs ke native pdf issues batao": ("Northwind Labs", "native pdf", "Bug"),
    }
    for query, expected in examples.items():
        entities = svc.extract_entities(query)
        assert (entities.customer, entities.feature, entities.issue_type) == expected


def test_planner_prompt_has_no_sample_customer_default() -> None:
    assert "Cisco" not in PLANNER_SYSTEM_PROMPT
    assert "sample value" in PLANNER_SYSTEM_PROMPT


def test_customer_is_not_defaulted_when_query_has_no_customer() -> None:
    entities = MetadataService().extract_entities("conref related old bugs aur automation scenarios batao")
    assert entities.customer is None
    assert entities.feature == "conref"


def test_hinglish_extraction_supports_environment_and_future_feature() -> None:
    entities = MetadataService().extract_entities(
        "Hyundai ke map dashboard bugs Cloud environment me batao"
    )
    assert entities.customer == "Hyundai"
    assert entities.feature == "map dashboard"
    assert entities.issue_type == "Bug"
    assert entities.environment == "Cloud"


def test_hinglish_extraction_handles_on_prem_environment() -> None:
    entities = MetadataService().extract_entities(
        "ABS ke keyref related bugs on-prem environment me batao"
    )
    assert entities.customer == "ABS"
    assert entities.feature == "keyref"
    assert entities.issue_type == "Bug"
    assert entities.environment == "On-Prem"


def test_hinglish_extraction_ignores_leading_request_words() -> None:
    entities = MetadataService().extract_entities(
        "Can you show Topcon ke ditaval debugging notes in AEMaaCS"
    )
    assert entities.customer == "Topcon"
    assert entities.feature == "ditaval"
    assert entities.issue_type is None
    assert entities.environment == "Cloud"


def test_dynamic_query_patterns_from_qa_copilot_examples() -> None:
    svc = MetadataService()

    topcon = svc.extract_entities("Topcon ke ditaval related issues batao")
    assert topcon.customer == "Topcon"
    assert topcon.feature == "ditaval"
    assert topcon.issue_type == "Bug"

    swift = svc.extract_entities("Swift ke publishing regressions last 90 days ke dikhao")
    assert swift.customer == "Swift"
    assert swift.feature == "publishing"
    assert swift.issue_type == "Bug"
    assert swift.output_type == "Publishing"
    assert swift.time_window_days == 90

    abs_query = svc.extract_entities("ABS customer ke keyref bugs se automation scenarios banao")
    assert abs_query.customer == "ABS"
    assert abs_query.feature == "keyref"
    assert abs_query.issue_type == "Bug"
    assert "automation_generation" in abs_query.request_type

    editor = svc.extract_entities("New editor mein image paste related similar bugs find karo")
    assert editor.customer is None
    assert editor.feature == "image handling"
    assert editor.editor_type == "New Editor"
    assert editor.issue_type == "Bug"
    assert "similar_issue_search" in editor.request_type

    uuid = svc.extract_entities("UUID publishing ke old regressions and UAC points batao")
    assert uuid.customer is None
    assert uuid.feature == "uuid"
    assert uuid.output_type == "Publishing"
    assert uuid.issue_type == "Bug"
    assert "uac_generation" in uuid.request_type

    related = svc.extract_entities("Is Jira ke related previous customer escalations find karo")
    assert related.customer is None
    assert related.feature is None
    assert related.escalation_only is True
    assert "customer_escalation_search" in related.request_type
    assert "similar_issue_search" in related.request_type
    assert "query_references_current_jira_without_explicit_key" in related.notes


def test_jira_key_relative_escalation_query_does_not_become_customer() -> None:
    entities = MetadataService().extract_entities(
        "GUIDES-1234 ke related previous customer escalations find karo"
    )
    assert entities.source_jira_key == "GUIDES-1234"
    assert entities.customer is None
    assert entities.escalation_only is True


def test_planner_selects_enterprise_tool_sequence(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner_agent.is_llm_available", lambda: False)
    plan = asyncio.run(
        PlannerAgent().plan(
            "Cisco ke conref related old bugs aur automation scenarios batao",
            limit=7,
        )
    )
    assert [call.name for call in plan.tool_calls] == [
        "search_jira_issues",
        "get_related_issue_details",
        "detect_common_patterns",
        "generate_automation_scenarios",
        "generate_uac_points",
    ]
    assert plan.tool_calls[0].arguments["customer"] == "Cisco"
    assert plan.tool_calls[0].arguments["feature"] == "conref"
    assert plan.tool_calls[0].arguments["limit"] == 7


def test_planner_llm_merge_preserves_dynamic_rule_entities(monkeypatch) -> None:
    async def fake_generate_json(*args, **kwargs):
        return {
            "entities": {
                "customer": "Cisco",
                "feature": "",
                "environment": "Cloud",
                "confidence": 0.1,
            },
            "tool_calls": [
                {
                    "sequence": 1,
                    "name": "search_jira_issues",
                    "arguments": {},
                    "reason": "search first",
                }
            ],
        }

    monkeypatch.setattr("app.agents.planner_agent.is_llm_available", lambda: True)
    monkeypatch.setattr("app.agents.planner_agent.generate_json", fake_generate_json)
    plan = asyncio.run(
        PlannerAgent().plan(
            "Topcon ke ditaval related bugs Cloud environment me batao",
            limit=4,
        )
    )
    assert plan.entities.customer == "Topcon"
    assert plan.entities.feature == "ditaval"
    assert plan.entities.environment == "Cloud"
    assert plan.entities.confidence > 0.1
    assert plan.tool_calls[0].arguments["customer"] == "Topcon"
    assert plan.tool_calls[0].arguments["feature"] == "ditaval"


def test_planner_passes_generalized_query_intent_to_search_tool(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner_agent.is_llm_available", lambda: False)
    plan = asyncio.run(
        PlannerAgent().plan(
            "GUIDES-1234 ke related previous customer escalations find karo",
            limit=6,
        )
    )
    args = plan.tool_calls[0].arguments
    assert args["source_jira_key"] == "GUIDES-1234"
    assert args["escalation_only"] is True
    assert args["customer"] is None
    assert args["limit"] == 6


def test_metadata_filter_matches_customer_labels_and_feature() -> None:
    criteria = JiraMetadataCriteria(customer="Topcon", feature="ditaval", issue_type="Bug", environment="Cloud")
    meta = {
        "jira_key": "GUIDES-10",
        "customer_labels": json.dumps(["Topcon"]),
        "labels": json.dumps(["customer-topcon", "ditaval"]),
        "enrich_entities": json.dumps(["DITAVAL"]),
        "issue_type": "Bug",
        "environment": "Cloud",
    }
    assert matches_metadata(criteria, meta, "DITAVAL filtering fails in Cloud publish")


def test_metadata_filter_matches_future_customer_label_without_code_change() -> None:
    criteria = JiraMetadataCriteria(customer="Northwind Labs", feature="native pdf", issue_type="Bug")
    meta = {
        "jira_key": "GUIDES-11",
        "customer_labels": json.dumps(["customer-northwind-labs"]),
        "labels": json.dumps(["native-pdf", "future-customer"]),
        "enrich_outputs": json.dumps(["Native PDF"]),
        "issue_type": "Bug",
    }
    assert matches_metadata(criteria, meta, "Northwind Labs Native PDF publish output fails")


def test_hybrid_search_marks_semantic_fallback_when_customer_metadata_missing(monkeypatch) -> None:
    candidate = {
        "jira_key": "GUIDES-22",
        "title": "DITAVAL filtering fails in publishing",
        "score": 0.72,
        "document": "DITAVAL filtering fails during publishing.",
        "metadata": {
            "jira_key": "GUIDES-22",
            "title": "DITAVAL filtering fails in publishing",
            "labels": json.dumps(["ditaval"]),
            "enrich_entities": json.dumps(["ditaval"]),
            "issue_type": "Bug",
        },
    }
    monkeypatch.setattr("app.rag.semantic_search.semantic_search_jira_qa", lambda *args, **kwargs: [candidate])
    result = HybridJiraSearch().search(
        JiraMetadataCriteria(customer="Topcon", feature="ditaval", issue_type="Bug"),
        limit=5,
    )
    assert result.semantic_fallback_used is True
    assert result.hits[0]["jira_key"] == "GUIDES-22"


def test_retrieval_service_maps_grounded_issue_without_faking_customer(monkeypatch) -> None:
    candidate = {
        "jira_key": "GUIDES-101",
        "title": "Cisco conref breaks after topic move",
        "score": 0.81,
        "document": "Root cause: stale conref target after topic move.",
        "metadata": {
            "jira_key": "GUIDES-101",
            "title": "Cisco conref breaks after topic move",
            "customer_labels": json.dumps(["Cisco"]),
            "labels": json.dumps(["conref", "customer-cisco"]),
            "enrich_entities": json.dumps(["conref"]),
            "issue_type": "Bug",
            "environment": "Cloud",
        },
        "why_similar": "Same customer and conref metadata.",
    }
    monkeypatch.setattr("app.rag.semantic_search.semantic_search_jira_qa", lambda *args, **kwargs: [candidate])
    issues, output = QaCopilotRetrievalService().search_jira_issues(
        customer="Cisco",
        feature="conref",
        issue_type="Bug",
        environment="Cloud",
        limit=3,
    )
    assert output.semantic_fallback_used is False
    assert issues[0].issue_key == "GUIDES-101"
    assert issues[0].customer == "Cisco"
    assert issues[0].root_cause_summary == "stale conref target after topic move."


def test_tool_executor_resolves_previous_tool_outputs() -> None:
    registry = ToolRegistry()
    seen: dict[str, object] = {}

    async def first_tool() -> dict:
        return {"issues": [{"issue_key": "GUIDES-1"}]}

    async def second_tool(issues: list[dict]) -> dict:
        seen["issues"] = issues
        return {"issue_details": [{"issue_key": "GUIDES-1"}]}

    registry.register(ToolDefinition("first", "first", {}, first_tool))
    registry.register(ToolDefinition("second", "second", {}, second_tool))
    records = asyncio.run(
        ToolExecutor(registry).execute(
            [
                PlannedToolCall(sequence=1, name="first"),
                PlannedToolCall(sequence=2, name="second", arguments={"issues": "$first.issues"}),
            ]
        )
    )
    assert all(record.success for record in records)
    assert seen["issues"] == [{"issue_key": "GUIDES-1"}]


def test_automation_generation_uses_grounded_issue_keys() -> None:
    detail = JiraIssueDetails(
        issue_key="GUIDES-501",
        summary="Conref preview mismatch",
        description="Steps to reproduce: open Web Editor. Expected conref resolves. Actual broken reference.",
        regression_patterns=["conref resolution failures"],
        affected_areas=["Web Editor", "Publishing"],
    )
    result = asyncio.run(
        generate_automation_scenarios(
            issue_details=[detail.model_dump()],
            patterns=[
                {
                    "pattern": "conref resolution failures",
                    "frequency": 1,
                    "probable_root_causes": ["Not stated in retrieved evidence."],
                    "regression_risk": "Medium",
                    "impacted_modules": ["Web Editor"],
                    "supporting_issues": ["GUIDES-501"],
                }
            ],
            customer="Cisco",
            feature="conref",
        )
    )
    scenarios = result["automation_scenarios"]
    fit = AutomationFit.model_validate(result["automation_fit"])
    assert scenarios
    assert all("GUIDES-501" in scenario["grounded_in"] for scenario in scenarios)
    scenario_blob = "\n".join(scenario["scenario_text"] for scenario in scenarios)
    assert "customer-relevant" not in scenario_blob
    assert "evidence-relevant" in scenario_blob
    assert fit.score_0_10 > 0


def test_empty_response_guardrail_has_no_fake_jira_keys() -> None:
    final, grounding = ResponseGroundingService().compose(
        entities=MetadataService().extract_entities("Cisco ke conref bugs batao"),
        issues=[],
        patterns=[],
        scenarios=[],
        uac_points=[],
        automation_fit=None,
        semantic_fallback_used=False,
        metadata_filter_used=True,
    )
    assert "No matching grounded historical issues found." in final
    assert "GUIDES-" not in final
    assert grounding.hallucination_prevention_triggered is True


def test_api_v1_chat_empty_grounded_response(client, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner_agent.is_llm_available", lambda: False)
    monkeypatch.setattr("app.rag.semantic_search.semantic_search_jira_qa", lambda *args, **kwargs: [])
    response = client.post(
        "/api/v1/chat",
        json={"message": "Cisco ke conref related old bugs aur automation scenarios batao"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entities"]["customer"] == "Cisco"
    assert payload["retrieved_issues"] == []
    assert payload["grounding"]["hallucination_prevention_triggered"] is True
    assert "No matching grounded historical issues found." in payload["final_response"]
