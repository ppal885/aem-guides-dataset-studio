from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

import ingest_content_management_migration_ditaot_security as ingestion


class _FakeCollection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = {str(row["id"]): copy.deepcopy(row) for row in rows}
        self.upsert_batch_sizes: list[int] = []
        self.delete_batch_sizes: list[int] = []

    def count(self) -> int:
        return len(self.rows)

    def get(
        self,
        *,
        ids: list[str] | None = None,
        include: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict:
        del include
        if ids is None:
            keys = sorted(self.rows)
            start = int(offset or 0)
            stop = start + int(limit if limit is not None else len(keys))
            keys = keys[start:stop]
        else:
            keys = [str(identity) for identity in ids if str(identity) in self.rows]
        selected = [self.rows[identity] for identity in keys]
        return {
            "ids": keys,
            "documents": [row["document"] for row in selected],
            "metadatas": [copy.deepcopy(row["metadata"]) for row in selected],
            "embeddings": [list(row["embedding"]) for row in selected],
        }

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        self.upsert_batch_sizes.append(len(ids))
        for identity, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            self.rows[str(identity)] = {
                "id": str(identity),
                "document": str(document),
                "metadata": copy.deepcopy(metadata),
                "embedding": [float(value) for value in embedding],
            }

    def delete(self, *, ids: list[str]) -> None:
        self.delete_batch_sizes.append(len(ids))
        for identity in ids:
            self.rows.pop(str(identity), None)


def _stored_row(
    identity: str,
    *,
    document: str,
    embedding: list[float],
    metadata: dict | None = None,
) -> dict:
    return {
        "id": identity,
        "document": document,
        "metadata": copy.deepcopy(metadata or {}),
        "embedding": list(embedding),
    }


def _hold_activation_lock(lock_path: str, ready: object, release: object) -> None:
    ingestion.ACTIVATION_LOCK_PATH = Path(lock_path)
    with ingestion.activation_lock(timeout_seconds=10.0):
        ready.set()
        release.wait(15.0)


def _document(source_index: int, *, anchors: set[str] | None = None) -> ingestion.FetchedDocument:
    source = ingestion.SOURCES[source_index]
    return ingestion.FetchedDocument(
        source=source,
        canonical_url=source.url,
        title=source.label,
        raw_title=source.label + " | Adobe Experience Manager",
        last_updated="April 28, 2026",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_checksum="a" * 64,
        anchors=anchors or set(),
        raw_text="",
    )


def test_source_registry_contains_exactly_eleven_fragment_free_documents():
    assert len(ingestion.SOURCES) == 11
    canonical = [ingestion.canonicalize_url(source.url) for source in ingestion.SOURCES]
    assert len(set(canonical)) == 11
    assert all("#" not in url for url in canonical)
    assert ingestion.LEGACY_ANCHOR_INPUT.endswith("#id181NH0YN0AX")


def test_deterministic_identity_uses_canonical_document_and_versioned_section():
    url = ingestion.SOURCES[9].url
    doc_a = ingestion.document_id(url)
    doc_b = ingestion.document_id(url + "#id181NH0YN0AX")
    assert doc_a == doc_b
    section = ingestion.section_id(doc_a, ["Use custom DITA-OT plug-ins", "Timeout"])
    version_a = ingestion.section_version_id(section, "April 28, 2026", "a" * 64)
    version_b = ingestion.section_version_id(section, "April 28, 2026", "b" * 64)
    assert version_a != version_b
    assert ingestion.chunk_id(version_a, "DITA_OT_TIMEOUT") == ingestion.chunk_id(
        version_a, "DITA_OT_TIMEOUT"
    )


def test_legacy_anchor_is_not_guessed_when_live_dom_has_no_target():
    document = _document(9, anchors={"id181NH1020L7", "id211MB0E00XA"})
    result = ingestion.resolve_legacy_anchor(document, ingestion.LEGACY_ANCHOR_INPUT)
    assert result["status"] == "UNRESOLVED_LEGACY_ANCHOR"
    assert result["resolved_anchor"] == ""
    assert result["match_count"] == 0


def test_div_grid_permission_parser_preserves_blank_cells():
    soup = BeautifulSoup(
        """
        <main>
          <h2 id="feature-permissions">Feature permissions</h2>
          <div class="table 0-row-4 1-row-4 2-row-4">
            <div><div>Task</div><div>Authors</div><div>Reviewers</div><div>Publishers</div></div>
            <div><div>Create DITA Topic</div><div>Yes</div><div></div><div>Yes</div></div>
            <div><div>Review Topic 1</div><div>Yes</div><div>Yes</div><div>Yes</div></div>
          </div>
        </main>
        """,
        "html.parser",
    )
    tables = ingestion.extract_structured_tables(soup.main)
    assert tables[0].rows[1] == ["Create DITA Topic", "Yes", "", "Yes"]
    assert tables[0].heading_path == ["Feature permissions"]
    assert tables[0].anchor == "feature-permissions"
    document = _document(10)
    document.tables = tables
    document.permission_footnotes = {
        "1": "Authors and Publishers can review only when invited for review.",
        "2": "Depending on document-state-profile transition rights.",
    }
    assertions = ingestion.parse_permission_assertions(document)
    reviewer = next(
        item
        for item in assertions
        if item["task"] == "Create DITA Topic" and item["role"] == "Reviewers"
    )
    assert reviewer["allowed"] is None
    assert reviewer["cell_state"] == "blank"
    review_author = next(
        item
        for item in assertions
        if item["task"] == "Review Topic" and item["role"] == "Authors"
    )
    assert "invited" in review_author["footnote"]


def test_duplicate_permission_assertions_merge_provenance_not_semantics():
    base = {
        "assertion_id": "perm:1",
        "task": "Create DITA Topic",
        "raw_task": "Create DITA Topic",
        "role": "Authors",
        "allowed": True,
        "cell_state": "yes",
        "footnote": "",
        "footnote_number": "",
        "heading_path": ["Feature permissions"],
        "section_anchor": "feature-permissions",
        "table_source_order": 1,
        "row_index": 1,
        "column_index": 1,
    }
    merged = ingestion.merge_permission_assertions(
        [
            {**base, "source_id": "SOURCE-1", "canonical_url": ingestion.SOURCES[0].url},
            {**base, "source_id": "SOURCE-11", "canonical_url": ingestion.SOURCES[10].url},
        ]
    )
    assert len(merged) == 1
    assert merged[0]["source_ids"] == ["SOURCE-1", "SOURCE-11"]
    assert len(merged[0]["provenance_urls"]) == 2
    assert [item["source_id"] for item in merged[0]["source_decisions"]] == [
        "SOURCE-1",
        "SOURCE-11",
    ]
    assert merged[0]["decision_conflict"] is False


def test_permission_merge_detects_cross_source_conflicts_by_task_and_role():
    base = {
        "task": "Create DITA Topic",
        "raw_task": "Create DITA Topic",
        "role": "Authors",
        "allowed": True,
        "cell_state": "yes",
        "footnote": "",
        "footnote_number": "",
        "heading_path": ["Feature permissions"],
        "section_anchor": "feature-permissions",
        "table_source_order": 1,
        "row_index": 1,
        "column_index": 1,
    }
    merged = ingestion.merge_permission_assertions(
        [
            {**base, "source_id": "SOURCE-1", "canonical_url": ingestion.SOURCES[0].url},
            {
                **base,
                "source_id": "SOURCE-11",
                "canonical_url": ingestion.SOURCES[10].url,
                "allowed": False,
                "cell_state": "no",
            },
        ]
    )
    assert len(merged) == 1
    assert merged[0]["decision_conflict"] is True
    assert merged[0]["cell_state"] == "conflict"
    assert set(merged[0]["conflict_fields"]) == {"allowed", "cell_state"}
    assert len(merged[0]["source_decisions"]) == 2


def test_permission_merge_rejects_conflicting_duplicate_cells_within_one_source():
    base = {
        "task": "Create DITA Topic",
        "raw_task": "Create DITA Topic",
        "role": "Authors",
        "allowed": True,
        "cell_state": "yes",
        "footnote": "",
        "footnote_number": "",
        "source_id": "SOURCE-1",
        "canonical_url": ingestion.SOURCES[0].url,
    }
    with pytest.raises(ValueError, match="conflicting permission decisions within SOURCE-1"):
        ingestion.merge_permission_assertions(
            [base, {**base, "allowed": False, "cell_state": "no"}]
        )


def test_permission_validation_derives_counts_from_the_live_matrix_shape():
    rows = [
        ["Task", "Authors", "Reviewers", "Publishers"],
        ["Create DITA Topic", "Yes", "", "Yes"],
        ["Delete DITA Topic", "No", "No", "Yes"],
    ]
    documents = {
        "SOURCE-1": _document(0),
        "SOURCE-11": _document(10),
    }
    for source_order, document in enumerate(documents.values(), start=1):
        document.tables = [
            ingestion.ExtractedTable(
                ["Feature permissions"],
                "feature-permissions",
                copy.deepcopy(rows),
                source_order,
            )
        ]
    permissions = ingestion.merge_permission_assertions(
        assertion
        for document in documents.values()
        for assertion in ingestion.parse_permission_assertions(document)
    )
    metrics = ingestion._permission_model_metrics(documents, permissions)
    assert metrics["matrix_structural"] is True
    assert metrics["duplicates_merged"] is True
    assert metrics["decisions_consistent"] is True
    assert metrics["table_row_counts"] == [2, 2]
    assert metrics["expected_cell_count"] == 6
    assert metrics["actual_merged_cell_count"] == 6


def test_non_permission_table_rows_are_structured_individually():
    document = _document(9)
    document.tables = [
        ingestion.ExtractedTable(
            ["Profile properties"],
            "profile-properties",
            [
                ["Property", "Description"],
                ["DITA-OT Timeout", "Publishing stops after the configured timeout"],
                ["Assigned Path", "Repository path controlled by the profile"],
            ],
            1,
        )
    ]
    records = ingestion.build_table_records(document)
    assert len(records) == 2
    assert records[0]["record_type"] == "STRUCTURED_TABLE_ROW"
    assert records[0]["structured_fields"]["Property"] == "DITA-OT Timeout"
    assert "DITA_OT_TIMEOUT" in records[0]["capabilities"]
    assert records[1]["structured_fields"]["Property"] == "Assigned Path"
    assert "PROFILE_ASSIGNMENT" in records[1]["capabilities"]
    assert records[0]["heading_path"] == ["Profile properties"]
    assert records[0]["section_anchor"] == "profile-properties"


def test_structured_table_row_ids_ignore_table_and_row_ordinals():
    document = _document(9)
    header = ["Property", "Description"]
    timeout = ["DITA-OT Timeout", "Publishing stops after the configured timeout"]
    path = ["Assigned Path", "Repository path controlled by the profile"]
    document.tables = [
        ingestion.ExtractedTable(
            ["Profile properties"],
            "profile-properties",
            [header, timeout, path, timeout],
            1,
        )
    ]
    first = ingestion.build_table_records(document)
    document.tables = [
        ingestion.ExtractedTable(
            ["Profile properties"],
            "profile-properties",
            [header, path, timeout],
            99,
        )
    ]
    second = ingestion.build_table_records(document)

    first_ids = {
        record["structured_fields"]["Property"]: record["chunk_id"] for record in first
    }
    second_ids = {
        record["structured_fields"]["Property"]: record["chunk_id"] for record in second
    }
    assert len(first) == 2
    assert first_ids == second_ids
    assert {record["section_version_id"] for record in first} == {
        record["section_version_id"] for record in second
    }


def test_cosmetic_table_row_is_removed_before_property_header():
    rows = ingestion._normalize_table_rows(
        [
            ["table 0-row-2 1-row-2", ""],
            ["Property name", "Description"],
            ["DITA-OT Timeout", "Timeout description"],
        ]
    )
    assert rows[0] == ["Property name", "Description"]
    assert ingestion.normalize_symbol("DITA-OT PDF Arguments") == "PDF_ARGUMENTS"
    assert ingestion.normalize_symbol("DITA-OT Plug-in Path") == "PLUGIN_PATH"


def test_renderer_only_accordion_tables_and_rows_are_removed():
    assert ingestion._normalize_table_rows(
        [
            ["accordion On-premise non-UUID-based file system"],
            ["note tip"],
            ["TIP"],
            ["Select {width=\"25\"} near any field to view more details about it."],
        ]
    ) == []
    assert ingestion._normalize_table_rows(
        [
            ["Property", "Description"],
            ["note tip", "TIP"],
            ["Batch size", "Number of files moved in one batch"],
        ]
    ) == [
        ["Property", "Description"],
        ["Batch size", "Number of files moved in one batch"],
    ]


def test_query_routing_keeps_version_specific_migrations_separate():
    route_43 = ingestion.classify_query_intent("Migrate 4.3.1 non-UUID to UUID")
    route_46 = ingestion.classify_query_intent("Migrate 4.6.0 SP4 non-UUID to UUID")
    assert route_43["preferred_sources"][0] == "SOURCE-8"
    assert "NON_UUID_TO_UUID_4_6_PATH" in route_43["forbidden_capabilities"]
    assert route_46["preferred_sources"][0] == "SOURCE-9"
    assert "NON_UUID_TO_UUID_4_3_PATH" in route_46["forbidden_capabilities"]


def test_cloud_binary_store_routes_outside_guides_bulk_processor_batch():
    hits = ingestion.deterministic_retrieve(
        "Asset processing in Cloud binary store",
        [
            {
                "chunk_id": "guides",
                "source_id": "SOURCE-4",
                "capability": "TARGETED_MANUAL_PROCESSING",
                "capabilities": ["TARGETED_MANUAL_PROCESSING"],
                "content": "Guides Bulk Processor processing assets",
            }
        ],
    )
    assert hits[0]["source_id"] == "EXISTING-AEM-ASSETS-MICROSERVICES"
    assert hits[0]["capability"] == "AEM_ASSETS_MICROSERVICES"


def test_retrieval_catalog_contains_all_positive_and_negative_cases():
    cases = ingestion.load_retrieval_cases()
    assert len(cases) == 83
    assert [case["id"] for case in cases[:73]] == [f"Q{i}" for i in range(1, 74)]
    assert [case["id"] for case in cases[73:]] == [f"N{i}" for i in range(1, 11)]


def test_unchanged_full_activation_fingerprint_reuses_exact_stored_vector():
    model = "unit-test-embedding-model"
    vector = [0.125, -0.25, 0.5]
    vector_checksum = ingestion.embedding_checksum(vector)
    candidate = {"chunk_id": "same", "chunk_checksum": "aaa", "content": "body"}
    indexed = {
        **candidate,
        "embedding_identity": model,
        "embedding_checksum": vector_checksum,
    }
    indexed["activation_fingerprint"] = ingestion.indexed_record_fingerprint(
        indexed, model, vector_checksum
    )
    stored = _stored_row(
        "same",
        document="body",
        embedding=vector,
        metadata=ingestion._chroma_metadata(indexed),
    )

    reused, to_upsert = ingestion.partition_records_for_activation(
        [candidate.copy()],
        {"same": indexed},
        {"same": stored},
        embedding_identity=model,
    )
    assert [record["chunk_id"] for record in reused] == ["same"]
    assert to_upsert == []

    corrupted_vector = copy.deepcopy(stored)
    corrupted_vector["embedding"][1] = -0.5
    reused, to_upsert = ingestion.partition_records_for_activation(
        [candidate.copy()],
        {"same": indexed},
        {"same": corrupted_vector},
        embedding_identity=model,
    )
    assert reused == []
    assert [record["chunk_id"] for record in to_upsert] == ["same"]

    extra_metadata = copy.deepcopy(stored)
    extra_metadata["metadata"]["unexpected_legacy_field"] = "stale"
    reused, to_upsert = ingestion.partition_records_for_activation(
        [candidate.copy()],
        {"same": indexed},
        {"same": extra_metadata},
        embedding_identity=model,
    )
    assert reused == []
    assert [record["chunk_id"] for record in to_upsert] == ["same"]


def test_semantic_collision_registry_contains_mandatory_distinctions():
    collisions = set(ingestion.SEMANTIC_COLLISIONS)
    assert ("ASSET_BULK_INGESTOR", "GUIDES_BULK_PROCESSOR") in collisions
    assert ("MIGRATION_OUTPUT_VALIDATION_BASELINE", "DITA_MAP_BASELINE") in collisions
    assert ("XSD_CATALOG_INTEGRATION", "XSD_SUPPORT_IN_EDITOR") in collisions
    assert ("GROUP_PERMISSION", "REPOSITORY_ACL") in collisions


def test_section_version_is_shared_by_blocks_in_same_section_and_ignores_ordinal():
    document = _document(2)
    document.blocks = [
        ingestion.SectionBlock(["Copy files"], "copy-files", "p", 99, "Copy creates a new asset."),
        ingestion.SectionBlock(["Copy files"], "copy-files", "p", 1, "A new UUID is assigned."),
    ]
    first = ingestion.build_document_block_records(document)
    document.blocks[0].ordinal = 1
    document.blocks[1].ordinal = 99
    second = ingestion.build_document_block_records(document)
    assert len({record["section_version_id"] for record in first}) == 1
    assert {record["chunk_id"] for record in first} == {record["chunk_id"] for record in second}


def test_native_rowspan_and_div_tables_are_both_extracted():
    soup = BeautifulSoup(
        """
        <main>
          <table>
            <tr><th>Property</th><th>Value</th></tr>
            <tr><td rowspan="2">Query limits</td><td>queryLimitInMemory</td></tr>
            <tr><td>queryLimitReads</td></tr>
          </table>
          <div class="table 0-row-2 1-row-2">
            <div><div>State</div><div>Action</div></div>
            <div><div>Completed</div><div>Restart</div></div>
          </div>
        </main>
        """,
        "html.parser",
    )
    tables = ingestion.extract_structured_tables(soup.main)
    assert ["Query limits", "queryLimitInMemory"] in tables[0].rows
    assert ["Query limits", "queryLimitReads"] in tables[0].rows
    assert tables[1].rows[1] == ["Completed", "Restart"]


def test_flattened_responsive_table_prose_is_not_emitted_as_semantic_block():
    soup = BeautifulSoup(
        """
        <main>
          <h1>Configuration</h1>
          <p>Useful behavior outside the table.</p>
          <p>Configure values: table 0-row-2 1-row-2 Property Value Foo Bar</p>
        </main>
        """,
        "html.parser",
    )
    blocks = list(ingestion._iter_semantic_blocks(soup.main))
    assert [block.text for block in blocks] == ["Useful behavior outside the table."]


def test_fixture_derived_contract_builder_is_fail_closed():
    with pytest.raises(RuntimeError, match="fixture-derived behavior contracts are prohibited"):
        ingestion.build_normalized_contract_records({}, [], [{"id": "Q1"}])


def test_secret_scanner_covers_credentials_and_private_network_addresses():
    assert ingestion.find_secret_kinds("Authorization: Bearer abcdefghijklmnop") == ["BEARER_TOKEN"]
    assert ingestion.find_secret_kinds("password=supersecret") == ["SECRET_ASSIGNMENT"]
    assert ingestion.find_secret_kinds("http://admin:secretpass@example.invalid") == ["URI_CREDENTIALS"]
    assert ingestion.find_secret_kinds("connect to 10.0.0.23") == ["PRIVATE_NETWORK_ADDRESS"]


@pytest.mark.parametrize("payload", ["{}", '"not-a-list"', "[1]"])
def test_manifest_loader_rejects_non_array_or_non_object_rows(tmp_path: Path, payload: str):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        ingestion._load_manifest(manifest)


def test_manifest_loader_preserves_valid_rows_and_propagates_invalid_json(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    rows = [{"chunk_id": "one"}, {"chunk_id": "two"}]
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    assert ingestion._load_manifest(manifest) == rows
    manifest.write_text("[", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        ingestion._load_manifest(manifest)


def test_local_activation_refuses_to_initialize_a_missing_chroma_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _VectorStoreService:
        CHROMA_DB_DIR = "chroma_db"

    monkeypatch.delenv("CHROMA_HOST", raising=False)
    missing = tmp_path / "missing-storage"
    with pytest.raises(RuntimeError, match="will not create"):
        ingestion._require_existing_chroma_store(
            _VectorStoreService,
            storage_base=missing,
        )
    assert not missing.exists()

    database = tmp_path / "storage" / "chroma_db"
    database.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="will not create"):
        ingestion._require_existing_chroma_store(
            _VectorStoreService,
            storage_base=database.parent,
        )
    (database / "chroma.sqlite3").write_bytes(b"existing")
    ingestion._require_existing_chroma_store(
        _VectorStoreService,
        storage_base=database.parent,
    )

    monkeypatch.setenv("CHROMA_HOST", "chroma.internal")
    ingestion._require_existing_chroma_store(
        _VectorStoreService,
        storage_base=missing,
    )


def test_activation_ownership_includes_chroma_only_orphans_in_stale_partition():
    partition = ingestion._partition_activation_ownership(
        {"keep", "new"},
        {"keep", "manifest-stale"},
        {"keep", "chroma-orphan"},
    )
    assert partition["owned_before"] == {"keep", "manifest-stale", "chroma-orphan"}
    assert partition["target"] == {
        "keep",
        "new",
        "manifest-stale",
        "chroma-orphan",
    }
    assert partition["stale"] == {"manifest-stale", "chroma-orphan"}
    assert partition["chroma_orphans"] == {"chroma-orphan"}


def test_prepared_journal_recovers_exact_state_in_bounded_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    transaction = tmp_path / "transaction"
    transaction.mkdir()
    prior_rows = [
        _stored_row(
            f"old-{index:03d}",
            document=f"old document {index}",
            embedding=[float(index), 0.25],
            metadata={"generation": "before"},
        )
        for index in range(101)
    ]
    unrelated = _stored_row(
        "unrelated",
        document="must remain untouched",
        embedding=[9.0, 9.0],
        metadata={"owner": "another-batch"},
    )
    new_only_ids = [f"new-{index:03d}" for index in range(40)]
    mutated_rows = [
        _stored_row(
            row["id"],
            document="candidate replacement",
            embedding=[-1.0, -1.0],
            metadata={"generation": "candidate"},
        )
        for row in prior_rows
    ] + [
        _stored_row(
            identity,
            document="new candidate",
            embedding=[1.0, 1.0],
            metadata={"generation": "candidate"},
        )
        for identity in new_only_ids
    ]
    collection = _FakeCollection([*mutated_rows, unrelated])
    target_ids = [row["id"] for row in prior_rows] + new_only_ids
    ingestion.atomic_write_json(
        transaction / "chroma_preimage.json",
        {
            "rows": prior_rows,
            "state_root": ingestion._collection_state_root(prior_rows),
        },
    )

    live_manifest = tmp_path / "manifest.json"
    manifest_backup = transaction / "manifest.before"
    original_manifest = b'[{"chunk_id":"old"}]\n'
    live_manifest.write_bytes(b'[{"chunk_id":"candidate"}]\n')
    manifest_backup.write_bytes(original_manifest)
    file_specs = {
        "manifest": {
            "path": str(live_manifest),
            "backup": str(manifest_backup),
            "existed": True,
            "backup_checksum": hashlib.sha256(original_manifest).hexdigest(),
        }
    }
    expected_full_root = ingestion._collection_state_root([*prior_rows, unrelated])
    journal = {
        "schema": "aem-guides-activation-journal-v2",
        "status": "PREPARED",
        "activation_id": "unit-recovery",
        "transaction_dir": str(transaction),
        "candidate_ids": target_ids,
        "target_ids": target_ids,
        "files": file_specs,
        "collection_root_before": expected_full_root,
        "events": [],
    }
    journal_path = tmp_path / "activation_journal.json"
    ingestion.atomic_write_json(journal_path, journal)
    monkeypatch.setattr(ingestion, "ACTIVATION_JOURNAL_PATH", journal_path)

    ingestion._recover_incomplete_activation(collection)

    restored_rows, restored_root = ingestion._stable_collection_snapshot(collection)
    assert restored_root == expected_full_root
    assert {row["id"] for row in restored_rows} == {
        *(row["id"] for row in prior_rows),
        "unrelated",
    }
    assert live_manifest.read_bytes() == original_manifest
    assert max(collection.upsert_batch_sizes) <= 48
    assert max(collection.delete_batch_sizes) <= 128
    assert len(collection.upsert_batch_sizes) == 3
    assert len(collection.delete_batch_sizes) == 2
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
    assert json.loads(
        (transaction / "activation_journal.json").read_text(encoding="utf-8")
    )["status"] == "ROLLED_BACK"

    operation_counts = (
        len(collection.upsert_batch_sizes),
        len(collection.delete_batch_sizes),
    )
    ingestion._recover_incomplete_activation(collection)
    assert operation_counts == (
        len(collection.upsert_batch_sizes),
        len(collection.delete_batch_sizes),
    )


def test_committed_journal_finalizes_prepared_history_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prepared = tmp_path / "transaction" / "history_prepared"
    prepared.mkdir(parents=True)
    (prepared / "activation.json").write_text('{"status":"COMMITTED"}\n', encoding="utf-8")
    final = tmp_path / "history" / "activation-1"
    journal_path = tmp_path / "activation_journal.json"
    ingestion.atomic_write_json(
        journal_path,
        {
            "status": "COMMITTED",
            "prepared_history_dir": str(prepared),
            "history_dir": str(final),
        },
    )
    monkeypatch.setattr(ingestion, "ACTIVATION_JOURNAL_PATH", journal_path)
    collection = _FakeCollection([])

    ingestion._recover_incomplete_activation(collection)
    assert not prepared.exists()
    assert (final / "activation.json").exists()
    ingestion._recover_incomplete_activation(collection)
    assert (final / "activation.json").exists()


def test_rollback_restores_files_even_when_unrelated_chroma_state_diverged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    transaction = tmp_path / "transaction"
    transaction.mkdir()
    prior = _stored_row(
        "owned",
        document="old",
        embedding=[1.0],
        metadata={"generation": "before"},
    )
    unrelated_before = _stored_row(
        "unrelated",
        document="before",
        embedding=[2.0],
        metadata={"owner": "other"},
    )
    unrelated_after = copy.deepcopy(unrelated_before)
    unrelated_after["document"] = "changed externally"
    collection = _FakeCollection(
        [
            _stored_row(
                "owned",
                document="candidate",
                embedding=[3.0],
                metadata={"generation": "candidate"},
            ),
            unrelated_after,
        ]
    )
    ingestion.atomic_write_json(
        transaction / "chroma_preimage.json",
        {"rows": [prior], "state_root": ingestion._collection_state_root([prior])},
    )
    live = tmp_path / "manifest.json"
    backup = transaction / "manifest.before"
    original = b"old manifest\n"
    live.write_bytes(b"candidate manifest\n")
    backup.write_bytes(original)
    journal_path = tmp_path / "activation_journal.json"
    monkeypatch.setattr(ingestion, "ACTIVATION_JOURNAL_PATH", journal_path)
    journal = {
        "transaction_dir": str(transaction),
        "candidate_ids": ["owned"],
        "target_ids": ["owned"],
        "collection_root_before": ingestion._collection_state_root(
            [prior, unrelated_before]
        ),
        "files": {
            "manifest": {
                "path": str(live),
                "backup": str(backup),
                "existed": True,
                "backup_checksum": hashlib.sha256(original).hexdigest(),
            }
        },
        "events": [],
    }

    with pytest.raises(RuntimeError, match="full-state verification"):
        ingestion._rollback_activation(collection, journal)
    assert live.read_bytes() == original
    assert collection.rows["owned"] == prior
    assert collection.rows["unrelated"]["document"] == "changed externally"
    assert not journal_path.exists()


def test_activation_lock_blocks_a_second_process_and_releases_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    lock_path = tmp_path / "activation.lock"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_activation_lock,
        args=(str(lock_path), ready, release),
    )
    process.start()
    try:
        assert ready.wait(20.0), "child did not acquire the activation lock"
        monkeypatch.setattr(ingestion, "ACTIVATION_LOCK_PATH", lock_path)
        with pytest.raises(TimeoutError, match="activation lock"):
            with ingestion.activation_lock(timeout_seconds=0.2):
                pytest.fail("contended activation lock was acquired")
    finally:
        release.set()
        process.join(20.0)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
    assert process.exitcode == 0
    with ingestion.activation_lock(timeout_seconds=1.0):
        pass
