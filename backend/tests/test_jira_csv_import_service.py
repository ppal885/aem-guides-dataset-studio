from __future__ import annotations

import csv
import io
from datetime import datetime

import pytest
import numpy as np

from app.services.jira_chunking_service import build_comments_digest
from app.services.jira_csv_import_service import (
    _completed_file_hashes,
    parse_jira_csv_bytes,
    merge_parsed_issues,
    preview_jira_csv_files,
    should_skip_existing,
)
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_qa_chunking_service import build_jira_qa_chunks


BASE_HEADERS = [
    "Summary",
    "Issue key",
    "Issue Type",
    "Status",
    "Resolution",
    "Priority",
    "Description",
    "Updated",
]


def _csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def test_parse_repeated_headers_redacts_direct_identifiers_and_preserves_signals():
    headers = BASE_HEADERS + [
        "Labels",
        "Labels",
        "Component/s",
        "Comment",
        "Comment",
        "Attachment",
        "Custom field (Acceptance Criteria)",
        "Custom field (Root Cause)",
        "Custom field (Test Plan)",
        "Custom field (Customer Names)",
        "Outward issue link (Fixed By)",
    ]
    row = [
        "Publishing queue stalls",
        "GUIDES-50001",
        "Customer Request",
        "Closed",
        "Fixed",
        "Critical",
        "Contact owner@example.com in 6AAB041762B261FF0A495E40@AdobeOrg and [~owner].",
        "31/Jul/26 05:30 PM",
        "publishing",
        "regression",
        "AEM Guides",
        "31/Jul/26 05:31 PM;owner;Verified fix with [~reviewer].",
        "31/Jul/26 05:32 PM;owner;Token access_token=secret-value was revoked.",
        "31/Jul/26 05:33 PM;owner;error.log;https://jira.example/secure/attachment/1/error.log",
        "Publishing must finish and release the queue.",
        "Concurrent Oak writes collided.",
        "Run two large publishing jobs sequentially.",
        "Example Bank",
        "GUIDES-49999",
    ]
    parsed = parse_jira_csv_bytes(_csv_bytes(headers, [row]), "closed-cr.csv")

    assert len(parsed.issues) == 1
    assert parsed.duplicate_headers == {"Labels": 2, "Comment": 2}
    issue = parsed.issues[0]
    assert issue.resolution == "Fixed"
    assert issue.customer_names == ["Example Bank"]
    assert issue.attachment_filenames == ["error.log"]
    assert issue.linked_issue_refs == ["outward (Fixed By): GUIDES-49999"]
    privacy_blob = issue.issue["fields"]["description"] + build_comments_digest(issue.comments)
    assert "owner@example.com" not in privacy_blob
    assert "@AdobeOrg" not in privacy_blob
    assert "secret-value" not in privacy_blob
    assert "https://jira.example" not in " ".join(issue.attachment_filenames)


def test_high_signal_csv_chunks_are_generated():
    headers = BASE_HEADERS + [
        "Custom field (Acceptance Criteria)",
        "Custom field (Root Cause)",
        "Custom field (Test Plan)",
        "Attachment",
        "Inward issue link (Has a Test Case)",
    ]
    row = [
        "Translation API filters",
        "GUIDES-50002",
        "Customer Request",
        "Closed",
        "Complete",
        "Major",
        "Create a translation project through automation.",
        "2026-07-31T18:00:00+00:00",
        "Support latest version and baseline.",
        "Version selection ignored the baseline.",
        "Validate all project and filter combinations.",
        "31/Jul/26 06:00 PM;owner;translation.log;https://jira.example/attachment/translation.log",
        "GUIDES-50003",
    ]
    parsed_issue = parse_jira_csv_bytes(_csv_bytes(headers, [row]), "translation.csv").issues[0]
    enriched = enrich_jira(parsed_issue.issue).model_copy(
        update={
            "resolution": parsed_issue.resolution,
            "jira_updated_at": parsed_issue.jira_updated_at,
            "source_type": "jira_csv",
            "acceptance_criteria": parsed_issue.acceptance_criteria,
            "root_cause": parsed_issue.root_cause,
            "test_plan": parsed_issue.test_plan,
            "linked_issue_refs": parsed_issue.linked_issue_refs,
            "attachment_filenames": parsed_issue.attachment_filenames,
        }
    )
    chunks = build_jira_qa_chunks(parsed_issue.issue_key, parsed_issue.issue, enriched=enriched)
    chunk_types = {chunk["metadata"]["chunk_type"] for chunk in chunks}

    assert {
        "summary_chunk",
        "domain_entity_chunk",
        "acceptance_criteria_chunk",
        "resolution_rca_chunk",
        "test_evidence_chunk",
        "linked_issue_chunk",
        "attachment_signal_chunk",
    }.issubset(chunk_types)
    assert all(chunk["metadata"]["resolution"] == "Complete" for chunk in chunks)


