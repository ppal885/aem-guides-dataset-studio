from __future__ import annotations

import csv
import hashlib
import io
import json

import pytest

from app.services.jira_csv_import_service import (
    MIXED_CUSTOMER_ASSIGNMENT,
    parse_jira_csv_bytes,
    preview_jira_csv_files,
)
from app.services.jira_historical_uac_import_service import (
    load_historical_uac_component_overrides,
    normalize_historical_uac_csv_bytes,
)
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_qa_chunking_service import build_jira_qa_chunks


HEADERS = [
    "Summary",
    "Issue key",
    "Issue Type",
    "Status",
    "Resolution",
    "Priority",
    "Description",
    "Updated",
    "Component/s",
    "Component/s",
]


def _csv_bytes(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_historical_uac_normalization_preserves_source_components_and_stays_strict(monkeypatch):
    source = _csv_bytes(
        [
            [
                "Native PDF history",
                "GUIDES-1",
                "Customer Request",
                "Closed",
                "Fixed",
                "Major",
                "Body",
                "2026-08-01",
                "Native_PDF",
                "Triaged",
            ],
            [
                "Missing source component",
                "GUIDES-2",
                "Customer Request",
                "Closed",
                "Fixed",
                "Major",
                "Body",
                "2026-08-01",
                "",
                "",
            ],
            [
                "Canonical plus generic marker",
                "GUIDES-5",
                "Customer Request",
                "Closed",
                "Fixed",
                "Major",
                "Body",
                "2026-08-01",
                "Authoring",
                "Miscellaneous",
            ],
        ]
    )
    normalized = normalize_historical_uac_csv_bytes(
        source,
        "historical.csv",
        component_overrides={"GUIDES-2": ["Editor"]},
    )

    assert normalized.report["valid"] is True
    assert normalized.report["assignment_method_counts"] == {
        "explicit_issue_override": 1,
        "legacy_alias": 1,
        "source_canonical": 1,
    }
    assert normalized.report["ignored_component_markers"] == {
        "Triaged": 1,
        "Miscellaneous": 1,
    }
    parsed = parse_jira_csv_bytes(normalized.data, "historical.csv")
    assert parsed.issues[0].raw_components == ["Publishing"]
    assert parsed.issues[0].source_components == ["Native_PDF", "Triaged"]
    assert parsed.issues[0].component_assignment_method == "legacy_alias"
    assert parsed.issues[0].issue["fields"]["components"] == [{"name": "Publishing"}]
    assert parsed.issues[0].issue["fields"]["_components_raw"] == [
        "Native_PDF",
        "Triaged",
    ]
    assert parsed.issues[1].raw_components == ["Editor"]
    assert parsed.issues[2].raw_components == ["Authoring"]
    assert parsed.rows_without_canonical_component == 0
    assert parsed.rows_with_noncanonical_component == 0
    enriched = enrich_jira(parsed.issues[0].issue)
    chunks = build_jira_qa_chunks(
        parsed.issues[0].issue_key,
        parsed.issues[0].issue,
        comments=[],
        linked_issues=[],
        enriched=enriched,
    )
    assert chunks
    assert json.loads(chunks[0]["metadata"]["components"]) == ["Publishing"]
    assert json.loads(chunks[0]["metadata"]["components_raw"]) == [
        "Native_PDF",
        "Triaged",
    ]
    assert chunks[0]["metadata"]["component_primary"] == "publishing"
    assert chunks[0]["metadata"]["component_assignment_method"] == "legacy_alias"

    monkeypatch.setattr(
        "app.services.jira_csv_import_service._completed_file_hashes",
        lambda: set(),
    )
    preview = preview_jira_csv_files(
        [("historical.csv", normalized.data)],
        customer_assignments={parsed.file_hash: MIXED_CUSTOMER_ASSIGNMENT},
    )
    assert preview["valid"] is True
    assert preview["files"][0]["assigned_customer"] == MIXED_CUSTOMER_ASSIGNMENT


def test_historical_uac_normalization_blocks_unresolved_components():
    source = _csv_bytes(
        [["Unknown", "GUIDES-3", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "Miscellaneous", ""]]
    )

    normalized = normalize_historical_uac_csv_bytes(source, "historical.csv")

    assert normalized.report["valid"] is False
    assert normalized.report["unresolved_issue_keys"] == ["GUIDES-3"]
    assert normalized.report["unresolved_component_values"] == {"Miscellaneous": 1}


def test_component_override_manifest_is_bound_to_the_exact_source_file(tmp_path):
    source = _csv_bytes(
        [["Unknown", "GUIDES-4", "Customer Request", "Closed", "Fixed", "Major", "Body", "2026-08-01", "", ""]]
    )
    source_hash = hashlib.sha256(source).hexdigest()
    manifest = tmp_path / "overrides.json"
    manifest.write_text(
        json.dumps(
            {
                "source_file_sha256": source_hash,
                "assignments": {"GUIDES-4": ["Platform"]},
            }
        ),
        encoding="utf-8",
    )

    assert load_historical_uac_component_overrides(
        manifest,
        source_file_hash=source_hash,
    ) == {"GUIDES-4": ["Platform"]}
    with pytest.raises(ValueError, match="does not match"):
        load_historical_uac_component_overrides(
            manifest,
            source_file_hash="0" * 64,
        )
