"""Tests for issue-level Jira QA corpus coverage auditing."""

from __future__ import annotations

from app.services.jira_corpus_audit_service import build_jira_corpus_audit


def _record(record_id: str, jira_key: str, document: str, **metadata):
    return {
        "id": record_id,
        "document": document,
        "metadata": {"jira_key": jira_key, **metadata},
    }


def test_audit_counts_unique_issues_not_chunks_and_reports_coverage():
    records = [
        _record(
            "G-1::summary::0",
            "G-1",
            "Shared normalized document",
            chunk_type="summary",
            customer="Acme",
            components='["Editor"]',
            component_primary="editor",
            enrich_domain="authoring",
            jira_updated_at="10/Jan/25 10:00 AM",
            import_source_type="jira_csv",
            source_file_hashes='["hash-a", "hash-b"]',
        ),
        _record(
            "G-1::problem::0",
            "G-1",
            "Acme editor problem detail",
            chunk_type="problem",
            customer="acme",
            components='["editor"]',
            component_primary="editor",
            enrich_domain="unknown",
            jira_updated_at="10/Jan/25 10:00 AM",
            import_source_type="jira_csv",
            source_file_hashes='["hash-a", "hash-b"]',
        ),
        _record(
            "G-2::summary::0",
            "G-2",
            "Shared   normalized\n document",
            chunk_type="summary",
            customer="Beta",
            components='["Publishing"]',
            component_primary="publishing",
            enrich_domain="unknown",
            jira_updated_at="2026-02-15T12:00:00+00:00",
            import_source_type="jira_api",
        ),
        {"id": "orphan", "document": "No Jira metadata", "metadata": {}},
    ]

    report = build_jira_corpus_audit(records, collection_count=4)

    assert report["scan_complete"] is True
    assert report["coverage_confidence"] == "complete"
    assert report["totals"]["scanned_chunk_count"] == 4
    assert report["totals"]["unique_issue_count"] == 2
    assert report["totals"]["represented_customer_count"] == 2
    assert report["totals"]["represented_component_count"] == 2
    assert report["canonical_component_taxonomy"] == [
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ]
    assert report["totals"]["expected_multi_chunk_issue_count"] == 1
    customers = {row["customer"]: row for row in report["customer_coverage"]}
    assert customers["Acme"]["issue_count"] == 1
    assert customers["Acme"]["chunk_count"] == 2
    assert customers["Beta"]["latest_updated_at"].startswith("2026-02-15")
    components = {row["component"]: row for row in report["component_coverage"]}
    assert components["Editor"]["issue_count"] == 1
    assert components["Publishing"]["customer_count"] == 1
    assert report["date_coverage"]["earliest_updated_at"].startswith("2025-01-10")
    assert report["date_coverage"]["latest_updated_at"].startswith("2026-02-15")
    assert report["quality_gaps"]["chunks_missing_jira_key"] == 1
    assert report["quality_gaps"]["issues_with_multiple_source_hashes"] == 1
    assert report["domain_coverage"]["ranking_policy"] == "soft_boost_only"
    assert report["domain_coverage"]["unknown_issue_count"] == 1
    assert report["domain_coverage"]["unknown_issue_percent"] == 50.0
    assert report["quality_gaps"]["issues_with_unknown_domain"] == 1
    assert report["duplicates"]["normalized_exact_duplicate_document_groups"] == 1
    assert report["duplicates"]["cross_issue_duplicate_document_groups"] == 1
    assert set(report["duplicates"]["sample_groups"][0]["jira_keys"]) == {"G-1", "G-2"}


def test_audit_reports_partial_scan_and_metadata_gaps_without_crashing():
    report = build_jira_corpus_audit(
        [
            _record(
                "G-3::summary::0",
                "G-3",
                "Only record",
                components="not-json",
                enrich_customers="not-json",
                jira_updated_at="not-a-date",
            )
        ],
        collection_count=2,
    )

    assert report["scan_complete"] is False
    assert report["coverage_confidence"] == "partial"
    assert report["quality_gaps"]["issues_missing_updated_at"] == 0
    assert report["quality_gaps"]["issues_missing_customer"] == 1
    assert report["quality_gaps"]["issues_missing_component"] == 1
    assert report["quality_gaps"]["issues_missing_component_primary"] == 1
    assert report["quality_gaps"]["issues_with_invalid_updated_at"] == 1
    assert report["quality_gaps"]["malformed_json_metadata_values"] == 2


def test_audit_flags_noncanonical_component_as_a_data_quality_gap():
    report = build_jira_corpus_audit(
        [
            _record(
                "G-4::summary::0",
                "G-4",
                "Legacy component",
                components='["Platform and Integration"]',
                component_primary="platform and integration",
            )
        ],
        collection_count=1,
    )

    assert report["quality_gaps"]["issues_missing_component"] == 1
    assert report["quality_gaps"]["issues_missing_component_primary"] == 1
    assert report["quality_gaps"]["issues_with_noncanonical_component"] == 1
    assert report["noncanonical_component_values"] == [
        {"component": "Platform and Integration", "issue_count": 1},
    ]


def test_live_audit_includes_incremental_cursor_health(monkeypatch):
    from app.services import jira_corpus_audit_service

    records = [
        _record(
            "DXML-1::summary::0",
            "DXML-1",
            "Publishing failure",
            jira_updated_at="2026-08-07T12:30:00Z",
        )
    ]
    monkeypatch.setattr(jira_corpus_audit_service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(jira_corpus_audit_service, "get_collection_count", lambda _name: 1)
    monkeypatch.setattr(
        jira_corpus_audit_service,
        "get_collection_records",
        lambda *args, **kwargs: records,
    )
    monkeypatch.setattr(
        "app.services.jira_sync_cursor_service.inspect_jira_sync_cursor",
        lambda **kwargs: {
            "valid": False,
            "repair_available": True,
            "repair_command": "bootstrap",
            "options": kwargs,
        },
    )

    report = jira_corpus_audit_service.audit_jira_corpus()

    assert report["incremental_sync_cursor"]["repair_available"] is True
    assert report["quality_gaps"]["invalid_incremental_sync_cursor"] is True
