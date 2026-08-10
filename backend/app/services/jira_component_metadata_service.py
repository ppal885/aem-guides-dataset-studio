"""Canonical Jira component metadata for Chroma filtering and migration."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    iter_collection_records,
    update_document_metadatas,
)


COMPONENT_FILTER_SCHEMA_VERSION = 5
COMPONENT_TEXT_CLASSIFIER_VERSION = "component-text-v1"
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
_COMPONENT_ALIASES_BY_TOKEN: dict[str, tuple[str, ...]] = {
    "aem site": ("Publishing",),
    "asset management": ("Platform",),
    "baseline": ("Authoring",),
    "baseline ui": ("Authoring", "Editor"),
    "citation management": ("Authoring", "Editor"),
    "database": ("Platform",),
    "ditaval": ("Authoring", "Publishing"),
    "external data sources": ("Integration",),
    "homepage": ("Editor", "Authoring"),
    "learning": ("Authoring", "Publishing"),
    "native pdf": ("Publishing",),
    "oxygen": ("Integration", "Authoring"),
    "reports": ("Authoring", "Platform"),
    "translation": ("Integration", "Authoring"),
    "uuid migration": ("Platform",),
}
_COMPONENT_TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Schematron", re.compile(r"\bschematron\b", re.I)),
    (
        "Publishing",
        re.compile(
            r"\b(?:publish\w*|output|native\s*pdf|pdf|dita[ -]?ot|preset|map generation|"
            r"generation waiting|bookmap download|download bookmap|exportditamap|page layout|"
            r"template layout|reactor tagged|output path|fluid topics|salesforce)\b",
            re.I,
        ),
    ),
    (
        "Integration",
        re.compile(
            r"\b(?:translations?|translated|framemaker|open in fm|oxygen|salesforce|"
            r"fluid topics|html to dita|framemaker to dita|conversion|ilx|external system)\b",
            re.I,
        ),
    ),
    (
        "Editor",
        re.compile(
            r"\b(?:editor|webeditor|xml editor|author mode|spellcheck|special character|"
            r"paste|pasting|insert rows|tables?|save documents|save after|folder profile|"
            r"search bar|close unlocked topic|mathml|codeblock|merged cells|track changes|"
            r"toolbar|language variables panel|template file|schema to json)\b",
            re.I,
        ),
    ),
    (
        "Platform",
        re.compile(
            r"\b(?:pipeline|provision\w*|install\w*|package|index(?:ing)?|jvm|heap|deadlock|"
            r"dam asset|assets?|asset view|asset previous|assets ui|asset detail|repository|"
            r"uuid migration|version purge|resource resolver|user preferences|admin user|"
            r"dispatcher|api|endpoint|oak|btree|server details|cloud env|environment|deployment|"
            r"bulk move|move operation|copying dam asset|copy non-unique properties|asset move|"
            r"page properties|postprocessing|support tasks|javascript error|path browser|"
            r"projects/properties|card view|property in page)\b",
            re.I,
        ),
    ),
    (
        "Authoring",
        re.compile(
            r"\b(?:reviews?|baseline|condition|key references?|keydefs?|conrefs?|xrefs?|"
            r"doc state|topics?|map|folder profile|search|references|broken links|workflow|"
            r"elements?|attributes?|content fragments?|projects?|tasks?|notifications?|"
            r"favourites|favorites|collection|dita|document state|guides ui|image scaling|"
            r"authoring|external links|template file|schema to json)\b",
            re.I,
        ),
    ),
)


def _component_names_for_value(value: str) -> tuple[str, ...]:
    token = re.sub(r"[_-]+", " ", str(value or "").strip())
    token = re.sub(r"\s+", " ", token).casefold()
    canonical = _CANONICAL_COMPONENT_BY_TOKEN.get(token)
    if canonical:
        return (canonical,)
    return _COMPONENT_ALIASES_BY_TOKEN.get(token, ())


def canonical_component_name(value: str) -> str:
    """Return the primary canonical component for a supported raw Jira value."""
    names = _component_names_for_value(value)
    return names[0] if names else ""


def normalize_component_token(value: str) -> str:
    """Return a canonical lowercase token for exact Chroma filtering."""
    canonical = canonical_component_name(value)
    return canonical.casefold() if canonical else ""


def canonical_component_names(components: list[str]) -> list[str]:
    """Return unique canonical Jira component names in source order."""
    seen: set[str] = set()
    canonical: list[str] = []
    for component in components or []:
        for name in _component_names_for_value(component):
            token = name.casefold()
            if token in seen:
                continue
            seen.add(token)
            canonical.append(name)
    return canonical


def infer_component_names(summary: str, description: str = "") -> tuple[list[str], list[str]]:
    """Infer supporting component metadata from deterministic mechanism keywords."""
    for source, value in (("summary", summary), ("description", description)):
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if not text:
            continue
        names: list[str] = []
        signals: list[str] = []
        for component, pattern in _COMPONENT_TEXT_RULES:
            match = pattern.search(text)
            if not match:
                continue
            names.append(component)
            signals.append(f"{source}:{component.casefold()}:{match.group(0).casefold()}")
        if names:
            return canonical_component_names(names), signals
    return [], []


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


def component_filter_field(value: str) -> str:
    """Return the scalar Chroma field used to filter one canonical component."""
    token = normalize_component_token(value)
    return f"component_{token}" if token else ""


def component_filter_metadata(components: list[str]) -> dict[str, Any]:
    """Return primary plus membership flags so multi-component issues remain searchable."""
    canonical = canonical_component_names(components)
    selected = {component.casefold() for component in canonical}
    metadata: dict[str, Any] = {
        "component_primary": component_primary_from_names(canonical),
        "component_filter_schema_version": COMPONENT_FILTER_SCHEMA_VERSION,
    }
    for component in CANONICAL_JIRA_COMPONENTS:
        metadata[component_filter_field(component)] = component.casefold() in selected
    return metadata


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
    size = max(1, min(int(batch_size or 500), 5000))
    pending_ids: list[str] = []
    pending_metadatas: list[dict[str, Any]] = []
    scanned = 0
    pending = 0
    updated = 0
    unchanged = 0
    without_component = 0
    noncanonical_component_records = 0
    canonicalized_component_records = 0
    raw_component_metadata_added = 0
    canonical_record_counts: dict[str, int] = {
        component: 0 for component in CANONICAL_JIRA_COMPONENTS
    }

    def flush_pending() -> None:
        nonlocal updated
        if dry_run or not pending_ids:
            return
        offset = scanned - len(pending_ids)
        if not update_document_metadatas(
            CHROMA_COLLECTION_JIRA_QA,
            list(pending_ids),
            list(pending_metadatas),
        ):
            raise RuntimeError(f"component metadata migration failed near record offset {offset}")
        updated += len(pending_ids)
        pending_ids.clear()
        pending_metadatas.clear()

    records = iter_collection_records(
        CHROMA_COLLECTION_JIRA_QA,
        batch_size=size,
    )
    for record in records:
        scanned += 1
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
        filter_metadata = component_filter_metadata(canonical_values)
        classification_source = str(metadata.get("component_classification_source") or "")
        if not classification_source:
            classification_source = "jira_component" if canonical_values else "unclassified"
        if (
            str(metadata.get("component_primary") or "") == primary
            and str(metadata.get("components") or "") == canonical_json
            and str(metadata.get("components_raw") or "") == raw_json
            and metadata.get("component_filter_schema_version") == COMPONENT_FILTER_SCHEMA_VERSION
            and all(metadata.get(key) == value for key, value in filter_metadata.items())
            and metadata.get("component_classification_source") == classification_source
        ):
            unchanged += 1
            continue
        metadata["components"] = canonical_json
        metadata["components_raw"] = raw_json
        metadata.update(filter_metadata)
        metadata["component_classification_source"] = classification_source
        pending += 1
        record_id = str(record.get("id") or "")
        if not record_id:
            raise RuntimeError(f"component metadata migration found a record without an id at offset {scanned - 1}")
        if not dry_run:
            pending_ids.append(record_id)
            pending_metadatas.append(metadata)
            if len(pending_ids) >= size:
                flush_pending()

    flush_pending()

    return {
        "dry_run": dry_run,
        "scanned": scanned,
        "pending": pending,
        "updated": updated,
        "unchanged": unchanged,
        "without_component": without_component,
        "noncanonical_component_records": noncanonical_component_records,
        "canonicalized_component_records": canonicalized_component_records,
        "raw_component_metadata_added": raw_component_metadata_added,
        "canonical_component_record_counts": canonical_record_counts,
    }
