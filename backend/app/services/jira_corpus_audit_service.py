"""Deterministic coverage audit for the searchable Jira QA Chroma corpus."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from app.services.customer_tokens import clean_customer_tokens
from app.services.jira_component_metadata_service import (
    CANONICAL_JIRA_COMPONENTS,
    canonical_component_name,
    normalize_component_token,
)
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_count,
    get_collection_records,
    is_chroma_available,
)


AUDIT_VERSION = "jira-corpus-audit-v2"
_WHITESPACE_RE = re.compile(r"\s+")


def _json_list(value: Any) -> tuple[list[str], bool]:
    if value is None or value == "":
        return [], False
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()], False
    if not isinstance(value, str):
        return [], True
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [], True
    if not isinstance(decoded, list):
        return [], True
    return [str(item).strip() for item in decoded if str(item).strip()], False


def _date_value(metadata: dict[str, Any]) -> tuple[datetime | None, str]:
    raw = str(metadata.get("jira_updated_at") or metadata.get("updated_at") or "").strip()
    if not raw:
        return None, ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for date_format in ("%d/%b/%y %I:%M %p", "%d/%b/%y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            return None, raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), ""


def _canonical_document_hash(document: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", str(document or "").strip())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _customer_key(customer: str) -> str:
    return re.sub(r"[-_]+", " ", _WHITESPACE_RE.sub(" ", customer.strip())).casefold()


def _domain_token(domain: str) -> str:
    return re.sub(r"[-\s]+", "_", str(domain or "").strip().casefold())


def _select_display(current: str | None, candidate: str) -> str:
    if not current:
        return candidate
    return min(current, candidate, key=lambda value: (value.casefold(), value))


def _percent(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def _sorted_distribution(counter: Counter[str], *, key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: name, "issue_count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]


def build_jira_corpus_audit(
    records: list[dict[str, Any]],
    *,
    collection_count: int | None = None,
    duplicate_sample_limit: int = 20,
    top_components_per_customer: int = 10,
) -> dict[str, Any]:
    """Build an issue-level audit from Chroma records without double-counting chunks."""
    issues: dict[str, dict[str, Any]] = {}
    missing_jira_key_chunks = 0
    malformed_metadata_values = 0
    duplicate_chunk_ids = 0
    seen_chunk_ids: set[str] = set()
    document_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for record in records:
        chunk_id = str(record.get("id") or "").strip()
        if chunk_id in seen_chunk_ids:
            duplicate_chunk_ids += 1
        elif chunk_id:
            seen_chunk_ids.add(chunk_id)
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        jira_key = str(metadata.get("jira_key") or "").strip().upper()
        if not jira_key and "::" in chunk_id:
            jira_key = chunk_id.split("::", 1)[0].strip().upper()
        if not jira_key:
            missing_jira_key_chunks += 1
            continue

        issue = issues.setdefault(
            jira_key,
            {
                "chunk_count": 0,
                "chunk_types": set(),
                "customers": {},
                "components": {},
                "primary_components": set(),
                "noncanonical_components": {},
                "domains": set(),
                "dates": [],
                "invalid_dates": set(),
                "import_sources": set(),
                "source_hashes": set(),
            },
        )
        issue["chunk_count"] += 1
        chunk_type = str(metadata.get("chunk_type") or "unknown").strip() or "unknown"
        issue["chunk_types"].add(chunk_type)

        customer_values: list[str] = []
        scalar_customer = str(metadata.get("customer") or "").strip()
        if scalar_customer:
            customer_values.append(scalar_customer)
        for field in ("enrich_customers", "customer_names", "customer_labels"):
            values, malformed = _json_list(metadata.get(field))
            malformed_metadata_values += int(malformed)
            customer_values.extend(values)
        for customer in clean_customer_tokens(customer_values):
            customer_key = _customer_key(customer)
            if customer_key:
                issue["customers"][customer_key] = _select_display(
                    issue["customers"].get(customer_key), customer
                )

        components, malformed = _json_list(metadata.get("components"))
        malformed_metadata_values += int(malformed)
        for component in components:
            canonical = canonical_component_name(component)
            normalized = normalize_component_token(component)
            if normalized and normalized not in issue["components"]:
                issue["components"][normalized] = canonical
            elif str(component or "").strip():
                display = _WHITESPACE_RE.sub(" ", str(component).strip())
                key = display.casefold()
                issue["noncanonical_components"][key] = _select_display(
                    issue["noncanonical_components"].get(key), display
                )
        raw_primary = str(metadata.get("component_primary") or "").strip()
        primary = normalize_component_token(raw_primary)
        if primary:
            issue["primary_components"].add(primary)
            issue["components"].setdefault(primary, canonical_component_name(primary))
        elif raw_primary:
            display = _WHITESPACE_RE.sub(" ", raw_primary)
            key = display.casefold()
            issue["noncanonical_components"][key] = _select_display(
                issue["noncanonical_components"].get(key), display
            )
        domain = _domain_token(str(metadata.get("enrich_domain") or metadata.get("domain") or ""))
        if domain:
            issue["domains"].add(domain)

        parsed_date, invalid_date = _date_value(metadata)
        if parsed_date is not None:
            issue["dates"].append(parsed_date)
        elif invalid_date:
            issue["invalid_dates"].add(invalid_date)

        import_source = str(metadata.get("import_source_type") or "unknown").strip() or "unknown"
        issue["import_sources"].add(import_source)
        source_hash = str(metadata.get("source_file_hash") or "").strip()
        if source_hash:
            issue["source_hashes"].add(source_hash)
        source_hashes, malformed = _json_list(metadata.get("source_file_hashes"))
        malformed_metadata_values += int(malformed)
        issue["source_hashes"].update(source_hashes)

        document_hash = _canonical_document_hash(str(record.get("document") or ""))
        if document_hash:
            document_groups[document_hash].append((chunk_id, jira_key))

    unique_issue_count = len(issues)
    customer_issue_counts: Counter[str] = Counter()
    customer_chunk_counts: Counter[str] = Counter()
    component_issue_counts: Counter[str] = Counter()
    component_chunk_counts: Counter[str] = Counter()
    primary_component_counts: Counter[str] = Counter()
    month_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    import_source_counts: Counter[str] = Counter()
    domain_issue_counts: Counter[str] = Counter()
    chunks_per_issue: Counter[int] = Counter()
    customer_component_counts: dict[str, Counter[str]] = defaultdict(Counter)
    customer_dates: dict[str, list[datetime]] = defaultdict(list)
    component_customers: dict[str, set[str]] = defaultdict(set)
    customer_displays: dict[str, str] = {}
    component_displays: dict[str, str] = {}
    missing_customer = 0
    missing_component = 0
    missing_date = 0
    invalid_date_issue_count = 0
    missing_component_primary = 0
    source_overlap_issue_count = 0
    unknown_domain_issue_count = 0
    conflicting_domain_issue_count = 0
    issues_with_noncanonical_component = 0
    noncanonical_component_values: Counter[str] = Counter()
    all_dates: list[datetime] = []

    for issue in issues.values():
        chunk_count = int(issue["chunk_count"])
        chunks_per_issue[chunk_count] += 1
        customers = sorted(issue["customers"])
        components = sorted(issue["components"])
        for customer_key, display in issue["customers"].items():
            customer_displays[customer_key] = _select_display(customer_displays.get(customer_key), display)
        for component_key, display in issue["components"].items():
            component_displays[component_key] = _select_display(component_displays.get(component_key), display)
        dates = list(issue["dates"])
        if not customers:
            missing_customer += 1
        if not components:
            missing_component += 1
        if not issue["primary_components"]:
            missing_component_primary += 1
        if issue["noncanonical_components"]:
            issues_with_noncanonical_component += 1
            noncanonical_component_values.update(issue["noncanonical_components"].values())
        if not dates and not issue["invalid_dates"]:
            missing_date += 1
        if issue["invalid_dates"]:
            invalid_date_issue_count += 1
        if len(issue["source_hashes"]) > 1:
            source_overlap_issue_count += 1
        known_domains = sorted(domain for domain in issue["domains"] if domain != "unknown")
        selected_domain = known_domains[0] if known_domains else "unknown"
        domain_issue_counts[selected_domain] += 1
        if selected_domain == "unknown":
            unknown_domain_issue_count += 1
        if len(known_domains) > 1:
            conflicting_domain_issue_count += 1

        latest_date = max(dates) if dates else None
        if latest_date:
            all_dates.append(latest_date)
            month_counts[latest_date.strftime("%Y-%m")] += 1
            year_counts[latest_date.strftime("%Y")] += 1
        for customer in customers:
            customer_issue_counts[customer] += 1
            customer_chunk_counts[customer] += chunk_count
            if latest_date:
                customer_dates[customer].append(latest_date)
            for component in components:
                customer_component_counts[customer][component] += 1
        for component in components:
            component_issue_counts[component] += 1
            component_chunk_counts[component] += chunk_count
            component_customers[component].update(customers)
        for primary in issue["primary_components"]:
            primary_component_counts[primary] += 1
        for source in issue["import_sources"]:
            import_source_counts[source] += 1

    customers = []
    for customer_key, issue_count in sorted(
        customer_issue_counts.items(), key=lambda item: (-item[1], customer_displays[item[0]].casefold())
    ):
        dates = customer_dates.get(customer_key) or []
        component_counts = customer_component_counts.get(customer_key) or Counter()
        customers.append({
            "customer": customer_displays[customer_key],
            "issue_count": issue_count,
            "chunk_count": customer_chunk_counts[customer_key],
            "issue_percent": _percent(issue_count, unique_issue_count),
            "earliest_updated_at": min(dates).isoformat() if dates else None,
            "latest_updated_at": max(dates).isoformat() if dates else None,
            "top_components": [
                {"component": component_displays[component_key], "issue_count": count}
                for component_key, count in sorted(
                    component_counts.items(),
                    key=lambda item: (-item[1], component_displays[item[0]].casefold()),
                )[: max(1, top_components_per_customer)]
            ],
        })

    components = []
    for component_key, issue_count in sorted(
        component_issue_counts.items(), key=lambda item: (-item[1], component_displays[item[0]].casefold())
    ):
        components.append({
            "component": component_displays[component_key],
            "issue_count": issue_count,
            "chunk_count": component_chunk_counts[component_key],
            "issue_percent": _percent(issue_count, unique_issue_count),
            "customer_count": len(component_customers[component_key]),
        })

    duplicate_groups = []
    duplicate_document_excess = 0
    cross_issue_duplicate_groups = 0
    for document_hash, members in document_groups.items():
        if len(members) < 2:
            continue
        duplicate_document_excess += len(members) - 1
        jira_keys = sorted({jira_key for _, jira_key in members})
        if len(jira_keys) > 1:
            cross_issue_duplicate_groups += 1
        duplicate_groups.append({
            "document_sha256": document_hash,
            "chunk_count": len(members),
            "jira_keys": jira_keys,
            "chunk_ids": [chunk_id for chunk_id, _ in members[:10]],
        })
    duplicate_groups.sort(key=lambda group: (-group["chunk_count"], group["document_sha256"]))

    scanned_chunk_count = len(records)
    expected_count = scanned_chunk_count if collection_count is None else int(collection_count)
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": CHROMA_COLLECTION_JIRA_QA,
        "coverage_basis": "Chroma jira_qa documents grouped by jira_key; customers/components count unique issues, not chunks.",
        "scan_complete": scanned_chunk_count == expected_count,
        "coverage_confidence": "complete" if scanned_chunk_count == expected_count else "partial",
        "counting_notes": [
            "Each Jira is counted once per represented customer and component.",
            "Multi-customer and multi-component distributions can therefore sum above the unique issue total.",
            "Date distributions use each Jira's latest valid updated timestamp.",
        ],
        "totals": {
            "collection_chunk_count": expected_count,
            "scanned_chunk_count": scanned_chunk_count,
            "unique_issue_count": unique_issue_count,
            "represented_customer_count": len(customer_issue_counts),
            "represented_component_count": len(component_issue_counts),
            "known_domain_issue_count": unique_issue_count - unknown_domain_issue_count,
            "unknown_domain_issue_count": unknown_domain_issue_count,
            "expected_multi_chunk_issue_count": sum(count for size, count in chunks_per_issue.items() if size > 1),
        },
        "date_coverage": {
            "earliest_updated_at": min(all_dates).isoformat() if all_dates else None,
            "latest_updated_at": max(all_dates).isoformat() if all_dates else None,
            "issues_by_year": _sorted_distribution(year_counts, key_name="year"),
            "issues_by_month": _sorted_distribution(month_counts, key_name="month"),
        },
        "customer_coverage": customers,
        "component_coverage": components,
        "canonical_component_taxonomy": list(CANONICAL_JIRA_COMPONENTS),
        "primary_component_distribution": _sorted_distribution(
            primary_component_counts, key_name="component_primary"
        ),
        "domain_coverage": {
            "ranking_policy": "soft_boost_only",
            "hard_filtering_allowed": False,
            "unknown_issue_count": unknown_domain_issue_count,
            "unknown_issue_percent": _percent(unknown_domain_issue_count, unique_issue_count),
            "issues_with_conflicting_known_domains": conflicting_domain_issue_count,
            "backfill_command": "bash scripts/migrate_unknown_jira_domains_vm.sh --apply",
            "distribution": _sorted_distribution(domain_issue_counts, key_name="domain"),
            "note": "Unknown or mismatched domains remain retrievable by semantic, keyword, component, entity, output, customer, and issue-type evidence.",
        },
        "import_source_distribution": _sorted_distribution(import_source_counts, key_name="import_source_type"),
        "chunks_per_issue_distribution": [
            {"chunk_count": size, "issue_count": count}
            for size, count in sorted(chunks_per_issue.items())
        ],
        "quality_gaps": {
            "issues_missing_customer": missing_customer,
            "issues_missing_component": missing_component,
            "issues_missing_component_primary": missing_component_primary,
            "issues_with_noncanonical_component": issues_with_noncanonical_component,
            "issues_missing_updated_at": missing_date,
            "issues_with_invalid_updated_at": invalid_date_issue_count,
            "chunks_missing_jira_key": missing_jira_key_chunks,
            "malformed_json_metadata_values": malformed_metadata_values,
            "issues_with_multiple_source_hashes": source_overlap_issue_count,
            "issues_with_unknown_domain": unknown_domain_issue_count,
            "issues_with_conflicting_known_domains": conflicting_domain_issue_count,
        },
        "noncanonical_component_values": _sorted_distribution(
            noncanonical_component_values, key_name="component"
        ),
        "duplicates": {
            "duplicate_chunk_id_count": duplicate_chunk_ids,
            "normalized_exact_duplicate_document_groups": len(duplicate_groups),
            "normalized_exact_duplicate_document_excess": duplicate_document_excess,
            "cross_issue_duplicate_document_groups": cross_issue_duplicate_groups,
            "sample_groups": duplicate_groups[: max(0, duplicate_sample_limit)],
            "note": "Multiple chunks per Jira are expected. Duplicate metrics only flag repeated IDs or normalized-identical document text.",
        },
    }


def audit_jira_corpus(
    *, duplicate_sample_limit: int = 20, top_components_per_customer: int = 10
) -> dict[str, Any]:
    """Scan the live searchable corpus and return its issue-level coverage audit."""
    if not is_chroma_available():
        return {
            "audit_version": AUDIT_VERSION,
            "collection": CHROMA_COLLECTION_JIRA_QA,
            "available": False,
            "error": "ChromaDB is unavailable",
        }
    count = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
    records = get_collection_records(CHROMA_COLLECTION_JIRA_QA, include_documents=True)
    report = build_jira_corpus_audit(
        records,
        collection_count=count,
        duplicate_sample_limit=duplicate_sample_limit,
        top_components_per_customer=top_components_per_customer,
    )
    from app.services.jira_sync_cursor_service import inspect_jira_sync_cursor

    cursor = inspect_jira_sync_cursor(
        records=records,
        collection_count=count,
    )
    report["incremental_sync_cursor"] = cursor
    report["quality_gaps"]["invalid_incremental_sync_cursor"] = not cursor["valid"]
    report["available"] = True
    return report
