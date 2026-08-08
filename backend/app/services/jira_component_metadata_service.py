"""Scalar Jira component metadata for Chroma filtering and migration."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_records,
    update_document_metadatas,
)


COMPONENT_FILTER_SCHEMA_VERSION = 1


def normalize_component_token(value: str) -> str:
    """Normalize a Jira component name for exact, case-insensitive filtering."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def component_primary_from_names(components: list[str]) -> str:
    """Return the normalized primary component from Jira's ordered component list."""
    for component in components:
        normalized = normalize_component_token(component)
        if normalized:
            return normalized
    return ""


def component_primary_from_metadata(metadata: dict[str, Any]) -> str:
    """Derive component_primary from existing scalar or JSON-list metadata."""
    existing = normalize_component_token(str(metadata.get("component_primary") or ""))
    if existing:
        return existing
    raw = metadata.get("components")
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        values = []
    if not isinstance(values, list):
        return ""
    return component_primary_from_names([str(value) for value in values if value])


def migrate_jira_component_primary(*, dry_run: bool = False, batch_size: int = 500) -> dict[str, int | bool]:
    """Backfill scalar component metadata without Jira access or re-embedding."""
    records = get_collection_records(CHROMA_COLLECTION_JIRA_QA)
    pending: list[tuple[str, dict[str, Any]]] = []
    unchanged = 0
    without_component = 0

    for record in records:
        metadata = dict(record.get("metadata") or {})
        primary = component_primary_from_metadata(metadata)
        if not primary:
            without_component += 1
        if (
            str(metadata.get("component_primary") or "") == primary
            and metadata.get("component_filter_schema_version") == COMPONENT_FILTER_SCHEMA_VERSION
        ):
            unchanged += 1
            continue
        metadata["component_primary"] = primary
        metadata["component_filter_schema_version"] = COMPONENT_FILTER_SCHEMA_VERSION
        pending.append((str(record.get("id") or ""), metadata))

    updated = 0
    if not dry_run:
        size = max(1, batch_size)
        for start in range(0, len(pending), size):
            batch = pending[start : start + size]
            ids = [record_id for record_id, _ in batch if record_id]
            metadatas = [metadata for record_id, metadata in batch if record_id]
            if ids and not update_document_metadatas(CHROMA_COLLECTION_JIRA_QA, ids, metadatas):
                raise RuntimeError(f"component metadata migration failed at record offset {start}")
            updated += len(ids)

    return {
        "dry_run": dry_run,
        "scanned": len(records),
        "pending": len(pending),
        "updated": updated,
        "unchanged": unchanged,
        "without_component": without_component,
    }
