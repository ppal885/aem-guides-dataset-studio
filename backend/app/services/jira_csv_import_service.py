"""Admin Jira CSV preview and asynchronous SQL/Chroma ingestion."""

from __future__ import annotations

import asyncio
import copy
import csv
import hashlib
import io
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.db.jira_enrichment_models import JiraCsvImportRun, JiraEnrichedIssue, JiraIssueChunk
from app.db.jira_enrichment_repository import insert_jira_chunks, upsert_jira_issue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched, is_embedding_available
from app.services.jira_chunking_service import build_comments_digest
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_qa_chunking_service import build_jira_qa_chunks
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    delete_documents,
    is_chroma_available,
    update_documents_metadata,
)

logger = get_structured_logger(__name__)

MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 10_000
IMPORTER_VERSION = "customer-intelligence-v6"
REQUIRED_HEADERS = {"Summary", "Issue key", "Issue Type", "Status", "Resolution", "Description", "Updated"}
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_IMS_ORG_RE = re.compile(r"\b[A-Z0-9]{8,}@AdobeOrg\b", re.I)
_MENTION_RE = re.compile(r"\[~[^\]]+\]")
_SECRET_RE = re.compile(
    r"(?i)\b(client[_ -]?secret|access[_ -]?token|oauth[_ -]?token|api[_ -]?token|password)\b\s*[:=]\s*\S+"
)
_LINK_HEADER_RE = re.compile(r"issue link", re.I)
_RUN_TASKS: set[asyncio.Task[Any]] = set()
_CUSTOMER_ALIASES = {
    "red hat": "Red Hat",
    "redhat": "Red Hat",
    "red_hat": "Red Hat",
    "ibm": "IBM",
    "international business machines": "IBM",
    "swift": "Swift",
    "s.w.i.f.t": "Swift",
    "lexmark": "Lexmark",
    "topcon": "Topcon",
    "fidelity": "Fidelity",
    "jpmc": "JPMC",
    "jp morgan": "JPMC",
    "jpmorgan": "JPMC",
    "jpmorgan chase": "JPMC",
    "kone": "KONE",
    "mayo clinic": "Mayo Clinic",
    "mayoclinic": "Mayo Clinic",
    "mayo foundation for medical education and research": "Mayo Clinic",
    "thomson reuters": "Thomson Reuters",
    "thomsonreuters": "Thomson Reuters",
}
_SUPPORTED_CUSTOMERS = {
    "Red Hat", "IBM", "Swift", "Lexmark", "Topcon", "Fidelity", "JPMC", "KONE",
    "Mayo Clinic", "Thomson Reuters",
}
_MIXED_CUSTOMER = "Mixed (row-level cohorts)"
_CUSTOMER_LABELS = {
    "redhat": "Red Hat",
    "red_hat": "Red Hat",
    "ibm": "IBM",
    "swift": "Swift",
    "lexmark": "Lexmark",
    "topcon": "Topcon",
    "fidelity": "Fidelity",
    "jpmc": "JPMC",
    "jpmorgan": "JPMC",
    "jp_morgan": "JPMC",
    "kone": "KONE",
    "mayoclinic": "Mayo Clinic",
    "mayo_clinic": "Mayo Clinic",
    "thomsonreuters": "Thomson Reuters",
    "thomson_reuters": "Thomson Reuters",
}
_UNSAFE_CUSTOMER_RE = re.compile(
    r"(?i)(?:https?://|@AdobeOrg|\[~|client[_ -]?secret|access[_ -]?token|oauth[_ -]?token|password|feature[_ -]?flag)"
)


@dataclass
class ParsedCsvIssue:
    issue_key: str
    issue: dict[str, Any]
    comments: list[dict[str, str]]
    acceptance_criteria: str
    root_cause: str
    test_plan: str
    resolution: str
    jira_updated_at: str
    company_names: list[str]
    customer_names: list[str]
    customer_cohorts: list[str]
    resolutions: list[str]
    source_file_hashes: list[str]
    import_provenance: list[dict[str, str]]
    evidence_archive: dict[str, list[str]]
    linked_issue_refs: list[str]
    attachment_filenames: list[str]
    redacted_fields: int


@dataclass
class ParsedCsvFile:
    filename: str
    file_hash: str
    headers: list[str]
    issues: list[ParsedCsvIssue]
    duplicate_headers: dict[str, int]
    resolution_counts: dict[str, int]
    redacted_fields: int
    detected_customer: str = ""
    detection_confidence: str = "none"
    detection_signals: list[str] | None = None
    detection_warnings: list[str] | None = None


