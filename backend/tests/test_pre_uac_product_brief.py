"""Tests for Pre-UAC product brief."""

from __future__ import annotations

from app.core.schemas_test_plan_pipeline import TicketBrief
from app.services.pre_uac_product_brief_service import (
    build_pre_uac_product_brief,
    clean_evidence_snippet_text,
    detect_product_topics,
    score_evidence_snippet,
)


def test_detect_baseline_topic_from_guidES_52248_summary():
    topics = detect_product_topics(
        "Add Version comment column in AEM Guides Baseline Table or custom property fields"
    )
    assert topics
    assert topics[0]["id"] == "baseline"


def test_score_prefers_baseline_ui_over_openapi_dto():
    baseline_topic = detect_product_topics("baseline table version comment")[0]
    ui_snippet = {
        "source": "experience_league",
        "title": "Work with baselines",
        "url": "https://experienceleague.adobe.com/work-with-baseline",
        "snippet": "Browse the baseline table, filter topics, and export CSV from the baseline dashboard.",
    }
    dto_snippet = {
        "source": "learned_behavior",
        "title": "BaselineRebuildRequestDto",
        "url": "https://adobeaemcloud.com/guides-baseline.yaml",
        "snippet": '{"type": "object", "required": ["baselineId", "title"], "properties": {}}',
    }
    assert score_evidence_snippet(ui_snippet, baseline_topic) > score_evidence_snippet(
        dto_snippet, baseline_topic
    )


def test_score_demotes_reports_api_for_baseline_topic():
    baseline_topic = detect_product_topics("baseline table version comment")[0]
    reports_snippet = {
        "source": "learned_behavior",
        "title": "Reports API DTO — MetadataExportRequestDto",
        "url": "https://adobeaemcloud.com/libs/fmdita/clientlibs/api-docs/index.html?urls.primaryName=Reports",
        "snippet": (
            'Reports API schema: MetadataExportRequestDto. {"type": "object", '
            '"properties": {"columns": {"type": "object"}}}'
        ),
    }
    baseline_ui = {
        "source": "experience_league",
        "title": "Work with Baseline",
        "url": "https://experienceleague.adobe.com/work-with-baseline",
        "snippet": "View contents of a Baseline and export CSV from the baseline table.",
    }
    assert score_evidence_snippet(reports_snippet, baseline_topic) < 5
    assert score_evidence_snippet(baseline_ui, baseline_topic) > score_evidence_snippet(
        reports_snippet, baseline_topic
    )


def test_clean_evidence_snippet_summarizes_openapi_json():
    cleaned = clean_evidence_snippet_text(
        {
            "title": "BaselineExportRequestDto",
            "url": "https://adobeaemcloud.com/guides-baseline.yaml",
            "snippet": '{"type": "object", "properties": {"baselineId": {"type": "string"}}}',
        }
    )
    assert "OpenAPI schema" in cleaned
    assert "BaselineExportRequestDto" in cleaned
    assert "{" not in cleaned


def test_clean_evidence_snippet_collapses_scrape_noise():
    cleaned = clean_evidence_snippet_text(
        {
            "title": "Work with Baseline",
            "url": "https://experienceleague.adobe.com/work-with-baseline",
            "snippet": "Create a Baseline\n\n\nView contents of a Baseline\nEdit, duplicate, or remove Baselines",
        }
    )
    assert "\n\n" not in cleaned
    assert "Create a Baseline" in cleaned


def test_baseline_brief_excludes_reports_api_from_documented_behavior(monkeypatch):
    brief = TicketBrief(
        jira_key="GUIDES-52248",
        summary="Add Version comment column in Baseline Table",
        component="Publishing",
        current_behavior="Baseline table shows fixed columns only.",
    )
    packet = {
        "issue": {"description": "baseline table version comment"},
        "mcp_fast_mode": True,
        "experience_league_evidence": [
            {
                "title": "Work with baselines",
                "snippet": "Create a baseline from the map dashboard and browse topics in the baseline table with filter and CSV export.",
                "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/generate-output/generate-output-use-baseline-for-publishing",
            },
            {
                "title": "BaselineRebuildRequestDto",
                "snippet": '{"type": "object", "required": ["baselineId"], "properties": {"title": {"type": "string"}}}',
                "source_url": "https://adobeaemcloud.com/guides-baseline.yaml",
            },
        ],
        "learned_behavior_evidence": {
            "available": True,
            "results": [
                {
                    "title": "Reports API DTO — MetadataExportRequestDto",
                    "snippet": (
                        'Reports API schema: MetadataExportRequestDto. {"type": "object", '
                        '"properties": {"columns": {"type": "object"}}}'
                    ),
                    "source_url": "https://adobeaemcloud.com/libs/fmdita/clientlibs/api-docs/index.html?urls.primaryName=Reports",
                }
            ],
        },
    }

    def _no_supplemental(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.pre_uac_product_brief_service._fetch_supplemental_topic_evidence",
        _no_supplemental,
    )

    pre = build_pre_uac_product_brief(packet, brief)
    documented_blob = " ".join(pre.documented_behavior).lower()
    assert "reports api" not in documented_blob
    assert "metadataexport" not in documented_blob
    assert "baseline table" in documented_blob


def test_pre_uac_brief_includes_curated_and_ranked_behavior(monkeypatch):
    brief = TicketBrief(
        jira_key="GUIDES-52248",
        summary="Add Version comment column in Baseline Table",
        component="Publishing",
        current_behavior="Baseline table shows fixed columns only.",
    )
    packet = {
        "issue": {"description": "baseline table version comment"},
        "mcp_fast_mode": True,
        "experience_league_evidence": [
            {
                "title": "Work with baselines",
                "snippet": "Create a baseline from the map dashboard and browse topics in the baseline table with filter and CSV export.",
                "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/generate-output/generate-output-use-baseline-for-publishing",
            },
        ],
        "learned_behavior_evidence": {"available": True, "results": []},
    }

    def _no_supplemental(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.pre_uac_product_brief_service._fetch_supplemental_topic_evidence",
        _no_supplemental,
    )

    pre = build_pre_uac_product_brief(packet, brief)
    assert pre.primary_product_area == "AEM Guides Baseline"
    assert pre.known_product_behavior
    assert any("Version comment" in kb for kb in pre.known_product_behavior)
    assert pre.documented_behavior
    assert "baseline table" in pre.documented_behavior[0].lower()
    assert pre.pre_uac_clarifications
    assert any("baseline v2" in q.lower() or "Version comment" in q for q in pre.pre_uac_clarifications)
