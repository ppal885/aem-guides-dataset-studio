"""Tests for deterministic UAC cross-output parity analysis."""

from __future__ import annotations

from services.uac import uac_output_parity as parity_mod
from services.uac.uac_output_parity import build_output_parity
from services.uac_generation_service import UACGenerationEngine, _build_context, _normalize_similar_jiras


def _enriched(**kwargs: object) -> dict:
    base = {
        "jira_key": "GUIDES-100",
        "summary": "Keyref resolution issue",
        "description": "Description body",
        "domain": "keyref",
        "dita_entities": ["keyref"],
        "affected_outputs": ["editor_preview", "native_pdf"],
    }
    base.update(kwargs)
    return base


def test_build_output_parity_multi_output_keyref():
    ctx = _build_context(_enriched(), [], {})
    out = build_output_parity(ctx, similar_rows=[])
    assert out["parity_required"] is True
    pairs = {(p["source"], p["target"]) for p in out["parity_pairs"]}
    assert ("preview", "native_pdf") in pairs
    assert out["validation_points"]


def test_build_output_parity_single_surface_no_contrast():
    ctx = _build_context(
        {
            "jira_key": "GUIDES-PDF",
            "summary": "Adjust PDF template leading",
            "description": "Spacing change only.",
            "domain": "native_pdf",
            "dita_entities": ["topicref"],
            "affected_outputs": ["native_pdf"],
        },
        [],
        {},
    )
    out = build_output_parity(ctx, similar_rows=[])
    assert out["parity_required"] is False
    assert out["parity_pairs"] == []
    assert out["validation_points"] == []


def test_build_output_parity_contrast_text_boosts_surfaces():
    ctx = _build_context(
        {
            "jira_key": "GUIDES-101",
            "summary": "Works in preview but fails in Native PDF for keyref",
            "description": "",
            "domain": "keyref",
            "dita_entities": ["keyref"],
            "affected_outputs": [],
        },
        [],
        {},
    )
    out = build_output_parity(ctx, similar_rows=[])
    assert out["parity_required"] is True
    pairs = {(p["source"], p["target"]) for p in out["parity_pairs"]}
    assert ("preview", "native_pdf") in pairs


def test_build_output_parity_baseline_includes_baseline_export_pairs():
    ctx = _build_context(
        _enriched(
            domain="baseline",
            summary="Baseline export mismatch",
            dita_entities=["baseline"],
            affected_outputs=["native_pdf"],
        ),
        [],
        {},
    )
    out = build_output_parity(ctx, similar_rows=[])
    assert out["parity_required"] is True
    tgt_sources = {(p["source"], p["target"]) for p in out["parity_pairs"]}
    assert any("baseline_export" in t for t in tgt_sources)


def test_generation_insufficient_clears_parity():
    out = UACGenerationEngine().generate(
        enriched_jira={"jira_key": "X", "summary": "vague", "domain": "unknown"},
        similar_jiras=[],
    )
    assert out["output_parity"]["parity_required"] is False
    assert out["output_parity"]["parity_pairs"] == []


def test_generation_attaches_parity_when_grounded():
    out = UACGenerationEngine().generate(
        enriched_jira=_enriched(),
        similar_jiras=[],
    )
    assert "output_parity" in out
    assert out["output_parity"]["parity_required"] is True


def test_similar_row_matching_outputs_expand_parity():
    ctx = _build_context(
        _enriched(affected_outputs=["editor_preview"]),
        [
            {
                "jira_key": "GUIDES-OLD",
                "matching_entities": ["keyref"],
                "matching_outputs": ["sites"],
                "final_score": 0.9,
                "title": "Sites keyref issue",
                "metadata": {},
            }
        ],
        {},
    )
    accepted, _ = _normalize_similar_jiras(ctx)
    assert accepted, "expected similar/jira overlap"
    out = build_output_parity(ctx, similar_rows=accepted)
    applicable = parity_mod._collect_applicable(ctx, accepted)
    assert "aem_sites" in applicable