def _sanitize_text(value: Any) -> tuple[str, int]:
    text = str(value or "").replace("\x00", "").strip()
    redactions = 0
    for pattern, replacement in (
        (_EMAIL_RE, "[redacted-email]"),
        (_IMS_ORG_RE, "[redacted-ims-org]"),
        (_MENTION_RE, "[redacted-mention]"),
        (_SECRET_RE, "[redacted-secret]"),
    ):
        text, count = pattern.subn(replacement, text)
        redactions += count
    return text, redactions


def _dedupe(values: list[str], *, limit: int = 200) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))[:limit]


def _canonical_customer(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    key = re.sub(r"[-_]+", " ", clean).casefold()
    return _CUSTOMER_ALIASES.get(key, clean)


def _safe_customer_values(values: list[str]) -> tuple[list[str], int]:
    output: list[str] = []
    redactions = 0
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if raw.isdigit() or _UNSAFE_CUSTOMER_RE.search(raw) or _EMAIL_RE.search(raw) or _IMS_ORG_RE.search(raw):
            redactions += 1
            continue
        clean, count = _sanitize_text(raw)
        redactions += count
        if not clean or clean.startswith("[redacted-"):
            continue
        output.append(_canonical_customer(clean))
    return _dedupe(output, limit=100), redactions


def _detect_file_customer(item: ParsedCsvFile) -> tuple[str, str, list[str], list[str]]:
    label_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    total = max(len(item.issues), 1)
    for issue in item.issues:
        labels = issue.issue.get("fields", {}).get("labels") or []
        row_labels = {_CUSTOMER_LABELS.get(str(label).strip().casefold(), "") for label in labels}
        for customer in row_labels - {""}:
            label_counts[customer] += 1
        for customer in issue.customer_names + issue.company_names:
            canonical = _canonical_customer(customer)
            if canonical in _SUPPORTED_CUSTOMERS:
                field_counts[canonical] += 1
    signals: list[str] = []
    candidates = set(label_counts) | set(field_counts)
    for customer in sorted(candidates):
        signals.append(
            f"{customer}: label rows {label_counts[customer]}/{total}; safe customer-field rows {field_counts[customer]}/{total}"
        )
    unanimous = [customer for customer, count in label_counts.items() if count == total]
    warnings: list[str] = []
    if len(unanimous) == 1:
        return unanimous[0], "high", signals, warnings
    row_covered = sum(1 for issue in item.issues if issue.customer_cohorts)
    row_cohorts = sorted(
        {customer for issue in item.issues for customer in issue.customer_cohorts},
        key=str.casefold,
    )
    if row_covered == total and len(row_cohorts) > 1:
        signals.append(f"Mixed row-level cohort coverage: {row_covered}/{total} rows; {', '.join(row_cohorts)}")
        return _MIXED_CUSTOMER, "high", signals, warnings
    ranked = (label_counts + field_counts).most_common()
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        warnings.append("Customer was inferred from majority evidence; confirm before import.")
        return ranked[0][0], "medium", signals, warnings
    warnings.append("Customer could not be inferred unambiguously; assign it before import.")
    return "", "low" if ranked else "none", signals, warnings


def _parse_comment(value: str) -> tuple[dict[str, str] | None, int]:
    parts = value.split(";", 2)
    created = parts[0].strip() if parts else ""
    body = parts[2] if len(parts) == 3 else value
    clean, redactions = _sanitize_text(body)
    if not clean:
        return None, redactions
    return {"created": created[:80], "author": "", "body_text": clean[:12_000]}, redactions


def _attachment_filename(value: str) -> str:
    parts = value.split(";", 3)
    raw = parts[2] if len(parts) >= 3 else ""
    filename = Path(raw.replace("\\", "/")).name
    filename, _ = _sanitize_text(filename)
    return filename[:500]


def _parse_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%d/%b/%y %I:%M %p", "%d/%b/%y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
    return None


def should_skip_existing(existing_updated: datetime | None, incoming_updated: str) -> bool:
    """Skip only when the indexed Jira record is strictly newer than the CSV row."""
    incoming = _parse_datetime(incoming_updated)
    return bool(existing_updated and incoming and existing_updated > incoming)


def parse_jira_csv_bytes(data: bytes, filename: str) -> ParsedCsvFile:
    if not filename.lower().endswith(".csv"):
        raise ValueError("Only .csv Jira exports are accepted")
    if not data:
        raise ValueError("CSV file is empty")
    if len(data) > MAX_CSV_BYTES:
        raise ValueError(f"CSV file exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV file has no header row") from exc
    missing = sorted(REQUIRED_HEADERS - set(headers))
    if missing:
        raise ValueError("Missing required Jira columns: " + ", ".join(missing))

    positions: dict[str, list[int]] = defaultdict(list)
    for index, header in enumerate(headers):
        positions[header].append(index)
    duplicate_headers = {key: len(indexes) for key, indexes in positions.items() if len(indexes) > 1}

    issues: list[ParsedCsvIssue] = []
    resolution_counts: Counter[str] = Counter()
    total_redactions = 0
    seen_keys: set[str] = set()

    def values(row: list[str], header: str) -> list[str]:
        return [row[index].strip() for index in positions.get(header, []) if index < len(row) and row[index].strip()]

    def first(row: list[str], header: str) -> str:
        found = values(row, header)
        return found[0] if found else ""

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise ValueError(f"CSV exceeds the {MAX_CSV_ROWS} row limit")
    for row_number, row in enumerate(rows, start=2):
        if len(row) != len(headers):
            raise ValueError(f"Row {row_number} has {len(row)} columns; expected {len(headers)}")
        issue_key = first(row, "Issue key").upper()
        if not _JIRA_KEY_RE.match(issue_key):
            raise ValueError(f"Row {row_number} has an invalid Issue key")
        if issue_key in seen_keys:
            raise ValueError(f"Duplicate Issue key in CSV: {issue_key}")
        seen_keys.add(issue_key)

        redactions = 0
        sanitized: dict[str, str] = {}
        for name in (
            "Summary",
            "Description",
            "Environment",
            "Custom field (Acceptance Criteria)",
            "Custom field (Root Cause)",
            "Custom field (Test Plan)",
        ):
            sanitized[name], count = _sanitize_text(first(row, name))
            redactions += count

        labels = _dedupe(values(row, "Labels"))
        components = _dedupe(values(row, "Component/s"))
        fix_versions = _dedupe(values(row, "Fix Version/s"))
        affected_versions = _dedupe(values(row, "Affects Version/s"))
        customer_names, customer_redactions = _safe_customer_values(
            values(row, "Custom field (Customer Names)")
            + values(row, "Custom field (Customers)")
            + values(row, "Custom field (Beta Customer Name)")
        )
        company_names, company_redactions = _safe_customer_values(
            values(row, "Custom field (Company)") + values(row, "Company")
        )
        redactions += customer_redactions + company_redactions
        row_customer_cohorts = _dedupe(
            [
                customer
                for customer in (
                    [_CUSTOMER_LABELS.get(str(label).strip().casefold(), "") for label in labels]
                    + [_canonical_customer(value) for value in customer_names + company_names]
                )
                if customer in _SUPPORTED_CUSTOMERS
            ],
            limit=20,
        )

        comments: list[dict[str, str]] = []
        for raw_comment in values(row, "Comment"):
            comment, count = _parse_comment(raw_comment)
            redactions += count
            if comment:
                comments.append(comment)

        attachment_filenames = _dedupe(
            [_attachment_filename(raw) for raw in values(row, "Attachment")],
            limit=100,
        )
        linked_refs: list[str] = []
        for header, indexes in positions.items():
            if not _LINK_HEADER_RE.search(header):
                continue
            relation = header.replace("Inward issue link", "inward").replace("Outward issue link", "outward")
            for index in indexes:
                raw = row[index].strip()
                for linked_key in re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", raw.upper()):
                    linked_refs.append(f"{relation}: {linked_key}")

        resolution = first(row, "Resolution")
        resolution_counts[resolution or "Unspecified"] += 1
        description = sanitized["Description"]
        if sanitized["Environment"]:
            description = f"{description}\n\nEnvironment:\n{sanitized['Environment']}".strip()

        fields = {
            "summary": sanitized["Summary"],
            "description": description,
            "issuetype": {"name": first(row, "Issue Type")},
            "status": {"name": first(row, "Status")},
            "priority": {"name": first(row, "Priority")},
            "labels": labels,
            "components": [{"name": item} for item in components],
            "fixVersions": [{"name": item} for item in fix_versions],
            "versions": [{"name": item} for item in affected_versions],
            "created": first(row, "Created"),
            "updated": first(row, "Updated"),
            "resolutiondate": first(row, "Resolved"),
            "customfield_13400": sanitized["Custom field (Acceptance Criteria)"],
            "_csv_resolution": resolution,
            "_source_type": "jira_csv",
            "_source_file_hash": hashlib.sha256(data).hexdigest(),
        }
        issues.append(
            ParsedCsvIssue(
                issue_key=issue_key,
                issue={"key": issue_key, "fields": fields},
                comments=comments,
                acceptance_criteria=sanitized["Custom field (Acceptance Criteria)"],
                root_cause=sanitized["Custom field (Root Cause)"],
                test_plan=sanitized["Custom field (Test Plan)"],
                resolution=resolution,
                jira_updated_at=first(row, "Updated"),
                company_names=company_names,
                customer_names=customer_names,
                customer_cohorts=row_customer_cohorts,
                resolutions=[resolution] if resolution else [],
                source_file_hashes=[hashlib.sha256(data).hexdigest()],
                import_provenance=[
                    {
                        "filename": Path(filename).name,
                        "file_hash": hashlib.sha256(data).hexdigest(),
                        "jira_updated_at": first(row, "Updated")[:80],
                    }
                ],
                evidence_archive={
                    "acceptance_criteria": [sanitized["Custom field (Acceptance Criteria)"]]
                    if sanitized["Custom field (Acceptance Criteria)"] else [],
                    "root_causes": [sanitized["Custom field (Root Cause)"]]
                    if sanitized["Custom field (Root Cause)"] else [],
                    "test_plans": [sanitized["Custom field (Test Plan)"]]
                    if sanitized["Custom field (Test Plan)"] else [],
                    "comments": [comment["body_text"] for comment in comments if comment.get("body_text")],
                    "linked_issue_refs": _dedupe(linked_refs, limit=200),
                    "attachment_filenames": attachment_filenames,
                },
                linked_issue_refs=_dedupe(linked_refs, limit=200),
                attachment_filenames=attachment_filenames,
                redacted_fields=redactions,
            )
        )
        total_redactions += redactions

    parsed_file = ParsedCsvFile(
        filename=Path(filename).name,
        file_hash=hashlib.sha256(data).hexdigest(),
        headers=headers,
        issues=issues,
        duplicate_headers=duplicate_headers,
        resolution_counts=dict(resolution_counts),
        redacted_fields=total_redactions,
    )
    detected, confidence, signals, warnings = _detect_file_customer(parsed_file)
    parsed_file.detected_customer = detected
    parsed_file.detection_confidence = confidence
    parsed_file.detection_signals = signals
    parsed_file.detection_warnings = warnings
    return parsed_file


def _normalize_customer_assignments(
    parsed: list[ParsedCsvFile], assignments: dict[str, str] | None
) -> dict[str, str]:
    supplied = assignments or {}
    normalized: dict[str, str] = {}
    for item in parsed:
        raw = supplied.get(item.file_hash, item.detected_customer)
        if str(raw).strip() == _MIXED_CUSTOMER:
            normalized[item.file_hash] = _MIXED_CUSTOMER
            continue
        customer = _canonical_customer(raw)
        if customer not in _SUPPORTED_CUSTOMERS:
            customer = ""
        normalized[item.file_hash] = customer
    return normalized


def _issue_richness(issue: ParsedCsvIssue) -> tuple[int, str]:
    fields = issue.issue.get("fields") or {}
    score = sum(len(str(fields.get(key) or "")) for key in ("summary", "description", "customfield_13400"))
    score += sum(len(values) for values in (issue.comments, issue.linked_issue_refs, issue.attachment_filenames)) * 100
    return score, issue.import_provenance[0].get("file_hash", "") if issue.import_provenance else ""


def merge_parsed_issues(
    parsed_files: list[ParsedCsvFile], assignments: dict[str, str] | None = None
) -> list[ParsedCsvIssue]:
    """Merge cross-file snapshots while retaining every safe customer association and evidence signal."""
    assignment_map = _normalize_customer_assignments(parsed_files, assignments)
    grouped: dict[str, list[ParsedCsvIssue]] = defaultdict(list)
    for parsed_file in parsed_files:
        cohort = assignment_map.get(parsed_file.file_hash, "")
        if cohort == _MIXED_CUSTOMER:
            cohort = ""
        for issue in parsed_file.issues:
            grouped[issue.issue_key].append(
                replace(
                    issue,
                    customer_cohorts=_dedupe(
                        issue.customer_cohorts + ([cohort] if cohort else []),
                        limit=20,
                    ),
                )
            )

    merged: list[ParsedCsvIssue] = []
    for issue_key in sorted(grouped):
        snapshots = grouped[issue_key]
        winner = max(
            snapshots,
            key=lambda item: (_parse_datetime(item.jira_updated_at) or datetime.min, *_issue_richness(item)),
        )
        output = replace(winner, issue=copy.deepcopy(winner.issue), comments=list(winner.comments))
        fields = output.issue.setdefault("fields", {})

        def union(attr: str, limit: int = 200) -> list[str]:
            return _dedupe([value for snapshot in snapshots for value in getattr(snapshot, attr)], limit=limit)

        def field_union(key: str, object_values: bool = False) -> list[Any]:
            values: list[str] = []
            for snapshot in snapshots:
                raw_values = snapshot.issue.get("fields", {}).get(key) or []
                for value in raw_values:
                    values.append(str(value.get("name") or "") if object_values and isinstance(value, dict) else str(value))
            clean = _dedupe(values)
            return [{"name": value} for value in clean] if object_values else clean

        fields["labels"] = field_union("labels")
        fields["components"] = field_union("components", object_values=True)
        fields["fixVersions"] = field_union("fixVersions", object_values=True)
        fields["versions"] = field_union("versions", object_values=True)
        output.company_names = union("company_names", 100)
        output.customer_names = union("customer_names", 100)
        output.customer_cohorts = union("customer_cohorts", 20)
        output.resolutions = union("resolutions", 50)
        output.source_file_hashes = union("source_file_hashes", 50)
        output.linked_issue_refs = union("linked_issue_refs")
        output.attachment_filenames = union("attachment_filenames", 100)
        output.comments = list(
            {
                (comment.get("created", ""), comment.get("body_text", "")): comment
                for snapshot in snapshots
                for comment in snapshot.comments
            }.values()
        )[:40]
        provenance_seen: set[tuple[str, str]] = set()
        output.import_provenance = []
        for snapshot in snapshots:
            for entry in snapshot.import_provenance:
                key = (entry.get("file_hash", ""), entry.get("jira_updated_at", ""))
                if key not in provenance_seen:
                    provenance_seen.add(key)
                    output.import_provenance.append(entry)
        archive_keys = {
            key for snapshot in snapshots for key in snapshot.evidence_archive
        }
        output.evidence_archive = {
            key: _dedupe(
                [value for snapshot in snapshots for value in snapshot.evidence_archive.get(key, [])],
                limit=200,
            )
            for key in sorted(archive_keys)
        }
        output.redacted_fields = sum(snapshot.redacted_fields for snapshot in snapshots)
        merged.append(output)
    return merged


def preview_jira_csv_files(
    files: list[tuple[str, bytes]], customer_assignments: dict[str, str] | None = None
) -> dict[str, Any]:
    parsed = [parse_jira_csv_bytes(data, filename) for filename, data in files]
    keys = [issue.issue_key for item in parsed for issue in item.issues]
    duplicate_keys = sorted(key for key, count in Counter(keys).items() if count > 1)
    assignment_map = _normalize_customer_assignments(parsed, customer_assignments)
    completed_hashes = _completed_file_hashes()
    return {
        "valid": all(assignment_map.values()),
        "importer_version": IMPORTER_VERSION,
        "total_files": len(parsed),
        "total_rows": len(keys),
        "unique_issue_keys": len(set(keys)),
        "overlap_count": len(keys) - len(set(keys)),
        "overlapping_issue_keys": duplicate_keys,
        "redacted_fields": sum(item.redacted_fields for item in parsed),
        "files": [
            {
                "filename": item.filename,
                "file_hash": item.file_hash,
                "rows": len(item.issues),
                "columns": len(item.headers),
                "duplicate_headers": item.duplicate_headers,
                "resolution_counts": item.resolution_counts,
                "already_imported": item.file_hash in completed_hashes,
                "detected_customer": item.detected_customer,
                "assigned_customer": assignment_map.get(item.file_hash, ""),
                "customer_confidence": item.detection_confidence,
                "customer_evidence_signals": item.detection_signals or [],
                "warnings": item.detection_warnings or [],
            }
            for item in parsed
        ],
    }


def _completed_file_hashes(*, exclude_run_id: str = "") -> set[str]:
    db = SessionLocal()
    try:
        rows = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.status == "completed").all()
        return {
            str(file_hash)
            for row in rows
            if row.id != exclude_run_id and str(row.importer_version or "1") == IMPORTER_VERSION
            for file_hash in (row.file_hashes or [])
            if file_hash
        }
    finally:
        db.close()