def test_variable_schema_and_cross_file_duplicate_merge(monkeypatch):
    minimal = _csv_bytes(BASE_HEADERS, [["One", "GUIDES-1", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31"]])
    wider = _csv_bytes(
        BASE_HEADERS + ["Labels", "Labels", "Comment"],
        [["Two", "GUIDES-2", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31", "a", "b", ""]],
    )
    monkeypatch.setattr(
        "app.services.jira_csv_import_service._completed_file_hashes",
        lambda **_kwargs: set(),
    )
    preview = preview_jira_csv_files([("minimal.csv", minimal), ("wider.csv", wider)])
    assert preview["total_rows"] == 2
    assert preview["unique_issue_keys"] == 2
    assert [item["columns"] for item in preview["files"]] == [8, 11]

    duplicate = _csv_bytes(BASE_HEADERS, [["Again", "GUIDES-1", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31"]])
    duplicate_preview = preview_jira_csv_files([("minimal.csv", minimal), ("duplicate.csv", duplicate)])
    assert duplicate_preview["total_rows"] == 2
    assert duplicate_preview["unique_issue_keys"] == 1
    assert duplicate_preview["overlap_count"] == 1
    assert duplicate_preview["overlapping_issue_keys"] == ["GUIDES-1"]


def test_customer_detection_privacy_and_cross_cohort_association(monkeypatch):
    headers = BASE_HEADERS + [
        "Labels",
        "Custom field (Customer Names)",
        "Custom field (Company)",
        "Component/s",
    ]
    red_hat = _csv_bytes(
        headers,
        [["Same", "GUIDES-21", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "Redhat", "Red Hat", "12345", "Schematron"]],
    )
    ibm = _csv_bytes(
        headers,
        [["Same", "GUIDES-21", "Customer Request", "Closed", "Done", "Major", "Body", "2026-08-01", "IBM", "6AAB041762B261FF0A495E40@AdobeOrg", "IBM", "Publishing"]],
    )
    monkeypatch.setattr(
        "app.services.jira_csv_import_service._completed_file_hashes",
        lambda **_kwargs: set(),
    )
    preview = preview_jira_csv_files([("redhat.csv", red_hat), ("ibm.csv", ibm)])
    assert [(item["detected_customer"], item["customer_confidence"]) for item in preview["files"]] == [
        ("Red Hat", "high"),
        ("IBM", "high"),
    ]
    parsed = [parse_jira_csv_bytes(red_hat, "redhat.csv"), parse_jira_csv_bytes(ibm, "ibm.csv")]
    assignments = {parsed[0].file_hash: "Red Hat", parsed[1].file_hash: "IBM"}
    merged = merge_parsed_issues(parsed, assignments)
    assert len(merged) == 1
    assert merged[0].customer_cohorts == ["Red Hat", "IBM"]
    assert merged[0].resolutions == ["Fixed", "Done"]
    assert merged[0].evidence_archive["acceptance_criteria"] == []
    assert merged[0].company_names == ["IBM"]
    assert "@AdobeOrg" not in " ".join(merged[0].customer_names)
    assert {item["name"] for item in merged[0].issue["fields"]["components"]} == {"Schematron", "Publishing"}


def test_completed_hash_is_reprocessed_when_customer_assignment_changes(monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_csv_import_service._prior_file_customer_assignments",
        lambda **_kwargs: {"same-hash": {"Swift"}},
    )

    assert _completed_file_hashes() == {"same-hash"}
    assert _completed_file_hashes(customer_assignments={"same-hash": "Swift"}) == {"same-hash"}
    assert _completed_file_hashes(
        customer_assignments={"same-hash": "American Bureau of Shipping"}
    ) == set()


def test_row_level_customer_labels_are_preserved_with_file_cohort():
    headers = BASE_HEADERS + ["Labels", "Labels"]
    payload = _csv_bytes(
        headers,
        [
            ["Lexmark association", "GUIDES-31", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "SWIFT", "Lexmark"],
            ["Topcon association", "GUIDES-32", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "SWIFT", "Topcon"],
        ],
    )
    parsed = parse_jira_csv_bytes(payload, "swift.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "Swift"})

    assert parsed.detected_customer == "Swift"
    assert merged[0].customer_cohorts == ["Swift", "Lexmark"]
    assert merged[1].customer_cohorts == ["Swift", "Topcon"]


def test_fidelity_file_detection_and_assignment():
    headers = BASE_HEADERS + ["Labels", "Custom field (Customer Names)"]
    payload = _csv_bytes(
        headers,
        [["Fidelity issue", "GUIDES-33", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "Fidelity", "FIDELITY"]],
    )
    parsed = parse_jira_csv_bytes(payload, "fidelity.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "Fidelity"})

    assert parsed.detected_customer == "Fidelity"
    assert parsed.detection_confidence == "high"
    assert merged[0].customer_cohorts == ["Fidelity"]


@pytest.mark.parametrize(
    ("label", "customer_field", "canonical"),
    [
        ("Crown", "Crown Equipment", "Crown Equipment"),
        ("ABS", "AMERICAN BUREAU OF SHIPPING", "American Bureau of Shipping"),
    ],
)
def test_crown_and_abs_detection_and_assignment(label, customer_field, canonical):
    headers = BASE_HEADERS + ["Labels", "Custom field (Customer Names)"]
    payload = _csv_bytes(
        headers,
        [
            [
                f"{label} issue",
                "GUIDES-34",
                "Customer Request",
                "Closed",
                "Fixed",
                "Major",
                "Body",
                "2026-08-01",
                label,
                customer_field,
            ]
        ],
    )
    parsed = parse_jira_csv_bytes(payload, f"{label.lower()}.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: canonical})

    assert parsed.detected_customer == canonical
    assert parsed.detection_confidence == "high"
    assert merged[0].customer_cohorts == [canonical]


def test_mixed_jpmc_kone_file_uses_row_level_cohorts_without_global_assignment():
    headers = BASE_HEADERS + ["Labels", "Labels"]
    payload = _csv_bytes(
        headers,
        [
            ["JPMC issue", "GUIDES-34", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "JPMC", ""],
            ["KONE issue", "GUIDES-35", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "KONE", ""],
            ["Shared issue", "GUIDES-36", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "JPMC", "KONE"],
        ],
    )
    parsed = parse_jira_csv_bytes(payload, "mixed.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "Mixed (row-level cohorts)"})

    assert parsed.detected_customer == "Mixed (row-level cohorts)"
    assert parsed.detection_confidence == "high"
    assert [issue.customer_cohorts for issue in merged] == [["JPMC"], ["KONE"], ["JPMC", "KONE"]]


def test_mayo_primary_cohort_preserves_swift_cross_association():
    headers = BASE_HEADERS + ["Labels", "Labels"]
    payload = _csv_bytes(
        headers,
        [
            ["Mayo issue", "GUIDES-37", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "MayoClinic", ""],
            ["Shared issue", "GUIDES-38", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "MayoClinic", "SWIFT"],
        ],
    )
    parsed = parse_jira_csv_bytes(payload, "mayo.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "Mayo Clinic"})

    assert parsed.detected_customer == "Mayo Clinic"
    assert [issue.customer_cohorts for issue in merged] == [["Mayo Clinic"], ["Mayo Clinic", "Swift"]]


def test_pwc_file_detection():
    payload = _csv_bytes(
        BASE_HEADERS + ["Labels"],
        [["PwC issue", "GUIDES-39", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "PWC"]],
    )
    parsed = parse_jira_csv_bytes(payload, "pwc.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "PwC"})

    assert parsed.detected_customer == "PwC"
    assert parsed.detection_confidence == "high"
    assert merged[0].customer_cohorts == ["PwC"]


def test_linkedin_file_detection():
    payload = _csv_bytes(
        BASE_HEADERS + ["Labels"],
        [["LinkedIn issue", "GUIDES-40", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "LinkedIn"]],
    )
    parsed = parse_jira_csv_bytes(payload, "linkedin.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "LinkedIn"})

    assert parsed.detected_customer == "LinkedIn"
    assert parsed.detection_confidence == "high"
    assert merged[0].customer_cohorts == ["LinkedIn"]


def test_mixed_sonova_demant_file_detection():
    payload = _csv_bytes(
        BASE_HEADERS + ["Labels", "Labels"],
        [
            ["Sonova issue", "GUIDES-41", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "Sonova", ""],
            ["Demant issue", "GUIDES-42", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "Demant", ""],
            ["Shared issue", "GUIDES-43", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-02", "Sonova", "Demant"],
        ],
    )
    parsed = parse_jira_csv_bytes(payload, "sonova-demant.csv")
    merged = merge_parsed_issues([parsed], {parsed.file_hash: "Mixed (row-level cohorts)"})

    assert parsed.detected_customer == "Mixed (row-level cohorts)"
    assert [issue.customer_cohorts for issue in merged] == [["Sonova"], ["Demant"], ["Sonova", "Demant"]]


def test_newest_updated_timestamp_wins():
    existing = datetime(2026, 7, 31, 18, 0, 0)
    assert should_skip_existing(existing, "2026-07-31T17:59:59+00:00") is True
    assert should_skip_existing(existing, "2026-07-31T18:00:00+00:00") is False
    assert should_skip_existing(existing, "2026-08-01T00:00:00+00:00") is False


@pytest.mark.parametrize("column_count", [230, 340, 361])
def test_large_variable_export_schemas_with_repeated_positional_headers(column_count):
    repeated_count = column_count - len(BASE_HEADERS)
    headers = BASE_HEADERS + ["Labels"] * repeated_count
    row = ["Wide", f"GUIDES-{column_count}", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01"]
    row += ["IBM" if index == 0 else "" for index in range(repeated_count)]
    parsed = parse_jira_csv_bytes(_csv_bytes(headers, [row]), f"wide-{column_count}.csv")
    assert len(parsed.headers) == column_count
    assert parsed.duplicate_headers["Labels"] == repeated_count
    assert parsed.detected_customer == "IBM"


def test_malformed_row_width_is_rejected():
    payload = b"Summary,Issue key,Issue Type,Status,Resolution,Description,Updated\nOnly one value\n"
    with pytest.raises(ValueError, match="columns; expected"):
        parse_jira_csv_bytes(payload, "malformed.csv")


def test_admin_csv_preview_endpoint(client, auth_headers, monkeypatch):
    payload = _csv_bytes(BASE_HEADERS, [["One", "GUIDES-9", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31"]])
    monkeypatch.setattr(
        "app.services.jira_csv_import_service._completed_file_hashes",
        lambda **_kwargs: set(),
    )
    response = client.post(
        "/api/v1/admin/jira-rag/import-csv?dry_run=true",
        files=[("files", ("jira.csv", payload, "text/csv"))],
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["total_rows"] == 1


def test_admin_csv_preview_requires_admin(client, monkeypatch):
    payload = _csv_bytes(BASE_HEADERS, [["One", "GUIDES-10", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31"]])
    monkeypatch.setenv(
        "AUTH_TOKENS_JSON",
        '{"writer-token":{"id":"writer","roles":["writer"],"allowed_tenants":["*"]}}',
    )
    response = client.post(
        "/api/v1/admin/jira-rag/import-csv?dry_run=true",
        files=[("files", ("jira.csv", payload, "text/csv"))],
        headers={"Authorization": "Bearer writer-token"},
    )
    assert response.status_code == 403


def test_flush_batch_retries_chroma_and_persists_sql(monkeypatch):
    from app.services import jira_csv_import_service as service

    parsed = parse_jira_csv_bytes(
        _csv_bytes(BASE_HEADERS, [["One", "GUIDES-11", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-07-31"]]),
        "jira.csv",
    ).issues[0]
    enriched = enrich_jira(parsed.issue).model_copy(update={"resolution": "Fixed", "source_type": "jira_csv"})
    chunks = build_jira_qa_chunks(parsed.issue_key, parsed.issue, enriched=enriched)
    attempts = []

    class FakeSession:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    def flaky_add(*_args, **_kwargs):
        attempts.append(1)
        return len(attempts) > 1

    monkeypatch.setattr(service, "embed_texts_batched", lambda docs, batch_size: np.zeros((len(docs), 3)))
    monkeypatch.setattr(service, "add_documents", flaky_add)
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(service, "SessionLocal", FakeSession)
    monkeypatch.setattr(service, "upsert_jira_issue", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "insert_jira_chunks", lambda *_args, **_kwargs: len(chunks))

    chunk_count, issue_count, errors = service._flush_issue_batch([(parsed, enriched, chunks)])
    assert len(attempts) == 2
    assert chunk_count == len(chunks)
    assert issue_count == 1
    assert errors == []
