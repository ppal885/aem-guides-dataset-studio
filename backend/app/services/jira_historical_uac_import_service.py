"""Auditable normalization for mixed-customer historical UAC Jira exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.jira_component_metadata_service import (
    CANONICAL_JIRA_COMPONENTS,
    canonical_component_name,
)


HISTORICAL_UAC_NORMALIZATION_VERSION = "historical-uac-csv-v1"
SOURCE_COMPONENTS_HEADER = "Dataset Studio Original Component/s"
COMPONENT_ASSIGNMENT_METHOD_HEADER = "Dataset Studio Component Assignment Method"
COMPONENT_ASSIGNMENT_EVIDENCE_HEADER = "Dataset Studio Component Assignment Evidence"
SOURCE_FILE_HASH_HEADER = "Dataset Studio Source File SHA256"

_SPECIAL_HEADERS = {
    SOURCE_COMPONENTS_HEADER,
    COMPONENT_ASSIGNMENT_METHOD_HEADER,
    COMPONENT_ASSIGNMENT_EVIDENCE_HEADER,
    SOURCE_FILE_HASH_HEADER,
}
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

_LEGACY_COMPONENT_ALIASES: dict[str, tuple[str, ...]] = {
    "ai": ("Integration",),
    "asset management": ("Platform",),
    "baseline": ("Authoring",),
    "citation management": ("Authoring",),
    "database": ("Platform",),
    "ditaval": ("Authoring",),
    "external data sources": ("Integration",),
    "learning": ("Authoring",),
    "native pdf": ("Publishing",),
    "oxygen": ("Integration",),
    "reports": ("Authoring",),
    "review": ("Authoring",),
    "translation": ("Integration",),
    "uuid migration": ("Platform",),
}
_IGNORED_COMPONENT_MARKERS = {"triaged"}


@dataclass(frozen=True)
class HistoricalUacCsvNormalization:
    data: bytes
    report: dict[str, Any]


def _component_token(value: Any) -> str:
    return re.sub(r"[-_]+", " ", re.sub(r"\s+", " ", str(value or "").strip())).casefold()


def _dedupe(values: list[str]) -> list[str]:
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


def _validated_components(values: Any, *, jira_key: str) -> list[str]:
    raw_values = values if isinstance(values, list) else [values]
    components: list[str] = []
    for value in raw_values:
        canonical = canonical_component_name(str(value or ""))
        if not canonical:
            raise ValueError(
                f"{jira_key}: override must use only canonical components: "
                + ", ".join(CANONICAL_JIRA_COMPONENTS)
            )
        components.append(canonical)
    components = _dedupe(components)
    if not components:
        raise ValueError(f"{jira_key}: component override is empty")
    return components


def load_historical_uac_component_overrides(
    path: str | Path,
    *,
    source_file_hash: str,
) -> dict[str, list[str]]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Historical UAC component override manifest must be a JSON object")
    expected_hash = str(payload.get("source_file_sha256") or "").strip().casefold()
    if not _SHA256_RE.fullmatch(expected_hash):
        raise ValueError("Historical UAC component override manifest has an invalid source hash")
    if expected_hash != source_file_hash.casefold():
        raise ValueError(
            "Historical UAC component override manifest does not match the supplied CSV"
        )
    raw_assignments = payload.get("assignments")
    if not isinstance(raw_assignments, dict):
        raise ValueError("Historical UAC component override manifest lacks assignments")
    assignments: dict[str, list[str]] = {}
    for raw_key, raw_components in raw_assignments.items():
        jira_key = str(raw_key or "").strip().upper()
        if not _JIRA_KEY_RE.fullmatch(jira_key):
            raise ValueError(f"Invalid Jira key in component override manifest: {raw_key}")
        assignments[jira_key] = _validated_components(raw_components, jira_key=jira_key)
    return assignments


def _map_source_components(values: list[str]) -> tuple[list[str], list[str], list[str]]:
    canonical: list[str] = []
    unresolved: list[str] = []
    ignored: list[str] = []
    for value in values:
        direct = canonical_component_name(value)
        if direct:
            canonical.append(direct)
            continue
        token = _component_token(value)
        aliases = _LEGACY_COMPONENT_ALIASES.get(token)
        if aliases:
            canonical.extend(aliases)
        elif token in _IGNORED_COMPONENT_MARKERS:
            ignored.append(value)
        else:
            unresolved.append(value)
    return _dedupe(canonical), _dedupe(unresolved), _dedupe(ignored)


def normalize_historical_uac_csv_bytes(
    data: bytes,
    filename: str,
    *,
    component_overrides: dict[str, list[str]] | None = None,
) -> HistoricalUacCsvNormalization:
    if not str(filename or "").lower().endswith(".csv"):
        raise ValueError("Only .csv Jira exports are accepted")
    if not data:
        raise ValueError("CSV file is empty")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    source_file_hash = hashlib.sha256(data).hexdigest()
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        original_headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV file has no header row") from exc

    keep_indexes = [
        index for index, header in enumerate(original_headers) if header not in _SPECIAL_HEADERS
    ]
    headers = [original_headers[index] for index in keep_indexes]
    rows = []
    for row_number, original_row in enumerate(reader, start=2):
        if len(original_row) != len(original_headers):
            raise ValueError(
                f"Row {row_number} has {len(original_row)} columns; expected {len(original_headers)}"
            )
        rows.append([original_row[index] for index in keep_indexes])

    if "Issue key" not in headers:
        raise ValueError("CSV lacks the Issue key column")
    issue_key_index = headers.index("Issue key")
    component_indexes = [
        index for index, header in enumerate(headers) if header == "Component/s"
    ]
    if not component_indexes:
        headers.append("Component/s")
        component_indexes = [len(headers) - 1]
        for row in rows:
            row.append("")

    overrides = component_overrides or {}
    normalized_rows: list[dict[str, Any]] = []
    unresolved_component_values: Counter[str] = Counter()
    component_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    ignored_markers: Counter[str] = Counter()
    unresolved_issue_keys: list[str] = []
    source_issue_keys: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        jira_key = str(row[issue_key_index] or "").strip().upper()
        if not _JIRA_KEY_RE.fullmatch(jira_key):
            raise ValueError(f"Row {row_number} has an invalid Issue key")
        if jira_key in source_issue_keys:
            raise ValueError(f"Duplicate Issue key in CSV: {jira_key}")
        source_issue_keys.add(jira_key)
        source_components = _dedupe(
            [row[index] for index in component_indexes if index < len(row) and row[index].strip()]
        )
        mapped, unresolved, ignored = _map_source_components(source_components)
        if mapped:
            residual_unresolved: list[str] = []
            for value in unresolved:
                if _component_token(value) == "miscellaneous":
                    ignored.append(value)
                else:
                    residual_unresolved.append(value)
            unresolved = residual_unresolved
        for marker in ignored:
            ignored_markers[marker] += 1
        override = overrides.get(jira_key)
        if override is not None:
            assigned = _validated_components(override, jira_key=jira_key)
            method = "explicit_issue_override"
            unresolved = []
        else:
            assigned = mapped
            direct_count = sum(bool(canonical_component_name(value)) for value in source_components)
            alias_count = sum(
                _component_token(value) in _LEGACY_COMPONENT_ALIASES for value in source_components
            )
            if direct_count and alias_count:
                method = "source_canonical_and_legacy_alias"
            elif direct_count:
                method = "source_canonical"
            elif alias_count:
                method = "legacy_alias"
            else:
                method = "unresolved"
        if unresolved or not assigned:
            unresolved_issue_keys.append(jira_key)
            for value in unresolved or ["<missing>"]:
                unresolved_component_values[value] += 1
            method = "unresolved"
        else:
            component_counts.update(assigned)
        method_counts[method] += 1
        normalized_rows.append(
            {
                "jira_key": jira_key,
                "row": row,
                "source_components": source_components,
                "assigned_components": assigned,
                "assignment_method": method,
                "unresolved_components": unresolved,
                "ignored_markers": ignored,
            }
        )

    unused_overrides = sorted(set(overrides) - source_issue_keys)
    max_components = max(
        (len(item["assigned_components"]) for item in normalized_rows),
        default=1,
    )
    while len(component_indexes) < max_components:
        headers.append("Component/s")
        component_indexes.append(len(headers) - 1)
        for item in normalized_rows:
            item["row"].append("")

    headers.extend(
        [
            SOURCE_COMPONENTS_HEADER,
            COMPONENT_ASSIGNMENT_METHOD_HEADER,
            COMPONENT_ASSIGNMENT_EVIDENCE_HEADER,
            SOURCE_FILE_HASH_HEADER,
        ]
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    for item in normalized_rows:
        row = item["row"]
        for index in component_indexes:
            row[index] = ""
        for index, component in zip(component_indexes, item["assigned_components"]):
            row[index] = component
        evidence = {
            "schema_version": HISTORICAL_UAC_NORMALIZATION_VERSION,
            "source_components": item["source_components"],
            "assigned_components": item["assigned_components"],
            "method": item["assignment_method"],
            "ignored_markers": item["ignored_markers"],
        }
        writer.writerow(
            row
            + [
                json.dumps(item["source_components"], ensure_ascii=False),
                item["assignment_method"],
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                source_file_hash,
            ]
        )

    normalized_data = output.getvalue().encode("utf-8")
    normalized_file_hash = hashlib.sha256(normalized_data).hexdigest()
    report = {
        "normalization_version": HISTORICAL_UAC_NORMALIZATION_VERSION,
        "filename": Path(filename).name,
        "source_file_hash": source_file_hash,
        "normalized_file_hash": normalized_file_hash,
        "total_rows": len(normalized_rows),
        "normalized_rows": len(normalized_rows) - len(unresolved_issue_keys),
        "valid": not unresolved_issue_keys and not unused_overrides,
        "mixed_customer_assignment_required": True,
        "component_counts": {
            component: component_counts.get(component, 0)
            for component in CANONICAL_JIRA_COMPONENTS
        },
        "assignment_method_counts": dict(sorted(method_counts.items())),
        "unresolved_rows": len(unresolved_issue_keys),
        "unresolved_issue_keys": unresolved_issue_keys,
        "unresolved_component_values": dict(unresolved_component_values.most_common()),
        "ignored_component_markers": dict(ignored_markers.most_common()),
        "override_count": len(overrides),
        "unused_override_keys": unused_overrides,
    }
    return HistoricalUacCsvNormalization(data=normalized_data, report=report)