def create_import_run(
    files: list[tuple[str, bytes]], *, created_by: str, customer_assignments: dict[str, str] | None = None
) -> tuple[str, list[Path]]:
    preview = preview_jira_csv_files(files, customer_assignments)
    if not preview["valid"]:
        raise ValueError("Confirm a supported customer assignment for every file")
    run_id = str(uuid.uuid4())
    import_dir = Path(__file__).resolve().parents[2] / "storage" / "jira_csv_imports" / run_id
    import_dir.mkdir(parents=True, exist_ok=False)
    paths: list[Path] = []
    for index, (filename, data) in enumerate(files):
        path = import_dir / f"{index:03d}-{Path(filename).name}"
        path.write_bytes(data)
        paths.append(path)
    db = SessionLocal()
    try:
        db.add(
            JiraCsvImportRun(
                id=run_id,
                status="pending",
                filenames=[item["filename"] for item in preview["files"]],
                file_hashes=[item["file_hash"] for item in preview["files"]],
                importer_version=IMPORTER_VERSION,
                customer_assignments={item["file_hash"]: item["assigned_customer"] for item in preview["files"]},
                total_rows=int(preview["total_rows"]),
                redacted_fields=int(preview["redacted_fields"]),
                created_by=created_by[:120],
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        import_dir.rmdir()
        raise
    finally:
        db.close()
    return run_id, paths


def get_import_run(run_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
        if row is None:
            return None
        percent = 100 if row.status == "completed" else int((row.processed_rows / row.total_rows) * 100) if row.total_rows else 0
        return {
            "import_id": row.id,
            "status": row.status,
            "filenames": row.filenames or [],
            "file_hashes": row.file_hashes or [],
            "importer_version": row.importer_version,
            "customer_assignments": row.customer_assignments or {},
            "profile_rebuild": row.profile_rebuild or {},
            "total_rows": row.total_rows,
            "processed_rows": row.processed_rows,
            "indexed_issues": row.indexed_issues,
            "skipped_issues": row.skipped_issues,
            "metadata_merged_issues": row.metadata_merged_issues,
            "failed_issues": row.failed_issues,
            "chunks_indexed": row.chunks_indexed,
            "redacted_fields": row.redacted_fields,
            "errors": row.errors or [],
            "progress_percent": max(0, min(100, percent)),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
    finally:
        db.close()


def _set_run(run_id: str, **changes: Any) -> None:
    db = SessionLocal()
    try:
        row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
        if row is None:
            return
        for key, value in changes.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def _union_values(existing: Any, incoming: list[str], *, limit: int = 200) -> list[str]:
    current = existing if isinstance(existing, list) else []
    return _dedupe([str(value) for value in current] + incoming, limit=limit)


def _metadata_only_merge(parsed_issue: ParsedCsvIssue) -> bool:
    """Union cohort/provenance evidence into a newer SQL/Chroma issue without replacing its content."""
    db = SessionLocal()
    try:
        row = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == parsed_issue.issue_key).first()
        if row is None:
            return False
        row.company_names = _union_values(row.company_names, parsed_issue.company_names, limit=100)
        row.customer_names = _union_values(row.customer_names, parsed_issue.customer_names, limit=100)
        row.customer_cohorts = _union_values(row.customer_cohorts, parsed_issue.customer_cohorts, limit=20)
        row.components = _union_values(
            row.components,
            [str(item.get("name") or "") for item in parsed_issue.issue.get("fields", {}).get("components", [])],
        )
        row.resolutions = _union_values(row.resolutions, parsed_issue.resolutions, limit=50)
        row.source_file_hashes = _union_values(row.source_file_hashes, parsed_issue.source_file_hashes, limit=50)
        provenance = list(row.import_provenance or [])
        seen = {(str(item.get("file_hash") or ""), str(item.get("jira_updated_at") or "")) for item in provenance}
        for item in parsed_issue.import_provenance:
            key = (item.get("file_hash", ""), item.get("jira_updated_at", ""))
            if key not in seen:
                seen.add(key)
                provenance.append(item)
        row.import_provenance = provenance[:100]
        archive = dict(row.evidence_archive or {})
        for key, values in parsed_issue.evidence_archive.items():
            archive[key] = _union_values(archive.get(key), values, limit=200)
        row.evidence_archive = archive
        row.updated_at = datetime.utcnow()
        db.query(JiraIssueChunk).filter(JiraIssueChunk.jira_key == parsed_issue.issue_key).update(
            {JiraIssueChunk.customer_names: row.customer_names}, synchronize_session=False
        )
        db.commit()
        update_documents_metadata(
            CHROMA_COLLECTION_JIRA_QA,
            {"jira_key": parsed_issue.issue_key},
            {
                "enrich_customers": json.dumps(row.customer_names, ensure_ascii=False)[:4000],
                "company_names": json.dumps(row.company_names, ensure_ascii=False)[:4000],
                "customer_cohorts": json.dumps(row.customer_cohorts, ensure_ascii=False)[:4000],
                "resolutions": json.dumps(row.resolutions, ensure_ascii=False)[:4000],
                "source_file_hashes": json.dumps(row.source_file_hashes, ensure_ascii=False)[:4000],
                "metadata_only_merge": True,
                "import_evidence_archive": json.dumps(row.evidence_archive, ensure_ascii=False)[:4000],
            },
        )
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _flush_issue_batch(
    batch: list[tuple[ParsedCsvIssue, Any, list[dict[str, Any]]]],
) -> tuple[int, int, list[str]]:
    rows = [chunk for _, _, chunks in batch for chunk in chunks]
    if not rows:
        return 0, 0, []
    embeddings = embed_texts_batched([row["document"] for row in rows], batch_size=48)
    if embeddings is None:
        return 0, 0, [f"{item.issue_key}: embedding batch failed" for item, _, _ in batch]
    ids = [row["chunk_id"] for row in rows]
    metadata = [
        {key: value for key, value in row["metadata"].items() if isinstance(value, (str, int, float, bool))}
        for row in rows
    ]
    vectors = [embeddings[index].tolist() for index in range(len(ids))]
    chroma_ok = False
    for attempt in range(1, 4):
        chroma_ok = add_documents(
            CHROMA_COLLECTION_JIRA_QA,
            ids,
            [row["document"] for row in rows],
            metadata,
            vectors,
        )
        if chroma_ok:
            break
        if attempt < 3:
            time.sleep(0.5 * attempt)
    if not chroma_ok:
        return 0, 0, [f"{item.issue_key}: Chroma upsert failed" for item, _, _ in batch]

    errors: list[str] = []
    persisted = 0
    db = SessionLocal()
    try:
        for parsed_issue, enriched, chunks in batch:
            try:
                upsert_jira_issue(db, enriched)
                insert_jira_chunks(db, parsed_issue.issue_key, chunks, enrichment=enriched)
                db.commit()
                persisted += len(chunks)
            except Exception as exc:
                db.rollback()
                delete_documents(CHROMA_COLLECTION_JIRA_QA, [chunk["chunk_id"] for chunk in chunks])
                errors.append(f"{parsed_issue.issue_key}: SQL persistence failed: {exc}")
    finally:
        db.close()
    return persisted, len(batch) - len(errors), errors


def run_import(run_id: str, paths: list[Path]) -> None:
    errors: list[str] = []
    processed = indexed = skipped = metadata_merged = failed = chunks_indexed = 0
    import_dir = paths[0].parent if paths else None
    try:
        if not is_chroma_available():
            raise RuntimeError("ChromaDB is not available")
        if not is_embedding_available():
            raise RuntimeError("Embedding model is not available")
        _set_run(run_id, status="running", started_at=datetime.utcnow())
        completed_hashes = _completed_file_hashes(exclude_run_id=run_id)
        db = SessionLocal()
        try:
            run_row = db.query(JiraCsvImportRun).filter(JiraCsvImportRun.id == run_id).first()
            customer_assignments = dict(run_row.customer_assignments or {}) if run_row else {}
        finally:
            db.close()
        parsed_files = [parse_jira_csv_bytes(path.read_bytes(), path.name.split("-", 1)[-1]) for path in paths]
        import_files = [item for item in parsed_files if item.file_hash not in completed_hashes]
        for item in parsed_files:
            if item.file_hash in completed_hashes:
                skipped += len(item.issues)
                processed += len(item.issues)
        merged_issues = merge_parsed_issues(import_files, customer_assignments)
        batch: list[tuple[ParsedCsvIssue, Any, list[dict[str, Any]]]] = []

        def flush() -> None:
            nonlocal chunks_indexed, indexed, failed, batch
            count, persisted_issues, batch_errors = _flush_issue_batch(batch)
            chunks_indexed += count
            indexed += persisted_issues
            failed += len(batch_errors)
            errors.extend(batch_errors)
            batch = []

        for parsed_issue in merged_issues:
                source_row_count = max(1, len(parsed_issue.import_provenance))
                db = SessionLocal()
                try:
                    existing = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == parsed_issue.issue_key).first()
                    existing_updated = existing.jira_updated_at if existing else None
                    existing_metadata = {
                        "components": list(existing.components or []),
                        "company_names": list(existing.company_names or []),
                        "customer_names": list(existing.customer_names or []),
                        "customer_cohorts": list(existing.customer_cohorts or []),
                        "resolutions": list(existing.resolutions or []),
                        "source_file_hashes": list(existing.source_file_hashes or []),
                        "import_provenance": list(existing.import_provenance or []),
                        "evidence_archive": dict(existing.evidence_archive or {}),
                    } if existing else {}
                finally:
                    db.close()
                if should_skip_existing(existing_updated, parsed_issue.jira_updated_at):
                    try:
                        if _metadata_only_merge(parsed_issue):
                            metadata_merged += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        failed += 1
                        errors.append(f"{parsed_issue.issue_key}: metadata-only merge failed: {exc}")
                    processed += source_row_count
                    continue
                try:
                    enriched = enrich_jira(parsed_issue.issue)
                    existing_provenance = existing_metadata.get("import_provenance", [])
                    provenance = list(existing_provenance)
                    seen_provenance = {
                        (str(item.get("file_hash") or ""), str(item.get("jira_updated_at") or ""))
                        for item in provenance if isinstance(item, dict)
                    }
                    for item in parsed_issue.import_provenance:
                        key = (item.get("file_hash", ""), item.get("jira_updated_at", ""))
                        if key not in seen_provenance:
                            seen_provenance.add(key)
                            provenance.append(item)
                    evidence_archive = dict(existing_metadata.get("evidence_archive") or {})
                    for key, values in parsed_issue.evidence_archive.items():
                        evidence_archive[key] = _union_values(evidence_archive.get(key), values, limit=200)
                    enriched = enriched.model_copy(
                        update={
                            "resolution": parsed_issue.resolution,
                            "resolutions": _union_values(existing_metadata.get("resolutions"), parsed_issue.resolutions, limit=50),
                            "jira_updated_at": parsed_issue.jira_updated_at,
                            "source_type": "jira_csv",
                            "source_file_hash": parsed_issue.source_file_hashes[0] if parsed_issue.source_file_hashes else "",
                            "source_file_hashes": _union_values(
                                existing_metadata.get("source_file_hashes"), parsed_issue.source_file_hashes, limit=50
                            ),
                            "import_provenance": provenance[:100],
                            "evidence_archive": evidence_archive,
                            "acceptance_criteria": parsed_issue.acceptance_criteria,
                            "root_cause": parsed_issue.root_cause,
                            "test_plan": parsed_issue.test_plan,
                            "linked_issue_refs": parsed_issue.linked_issue_refs,
                            "attachment_filenames": parsed_issue.attachment_filenames,
                            "comments_digest": build_comments_digest(parsed_issue.comments),
                            "components": _union_values(
                                existing_metadata.get("components"), list(enriched.components or []), limit=200
                            ),
                            "company_names": _union_values(
                                existing_metadata.get("company_names"), parsed_issue.company_names, limit=100
                            ),
                            "customer_names": _union_values(
                                existing_metadata.get("customer_names"),
                                parsed_issue.customer_names + parsed_issue.customer_cohorts + list(enriched.customer_names or []),
                                limit=100,
                            ),
                            "customer_cohorts": _union_values(
                                existing_metadata.get("customer_cohorts"), parsed_issue.customer_cohorts, limit=20
                            ),
                        }
                    )
                    chunks = build_jira_qa_chunks(
                        parsed_issue.issue_key,
                        parsed_issue.issue,
                        comments=parsed_issue.comments,
                        linked_issues=[],
                        enriched=enriched,
                    )
                    batch.append((parsed_issue, enriched, chunks))
                except Exception as exc:
                    failed += 1
                    errors.append(f"{parsed_issue.issue_key}: {exc}")
                processed += source_row_count
                if len(batch) >= 24:
                    flush()
                _set_run(
                    run_id,
                    processed_rows=processed,
                    indexed_issues=indexed,
                    skipped_issues=skipped,
                    metadata_merged_issues=metadata_merged,
                    failed_issues=failed,
                    chunks_indexed=chunks_indexed,
                    errors=errors[:100],
                )
        if batch:
            flush()
        affected_customers = sorted(
            {
                customer
                for issue in merged_issues
                for customer in issue.customer_cohorts
                if customer
            }
        )
        profile_rebuild: dict[str, Any] = {}
        if affected_customers and failed == 0:
            try:
                from app.services.jira_customer_profile_service import rebuild_customer_profiles

                profile_rebuild = rebuild_customer_profiles(affected_customers)
                profile_failures = [
                    customer
                    for customer, result in (profile_rebuild.get("profiles") or {}).items()
                    if result.get("status") != "completed"
                ]
                if profile_failures:
                    errors.append("Customer profile rebuild failed for: " + ", ".join(profile_failures))
                    failed += len(profile_failures)
            except Exception as exc:
                errors.append(f"Customer profile rebuild failed: {exc}")
                profile_rebuild = {"status": "failed", "error": str(exc)}
                failed += 1
        final_status = "completed" if failed == 0 else "completed_with_errors"
        _set_run(
            run_id,
            status=final_status,
            processed_rows=processed,
            indexed_issues=indexed,
            skipped_issues=skipped,
            metadata_merged_issues=metadata_merged,
            failed_issues=failed,
            chunks_indexed=chunks_indexed,
            errors=errors[:100],
            profile_rebuild=profile_rebuild,
            completed_at=datetime.utcnow(),
        )
    except Exception as exc:
        errors.append(str(exc))
        _set_run(run_id, status="failed", failed_issues=max(failed, 1), errors=errors[:100], completed_at=datetime.utcnow())
        logger.error_structured("jira_csv_import_failed", extra_fields={"import_id": run_id, "error": str(exc)})
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        if import_dir and import_dir.exists():
            try:
                import_dir.rmdir()
            except OSError:
                pass


def start_import(run_id: str, paths: list[Path]) -> None:
    async def runner() -> None:
        await asyncio.to_thread(run_import, run_id, paths)

    task = asyncio.create_task(runner(), name=f"jira-csv-import-{run_id}")
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)
