"""Tests for authority-aware documentation knowledge-gap auditing."""

from __future__ import annotations

from app.services.knowledge_corpus_audit_service import (
    build_knowledge_corpus_audit,
    build_knowledge_metadata_updates,
)
from app.services import knowledge_corpus_audit_service
from app.services.vector_store_service import CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC


def _record(record_id: str, document: str, source_url: str = "", **metadata):
    return {
        "id": record_id,
        "document": document,
        "metadata": {"source_url": source_url, **metadata},
    }


def test_audit_distinguishes_primary_weak_and_missing_topic_evidence():
    aem_records = [
        _record(
            "aem-image-map-1",
            "Dynamic Media image maps provide clickable hotspots and support asset upload workflows.",
            "https://experienceleague.adobe.com/en/docs/experience-manager-65/content/assets/using/image-maps",
            title="Image maps",
            source_type="experience_league",
        ),
        _record(
            "community-review-1",
            "Review workflows let reviewers inspect content.",
            "https://experienceleaguecommunities.adobe.com/review-example",
            title="Review example",
            source_type="community",
        ),
        _record("orphan", "", ""),
    ]
    dita_records = [
        _record(
            "dita13-dir",
            "The @dir attribute defines bidirectional text behavior.",
            "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/archSpec/base/diratt.html",
            title="@dir",
            construct="@dir",
            spec_version="DITA 1.3",
            curated=True,
        ),
        _record(
            "dita12-keys",
            "DITA 1.2 keyref and keydef processing behavior.",
            "https://docs.oasis-open.org/dita/v1.2/os/spec/archSpec/keys.html",
            title="Keys",
        ),
        _record(
            "secondary-sort-as",
            "The sort-as element controls an effective sorting phrase.",
            "https://www.oxygenxml.com/dita/1.3/specs/langRef/base/sort-as.html",
            title="sort-as",
        ),
    ]

    report = build_knowledge_corpus_audit(
        {CHROMA_COLLECTION_AEM_GUIDES: aem_records, CHROMA_COLLECTION_DITA_SPEC: dita_records},
        collection_counts={CHROMA_COLLECTION_AEM_GUIDES: 3, CHROMA_COLLECTION_DITA_SPEC: 3},
    )

    aem = report["collections"][CHROMA_COLLECTION_AEM_GUIDES]
    aem_probes = {row["code"]: row for row in aem["probe_coverage"]}
    assert aem_probes["image-maps"]["status"] == "covered"
    assert aem_probes["dynamic-media"]["status"] == "covered"
    assert aem_probes["review"]["status"] == "weak"
    assert aem["metadata_gaps"]["chunks_missing_source_url"] == 1
    assert aem["metadata_gaps"]["empty_document_chunks"] == 1

    dita = report["collections"][CHROMA_COLLECTION_DITA_SPEC]
    dita_probes = {row["code"]: row for row in dita["probe_coverage"]}
    assert dita_probes["dir"]["status"] == "covered"
    assert dita_probes["keys"]["status"] == "covered"
    assert dita_probes["sort-as"]["status"] == "weak"
    assert dita["missing_required_versions"] == []
    assert {row["version"] for row in dita["version_distribution"]} >= {"DITA 1.2", "DITA 1.3"}
    assert report["summary"]["knowledge_gap_count"] == len(report["knowledge_gaps"])


