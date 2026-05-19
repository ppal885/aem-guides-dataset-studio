"""Assertion traceability: Jira sources, generic Then rejection, mapping heuristics."""

from __future__ import annotations

from app.services.qa_studio_assertion_traceability import (
    build_traceability_report,
    list_generic_then_violations,
    merge_user_and_jira_fields,
    ui_snapshot_supports_assertion,
    then_step_mentions_visual_snapshot_evidence,
)


def test_generic_then_verify_page():
    v = list_generic_then_violations("Then I verify the page works")
    assert v


def test_merge_populates_source_quote():
    f = merge_user_and_jira_fields(
        jira_summary="",
        jira_description="Expected: PDF downloads.\nAcceptance: File is valid.",
        jira_raw="",
        repro_steps="",
        expected_behavior="",
        acceptance_criteria="",
    )
    assert f.get("acceptance_criteria") or f.get("expected_fixed_behavior")
    assert f.get("source_quote")


def test_traceability_blocked_without_expected():
    fields = merge_user_and_jira_fields(
        jira_summary="Bug",
        jira_description="Actual: crash",
        jira_raw="",
        repro_steps="",
        expected_behavior="",
        acceptance_criteria="",
    )
    r = build_traceability_report(
        fields=fields,
        then_steps=["Then PDF downloads"],
    )
    assert r["blocked_no_observable_expected"]
    assert r["open_questions"]


def test_each_then_maps_to_source_when_expected_present():
    fields = merge_user_and_jira_fields(
        jira_summary="",
        jira_description="",
        jira_raw="",
        repro_steps="",
        expected_behavior="The PDF export completes and lists the map title on the cover page.",
        acceptance_criteria="",
    )
    r = build_traceability_report(
        fields=fields,
        then_steps=[
            "Then the PDF export completes and the map title appears on the cover page.",
        ],
    )
    assert not r["blocked_no_observable_expected"]
    assert r["then_step_results"]
    assert r["then_step_results"][0]["ok"]
    assert r["then_step_results"][0]["mapped_source"] in (
        "expected_fixed_behavior",
        "acceptance_criteria",
        "source_quote",
    )


def test_ui_snapshot_supports_assertion_rules():
    assert not ui_snapshot_supports_assertion({"disposition": "rejected"})
    assert not ui_snapshot_supports_assertion({"disposition": "used", "is_generic_screen": True})
    assert not ui_snapshot_supports_assertion({"disposition": "used", "is_bug_state_only": True})
    assert ui_snapshot_supports_assertion(
        {"disposition": "used", "expected_fixed_behavior": True}
    )
    assert ui_snapshot_supports_assertion(
        {"disposition": "used", "linked_acceptance_criteria": True}
    )
    assert ui_snapshot_supports_assertion(
        {"disposition": "used", "expected_behavior": "Toolbar shows Save."}
    )
    assert ui_snapshot_supports_assertion(
        {
            "disposition": "used",
            "confirms_post_action_ui_from_jira": True,
            "jira_reference": "GUIDES-100 AC2",
        }
    )


def test_visual_then_blocked_when_only_bug_mapping_and_no_labeled_snapshot():
    fields = merge_user_and_jira_fields(
        jira_summary="Crash",
        jira_description="Actual: NPE when opening map. Expected: editor loads.",
        jira_raw="",
        repro_steps="Open map",
        expected_behavior="",
        acceptance_criteria="",
    )
    assert fields.get("expected_fixed_behavior")
    r = build_traceability_report(
        fields=fields,
        then_steps=["Then the UI matches the screenshot of the editor."],
        ui_snapshots=None,
    )
    assert any("screenshot" in e.lower() or "snapshot" in e.lower() for e in r["errors"])


def test_visual_then_passes_with_labeled_snapshot():
    fields = merge_user_and_jira_fields(
        jira_summary="UI",
        jira_description="Regression in panel.",
        jira_raw="",
        repro_steps="",
        expected_behavior="",
        acceptance_criteria="Panel shows Saved state.",
    )
    snap = {"disposition": "used", "expected_behavior": "Panel shows Saved state after click."}
    r = build_traceability_report(
        fields=fields,
        then_steps=["Then the screenshot shows the panel in Saved state."],
        ui_snapshots=[snap],
    )
    assert r["ok"]
    assert r["then_step_results"][0]["ok"]


def test_visual_then_resolved_by_strong_ac_mapping():
    fields = merge_user_and_jira_fields(
        jira_summary="",
        jira_description="",
        jira_raw="",
        repro_steps="",
        expected_behavior="",
        acceptance_criteria="After publish, the PDF contains the glossary header on page one.",
    )
    r = build_traceability_report(
        fields=fields,
        then_steps=[
            "Then the published PDF matches the screenshot baseline for glossary header on page one.",
        ],
        ui_snapshots=None,
    )
    assert r["ok"]
    assert then_step_mentions_visual_snapshot_evidence(r["then_step_results"][0]["then_text"])
