"""Deterministic reliability and topic-coverage audit for documentation RAG corpora."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_SPEC,
    get_collection_count,
    get_collection_records,
    is_chroma_available,
)


AUDIT_VERSION = "knowledge-corpus-audit-v1"
_WHITESPACE_RE = re.compile(r"\s+")

_COLLECTION_RULES = {
    CHROMA_COLLECTION_AEM_GUIDES: {
        "primary_hosts": {"experienceleague.adobe.com"},
        "secondary_hosts": {
            "experienceleaguecommunities.adobe.com",
            "www.dita-ot.org",
            "dita-lang.org",
            "docs.oasis-open.org",
            "www.oxygenxml.com",
            "github.com",
        },
        "probes": (
            ("authoring-editor", "Authoring and editor", r"\b(?:web|xml) editor\b|\bauthoring\b"),
            ("map-management", "Map management", r"\bmap console\b|\bmap management\b|\bmanage maps?\b"),
            ("publishing", "Publishing and output generation", r"\bpublish(?:ing|ed)?\b|\boutput generation\b"),
            ("native-pdf", "Native PDF", r"\bnative pdf\b"),
            ("dita-ot", "DITA-OT output", r"\bdita[ -]?ot\b"),
            ("aem-sites", "AEM Sites output", r"\baem sites\b|\bsite output\b"),
            ("translation", "Translation", r"\btranslat(?:e|ed|es|ing|ion|ions)\b"),
            ("baseline", "Baselines", r"\bbaselines?\b"),
            ("review", "Review workflows", r"\breview(?:ing|ed|er|ers)?\b"),
            ("output-presets", "Output presets", r"\boutput presets?\b"),
            ("upgrade", "Upgrade instructions", r"\bupgrade instructions?\b|\bupgrad(?:e|ed|ing)\b"),
            ("release-notes", "Release notes and fixed issues", r"\brelease notes?\b|\bfixed issues?\b"),
            ("dynamic-media", "Dynamic Media", r"\bdynamic media\b"),
            ("image-maps", "Image maps and hotspots", r"\bimage[ -]?maps?\b|\bhotspots?\b"),
            ("asset-upload", "Asset upload", r"\basset uploads?\b|\bupload(?:ing|ed)? (?:an? )?(?:asset|image|video)\b"),
        ),
    },
    CHROMA_COLLECTION_DITA_SPEC: {
        "primary_hosts": {"docs.oasis-open.org", "dita-lang.org"},
        "secondary_hosts": {"www.oxygenxml.com", "www.dita-ot.org"},
        "required_versions": {"DITA 1.2", "DITA 1.3"},
        "probes": (
            ("dir", "@dir", r"@dir\b|\bdir attribute\b|\bbidirectional text\b"),
            ("domains", "@domains", r"@domains\b|\bdomains attribute\b"),
            ("sort-as", "sort-as", r"\bsort-as\b|\bindex-sort-as\b"),
            ("specialization", "DITA specialization", r"\bspeciali[sz](?:e|ed|es|ing|ation|ations)\b"),
            ("constraints", "Constraint behavior", r"\bconstraint modules?\b|\bconstrained grammar\b"),
            ("keys", "Keys and key references", r"\bkeyrefs?\b|\bkeydefs?\b|\bkey scopes?\b"),
            ("content-reuse", "Conref and conkeyref", r"\bconrefs?\b|\bconkeyrefs?\b|\bcontent references?\b"),
            ("conditional-processing", "Conditional processing", r"\bconditional processing\b|\bditavals?\b"),
            ("copy-to", "@copy-to", r"@copy-to\b|\bcopy-to(?: attribute)?\b"),
            ("chunk", "@chunk", r"@chunk\b|\bchunk attribute\b|\bchunking behavior\b"),
            ("processing-role", "@processing-role", r"@processing-role\b|\bprocessing-role(?: attribute)?\b"),
            ("xml-lang", "@xml:lang", r"@?xml:lang\b|\bxml:lang attribute\b"),
            ("external-xref", "External xref scope", r"\bscope=[\"']?external\b|\bexternal scope\b.*\bxref\b"),
        ),
    },
}

_REMEDIATION_COMMANDS = {
    (CHROMA_COLLECTION_AEM_GUIDES, "image-maps"): [
        "bash scripts/upsert_aem65_image_maps_vm.sh",
        "bash scripts/upsert_dynamic_media_carousel_hotspots_vm.sh",
    ],
    **{
        (CHROMA_COLLECTION_DITA_SPEC, code): ["bash scripts/upsert_dita_spec_gaps_vm.sh"]
        for code in ("dir", "domains", "sort-as", "specialization", "constraints")
    },
}
_METADATA_MIGRATION_COMMAND = "bash scripts/migrate_knowledge_corpus_metadata_vm.sh"
_SOURCE_TYPES = {
    "experienceleague.adobe.com": "experience_league",
    "experienceleaguecommunities.adobe.com": "adobe_community",
    "docs.oasis-open.org": "dita_spec",
    "dita-lang.org": "dita_spec",
    "www.oxygenxml.com": "dita_secondary_reference",
    "www.dita-ot.org": "dita_ot_reference",
    "github.com": "github_example",
}


def _source_url(metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("source_url")
        or metadata.get("canonical_url")
        or metadata.get("url")
        or ""
    ).strip()


def _host(url: str) -> str:
    return urlparse(url).netloc.casefold().split(":", 1)[0]


def _canonical_hash(document: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", document.strip()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _authority_role(collection: str, host: str) -> str:
    rules = _COLLECTION_RULES[collection]
    if host in rules["primary_hosts"]:
        return "primary"
    if host in rules["secondary_hosts"]:
        return "secondary"
    return "unknown"


def build_knowledge_metadata_updates(collection: str, metadata: dict[str, Any]) -> dict[str, str]:
    """Derive stable scalar provenance metadata without overwriting stronger existing values."""
    if collection not in _COLLECTION_RULES:
        raise ValueError(f"Unsupported knowledge collection: {collection}")
    url = _source_url(metadata)
    host = _host(url) if url else ""
    updates = {
        "knowledge_collection": collection,
        "authority_role": _authority_role(collection, host),
    }
    if host:
        updates["source_host"] = host
    if not str(metadata.get("source_type") or "").strip():
        updates["source_type"] = _SOURCE_TYPES.get(host, "external" if host else "unknown")
    if not str(metadata.get("title") or "").strip() and url:
        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if slug:
            updates["title"] = re.sub(r"[-_]+", " ", slug).strip().title()
    return {
        key: value
        for key, value in updates.items()
        if str(metadata.get(key) or "") != value
    }


def _version(metadata: dict[str, Any], searchable: str) -> str:
    explicit = str(metadata.get("spec_version") or "").strip()
    if explicit:
        return explicit
    if re.search(r"(?:/|\b)(?:dita/)?v?1[._-]?3(?:/|\b)", searchable, re.I):
        return "DITA 1.3"
    if re.search(r"(?:/|\b)(?:dita/)?v?1[._-]?2(?:/|\b)", searchable, re.I):
        return "DITA 1.2"
    return "Unknown"


def _release_label(url: str) -> str:
    cloud = re.search(r"cloud-release-notes/(\d{4})-releases/([^/]+)-release", url, re.I)
    if cloud:
        return f"cloud-{cloud.group(1)}-{cloud.group(2)}".lower()
    on_prem = re.search(r"on-prem-release-notes/([^/]+)-release", url, re.I)
    if on_prem:
        return f"on-prem-{on_prem.group(1)}".lower()
    return ""


def _distribution(counter: Counter[str], key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "chunk_count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_knowledge_collection_audit(
    collection: str,
    records: list[dict[str, Any]],
    *,
    collection_count: int | None = None,
    duplicate_sample_limit: int = 10,
) -> dict[str, Any]:
    """Audit one documentation collection using authority-aware topic probes."""
    if collection not in _COLLECTION_RULES:
        raise ValueError(f"Unsupported knowledge collection: {collection}")
    expected_count = len(records) if collection_count is None else int(collection_count)
    rules = _COLLECTION_RULES[collection]
    hosts: Counter[str] = Counter()
    authority_roles: Counter[str] = Counter()
    source_chunks: Counter[str] = Counter()
    source_roles: dict[str, str] = {}
    source_types: Counter[str] = Counter()
    evidence_types: Counter[str] = Counter()
    feature_areas: Counter[str] = Counter()
    versions: Counter[str] = Counter()
    releases: Counter[str] = Counter()
    probe_hits: dict[str, dict[str, Any]] = {
        code: {"code": code, "topic": label, "chunk_count": 0, "source_urls": set(), "authority": Counter()}
        for code, label, _pattern in rules["probes"]
    }
    document_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen_ids: set[str] = set()
    duplicate_ids = 0
    missing_url = 0
    missing_title = 0
    missing_source_type = 0
    missing_source_host = 0
    missing_authority_role = 0
    empty_documents = 0
    curated_chunks = 0

    for record in records:
        record_id = str(record.get("id") or "").strip()
        if record_id and record_id in seen_ids:
            duplicate_ids += 1
        elif record_id:
            seen_ids.add(record_id)
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        document = str(record.get("document") or "").strip()
        url = _source_url(metadata)
        host = _host(url) if url else "(missing)"
        role = _authority_role(collection, host)
        hosts[host] += 1
        authority_roles[role] += 1
        if url:
            source_chunks[url] += 1
            source_roles[url] = role
        else:
            missing_url += 1
        if not str(metadata.get("title") or "").strip():
            missing_title += 1
        source_type = str(metadata.get("source_type") or "").strip()
        if source_type:
            source_types[source_type] += 1
        else:
            missing_source_type += 1
        if not str(metadata.get("source_host") or "").strip():
            missing_source_host += 1
        if not str(metadata.get("authority_role") or "").strip():
            missing_authority_role += 1
        evidence_type = str(metadata.get("evidence_type") or "").strip()
        if evidence_type:
            evidence_types[evidence_type] += 1
        feature_area = str(metadata.get("feature_area") or "").strip()
        if feature_area:
            feature_areas[feature_area] += 1
        if metadata.get("curated") is True:
            curated_chunks += 1
        if not document:
            empty_documents += 1

        searchable = " ".join(
            str(metadata.get(field) or "")
            for field in ("title", "section", "construct", "feature_area", "evidence_type")
        )
        searchable = f"{searchable} {url} {document}"
        if collection == CHROMA_COLLECTION_DITA_SPEC:
            versions[_version(metadata, searchable)] += 1
        else:
            release = _release_label(url)
            if release:
                releases[release] += 1
        for code, _label, pattern in rules["probes"]:
            if re.search(pattern, searchable, re.I):
                probe = probe_hits[code]
                probe["chunk_count"] += 1
                probe["authority"][role] += 1
                if url:
                    probe["source_urls"].add(url)

        document_hash = _canonical_hash(document)
        if document_hash:
            document_groups[document_hash].append((record_id, url))

    probe_coverage = []
    knowledge_gaps = []
    for code, label, _pattern in rules["probes"]:
        probe = probe_hits[code]
        primary_count = probe["authority"]["primary"]
        secondary_count = probe["authority"]["secondary"]
        if primary_count:
            status = "covered"
        elif secondary_count:
            status = "weak"
            knowledge_gaps.append({
                "code": f"weak-{code}",
                "severity": "medium",
                "topic": label,
                "reason": "Only secondary evidence is indexed; no primary authoritative source matched.",
                "remediation": "Ingest an authoritative source page for this topic and rerun the audit.",
                "suggested_commands": _REMEDIATION_COMMANDS.get((collection, code), []),
            })
        else:
            status = "missing"
            knowledge_gaps.append({
                "code": f"missing-{code}",
                "severity": "high",
                "topic": label,
                "reason": "No primary or secondary source matched this baseline knowledge probe.",
                "remediation": "Ingest authoritative documentation with explicit behavior and validation boundaries.",
                "suggested_commands": _REMEDIATION_COMMANDS.get((collection, code), []),
            })
        probe_coverage.append({
            "code": code,
            "topic": label,
            "status": status,
            "chunk_count": probe["chunk_count"],
            "primary_chunk_count": primary_count,
            "secondary_chunk_count": secondary_count,
            "source_count": len(probe["source_urls"]),
            "sample_source_urls": sorted(probe["source_urls"])[:5],
        })

    missing_versions = []
    for version in sorted(rules.get("required_versions", set())):
        if versions[version] == 0:
            missing_versions.append(version)
            knowledge_gaps.append({
                "code": f"missing-{version.casefold().replace(' ', '-').replace('.', '-')}",
                "severity": "high",
                "topic": version,
                "reason": f"No chunks were identified as {version} evidence.",
                "remediation": f"Index authoritative {version} specification sources and rerun the audit.",
            })

    duplicate_groups = []
    duplicate_excess = 0
    for document_hash, members in document_groups.items():
        if len(members) < 2:
            continue
        duplicate_excess += len(members) - 1
        duplicate_groups.append({
            "document_sha256": document_hash,
            "chunk_count": len(members),
            "source_urls": sorted({url for _, url in members if url}),
            "chunk_ids": [record_id for record_id, _url in members[:10]],
        })
    duplicate_groups.sort(key=lambda group: (-group["chunk_count"], group["document_sha256"]))

    scan_complete = len(records) == expected_count
    if expected_count == 0:
        knowledge_gaps.insert(0, {
            "code": "empty-collection",
            "severity": "critical",
            "topic": "Corpus availability",
            "reason": f"The {collection} collection contains no searchable chunks.",
            "remediation": "Index the authoritative corpus before relying on RAG answers.",
        })
    if not scan_complete:
        knowledge_gaps.insert(0, {
            "code": "partial-scan",
            "severity": "critical",
            "topic": "Corpus audit completeness",
            "reason": f"Scanned {len(records)} of {expected_count} collection chunks.",
            "remediation": "Resolve the Chroma record scan failure before trusting coverage conclusions.",
        })
    for code, count, reason, remediation in (
        ("missing-source-url", missing_url, "Chunks have no source URL.", "Reindex them with source provenance."),
        ("missing-title", missing_title, "Chunks have no evidence title.", "Reindex them with a stable page or section title."),
        ("missing-source-type", missing_source_type, "Chunks have no scalar source_type metadata.", "Reindex or migrate metadata so source families are filterable."),
        ("missing-source-host", missing_source_host, "Chunks have no scalar source_host metadata.", "Migrate metadata so host distributions are filterable."),
        ("missing-authority-role", missing_authority_role, "Chunks have no scalar authority_role metadata.", "Migrate metadata so primary and secondary evidence are filterable."),
        ("unknown-authority", authority_roles["unknown"], "Chunks come from unclassified source hosts.", "Review those hosts and classify, replace, or remove their evidence."),
        ("empty-document", empty_documents, "Chunks contain no searchable document text.", "Delete or reindex empty chunks."),
    ):
        if count:
            knowledge_gaps.append({
                "code": code,
                "severity": "high" if code in {"missing-source-url", "unknown-authority", "empty-document"} else "medium",
                "topic": "Evidence integrity",
                "count": count,
                "reason": reason,
                "remediation": remediation,
                "suggested_commands": (
                    [_METADATA_MIGRATION_COMMAND]
                    if code in {"missing-title", "missing-source-type", "missing-source-host", "missing-authority-role"}
                    else []
                ),
            })
    if duplicate_excess:
        knowledge_gaps.append({
            "code": "duplicate-document-text",
            "severity": "medium",
            "topic": "Retrieval diversity",
            "count": duplicate_excess,
            "reason": "Normalized-identical document text is stored more than once and can skew ranking.",
            "remediation": "Review duplicate samples, then deduplicate only truly redundant chunks by stable source and content hash.",
        })

    source_distribution = [
        {
            "source_url": url,
            "chunk_count": count,
            "authority_role": source_roles[url],
        }
        for url, count in sorted(source_chunks.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "collection": collection,
        "scan_complete": scan_complete,
        "coverage_confidence": "complete" if scan_complete else "partial",
        "totals": {
            "collection_chunk_count": expected_count,
            "scanned_chunk_count": len(records),
            "unique_source_count": len(source_chunks),
            "primary_authority_chunk_count": authority_roles["primary"],
            "secondary_authority_chunk_count": authority_roles["secondary"],
            "unknown_authority_chunk_count": authority_roles["unknown"],
            "curated_chunk_count": curated_chunks,
            "covered_probe_count": sum(row["status"] == "covered" for row in probe_coverage),
            "weak_probe_count": sum(row["status"] == "weak" for row in probe_coverage),
            "missing_probe_count": sum(row["status"] == "missing" for row in probe_coverage),
        },
        "probe_coverage": probe_coverage,
        "knowledge_gaps": knowledge_gaps,
        "source_authority_distribution": _distribution(authority_roles, "authority_role"),
        "host_distribution": _distribution(hosts, "host"),
        "source_type_distribution": _distribution(source_types, "source_type"),
        "evidence_type_distribution": _distribution(evidence_types, "evidence_type"),
        "feature_area_distribution": _distribution(feature_areas, "feature_area"),
        "version_distribution": _distribution(versions, "version"),
        "missing_required_versions": missing_versions,
        "release_coverage": _distribution(releases, "release"),
        "source_distribution": source_distribution,
        "metadata_gaps": {
            "chunks_missing_source_url": missing_url,
            "chunks_missing_title": missing_title,
            "chunks_missing_source_type": missing_source_type,
            "chunks_missing_source_host": missing_source_host,
            "chunks_missing_authority_role": missing_authority_role,
            "empty_document_chunks": empty_documents,
        },
        "duplicates": {
            "duplicate_chunk_id_count": duplicate_ids,
            "normalized_exact_duplicate_document_groups": len(duplicate_groups),
            "normalized_exact_duplicate_document_excess": duplicate_excess,
            "sample_groups": duplicate_groups[: max(0, duplicate_sample_limit)],
        },
    }


def build_knowledge_corpus_audit(
    collection_records: dict[str, list[dict[str, Any]]],
    *,
    collection_counts: dict[str, int] | None = None,
    duplicate_sample_limit: int = 10,
) -> dict[str, Any]:
    """Build the combined product-documentation and DITA-spec knowledge audit."""
    counts = collection_counts or {}
    collections = {
        collection: build_knowledge_collection_audit(
            collection,
            collection_records.get(collection, []),
            collection_count=counts.get(collection),
            duplicate_sample_limit=duplicate_sample_limit,
        )
        for collection in (CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC)
    }
    gaps = [
        {"collection": collection, **gap}
        for collection, report in collections.items()
        for gap in report["knowledge_gaps"]
    ]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    gaps.sort(key=lambda gap: (severity_order.get(gap["severity"], 9), gap["collection"], gap["code"]))
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "available": True,
        "summary": {
            "collection_count": len(collections),
            "total_chunks": sum(report["totals"]["collection_chunk_count"] for report in collections.values()),
            "total_unique_sources": sum(report["totals"]["unique_source_count"] for report in collections.values()),
            "knowledge_gap_count": len(gaps),
            "critical_gap_count": sum(gap["severity"] == "critical" for gap in gaps),
            "high_gap_count": sum(gap["severity"] == "high" for gap in gaps),
            "medium_gap_count": sum(gap["severity"] == "medium" for gap in gaps),
            "all_scans_complete": all(report["scan_complete"] for report in collections.values()),
        },
        "knowledge_gaps": gaps,
        "collections": collections,
        "interpretation": "Covered requires at least one primary authoritative source match. Secondary-only evidence is weak, not authoritative product/spec behavior.",
    }


def audit_knowledge_corpora(*, duplicate_sample_limit: int = 10) -> dict[str, Any]:
    """Scan live documentation collections and report reliable knowledge coverage."""
    if not is_chroma_available():
        return {"audit_version": AUDIT_VERSION, "available": False, "error": "ChromaDB is unavailable"}
    collections = (CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC)
    return build_knowledge_corpus_audit(
        {collection: get_collection_records(collection, include_documents=True) for collection in collections},
        collection_counts={collection: get_collection_count(collection) for collection in collections},
        duplicate_sample_limit=max(0, min(int(duplicate_sample_limit), 100)),
    )


def migrate_knowledge_corpus_metadata(*, dry_run: bool = False, batch_size: int = 500) -> dict[str, Any]:
    """Backfill scalar source provenance in place without changing documents or embeddings."""
    if not is_chroma_available():
        return {"available": False, "error": "ChromaDB is unavailable", "dry_run": dry_run}
    from app.services.vector_store_service import update_document_metadatas

    reports = {}
    scan_failure_count = 0
    for collection in (CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC):
        expected_count = get_collection_count(collection)
        records = get_collection_records(collection)
        scan_complete = len(records) == expected_count
        if not scan_complete:
            scan_failure_count += 1
            reports[collection] = {
                "collection_count": expected_count,
                "scanned": len(records),
                "scan_complete": False,
                "pending_updates": 0,
                "updated": 0,
                "failed": 0,
                "records_missing_id": 0,
                "error": "Record scan count does not match collection count; no metadata was changed.",
            }
            continue
        pending: list[tuple[str, dict[str, Any]]] = []
        missing_ids = 0
        for record in records:
            record_id = str(record.get("id") or "").strip()
            if not record_id:
                missing_ids += 1
                continue
            metadata = dict(record.get("metadata") or {})
            updates = build_knowledge_metadata_updates(collection, metadata)
            if updates:
                metadata.update(updates)
                pending.append((record_id, metadata))
        updated = 0
        failed = 0
        if not dry_run:
            safe_batch_size = max(1, min(int(batch_size), 2000))
            for start in range(0, len(pending), safe_batch_size):
                batch = pending[start : start + safe_batch_size]
                if update_document_metadatas(
                    collection,
                    [record_id for record_id, _metadata in batch],
                    [metadata for _record_id, metadata in batch],
                ):
                    updated += len(batch)
                else:
                    failed += len(batch)
        reports[collection] = {
            "collection_count": expected_count,
            "scanned": len(records),
            "scan_complete": True,
            "pending_updates": len(pending),
            "updated": updated,
            "failed": failed,
            "records_missing_id": missing_ids,
        }
    return {
        "available": True,
        "dry_run": dry_run,
        "collections": reports,
        "total_pending_updates": sum(report["pending_updates"] for report in reports.values()),
        "total_updated": sum(report["updated"] for report in reports.values()),
        "total_failed": sum(report["failed"] for report in reports.values()),
        "scan_failure_count": scan_failure_count,
        "restart_required": False,
        "reembedding_required": False,
    }
