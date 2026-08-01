"""Build aggregate customer Jira-corpus profiles for retrieval and regression scoping."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

from app.db.jira_enrichment_models import JiraCustomerProfile, JiraEnrichedIssue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, add_documents, delete_documents

PROFILE_VERSION = "customer-profile-v4"
PROFILE_CHUNK_TYPES = (
    "customer_profile_overview",
    "customer_profile_components_domains",
    "customer_profile_workflows_outputs",
    "customer_profile_dita_entities",
    "customer_profile_issue_types_content_data",
    "customer_profile_failures_automation_resolutions",
)

_CONTENT_DATA_PATTERNS = {
    "DITA topics": re.compile(r"\bdita\s+topics?\b|\.dita\b", re.I),
    "DITA maps": re.compile(r"\bdita\s*maps?\b|\.ditamap\b", re.I),
    "Bookmaps": re.compile(r"\bbookmaps?\b", re.I),
    "XML content": re.compile(r"\bxml\b|xml editor", re.I),
    "Key references": re.compile(r"\bkeyrefs?\b|\bconkeyrefs?\b", re.I),
    "Content references": re.compile(r"\bconrefs?\b|\bconrefend\b", re.I),
    "Cross-references": re.compile(r"\bxrefs?\b|cross[- ]references?", re.I),
    "Images/assets": re.compile(r"\bimages?\b|\bassets?\b|\.png\b|\.jpe?g\b|\.svg\b", re.I),
    "Tables": re.compile(r"\btables?\b", re.I),
    "Baselines/versions": re.compile(r"\bbaselines?\b|version history|versioning", re.I),
    "UUID-based content": re.compile(r"\buuid\b|referencelistener", re.I),
    "Review tasks": re.compile(r"review tasks?|review workflow", re.I),
    "Output presets": re.compile(r"output presets?", re.I),
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")[:120]


def _list(value: Any) -> list[str]:
    return [str(item).strip() for item in value] if isinstance(value, list) else []


def _count_issue_values(rows: list[JiraEnrichedIssue], attribute: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    keys: dict[str, list[str]] = {}
    for row in rows:
        seen: set[str] = set()
        for raw in _list(getattr(row, attribute, None)):
            normalized = raw.casefold()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            counts[normalized] += 1
            display.setdefault(normalized, raw)
            keys.setdefault(normalized, []).append(row.jira_key)
    return [
        {"name": display[key], "issue_count": count, "representative_keys": keys[key][:5]}
        for key, count in counts.most_common(20)
    ]


def _count_scalar(rows: list[JiraEnrichedIssue], attribute: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    keys: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    for row in rows:
        raw = str(getattr(row, attribute, "") or "").strip()
        if not raw:
            continue
        key = raw.casefold()
        counts[key] += 1
        display.setdefault(key, raw)
        keys.setdefault(key, []).append(row.jira_key)
    return [
        {"name": display[key], "issue_count": count, "representative_keys": keys[key][:5]}
        for key, count in counts.most_common(20)
    ]


def _render_frequency(items: list[dict[str, Any]], *, limit: int = 12) -> str:
    return "; ".join(
        f"{item['name']} ({item['issue_count']} distinct Jira keys; examples: {', '.join(item['representative_keys'][:3])})"
        for item in items[:limit]
    ) or "No repeated signal classified."


def _count_content_data_signals(rows: list[JiraEnrichedIssue]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    keys: dict[str, list[str]] = {}
    for row in rows:
        text = "\n".join(
            str(value or "")
            for value in (row.summary, row.description, row.raw_text)
        )
        for name, pattern in _CONTENT_DATA_PATTERNS.items():
            if pattern.search(text):
                counts[name] += 1
                keys.setdefault(name, []).append(row.jira_key)
    return [
        {"name": name, "issue_count": count, "representative_keys": keys[name][:5]}
        for name, count in counts.most_common(20)
    ]


def _build_profile(customer_name: str, rows: list[JiraEnrichedIssue]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.jira_updated_at or datetime.min, row.jira_key), reverse=True)
    source_hashes = sorted({value for row in rows for value in _list(row.source_file_hashes) if value})
    automation = _count_scalar(rows, "automation_fit")
    failures = _count_issue_values(rows, "qa_risk_tags")
    resolutions = _count_issue_values(rows, "resolutions")
    if not resolutions:
        resolutions = _count_scalar(rows, "resolution")
    return {
        "customer_name": customer_name,
        "customer_key": _slug(customer_name),
        "issue_count": len(rows),
        "issue_types": _count_scalar(rows, "issue_type"),
        "components": _count_issue_values(rows, "components"),
        "domains": _count_scalar(rows, "domain"),
        "workflows": _count_issue_values(rows, "affected_features"),
        "affected_outputs": _count_issue_values(rows, "affected_outputs"),
        "dita_entities": _count_issue_values(rows, "dita_entities"),
        "content_data_signals": _count_content_data_signals(rows),
        "failure_areas": failures,
        "automation_signals": automation,
        "resolution_patterns": resolutions,
        "representative_keys": [row.jira_key for row in ordered[:25]],
        "source_file_hashes": source_hashes,
    }


def _profile_documents(profile: dict[str, Any]) -> list[tuple[str, str]]:
    customer = profile["customer_name"]
    issue_count = profile["issue_count"]
    boundary = (
        "This is aggregate Jira-corpus context. It can guide regression scope and historical-risk discovery, "
        "but it is not acceptance-criteria or product-behavior proof. Direct Jira or authoritative product evidence is required."
    )
    return [
        (
            "customer_profile_overview",
            f"Observed customer Jira profile for {customer}: {issue_count} distinct Jira keys. "
            f"Representative keys: {', '.join(profile['representative_keys'][:12])}. {boundary}",
        ),
        (
            "customer_profile_components_domains",
            f"{customer} frequently represented or affected components in this Jira corpus: "
            f"{_render_frequency(profile['components'])}\nDomains: {_render_frequency(profile['domains'])}\n{boundary}",
        ),
        (
            "customer_profile_workflows_outputs",
            f"{customer} frequently represented or affected workflows/features in this Jira corpus: "
            f"{_render_frequency(profile['workflows'])}\nPublishing outputs: {_render_frequency(profile['affected_outputs'])}\n{boundary}",
        ),
        (
            "customer_profile_dita_entities",
            f"{customer} frequently represented or affected DITA entities in this Jira corpus: "
            f"{_render_frequency(profile['dita_entities'])}\n{boundary}",
        ),
        (
            "customer_profile_issue_types_content_data",
            f"{customer} frequently represented issue types in this Jira corpus: "
            f"{_render_frequency(profile['issue_types'])}\nContent and data patterns: "
            f"{_render_frequency(profile['content_data_signals'])}\n{boundary}",
        ),
        (
            "customer_profile_failures_automation_resolutions",
            f"{customer} repeated failure/risk areas: {_render_frequency(profile['failure_areas'])}\n"
            f"Automation signals: {_render_frequency(profile['automation_signals'])}\n"
            f"Resolution patterns: {_render_frequency(profile['resolution_patterns'])}\n{boundary}",
        ),
    ]


def rebuild_customer_profiles(customer_names: list[str] | None = None) -> dict[str, Any]:
    """Rebuild SQL and Chroma profiles from distinct Jira rows for selected customer cohorts."""
    requested = {name.casefold(): name for name in (customer_names or []) if name.strip()}
    db = SessionLocal()
    try:
        all_rows = db.query(JiraEnrichedIssue).order_by(JiraEnrichedIssue.jira_key).all()
        cohorts = sorted(
            {
                cohort
                for row in all_rows
                for cohort in _list(row.customer_cohorts)
                if cohort and (not requested or cohort.casefold() in requested)
            },
            key=str.casefold,
        )
        results: dict[str, Any] = {}
        for customer in cohorts:
            rows = [row for row in all_rows if customer.casefold() in {value.casefold() for value in _list(row.customer_cohorts)}]
            profile = _build_profile(customer, rows)
            documents = _profile_documents(profile)
            embeddings = embed_texts_batched([text for _, text in documents], batch_size=16)
            if embeddings is None:
                results[customer] = {"status": "failed", "error": "embedding batch failed"}
                continue
            slug = profile["customer_key"]
            ids = [f"customer-profile::{slug}::{chunk_type}" for chunk_type, _ in documents]
            delete_documents(CHROMA_COLLECTION_JIRA_QA, ids)
            metadata = [
                {
                    "jira_key": f"CUSTOMER-PROFILE-{slug.upper()}",
                    "chunk_type": chunk_type,
                    "customer": customer,
                    "customer_key": slug,
                    "enrich_customers": json.dumps([customer], ensure_ascii=False),
                    "customer_cohorts": json.dumps([customer], ensure_ascii=False),
                    "components": json.dumps([item["name"] for item in profile["components"][:20]], ensure_ascii=False),
                    "issue_types": json.dumps([item["name"] for item in profile["issue_types"][:20]], ensure_ascii=False),
                    "enrich_entities": json.dumps([item["name"] for item in profile["dita_entities"][:20]], ensure_ascii=False),
                    "content_data_signals": json.dumps(
                        [item["name"] for item in profile["content_data_signals"][:20]], ensure_ascii=False
                    ),
                    "enrich_outputs": json.dumps([item["name"] for item in profile["affected_outputs"][:20]], ensure_ascii=False),
                    "aggregate_context": True,
                    "direct_assertion_allowed": False,
                    "evidence_class": "customer_jira_profile",
                    "profile_issue_count": profile["issue_count"],
                    "profile_version": PROFILE_VERSION,
                }
                for chunk_type, _ in documents
            ]
            ok = add_documents(
                CHROMA_COLLECTION_JIRA_QA,
                ids,
                [text for _, text in documents],
                metadata,
                [embedding.tolist() for embedding in embeddings],
            )
            if not ok:
                results[customer] = {"status": "failed", "error": "Chroma upsert failed"}
                continue
            row = db.query(JiraCustomerProfile).filter(JiraCustomerProfile.customer_key == slug).first()
            if row is None:
                row = JiraCustomerProfile(customer_key=slug)
                db.add(row)
            for key, value in profile.items():
                if key != "customer_key":
                    setattr(row, key, value)
            row.profile_version = PROFILE_VERSION
            row.rebuilt_at = datetime.utcnow()
            db.commit()
            results[customer] = {
                "status": "completed",
                "issue_count": profile["issue_count"],
                "chunks_indexed": len(ids),
            }
        return {"profile_version": PROFILE_VERSION, "profiles": results}
    finally:
        db.close()


def get_customer_profile(customer: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.query(JiraCustomerProfile).filter(JiraCustomerProfile.customer_key == _slug(customer)).first()
        if row is None:
            return None
        return {
            "customer_name": row.customer_name,
            "customer_key": row.customer_key,
            "issue_count": row.issue_count,
            "issue_types": row.issue_types or [],
            "components": row.components or [],
            "domains": row.domains or [],
            "workflows": row.workflows or [],
            "affected_outputs": row.affected_outputs or [],
            "dita_entities": row.dita_entities or [],
            "content_data_signals": row.content_data_signals or [],
            "failure_areas": row.failure_areas or [],
            "automation_signals": row.automation_signals or [],
            "resolution_patterns": row.resolution_patterns or [],
            "representative_keys": row.representative_keys or [],
            "evidence_boundary": "Aggregate Jira-corpus context only; direct Jira evidence is required for assertions.",
            "rebuilt_at": row.rebuilt_at.isoformat() if row.rebuilt_at else None,
        }
    finally:
        db.close()
