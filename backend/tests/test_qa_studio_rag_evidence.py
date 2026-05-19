"""Bundled RAG evidence assembly for QA Studio plans."""

from __future__ import annotations

from app.services.qa_studio_rag_evidence import build_rag_evidence_bundle


def test_bundle_has_all_groups():
    fields = {
        "source_quote": "PDF must open",
        "acceptance_criteria": "AC1: PDF opens",
        "expected_fixed_behavior": "",
    }
    plan = {
        "gherkin_outline": {"when": ["Click publish"]},
        "locator_decisions": [{"intent": "Tabs", "rationale": "Use tablist"}],
        "assertion_traceability": [{"then_step": "PDF visible"}],
    }
    rag = build_rag_evidence_bundle(
        blocked=False,
        plan_draft=plan,
        fields=fields,
        jira_summary="Publish PDF",
        target_area="repository",
        manual_notes="",
    )
    for key in (
        "playbook_matches",
        "ui_reference_matches",
        "ui_snapshot_matches",
        "dom_pattern_matches",
        "page_object_matches",
        "assertion_source_matches",
    ):
        assert key in rag
        assert isinstance(rag[key], list)
        assert rag[key], f"{key} should be non-empty for this fixture"


def test_evidence_item_shape():
    rag = build_rag_evidence_bundle(
        blocked=False,
        plan_draft={"assertion_traceability": [{"then_step": "X"}]},
        fields={"source_quote": "q"},
        jira_summary="",
        target_area="",
        manual_notes="",
    )
    item = rag["playbook_matches"][0]
    for k in (
        "id",
        "source_collection",
        "title",
        "relevance",
        "disposition",
        "reason",
        "linked_plan_ref",
    ):
        assert k in item
    assert item["linked_plan_ref"]["kind"]


def test_blocked_assertion_rejected():
    rag = build_rag_evidence_bundle(
        blocked=True,
        plan_draft=None,
        fields={},
        jira_summary="",
        target_area="",
        manual_notes="",
    )
    asrc = rag["assertion_source_matches"]
    assert asrc
    assert asrc[0]["disposition"] == "rejected"
