"""Tests for Bug vs Feature Request workflow classification."""

from __future__ import annotations

from app.core.schemas_test_plan_pipeline import TicketBrief
from app.services.ticket_workflow_profile_service import (
    classify_ticket_workflow,
    category_display_label,
)


def _bug_brief() -> TicketBrief:
    return TicketBrief(
        jira_key="GUIDES-49065",
        summary="Asset Status API fails for comma paths",
        issue_type="Bug",
        current_behavior="Job FAILED with Not an absolute path: comma/...",
        expected_behavior="Poll returns SUCCESS with full path intact.",
    )


def _feature_brief() -> TicketBrief:
    return TicketBrief(
        jira_key="GUIDES-52248",
        summary="Add Version comment column in Baseline Table",
        issue_type="Customer Request",
        current_behavior="Baseline table shows fixed columns only. Requested Enhancement.",
    )


def test_classify_bug_from_issue_type_and_fields():
    packet = {"issue": {"description": "Steps to reproduce: POST comma path"}}
    profile = classify_ticket_workflow(packet, _bug_brief())
    assert profile.ticket_category == "bug"
    assert profile.confidence in {"high", "medium"}
    assert profile.default_scenarios[0].title == "Primary repro"
    assert category_display_label(profile.ticket_category) == "Bug"


def test_classify_feature_request_from_customer_request():
    packet = {
        "issue": {
            "description": "*Request Type* Feature Enhancement\n*Requested Enhancement* Add column",
        }
    }
    profile = classify_ticket_workflow(packet, _feature_brief())
    assert profile.ticket_category == "feature_request"
    assert profile.default_scenarios[0].title == "New capability — happy path"
    assert profile.score_penalty == 10
    assert profile.human_review_reasons


def test_uac_classification_can_reinforce_feature_request():
    packet = {"issue": {"description": "Feature Request for baseline column"}}
    brief = _feature_brief()
    uac = {"classification": {"issue_type": "Customer Request"}}
    profile = classify_ticket_workflow(packet, brief, uac)
    assert profile.ticket_category == "feature_request"


def test_customer_request_with_no_longer_works_is_regression():
    brief = TicketBrief(
        jira_key="GUIDES-14500",
        summary='Schematron rules with context="//text()" do not work anymore',
        issue_type="Customer Request",
        component="Schematron",
        current_behavior='Schematron validation no longer evaluates rules with context="//text()".',
        expected_behavior='Schematron validation should evaluate text-node context rules such as context="//text()".',
    )
    packet = {
        "issue": {
            "description": """
While context="//text()" had worked earlier, they do not work in 2023.11 anymore.

Does not work:
<sch:rule context="//text()"/>

Works:
<sch:rule context="//p"/>
"""
        }
    }
    profile = classify_ticket_workflow(packet, brief)
    assert profile.ticket_category == "bug"
    assert "text=regression-overrides-request-type" in profile.detection_signals
