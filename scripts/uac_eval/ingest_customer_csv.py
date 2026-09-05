"""Append customer-labelled Jira CSV precedents to the existing jira_qa index.

No generated criteria, enrichment, approval or LLM calls occur here. CSV acceptance
criteria are preserved as historical source text; missing criteria remain empty.
Dry-run and self-tests use only the standard library and never initialise Chroma.

Usage::

    python scripts/uac_eval/ingest_customer_csv.py --csv export.csv --customer NAME --dry-run
    python scripts/uac_eval/ingest_customer_csv.py --csv export.csv --customer NAME --apply

Run --apply with the backend's Python/environment on the intended index host. The
script does not claim that a local index is the VM. Existing issue keys are skipped,
including keys indexed by another importer. The explicit metadata-reconciliation
option can add CSV-backed customer/component membership to existing keys without
replacing their documents, vectors, acceptance text or source authority. Embedded
Chroma requires exclusive maintenance access: stop other writers before running.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
MAX_CSV_BYTES = 256 * 1024 * 1024
MAX_FIELD_CHARS = 2 * 1024 * 1024
MAX_ROWS = 200_000
KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*\Z")
REQUIRED_HEADERS = (
    "Summary", "Issue key", "Issue Type", "Status", "Priority", "Resolution",
    "Description", "Custom field (Acceptance Criteria)", "Labels", "Component/s",
)
REPEATED_HEADERS = {"Labels", "Component/s"}


def _key(value: str) -> str:
    value = value.strip().upper()
    if not KEY_PATTERN.fullmatch(value):
        raise ValueError("Invalid issue key in input or exclusion list")
    return value


def _distinct(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def parse_export(path: Path, customer: str, exclude_keys: set[str] | None = None) -> tuple[list[dict], dict]:
    """Use header positions, not DictReader: Jira repeats Labels and Component/s."""
    path = path.resolve(strict=True)
    if not path.is_file() or path.suffix.casefold() != ".csv":
        raise ValueError("Input must be an existing CSV file")
    if not 0 < path.stat().st_size <= MAX_CSV_BYTES:
        raise ValueError("CSV is empty or exceeds the 256 MiB safety limit")
    customer = customer.strip()
    if not customer or len(customer) > 200 or any(ord(ch) < 32 for ch in customer):
        raise ValueError("Customer must be a nonempty label of at most 200 characters")
    excluded = {_key(value) for value in (exclude_keys or set())}
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    csv.field_size_limit(MAX_FIELD_CHARS)
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    try:
        headers = [header.strip() for header in next(reader)]
    except StopIteration as exc:
        raise ValueError("CSV header missing") from exc
    positions = {header: [i for i, name in enumerate(headers) if name == header] for header in REQUIRED_HEADERS}
    for header, indexes in positions.items():
        if not indexes or (header not in REPEATED_HEADERS and len(indexes) != 1):
            raise ValueError(f"Missing or ambiguous required CSV header: {header}")
    optional_headers = ("Updated", "Custom field (Customer Names)")
    for header in optional_headers:
        indexes = [i for i, name in enumerate(headers) if name == header]
        if len(indexes) > 1:
            raise ValueError(f"Ambiguous optional CSV header: {header}")
        positions[header] = indexes
    records: list[dict] = []
    seen: dict[str, dict] = {}
    matched_rows = ac_rows = duplicate_rows = 0
    for ordinal, row in enumerate(reader, start=2):
        if ordinal > MAX_ROWS + 1:
            raise ValueError("CSV exceeds the row safety limit")
        if not row or not any(row):
            continue
        if len(row) != len(headers):
            raise ValueError(f"CSV record {ordinal} has a different field count from its header")
        labels = _distinct([row[i] for i in positions["Labels"]])
        if customer.casefold() not in {label.casefold() for label in labels}:
            continue
        matched_rows += 1
        def cell(header: str) -> str:
            indexes = positions[header]
            return row[indexes[0]] if indexes else ""
        ac = cell("Custom field (Acceptance Criteria)")
        ac_rows += bool(ac.strip())
        record = {
            "key": _key(cell("Issue key")), "summary": cell("Summary"),
            "description": cell("Description"),
            "components": _distinct([row[i] for i in positions["Component/s"]]),
            "resolution": cell("Resolution"), "human_ac": ac,
            "customer": customer, "labels": labels,
            "issue_type": cell("Issue Type"), "status": cell("Status"),
            "priority": cell("Priority"), "updated": cell("Updated"),
            "customer_names_raw": cell("Custom field (Customer Names)"),
            "source_file_hash": digest, "source_record_number": ordinal,
            "source_evidence_mode": "validated_ac" if ac.strip() else "precedent_only",
            "reuse_authority": "SUPPORTING_DISCOVERY", "promotion_state": "VALIDATING",
        }
        prior = seen.get(record["key"])
        if prior is not None:
            if {k: v for k, v in prior.items() if k != "source_record_number"} != {
                k: v for k, v in record.items() if k != "source_record_number"
            }:
                raise ValueError("Duplicate issue key has conflicting source rows")
            duplicate_rows += 1
            continue
        seen[record["key"]] = record
        if record["key"] not in excluded:
            records.append(record)
    summary = {
        "customer": customer, "source_sha256": digest, "header_count": len(headers),
        "matched_rows": matched_rows, "with_ac": ac_rows,
        "without_ac": matched_rows - ac_rows, "duplicate_rows": duplicate_rows,
        "selected_records": len(records),
        "selected_with_ac": sum(bool(record["human_ac"].strip()) for record in records),
        "excluded_keys": sorted(excluded & seen.keys()),
        "column_positions": positions,
        "components": dict(sorted(Counter(c for record in records for c in record["components"]).items())),
    }
    return records, summary


def build_chunk(record: dict, canonical_components, component_metadata) -> dict:
    """Emit the real jira_qa {chunk_id, document, metadata} shape, one per issue.

    No enrich_jira/build_jira_qa_chunks call: those paths can produce inferred QA
    scopes. Here only CSV text is indexed. Description is retained as a report,
    not a validated expectation; source AC absence is explicit.
    """
    components = canonical_components(record["components"])
    lines = [
        f"Issue: {record['key']}", f"Summary: {record['summary']}",
        f"Components: {', '.join(record['components'])}", f"Customer: {record['customer']}",
        f"Resolution: {record['resolution']}", f"Labels: {', '.join(record['labels'])}",
        "Historical precedent for investigation only; not a current acceptance contract.",
        "Reported description (not a validated expectation):", record["description"],
        "Source acceptance criteria:" if record["human_ac"].strip() else "No source acceptance criteria; theme/precedent only.",
        record["human_ac"],
    ]
    document = "\n".join(lines)
    meta = {
        "source_type": "jira", "jira_key": record["key"], "title": record["summary"],
        "customer": record["customer"], "customer_names": json.dumps([record["customer"]]),
        "components": json.dumps(components), "components_raw": json.dumps(record["components"]),
        "labels": json.dumps(record["labels"]), "status": record["status"],
        "issue_type": record["issue_type"], "priority": record["priority"],
        "resolution": record["resolution"], "jira_updated_at": record["updated"],
        "updated_at": record["updated"], "chunk_type": "full_ticket_summary",
        "product_area": "AEM Guides", "qa_domain": "UAC",
        "import_source_type": "customer_csv", "source_file_hash": record["source_file_hash"],
        "source_content_hash": hashlib.sha256(document.encode("utf-8")).hexdigest(),
        "source_record_number": record["source_record_number"],
        "source_evidence_mode": record["source_evidence_mode"],
        "has_human_ac": bool(record["human_ac"].strip()),
        "human_ac": record["human_ac"], "human_ac_source": "csv_acceptance_criteria",
        "reuse_authority": "SUPPORTING_DISCOVERY", "promotion_state": "VALIDATING",
        "component_assignment_method": "source", "component_classification_source": "jira_csv",
    }
    meta.update(component_metadata(components))
    return {"chunk_id": f"{record['key']}::customer_csv::0", "document": document, "metadata": meta}


def _metadata_strings(metadata: dict, field: str) -> list[str]:
    raw = metadata.get(field)
    if raw in (None, ""):
        return []
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise ValueError("Existing list metadata is malformed; refusing to overwrite it") from exc
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("Existing list metadata has an unsupported shape")
    return values


def merge_existing_metadata(metadata: dict, record: dict, canonical_components, component_metadata) -> dict:
    """Add source-backed membership; retain original authority, AC and enrichment.

    The retriever scores customer_labels (not customer_names alone), and strict
    component queries use component_<name> membership flags. Scalar customer may
    identify another legitimate customer and is deliberately never replaced.
    """
    merged = dict(metadata)
    for field in ("customer_labels", "customer_names"):
        old = _metadata_strings(metadata, field)
        if record["customer"].casefold() not in {value.casefold() for value in old}:
            merged[field] = json.dumps([*old, record["customer"]], ensure_ascii=False)
    old_components = _metadata_strings(metadata, "components")
    old_raw = _metadata_strings(metadata, "components_raw")
    raw_components = _distinct([*old_raw, *old_components, *record["components"]])
    components = canonical_components(raw_components)
    if components != old_components:
        merged["components"] = json.dumps(components, ensure_ascii=False)
    if raw_components != old_raw:
        merged["components_raw"] = json.dumps(raw_components, ensure_ascii=False)
    for field, value in component_metadata(components).items():
        if field == "component_primary" and metadata.get(field):
            continue
        if type(value) is bool and metadata.get(field) is True:
            continue  # never erase previously indexed component membership
        if field == "component_filter_schema_version" and type(metadata.get(field)) is int:
            value = max(value, metadata[field])
        merged[field] = value
    hashes = _metadata_strings(metadata, "customer_csv_source_hashes")
    if record["source_file_hash"] not in hashes:
        merged["customer_csv_source_hashes"] = json.dumps([*hashes, record["source_file_hash"]])
    merged["customer_csv_membership_source"] = "exact_csv_label"
    # The imported membership does not approve or reclassify existing evidence.
    return merged


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _freeze_json(path: Path, value) -> None:
    payload = _json_bytes(value)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError("Immutable metadata snapshot conflict")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def reconcile_metadata(record: dict, adapter, snapshot_dir: Path) -> int:
    """Snapshot -> metadata-only update -> verify; interrupted writes are replayable.

    A pending snapshot is retained if Chroma succeeds but event delivery fails.
    Retrying verifies that each current record equals either its frozen before
    or after image, then replays the metadata/event update. Never restores over
    unrelated concurrent changes. Documents and vectors are hash-checked only,
    never passed to the update operation.
    """
    key = _key(record["key"])
    source_hash = record["source_file_hash"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("Invalid CSV source hash")
    snapshot_path = snapshot_dir.resolve() / f"{key}.{source_hash}.json"
    complete_path = snapshot_path.with_suffix(".completed.json")
    current = adapter.read_issue_state(key)
    if not current:
        raise RuntimeError("Existing issue disappeared before metadata reconciliation")
    if snapshot_path.exists():
        if snapshot_path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError("Metadata snapshot exceeds safety limit")
        packet = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if packet.get("jira_key") != key or packet.get("source_file_hash") != source_hash:
            raise RuntimeError("Metadata snapshot identity mismatch")
        before, after = packet["before"], packet["after"]
        expected = [dict(row, metadata=merge_existing_metadata(
            row["metadata"], record, adapter.canonical_components, adapter.component_metadata,
        )) for row in before]
        if after != expected:
            raise RuntimeError("Metadata snapshot does not match permitted membership-only transformation")
        if complete_path.exists():
            completion = json.loads(complete_path.read_text(encoding="utf-8"))
            if completion.get("snapshot_sha256") != hashlib.sha256(_json_bytes(packet)).hexdigest():
                raise RuntimeError("Completed metadata snapshot integrity mismatch")
            if current != after:
                raise RuntimeError("Completed metadata snapshot no longer matches index; audit concurrent changes")
            return 0
    else:
        before = current
        after = [dict(row, metadata=merge_existing_metadata(
            row["metadata"], record, adapter.canonical_components, adapter.component_metadata,
        )) for row in before]
        if before == after:
            return 0
        packet = {"schema_version": "customer-csv-metadata-snapshot-v1", "collection": "jira_qa",
                  "jira_key": key, "source_file_hash": source_hash, "before": before, "after": after}
        _freeze_json(snapshot_path, packet)
    if len(current) != len(before) or len(before) != len(after):
        raise RuntimeError("Index membership changed since metadata snapshot")
    for now, original, target in zip(current, before, after):
        if now not in (original, target):
            raise RuntimeError("Concurrent index changes detected; refusing metadata overwrite")
    # Recheck immediately before update to fail closed on a detected writer race.
    if adapter.read_issue_state(key) != current:
        raise RuntimeError("Concurrent writer changed the issue; retry after maintenance lock")
    adapter.update_metadata([row["id"] for row in after], [row["metadata"] for row in after])
    if adapter.read_issue_state(key) != after:
        raise RuntimeError("Metadata read-back failed or documents/embeddings changed")
    _freeze_json(complete_path, {"snapshot_sha256": hashlib.sha256(_json_bytes(packet)).hexdigest(),
                                 "documents_and_embeddings_unchanged": True})
    return sum(original != target for original, target in zip(before, after))


def append_records(records: list[dict], adapter, *, reconcile_existing: bool = False,
                   snapshot_dir: Path | None = None) -> dict:
    """Strict duplicate checks: inability to read the index is not 'key absent'."""
    if reconcile_existing and snapshot_dir is None:
        raise ValueError("Metadata reconciliation requires a snapshot directory")
    result = {"indexed": 0, "already_indexed": 0, "indexed_keys": [], "skipped_keys": [],
              "reconciled_chunks": 0, "reconciled_keys": []}
    for record in records:
        if adapter.has_key(record["key"]):
            result["already_indexed"] += 1
            result["skipped_keys"].append(record["key"])
            if reconcile_existing:
                count = reconcile_metadata(record, adapter, snapshot_dir)
                result["reconciled_chunks"] += count
                if count:
                    result["reconciled_keys"].append(record["key"])
            continue
        chunk = adapter.make_chunk(record)
        adapter.insert(chunk)
        if not adapter.has_key(record["key"]):
            raise RuntimeError("Index write did not pass read-back verification")
        result["indexed"] += 1
        result["indexed_keys"].append(record["key"])
    return result


class JiraQaAdapter:
    """Lazy existing-infrastructure adapter, constructed only for explicit --apply."""
    def __init__(self) -> None:
        sys.path.insert(0, str(REPO / "backend"))
        from dotenv import load_dotenv
        load_dotenv(REPO / "backend" / ".env", override=False)
        from app.services import vector_store_service as vectors
        from app.services.embedding_service import embed_texts
        from app.services.jira_component_metadata_service import canonical_component_names, component_filter_metadata
        self.vectors = vectors
        self.embed = embed_texts
        self.canonical_components = canonical_component_names
        self.component_metadata = component_filter_metadata
        # Public read helpers intentionally swallow backend errors. Duplicate
        # prevention needs strict reads, so use the service's existing client.
        self.client = vectors._get_client()
        if self.client is None:
            raise RuntimeError("Chroma unavailable; no records were fabricated or indexed")
        collections = self.client.list_collections()
        names = {item if isinstance(item, str) else item.name for item in collections}
        self.collection = (
            self.client.get_collection(vectors.CHROMA_COLLECTION_JIRA_QA)
            if vectors.CHROMA_COLLECTION_JIRA_QA in names else None
        )
        self.storage_mode = "REMOTE_CHROMA" if os.getenv("CHROMA_HOST", "").strip() else "LOCAL_CHROMA"

    def has_key(self, key: str) -> bool:
        if self.collection is None:
            return False
        result = self.collection.get(where={"jira_key": key}, limit=1, include=["metadatas"])
        if not isinstance(result, dict) or not isinstance(result.get("ids"), list):
            raise RuntimeError("Invalid index duplicate-check response")
        return bool(result["ids"])

    def make_chunk(self, record: dict) -> dict:
        return build_chunk(record, self.canonical_components, self.component_metadata)

    def read_issue_state(self, key: str) -> list[dict]:
        if self.collection is None:
            return []
        result = self.collection.get(where={"jira_key": key}, limit=10_001,
                                     include=["metadatas", "documents", "embeddings"])
        ids = result.get("ids")
        if not isinstance(ids, list) or len(ids) > 10_000:
            raise RuntimeError("Invalid or excessive issue chunk count")
        values = [result.get(field) for field in ("metadatas", "documents", "embeddings")]
        if any(value is None or len(value) != len(ids) for value in values):
            raise RuntimeError("Incomplete issue snapshot from index")
        rows = []
        for index, chunk_id in enumerate(ids):
            metadata, document, embedding = (value[index] for value in values)
            if not isinstance(metadata, dict) or not isinstance(document, str) or embedding is None:
                raise RuntimeError("Malformed indexed record")
            vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            rows.append({"id": chunk_id, "metadata": metadata,
                         "document_sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                         "embedding_sha256": hashlib.sha256(_json_bytes(vector)).hexdigest()})
        return sorted(rows, key=lambda row: row["id"])

    def update_metadata(self, ids: list[str], metadatas: list[dict]) -> None:
        if not self.vectors.update_document_metadatas(self.vectors.CHROMA_COLLECTION_JIRA_QA, ids, metadatas):
            raise RuntimeError("Metadata or evidence-event update failed; frozen snapshot retained for safe retry")

    def insert(self, chunk: dict) -> None:
        embedded = self.embed([chunk["document"]])
        if embedded is None:
            raise RuntimeError("Embeddings unavailable; no substitute or fabricated vectors were written")
        embeddings = embedded.tolist() if hasattr(embedded, "tolist") else list(embedded)
        if len(embeddings) != 1 or not embeddings[0] or any(not math.isfinite(float(x)) for x in embeddings[0]):
            raise RuntimeError("Invalid embedding response")
        # Recheck after potentially slow embedding; stable IDs also make retries
        # idempotent. Use maintenance access to exclude unrelated index writers.
        if self.has_key(chunk["metadata"]["jira_key"]):
            raise RuntimeError("Issue was indexed concurrently; retry safely to skip it")
        ok = self.vectors.add_documents(
            self.vectors.CHROMA_COLLECTION_JIRA_QA, [chunk["chunk_id"]],
            [chunk["document"]], [chunk["metadata"]], embeddings,
        )
        if not ok:
            raise RuntimeError("Index or evidence-event write failed; partial indexing is possible, rerun safely")
        self.collection = self.client.get_collection(self.vectors.CHROMA_COLLECTION_JIRA_QA)


def write_records(path: Path, records: list[dict]) -> None:
    """Explicit audit export, not the eval corpus; never overwrite different data."""
    path = path.resolve()
    payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError("Output exists with different content; choose a new audit output path")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def run_self_tests() -> None:
    headers = ["Summary", "Issue key", "Issue Type", "Status", "Priority", "Resolution",
               "Description", "Custom field (Acceptance Criteria)", "Labels", "Labels", "Component/s", "Component/s"]
    rows = [
        ["Table header", "SAMPLE-1", "Bug", "Closed", "Major", "Fixed", "Reported issue", "Original criterion\nunchanged", "other", "Example", "Authoring", "Editor"],
        ["Input issue", "SAMPLE-2", "Bug", "Closed", "Major", "Fixed", "Observed only", "", "Example", "", "Authoring", ""],
    ]
    with tempfile.TemporaryDirectory(prefix="customer-csv-selftest-") as folder:
        path = Path(folder) / "fixture.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream); writer.writerow(headers); writer.writerows(rows)
        records, summary = parse_export(path, "Example")
        assert (summary["matched_rows"], summary["with_ac"], summary["without_ac"]) == (2, 1, 1)
        assert records[0]["labels"] == ["other", "Example"] and records[0]["components"] == ["Authoring", "Editor"]
        assert records[0]["human_ac"] == rows[0][7] and records[1]["human_ac"] == ""
        assert parse_export(path, "Exam")[0] == []  # exact label, never substring
        assert [r["key"] for r in parse_export(path, "Example", {"SAMPLE-1"})[0]] == ["SAMPLE-2"]
        chunk = build_chunk(records[1], lambda value: value, lambda value: {"component_authoring": "Authoring" in value})
        assert chunk["metadata"]["has_human_ac"] is False and chunk["metadata"]["reuse_authority"] == "SUPPORTING_DISCOVERY"
        assert "No source acceptance criteria" in chunk["document"]
        class FakeIndex:
            def __init__(self): self.rows = {}
            def has_key(self, key): return key in self.rows
            def make_chunk(self, record): return build_chunk(record, lambda value: value, lambda value: {})
            def insert(self, item): self.rows[item["metadata"]["jira_key"]] = item
        index = FakeIndex()
        assert append_records(records, index)["indexed"] == 2
        before = json.dumps(index.rows, sort_keys=True)
        assert append_records(records, index)["already_indexed"] == 2
        assert json.dumps(index.rows, sort_keys=True) == before
        class BrokenIndex(FakeIndex):
            def has_key(self, key): raise RuntimeError("unavailable")
        try: append_records(records, BrokenIndex())
        except RuntimeError: pass
        else: raise AssertionError("Index read failure must not become key absent")
        class MetadataIndex(FakeIndex):
            canonical_components = staticmethod(lambda values: _distinct(values))
            component_metadata = staticmethod(lambda values: {
                "component_authoring": "Authoring" in values,
                "component_primary": values[0].lower() if values else "",
                "component_filter_schema_version": 5,
            })
            def __init__(self):
                super().__init__()
                self.fail_once = True
                self.write_count = 0
                self.rows = {"SAMPLE-2": {"id": "original-id", "metadata": {
                    "jira_key": "SAMPLE-2", "customer": "Swift", "customer_labels": '["Swift"]',
                    "enrich_customers": '["Swift", "Other"]', "human_ac": "Prior source AC",
                    "authority_class": "HUMAN_DECISION", "components": '["Editor"]',
                }, "document_sha256": "d" * 64, "embedding_sha256": "e" * 64}}
            def read_issue_state(self, key):
                return json.loads(json.dumps([self.rows[key]]))
            def update_metadata(self, ids, metadatas):
                assert ids == ["original-id"]
                self.rows["SAMPLE-2"]["metadata"] = metadatas[0]
                self.write_count += 1
                if self.fail_once:
                    self.fail_once = False
                    raise RuntimeError("simulated event delivery failure after index update")
        existing = MetadataIndex()
        snapshot_dir = Path(folder) / "snapshots"
        before_metadata = dict(existing.rows["SAMPLE-2"]["metadata"])
        try: reconcile_metadata(records[1], existing, snapshot_dir)
        except RuntimeError: pass
        else: raise AssertionError("Partial update failure not surfaced")
        assert len(list(snapshot_dir.glob("*.json"))) == 1  # immutable pending snapshot
        assert reconcile_metadata(records[1], existing, snapshot_dir) == 1
        assert existing.write_count == 2
        assert reconcile_metadata(records[1], existing, snapshot_dir) == 0
        assert existing.write_count == 2
        merged = existing.rows["SAMPLE-2"]["metadata"]
        for field in ("customer", "enrich_customers", "human_ac", "authority_class"):
            assert merged[field] == before_metadata[field]
        assert json.loads(merged["customer_labels"]) == ["Swift", "Example"]
        assert merged["component_authoring"] is True
        assert existing.rows["SAMPLE-2"]["document_sha256"] == "d" * 64
        assert existing.rows["SAMPLE-2"]["embedding_sha256"] == "e" * 64
        existing.rows["SAMPLE-2"]["metadata"]["human_ac"] = "Concurrent new source AC"
        try: reconcile_metadata(records[1], existing, snapshot_dir)
        except RuntimeError: pass
        else: raise AssertionError("Concurrent metadata change overwritten")
        output = Path(folder) / "audit.jsonl"
        write_records(output, records); write_records(output, records)
        try: write_records(output, records[:1])
        except ValueError: pass
        else: raise AssertionError("Different audit output must not be overwritten")
        with path.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(rows[0])
        assert parse_export(path, "Example")[1]["duplicate_rows"] == 1
        with path.open("a", encoding="utf-8", newline="") as stream:
            altered = list(rows[0]); altered[0] = "Different claim"; csv.writer(stream).writerow(altered)
        try: parse_export(path, "Example")
        except ValueError: pass
        else: raise AssertionError("Conflicting duplicate row accepted")
    print("PASS: customer CSV self-tests (2 fixture rows; provenance, exact filter, idempotency, metadata preservation, partial-retry recovery)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--customer")
    parser.add_argument("--exclude-key", action="append", default=[], help="Exclude held-out issue entirely before indexing/export")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true", help="Write to configured jira_qa; use exclusive maintenance access")
    parser.add_argument("--output", type=Path, help="Explicit normalized JSONL audit export (not eval corpus); disabled in --dry-run")
    parser.add_argument("--reconcile-existing-metadata", action="store_true",
                        help="Explicitly merge CSV membership metadata into existing keys; preserves documents, vectors and authorities")
    parser.add_argument("--snapshot-dir", type=Path,
                        help="Required with metadata reconciliation; immutable before/after metadata and document/vector hashes")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        run_self_tests(); return 0
    if not args.csv or not args.customer:
        parser.error("--csv and --customer are required")
    if args.reconcile_existing_metadata and not args.snapshot_dir:
        parser.error("--reconcile-existing-metadata requires --snapshot-dir")
    try:
        records, summary = parse_export(args.csv, args.customer, set(args.exclude_key))
        if args.output and not args.dry_run:
            write_records(args.output, records)
        if args.apply:
            adapter = JiraQaAdapter()
            summary.update(append_records(records, adapter, reconcile_existing=args.reconcile_existing_metadata,
                                          snapshot_dir=args.snapshot_dir))
            summary.update({"index_status": "APPLIED", "storage_mode": adapter.storage_mode, "collection": "jira_qa"})
        else:
            summary.update({"index_status": "NOT_CHECKED_DRY_RUN" if args.dry_run else "INDEX_NOT_REQUESTED", "indexed": None, "already_indexed": None})
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, csv.Error, RuntimeError, ImportError) as exc:
        # No source text, credentials or backend exception payload in CLI errors.
        print(f"ERROR: customer CSV operation failed ({type(exc).__name__}); no approval was created. Check input/schema and configured index/embedding availability.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
