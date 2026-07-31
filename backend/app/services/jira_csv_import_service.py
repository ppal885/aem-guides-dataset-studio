"""Admin Jira CSV preview and asynchronous SQL/Chroma ingestion."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.db.jira_enrichment_models import JiraCsvImportRun, JiraEnrichedIssue
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
)

logger = get_structured_logger(__name__)

MAX_CSV_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 10_000
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
    customer_names: list[str]
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
        customer_names = _dedupe(
            values(row, "Custom field (Customer Names)")
            + values(row, "Custom field (Customers)")
            + values(row, "Custom field (Beta Customer Name)")
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
                customer_names=customer_names,
                linked_issue_refs=_dedupe(linked_refs, limit=200),
                attachment_filenames=attachment_filenames,
                redacted_fields=redactions,
            )
        )
        total_redactions += redactions

    return ParsedCsvFile(
        filename=Path(filename).name,
        file_hash=hashlib.sha256(data).hexdigest(),
        headers=headers,
        issues=issues,
        duplicate_headers=duplicate_headers,
        resolution_counts=dict(resolution_counts),
        redacted_fields=total_redactions,
    )


def preview_jira_csv_files(files: list[tuple[str, bytes]]) -> dict[str, Any]:
    parsed = [parse_jira_csv_bytes(data, filename) for filename, data in files]
    keys = [issue.issue_key for item in parsed for issue in item.issues]
    duplicate_keys = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicate_keys:
        raise ValueError("Duplicate Jira keys across uploaded files: " + ", ".join(duplicate_keys[:20]))
    completed_hashes = _completed_file_hashes()
    return {
        "valid": True,
        "total_files": len(parsed),
        "total_rows": len(keys),
        "unique_issue_keys": len(set(keys)),
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
            if row.id != exclude_run_id
            for file_hash in (row.file_hashes or [])
            if file_hash
        }
    finally:
        db.close()


def create_import_run(files: list[tuple[str, bytes]], *, created_by: str) -> tuple[str, list[Path]]:
    preview = preview_jira_csv_files(files)
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
            "total_rows": row.total_rows,
            "processed_rows": row.processed_rows,
            "indexed_issues": row.indexed_issues,
            "skipped_issues": row.skipped_issues,
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
    processed = indexed = skipped = failed = chunks_indexed = 0
    import_dir = paths[0].parent if paths else None
    try:
        if not is_chroma_available():
            raise RuntimeError("ChromaDB is not available")
        if not is_embedding_available():
            raise RuntimeError("Embedding model is not available")
        _set_run(run_id, status="running", started_at=datetime.utcnow())
        completed_hashes = _completed_file_hashes(exclude_run_id=run_id)
        parsed_files = [parse_jira_csv_bytes(path.read_bytes(), path.name.split("-", 1)[-1]) for path in paths]
        batch: list[tuple[ParsedCsvIssue, Any, list[dict[str, Any]]]] = []

        def flush() -> None:
            nonlocal chunks_indexed, indexed, failed, batch
            count, persisted_issues, batch_errors = _flush_issue_batch(batch)
            chunks_indexed += count
            indexed += persisted_issues
            failed += len(batch_errors)
            errors.extend(batch_errors)
            batch = []

        for parsed_file in parsed_files:
            if parsed_file.file_hash in completed_hashes:
                skipped += len(parsed_file.issues)
                processed += len(parsed_file.issues)
                continue
            for parsed_issue in parsed_file.issues:
                db = SessionLocal()
                try:
                    existing = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key == parsed_issue.issue_key).first()
                    existing_updated = existing.jira_updated_at if existing else None
                finally:
                    db.close()
                if should_skip_existing(existing_updated, parsed_issue.jira_updated_at):
                    skipped += 1
                    processed += 1
                    continue
                try:
                    enriched = enrich_jira(parsed_issue.issue)
                    enriched = enriched.model_copy(
                        update={
                            "resolution": parsed_issue.resolution,
                            "jira_updated_at": parsed_issue.jira_updated_at,
                            "source_type": "jira_csv",
                            "source_file_hash": parsed_file.file_hash,
                            "acceptance_criteria": parsed_issue.acceptance_criteria,
                            "root_cause": parsed_issue.root_cause,
                            "test_plan": parsed_issue.test_plan,
                            "linked_issue_refs": parsed_issue.linked_issue_refs,
                            "attachment_filenames": parsed_issue.attachment_filenames,
                            "comments_digest": build_comments_digest(parsed_issue.comments),
                            "customer_names": parsed_issue.customer_names or enriched.customer_names,
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
                processed += 1
                if len(batch) >= 24:
                    flush()
                _set_run(
                    run_id,
                    processed_rows=processed,
                    indexed_issues=indexed,
                    skipped_issues=skipped,
                    failed_issues=failed,
                    chunks_indexed=chunks_indexed,
                    errors=errors[:100],
                )
        if batch:
            flush()
        final_status = "completed" if failed == 0 else "completed_with_errors"
        _set_run(
            run_id,
            status=final_status,
            processed_rows=processed,
            indexed_issues=indexed,
            skipped_issues=skipped,
            failed_issues=failed,
            chunks_indexed=chunks_indexed,
            errors=errors[:100],
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
