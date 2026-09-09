"""Tests for draft test plan content enrichment."""

from __future__ import annotations

from app.core.schemas_test_plan_pipeline import PreUacProductBrief, TicketBrief
from app.services.draft_test_plan_content_service import (
    build_ac_lines,
    build_blast_rows,
    build_eb_lines,
    build_historical_rows,
    build_regression_bullets,
    build_risk_rows,
    build_scenario_rows,
    build_step_lines,
)
from app.services.ticket_workflow_profile_service import classify_ticket_workflow


def test_baseline_feature_gets_concrete_scenarios_not_generic_repro():
    brief = TicketBrief(
        jira_key="GUIDES-52248",
        summary="Add Version comment column in Baseline Table",
        issue_type="Customer Request",
        current_behavior="Baseline table shows fixed columns only.",
    )
    pre_uac = PreUacProductBrief(
        primary_product_area="AEM Guides Baseline",
        topic_ids=["baseline"],
    )
    workflow = classify_ticket_workflow({"issue": {}}, brief)
    generic_areas = [
        {"id": "TA-REPRODUCTION", "category": "Reproduction", "priority": "P0", "rationale": "generic"},
        {"id": "TA-CONTROL", "category": "R0 control", "priority": "P0", "rationale": "generic"},
    ]
    scenarios = build_scenario_rows(generic_areas, workflow, pre_uac, brief)
    titles = " ".join(s.title for s in scenarios).lower()
    assert "version comment" in titles
    assert "csv export" in titles
    assert "reproduction" not in titles


def test_vague_uac_ac_replaced_for_feature_baseline():
    brief = TicketBrief(
        jira_key="GUIDES-52248",
        summary="Baseline column",
        current_behavior="fixed columns",
    )
    pre_uac = PreUacProductBrief(topic_ids=["baseline"])
    workflow = classify_ticket_workflow({"issue": {"description": "Feature Enhancement"}}, brief)
    scenarios = build_scenario_rows([], workflow, pre_uac, brief)
    bad_ac = [
        "Given baseline content in scope, when the fix is applied on unspecified_output, then behavior agreed in ticket after clarification.",
    ]
    ac_lines = build_ac_lines(bad_ac, brief, workflow, scenarios)
    blob = " ".join(ac_lines).lower()
    assert "unspecified_output" not in blob
    assert "version comment" in blob or "pm" in blob


def test_baseline_feature_supplementary_tables_are_topic_specific():
    from app.services.draft_test_plan_content_service import (
        build_blast_rows,
        build_hypothesis_rows,
        build_risk_rows,
        build_scenario_rows,
    )

    brief = TicketBrief(
        jira_key="GUIDES-52248",
        summary="Add Version comment column in Baseline Table",
        issue_type="Customer Request",
    )
    pre_uac = PreUacProductBrief(topic_ids=["baseline"])
    workflow = classify_ticket_workflow({"issue": {}}, brief)
    scenarios = build_scenario_rows([], workflow, pre_uac, brief)
    blast = build_blast_rows([], scenarios, workflow, pre_uac, brief)
    risks = build_risk_rows([], scenarios, workflow, pre_uac)
    hypos = build_hypothesis_rows([], scenarios, workflow, pre_uac)
    blob = " ".join(blast + risks + hypos).lower()
    assert "version comment" in blob or "csv export" in blob
    assert "rr-r0-control" not in blob
    assert "unspecified_output" not in blob


def test_baseline_feature_has_multiple_p0_steps():
    brief = TicketBrief(jira_key="GUIDES-52248", summary="Baseline column")
    pre_uac = PreUacProductBrief(topic_ids=["baseline"])
    workflow = classify_ticket_workflow({"issue": {"description": "Feature Request"}}, brief)
    scenarios = build_scenario_rows([], workflow, pre_uac, brief)
    steps = build_step_lines(scenarios, brief)
    assert len(steps) >= 3
    assert any("S-01" in s for s in steps)
    assert any("S-02" in s for s in steps)


def _translation_moved_brief() -> tuple[TicketBrief, PreUacProductBrief]:
    brief = TicketBrief(
        jira_key="GUIDES-49386",
        summary="Translation is not working for content created in en and later moved to en_us",
        component="Translation",
        issue_type="Bug",
        current_behavior=(
            "Translation is not working for content moved using Assets move. "
            "Existing production maps were moved around language codes."
        ),
        expected_behavior="Translation should work for moved content.",
    )
    pre_uac = PreUacProductBrief(
        primary_product_area="AEM Guides Translation",
        topic_ids=["translation"],
        ticket_specific_context=(
            "Customer has maps created in en, moved to en_us using Assets move, "
            "and may see LANGUAGE_UUID_PATH_MISMATCH / disableCode behavior."
        ),
    )
    return brief, pre_uac


def test_translation_moved_content_gets_concrete_scenarios_not_generic_fallback():
    brief, pre_uac = _translation_moved_brief()
    workflow = classify_ticket_workflow({"issue": {}}, brief)
    generic_areas = [
        {"id": "TA-REPRODUCTION", "category": "Reproduction", "priority": "P0", "rationale": "generic"},
        {"id": "TA-CONTROL", "category": "R0 control", "priority": "P0", "rationale": "generic"},
        {"id": "TA-NEGATIVE", "category": "Negative/error handling", "priority": "P1", "rationale": "generic"},
    ]

    scenarios = build_scenario_rows(generic_areas, workflow, pre_uac, brief)
    titles = " ".join(scenario.title for scenario in scenarios).lower()

    assert "`en` content moved to `en_us`" in titles
    assert "assets-move metadata" in titles
    assert "normal language-root translation" in titles
    assert "negative / edge inputs" not in titles
    assert "r0 control — unchanged valid path" not in titles


def test_translation_moved_content_sections_are_ticket_specific():
    brief, pre_uac = _translation_moved_brief()
    workflow = classify_ticket_workflow({"issue": {}}, brief)
    scenarios = build_scenario_rows([], workflow, pre_uac, brief)

    steps = build_step_lines(scenarios, brief)
    ac_lines = build_ac_lines([], brief, workflow, scenarios)
    eb_lines = build_eb_lines(brief, {}, workflow, pre_uac)
    blast_rows = build_blast_rows([], scenarios, workflow, pre_uac, brief)
    risk_rows = build_risk_rows([], scenarios, workflow, pre_uac, brief)
    historical_rows = build_historical_rows([], "GUIDES-49386", brief, pre_uac)
    regression_bullets = build_regression_bullets(workflow, pre_uac, brief)
    blob = " ".join(
        steps + ac_lines + eb_lines + blast_rows + risk_rows + historical_rows + regression_bullets
    )

    assert "Assets move" in blob
    assert "AEM Guides 2605+" in blob
    assert "LANGUAGE_UUID_PATH_MISMATCH" in blob
    assert "`en_us`" in blob
    assert "disableCode" in blob
    assert "manual per-topic recreation" in blob
    assert "Translation + Assets move + `en_us` + `disableCode`" in blob
    assert "Schematron/text-node/context" not in blob
    assert "RR-CONSTRUCT-MATRIX" not in blob
