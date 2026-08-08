"""Canonical Jira component metadata for Chroma filtering and migration."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_records,
    update_document_metadatas,
)


COMPONENT_FILTER_SCHEMA_VERSION = 2
CANONICAL_JIRA_COMPONENTS = (
    "Editor",
    "Authoring",
    "Publishing",
    "Platform",
    "Schematron",
    "Integration",
)
_CANONICAL_COMPONENT_BY_TOKEN = {
    component.casefold(): component for component in CANONICAL_JIRA_COMPONENTS
}


def canonical_component_name(value: str) -> str:
    """Return the canonical Jira component display name or an empty string."""
    token = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    return _CANONICAL_COMPONENT_BY_TOKEN.get(token, "")


def normalize_component_token(value: str) -> str:
    """Return a canonical lowercase token for exact Chroma filtering."""
    canonical = canonical_component_name(value)
    return canonical.casefold() if canonical else ""


def canonical_component_names(components: list[str]) -> list[str]:
    """Return unique canonical Jira component names in source order."""
    seen: set[str] = set()
    canonical: list[str] = []
    for component in components or []:
        name = canonical_component_name(component)
        token = name.casefold()
        if not name or token in seen:
            continue
        seen.add(token)
        canonical.append(name)
    return canonical


def component_primary_from_names(components: list[str]) -> str:
    """Return the normalized primary component from Jira's ordered component list."""
    canonical = canonical_component_names(components)
    return canonical[0].casefold() if canonical else ""


def component_primary_from_metadata(metadata: dict[str, Any]) -> str:
    """Derive component_primary from the ordered component list, then its scalar fallback."""
    raw = metadata.get("components")
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        values = []
    if isinstance(values, list):
        derived = component_primary_from_names([str(value) for value in values if value])
        if derived:
            return derived
    return normalize_component_token(str(metadata.get("component_primary") or ""))


def _metadata_list(value: Any) -> list[str]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item).strip() for item in decoded if str(item or "").strip()]


def _dedupe_source_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "").strip())
        token = clean.casefold()
        if not clean or token in seen:
            continue
        seen.add(token)
        output.append(clean)
    return output


def migrate_jira_component_primary(*, dry_run: bool = False, batch_size: int = 500) -> dict[str, Any]:
    """Canonicalize component metadata without Jira access or re-embedding."""
    records = get_collection_records(CHROMA_COLLECTION_JIRA_QA)
    pending: list[tuple[str, dict[str, Any]]] = []
    unchanged = 0
    without_component = 0
    noncanonical_component_records = 0
    canonicalized_component_records = 0
    raw_component_metadata_added = 0
    canonical_record_counts: dict[str, int] = {
        component: 0 for component in CANONICAL_JIRA_COMPONENTS
    }

    for record in records:
        metadata = dict(record.get("metadata") or {})
        active_values = _metadata_list(metadata.get("components"))
        preserved_values = _metadata_list(metadata.get("components_raw"))
        raw_values = _dedupe_source_values(preserved_values + active_values)
        canonical_values = canonical_component_names(active_values + preserved_values)
        if not canonical_values:
            scalar = canonical_component_name(str(metadata.get("component_primary") or ""))
            if scalar:
                canonical_values = [scalar]
                raw_values = _dedupe_source_values(raw_values + [scalar])
        primary = component_primary_from_names(canonical_values)
        canonical_json = json.dumps(canonical_values, ensure_ascii=False)
        raw_json = json.dumps(raw_values, ensure_ascii=False)
        if not primary:
            without_component += 1
        else:
            canonical_record_counts[_CANONICAL_COMPONENT_BY_TOKEN[primary]] += 1
        if any(not canonical_component_name(value) for value in active_values):
            noncanonical_component_records += 1
        if active_values != canonical_values:
            canonicalized_component_records += 1
        if "components_raw" not in metadata:
            raw_component_metadata_added += 1
        if (
            str(metadata.get("component_primary") or "") == primary
            and str(metadata.get("components") or "") == canonical_json
            and str(metadata.get("components_raw") or "") == raw_json
            and metadata.get("component_filter_schema_version") == COMPONENT_FILTER_SCHEMA_VERSION
        ):
            unchanged += 1
            continue
        metadata["components"] = canonical_json
        metadata["components_raw"] = raw_json
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
        "noncanonical_component_records": noncanonical_component_records,
        "canonicalized_component_records": canonicalized_component_records,
        "raw_component_metadata_added": raw_component_metadata_added,
        "canonical_component_record_counts": canonical_record_counts,
    }