def test_audit_reports_partial_scan_duplicates_and_missing_dita_version():
    duplicate_text = "Same normalized evidence text"
    report = build_knowledge_corpus_audit(
        {
            CHROMA_COLLECTION_AEM_GUIDES: [
                _record(
                    "one",
                    duplicate_text,
                    "https://experienceleague.adobe.com/en/docs/example-one",
                    title="One",
                ),
                _record(
                    "two",
                    "same   normalized evidence TEXT",
                    "https://experienceleague.adobe.com/en/docs/example-two",
                    title="Two",
                ),
            ],
            CHROMA_COLLECTION_DITA_SPEC: [
                _record(
                    "dita13",
                    "DITA 1.3 specialization defines derived vocabulary.",
                    "https://dita-lang.org/1.3/dita/archSpec/base/specialization.html",
                    title="Specialization",
                )
            ],
        },
        collection_counts={CHROMA_COLLECTION_AEM_GUIDES: 3, CHROMA_COLLECTION_DITA_SPEC: 1},
    )

    aem = report["collections"][CHROMA_COLLECTION_AEM_GUIDES]
    assert aem["scan_complete"] is False
    assert aem["duplicates"]["normalized_exact_duplicate_document_groups"] == 1
    assert report["summary"]["critical_gap_count"] == 1
    dita = report["collections"][CHROMA_COLLECTION_DITA_SPEC]
    assert dita["missing_required_versions"] == ["DITA 1.2"]
    assert any(gap["code"] == "missing-dita-1-2" for gap in report["knowledge_gaps"])


def test_metadata_migration_updates_are_scalar_conservative_and_idempotent():
    metadata = {
        "source_url": "https://experienceleague.adobe.com/en/docs/example/missing-title",
        "source_type": "custom_authoritative",
    }

    updates = build_knowledge_metadata_updates(CHROMA_COLLECTION_AEM_GUIDES, metadata)

    assert updates == {
        "knowledge_collection": CHROMA_COLLECTION_AEM_GUIDES,
        "source_host": "experienceleague.adobe.com",
        "authority_role": "primary",
        "title": "Missing Title",
    }
    migrated = {**metadata, **updates}
    assert build_knowledge_metadata_updates(CHROMA_COLLECTION_AEM_GUIDES, migrated) == {}


def test_metadata_migration_dry_run_never_writes(monkeypatch):
    records = {
        CHROMA_COLLECTION_AEM_GUIDES: [
            _record("aem-1", "Document", "https://experienceleague.adobe.com/en/docs/example")
        ],
        CHROMA_COLLECTION_DITA_SPEC: [
            _record("dita-1", "Document", "https://docs.oasis-open.org/dita/example")
        ],
    }
    monkeypatch.setattr(knowledge_corpus_audit_service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(knowledge_corpus_audit_service, "get_collection_count", lambda collection: 1)
    monkeypatch.setattr(
        knowledge_corpus_audit_service,
        "get_collection_records",
        lambda collection: records[collection],
    )
    monkeypatch.setattr(
        "app.services.vector_store_service.update_document_metadatas",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry run wrote metadata")),
    )

    report = knowledge_corpus_audit_service.migrate_knowledge_corpus_metadata(dry_run=True)

    assert report["total_pending_updates"] == 2
    assert report["total_updated"] == 0
    assert report["scan_failure_count"] == 0


def test_metadata_migration_refuses_partial_collection_scan(monkeypatch):
    monkeypatch.setattr(knowledge_corpus_audit_service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(knowledge_corpus_audit_service, "get_collection_count", lambda collection: 2)
    monkeypatch.setattr(knowledge_corpus_audit_service, "get_collection_records", lambda collection: [])
    monkeypatch.setattr(
        "app.services.vector_store_service.update_document_metadatas",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("partial scan wrote metadata")),
    )

    report = knowledge_corpus_audit_service.migrate_knowledge_corpus_metadata()

    assert report["scan_failure_count"] == 2
    assert report["total_updated"] == 0
    assert all(not item["scan_complete"] for item in report["collections"].values())


def test_empty_collection_is_a_critical_gap():
    report = build_knowledge_corpus_audit(
        {CHROMA_COLLECTION_AEM_GUIDES: [], CHROMA_COLLECTION_DITA_SPEC: []},
        collection_counts={CHROMA_COLLECTION_AEM_GUIDES: 0, CHROMA_COLLECTION_DITA_SPEC: 0},
    )

    assert report["summary"]["critical_gap_count"] == 2
    assert [gap["code"] for gap in report["knowledge_gaps"]].count("empty-collection") == 2
