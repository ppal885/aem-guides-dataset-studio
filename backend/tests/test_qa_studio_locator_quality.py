"""Locator quality and governance for QA Studio."""

from __future__ import annotations

from app.services.qa_studio_locator_quality import (
    SOURCE_DOM_SNAPSHOT,
    SOURCE_PAGE_OBJECT,
    assess_locator_full,
    assess_xpath_or_selector,
    infer_stable_anchor,
)


def test_role_tablist_is_reuse():
    r = assess_xpath_or_selector("//div[@role='tablist']")
    assert r.quality == "reuse"
    assert r.score_0_100 >= 90
    assert not r.flags


def test_react_spectrum_id_flag():
    r = assess_xpath_or_selector("//*[@id='react-spectrum-123']")
    assert r.quality == "fragile"
    assert "react_spectrum_generated_id" in r.flags


def test_tabview_id_flag():
    r = assess_xpath_or_selector("//*[@id='tabView-jui-react-42']")
    assert r.quality == "fragile"
    assert "tabview_generated_id" in r.flags


def test_topic_id_flag():
    r = assess_xpath_or_selector("//*[@id='topic_id__abc-def']")
    assert r.quality == "fragile"
    assert "hardcoded_topic_id" in r.flags


def test_global_button_index_fragile():
    r = assess_xpath_or_selector("(//button)[2]")
    assert r.quality == "fragile"
    assert "global_indexed_node" in r.flags


def test_infer_stable_anchor_menu_label():
    assert infer_stable_anchor(
        "//*[contains(@class,'spectrum-Menu-itemLabel') and normalize-space()='Save']"
    )


def test_full_response_includes_suggestions():
    out = assess_locator_full("//div[@role='tablist']")
    assert out["quality"] == "reuse"
    assert isinstance(out["suggestions"], list)
    assert "governance" in out
    assert out["governance"]["policy_skipped"] is True


def test_policy_skipped_by_default():
    out = assess_locator_full("//*[@id='react-spectrum-1']")
    assert out["governance"]["policy_skipped"] is True
    assert out["governance"]["new_xpath_gate_passed"] is None


def test_po_tier_waives_gate():
    out = assess_locator_full(
        "//*[@id='react-spectrum-1']",
        source=SOURCE_PAGE_OBJECT,
        has_dom_evidence=False,
        approval_status="none",
    )
    assert out["governance"]["new_xpath_gate_passed"] is True
    assert not out["governance"]["gate_blockers"]


def test_new_xpath_gate_requires_evidence_anchor_approval():
    out = assess_locator_full(
        "//div[@role='tablist']//div[@role='tab']",
        source=SOURCE_DOM_SNAPSHOT,
        has_dom_evidence=True,
        stable_anchor_confirmed=True,
        approval_status="pending",
    )
    assert out["governance"]["new_xpath_gate_passed"] is False
    assert any("Approval" in b for b in out["governance"]["gate_blockers"])

    ok = assess_locator_full(
        "//div[@role='tablist']//div[@role='tab']",
        source=SOURCE_DOM_SNAPSHOT,
        has_dom_evidence=True,
        stable_anchor_confirmed=True,
        approval_status="approved",
    )
    assert ok["governance"]["new_xpath_gate_passed"] is True
