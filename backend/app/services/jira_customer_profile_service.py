"""Build aggregate customer Jira-corpus profiles for retrieval and regression scoping."""

from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from datetime import datetime
from typing import Any

from app.db.jira_enrichment_models import JiraCustomerProfile, JiraEnrichedIssue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    add_documents,
    delete_documents,
    update_documents_metadata,
)

PROFILE_VERSION = "customer-profile-v6"
PROFILE_CHUNK_TYPES = (
    "customer_profile_overview",
    "customer_profile_components_domains",
    "customer_profile_workflows_outputs",
    "customer_profile_dita_entities",
    "customer_profile_issue_types_content_data",
    "customer_profile_failures_automation_resolutions",
    "customer_profile_bug_taxonomy",
    "customer_profile_bug_concentrations",
    "customer_profile_regression_recommendations",
    "customer_profile_test_data_exploration",
)

_CONTENT_DATA_PATTERNS = {
    "DITA topics": re.compile(r"\bdita\s+topics?\b|\.dita\b", re.I),
    "DITA maps": re.compile(r"\bdita\s*maps?\b|\.ditamap\b", re.I),
    "Bookmaps": re.compile(r"\bbookmaps?\b", re.I),
    "XML content": re.compile(r"\bxml\b|xml editor", re.I),
    "Key references": re.compile(r"\bkeyrefs?\b|\bconkeyrefs?\b", re.I),
    "Content references": re.compile(r"\bconrefs?\b|\bconrefend\b", re.I),
    "Cross-references": re.compile(r"\bxrefs?\b|cross[- ]references?", re.I),
    "Images/media": re.compile(r"\bimages?\b|\bmultimedia\b|\.png\b|\.jpe?g\b|\.svg\b|\.mp4\b", re.I),
    "AEM Assets/repository": re.compile(r"\baem assets\b|assets ui|asset management|\bdam\b|repository", re.I),
    "Tables": re.compile(r"\btables?\b", re.I),
    "Baselines/versions": re.compile(r"\bbaselines?\b|version history|versioning", re.I),
    "UUID-based content": re.compile(r"\buuid\b|referencelistener", re.I),
    "Review tasks": re.compile(r"review tasks?|review workflow", re.I),
    "Output presets": re.compile(r"output presets?", re.I),
}
_PROBLEM_TYPE_PATTERNS = {
    "Functional failure": re.compile(r"\bfails?\b|not work(?:ing)?|unable to|cannot|doesn.t|broken|error", re.I),
    "Workflow blockage": re.compile(r"\bstuck\b|blocked|waiting state|cannot complete|workflow", re.I),
    "Performance/scalability": re.compile(r"performance|slow|latency|timeout|hours?|memory|heap", re.I),
    "Data integrity/references": re.compile(r"missing|duplicate|corrupt|uuid|keyref|conref|xref|reference", re.I),
    "Usability/editor behavior": re.compile(r"editor|authoring|dialog|panel|cursor|selection|drag|drop|usability", re.I),
    "Publishing/output": re.compile(r"publish|output|preset|pdf|aem sites|html5|dita-ot", re.I),
    "Review/collaboration": re.compile(r"review|reviewer|comment|collaboration", re.I),
    "Migration/upgrade": re.compile(r"migration|upgrade|after update|regression", re.I),
    "Configuration/permissions": re.compile(r"configuration|permission|access control|acl|setting", re.I),
    "Search/indexing": re.compile(r"search|indexing|index", re.I),
}
_BUG_TYPE_PATTERNS = {
    "Create/edit/save failure": re.compile(r"\bcreate|edit|save|check[ -]?in|check[ -]?out|lock|unlock\b", re.I),
    "UI rendering or interaction": re.compile(r"\bui\b|render|display|dialog|panel|button|cursor|selection|drag|drop", re.I),
    "Publishing or output generation": re.compile(r"publish|output|preset|pdf|aem sites|html5|dita-ot", re.I),
    "Workflow or job-state failure": re.compile(r"workflow|job|stuck|queue|waiting|post[ -]?publish|cancel", re.I),
    "Reference resolution or integrity": re.compile(r"keyref|conref|xref|reference|uuid|broken link|missing copy", re.I),
    "Search or indexing": re.compile(r"search|indexing|index", re.I),
    "Permissions or authentication": re.compile(r"permission|access control|acl|auth|oauth|token|credential", re.I),
    "Performance or scalability": re.compile(r"performance|slow|latency|timeout|hours?|memory|heap|large map", re.I),
    "Upgrade or backward compatibility": re.compile(r"upgrade|migration|after update|backward compat|regression", re.I),
    "Import/export or integration": re.compile(r"import|export|api|integration|github|gitlab|salesforce|oxygen", re.I),
    "Localization or translation": re.compile(r"translation|multilingual|language|locale|xliff", re.I),
    "Data loss, duplication, or corruption": re.compile(r"data loss|missing|duplicate|corrupt|overwrite|orphan", re.I),
}
_PROBLEM_REPORT_PATTERN = re.compile(
    r"\bfail(?:s|ed|ure)?\b|not work(?:ing)?|unable to|cannot|doesn.t|broken|error|exception|"
    r"stuck|blocked|timeout|slow|missing|duplicate|corrupt|incorrect|wrong|regression|data loss|crash",
    re.I,
)
_TEST_DATA_RECIPES = {
    "DITA topics": "Create valid, minimal, long, specialized, and invalid DITA topics with stable expected snapshots.",
    "DITA maps": "Create small, nested, reused-topic, deeply referenced, and large DITA maps with deterministic link graphs.",
    "Bookmaps": "Create a bookmap with front matter, chapters, appendices, and mixed topic types.",
    "XML content": "Include namespace, special-character, large-text, malformed, and profile-specific XML samples.",
    "Key references": "Include valid, scoped, duplicate, missing, circular, and overridden key definitions and keyrefs.",
    "Content references": "Include valid, ranged, nested, missing-target, circular, and cross-folder conrefs.",
    "Cross-references": "Include internal, external, cross-map, missing-target, renamed-target, and fragment xrefs.",
    "Images/media": "Include supported images and multimedia plus missing, renamed, large, unsupported, and reused assets.",
    "AEM Assets/repository": "Create deep folders, reused assets, versioned assets, permission variants, and move/rename fixtures.",
    "Tables": "Include simple, wide, nested, merged-cell, accessibility, and boundary-size tables.",
    "Baselines/versions": "Create working-copy, latest-version, named-baseline, and as-of-date snapshots with changed references.",
    "UUID-based content": "Include copied, moved, renamed, deleted, duplicated, and restored UUID-based resources.",
    "Review tasks": "Create active, closed, reassigned, multi-reviewer, commented, and version-diverged review tasks.",
    "Output presets": "Create valid, cloned, edited, missing-config, permission-restricted, and multi-output presets.",
}
_EXPLORATORY_RECIPES = {
    "Functional failure": "Repeat the primary flow after refresh, relogin, retry, and reopen; confirm persisted state and no partial artifacts.",
    "Workflow blockage": "Exercise concurrent submission, cancellation, retry, restart recovery, queue ordering, and terminal-state cleanup.",
    "Performance/scalability": "Run controlled small/medium/large fixtures, record baselines, and inspect growth without inventing an SLA.",
    "Data integrity/references": "Vary missing, duplicate, moved, renamed, reused, circular, and cross-folder references; assert no silent loss.",
    "Usability/editor behavior": "Cover keyboard, mouse, focus, refresh, browser, viewport, long labels, empty states, and unsaved changes.",
    "Publishing/output": "Compare full and incremental publish, preset variants, output integrity, stale/orphan cleanup, and republish behavior.",
    "Review/collaboration": "Cover concurrent reviewers, replies, reassignment, closed tasks, stale versions, permissions, and notifications.",
    "Migration/upgrade": "Compare upgraded and fresh instances, retained configuration, old content, defaults, and rollback compatibility.",
    "Configuration/permissions": "Cross product roles with inherited/explicit permissions, missing configuration, invalid values, and least privilege.",
    "Search/indexing": "Cover new, updated, moved, deleted, permission-filtered, multilingual, and reindexed content with eventual consistency.",
}
_PRODUCT_AREA_ALIASES = {
    "authoring": "Web Editor & Authoring",
    "editor": "Web Editor & Authoring",
    "review": "Review & Collaboration",
    "publishing": "Publishing",
    "native_pdf": "Publishing",
    "asset management": "Assets & Repository",
    "platform": "Administration & Platform",
    "baseline": "Versioning & Baselines",
    "uuid": "References & Repository Integrity",
    "keyref": "DITA References",
    "post_processing": "Publishing Workflows",
    "migration": "Migration & Upgrade",
    "performance": "Performance & Scalability",
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


def _row_text(row: JiraEnrichedIssue) -> str:
    return "\n".join(str(value or "") for value in (row.summary, row.description, row.raw_text))


def _count_pattern_signals(
    rows: list[JiraEnrichedIssue], patterns: dict[str, re.Pattern[str]]
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    keys: dict[str, list[str]] = {}
    for row in rows:
        text = _row_text(row)
        for name, pattern in patterns.items():
            if pattern.search(text):
                counts[name] += 1
                keys.setdefault(name, []).append(row.jira_key)
    return [
        {"name": name, "issue_count": count, "representative_keys": keys[name][:5]}
        for name, count in counts.most_common(20)
    ]


def _is_bug_row(row: JiraEnrichedIssue) -> bool:
    issue_type = str(row.issue_type or "").strip().casefold()
    return issue_type in {"bug", "defect"} or "bug" in issue_type or "defect" in issue_type


def _is_problem_report_row(row: JiraEnrichedIssue) -> bool:
    return _is_bug_row(row) or bool(_PROBLEM_REPORT_PATTERN.search(_row_text(row)))


def _add_share(items: list[dict[str, Any]], denominator: int) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "problem_report_share_percent": round(
                (int(item["issue_count"]) / max(denominator, 1)) * 100, 1
            ),
        }
        for item in items
    ]


def _bug_concentrations(problem_rows: list[JiraEnrichedIssue]) -> dict[str, list[dict[str, Any]]]:
    count = len(problem_rows)
    return {
        "by_component": _add_share(_count_issue_values(problem_rows, "components"), count),
        "by_product_area": _add_share(_count_product_areas(problem_rows), count),
        "by_workflow": _add_share(_count_issue_values(problem_rows, "affected_features"), count),
        "by_output": _add_share(_count_issue_values(problem_rows, "affected_outputs"), count),
        "by_bug_type": _add_share(_count_pattern_signals(problem_rows, _BUG_TYPE_PATTERNS), count),
    }


def _build_regression_recommendations(
    bug_count: int,
    bug_types: list[dict[str, Any]],
    product_areas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for item in bug_types[:8]:
        name = item["name"]
        exploratory = _EXPLORATORY_RECIPES.get(name) or (
            f"Retest the current Jira flow plus positive, negative, recovery, persistence, and adjacent {name.lower()} paths."
        )
        recommendations.append(
            {
                "area": name,
                "priority": "P0" if item["issue_count"] >= max(3, round(bug_count * 0.2)) else "P1",
                "recommendation": exploratory,
                "issue_count": item["issue_count"],
                "problem_report_share_percent": item.get("problem_report_share_percent", 0.0),
                "representative_keys": item["representative_keys"],
            }
        )
    for item in product_areas[:5]:
        recommendations.append(
            {
                "area": item["name"],
                "priority": "P1",
                "recommendation": (
                    f"Run the current change against shared {item['name']} entry points, configurations, roles, "
                    "persisted state, and backward-compatible workflows represented by the cited Jira keys."
                ),
                "issue_count": item["issue_count"],
                "problem_report_share_percent": item.get("problem_report_share_percent", 0.0),
                "representative_keys": item["representative_keys"],
            }
        )
    return recommendations[:12]


def _build_test_data_recommendations(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "data_pattern": item["name"],
            "recommendation": _TEST_DATA_RECIPES[item["name"]],
            "issue_count": item["issue_count"],
            "representative_keys": item["representative_keys"],
        }
        for item in signals
        if item["name"] in _TEST_DATA_RECIPES
    ][:12]


def _build_exploratory_recommendations(problem_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "risk_pattern": item["name"],
            "recommendation": _EXPLORATORY_RECIPES[item["name"]],
            "issue_count": item["issue_count"],
            "representative_keys": item["representative_keys"],
        }
        for item in problem_types
        if item["name"] in _EXPLORATORY_RECIPES
    ][:10]


def _row_product_areas(row: JiraEnrichedIssue) -> set[str]:
    areas: set[str] = set()
    for component in _list(row.components):
        mapped = _PRODUCT_AREA_ALIASES.get(component.casefold())
        if mapped:
            areas.add(mapped)
    domain = str(row.domain or "").strip().casefold()
    mapped_domain = _PRODUCT_AREA_ALIASES.get(domain)
    if mapped_domain:
        areas.add(mapped_domain)
    return areas


def _count_product_areas(rows: list[JiraEnrichedIssue]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    keys: dict[str, list[str]] = {}
    for row in rows:
        for area in _row_product_areas(row):
            counts[area] += 1
            keys.setdefault(area, []).append(row.jira_key)
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
    known_domains = sum(1 for row in rows if str(row.domain or "unknown").casefold() != "unknown")
    product_areas = _count_product_areas(rows)
    problem_types = _count_pattern_signals(rows, _PROBLEM_TYPE_PATTERNS)
    content_data_signals = _count_content_data_signals(rows)
    bug_rows = [row for row in rows if _is_bug_row(row)]
    problem_rows = [row for row in rows if _is_problem_report_row(row)]
    bug_concentrations = _bug_concentrations(problem_rows)
    bug_taxonomy = bug_concentrations["by_bug_type"]
    product_area_covered_count = sum(1 for row in rows if _row_product_areas(row))
    return {
        "customer_name": customer_name,
        "customer_key": _slug(customer_name),
        "issue_count": len(rows),
        "bug_issue_count": len(bug_rows),
        "bug_issue_percent": round((len(bug_rows) / max(len(rows), 1)) * 100, 1),
        "problem_report_count": len(problem_rows),
        "problem_report_percent": round((len(problem_rows) / max(len(rows), 1)) * 100, 1),
        "issue_types": _count_scalar(rows, "issue_type"),
        "problem_types": problem_types,
        "bug_taxonomy": bug_taxonomy,
        "bug_concentrations": bug_concentrations,
        "components": _count_issue_values(rows, "components"),
        "product_areas": product_areas,
        "domains": _count_scalar(rows, "domain"),
        "workflows": _count_issue_values(rows, "affected_features"),
        "affected_outputs": _count_issue_values(rows, "affected_outputs"),
        "dita_entities": _count_issue_values(rows, "dita_entities"),
        "content_data_signals": content_data_signals,
        "classification_quality": {
            "domain_classified_count": known_domains,
            "domain_unknown_count": len(rows) - known_domains,
            "domain_coverage_percent": round((known_domains / max(len(rows), 1)) * 100, 1),
            "product_area_covered_count": product_area_covered_count,
            "product_area_unclassified_count": len(rows) - product_area_covered_count,
            "product_area_coverage_percent": round(
                (product_area_covered_count / max(len(rows), 1)) * 100, 1
            ),
        },
        "failure_areas": failures,
        "automation_signals": automation,
        "resolution_patterns": resolutions,
        "regression_recommendations": _build_regression_recommendations(
            len(problem_rows), bug_taxonomy, bug_concentrations["by_product_area"]
        ),
        "test_data_recommendations": _build_test_data_recommendations(content_data_signals),
        "exploratory_recommendations": _build_exploratory_recommendations(problem_types),
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
            f"{_render_frequency(profile['issue_types'])}\nProblem patterns: "
            f"{_render_frequency(profile['problem_types'])}\nProduct areas: "
            f"{_render_frequency(profile['product_areas'])}\nContent and data patterns: "
            f"{_render_frequency(profile['content_data_signals'])}\n{boundary}",
        ),
        (
            "customer_profile_failures_automation_resolutions",
            f"{customer} repeated failure/risk areas: {_render_frequency(profile['failure_areas'])}\n"
            f"Automation signals: {_render_frequency(profile['automation_signals'])}\n"
            f"Resolution patterns: {_render_frequency(profile['resolution_patterns'])}\n{boundary}",
        ),
        (
            "customer_profile_bug_taxonomy",
            f"{customer} reported-problem taxonomy from {profile['problem_report_count']} failure-like Jira keys "
            f"({profile['problem_report_percent']}% of this customer corpus), including "
            f"{profile['bug_issue_count']} native Bug/Defect keys: {_render_frequency(profile['bug_taxonomy'])}\n"
            f"Counts describe the Jira corpus, not feature usage. {boundary}",
        ),
        (
            "customer_profile_bug_concentrations",
            f"{customer} bug concentration by product area: "
            f"{_render_frequency(profile['bug_concentrations']['by_product_area'])}\n"
            f"By component: {_render_frequency(profile['bug_concentrations']['by_component'])}\n"
            f"By workflow: {_render_frequency(profile['bug_concentrations']['by_workflow'])}\n"
            f"By output: {_render_frequency(profile['bug_concentrations']['by_output'])}\n{boundary}",
        ),
        (
            "customer_profile_regression_recommendations",
            f"{customer} Jira-derived regression recommendations: "
            f"{json.dumps(profile['regression_recommendations'], ensure_ascii=False)}\n"
            f"Recommendations are risk-guided exploration, not acceptance criteria. {boundary}",
        ),
        (
            "customer_profile_test_data_exploration",
            f"{customer} Jira-derived test-data recommendations: "
            f"{json.dumps(profile['test_data_recommendations'], ensure_ascii=False)}\n"
            f"Additional exploratory coverage: {json.dumps(profile['exploratory_recommendations'], ensure_ascii=False)}\n"
            f"Use only recommendations relevant to the current Jira. {boundary}",
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
            slug = profile["customer_key"]
            profile_hash = hashlib.sha256(
                json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            row = db.query(JiraCustomerProfile).filter(JiraCustomerProfile.customer_key == slug).first()
            changed = row is None or row.profile_hash != profile_hash
            approval_status = "draft" if changed or row is None else row.approval_status
            documents = _profile_documents(profile)
            embeddings = embed_texts_batched([text for _, text in documents], batch_size=16)
            if embeddings is None:
                results[customer] = {"status": "failed", "error": "embedding batch failed"}
                continue
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
                    "bug_taxonomy": json.dumps([item["name"] for item in profile["bug_taxonomy"][:20]], ensure_ascii=False),
                    "bug_issue_count": profile["bug_issue_count"],
                    "problem_report_count": profile["problem_report_count"],
                    "enrich_entities": json.dumps([item["name"] for item in profile["dita_entities"][:20]], ensure_ascii=False),
                    "content_data_signals": json.dumps(
                        [item["name"] for item in profile["content_data_signals"][:20]], ensure_ascii=False
                    ),
                    "enrich_outputs": json.dumps([item["name"] for item in profile["affected_outputs"][:20]], ensure_ascii=False),
                    "aggregate_context": True,
                    "direct_assertion_allowed": False,
                    "approval_status": approval_status,
                    "reviewed_customer_profile": approval_status == "approved",
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
            if row is None:
                row = JiraCustomerProfile(customer_key=slug)
                db.add(row)
            for key, value in profile.items():
                if key != "customer_key":
                    setattr(row, key, value)
            row.profile_version = PROFILE_VERSION
            row.profile_hash = profile_hash
            if changed:
                row.approval_status = "draft"
                row.approved_by = None
                row.approved_at = None
                row.review_notes = None
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
            "bug_issue_count": row.bug_issue_count,
            "bug_issue_percent": row.bug_issue_percent,
            "problem_report_count": row.problem_report_count,
            "problem_report_percent": row.problem_report_percent,
            "issue_types": row.issue_types or [],
            "problem_types": row.problem_types or [],
            "bug_taxonomy": row.bug_taxonomy or [],
            "bug_concentrations": row.bug_concentrations or {},
            "components": row.components or [],
            "product_areas": row.product_areas or [],
            "domains": row.domains or [],
            "workflows": row.workflows or [],
            "affected_outputs": row.affected_outputs or [],
            "dita_entities": row.dita_entities or [],
            "content_data_signals": row.content_data_signals or [],
            "classification_quality": row.classification_quality or {},
            "failure_areas": row.failure_areas or [],
            "automation_signals": row.automation_signals or [],
            "resolution_patterns": row.resolution_patterns or [],
            "regression_recommendations": row.regression_recommendations or [],
            "test_data_recommendations": row.test_data_recommendations or [],
            "exploratory_recommendations": row.exploratory_recommendations or [],
            "representative_keys": row.representative_keys or [],
            "profile_version": row.profile_version,
            "profile_hash": row.profile_hash,
            "approval_status": row.approval_status,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "review_notes": row.review_notes,
            "evidence_boundary": "Aggregate Jira-corpus context only; direct Jira evidence is required for assertions.",
            "rebuilt_at": row.rebuilt_at.isoformat() if row.rebuilt_at else None,
        }
    finally:
        db.close()


def set_customer_profile_approval(
    customer: str, *, status: str, reviewer: str, notes: str = ""
) -> dict[str, Any] | None:
    normalized_status = status.strip().casefold()
    if normalized_status not in {"draft", "approved", "rejected"}:
        raise ValueError("Approval status must be draft, approved, or rejected")
    db = SessionLocal()
    try:
        row = db.query(JiraCustomerProfile).filter(JiraCustomerProfile.customer_key == _slug(customer)).first()
        if row is None:
            return None
        row.approval_status = normalized_status
        row.approved_by = reviewer[:120] if normalized_status == "approved" else None
        row.approved_at = datetime.utcnow() if normalized_status == "approved" else None
        row.review_notes = notes.strip()[:4000] or None
        db.commit()
        update_documents_metadata(
            CHROMA_COLLECTION_JIRA_QA,
            {"jira_key": f"CUSTOMER-PROFILE-{row.customer_key.upper()}"},
            {
                "approval_status": row.approval_status,
                "reviewed_customer_profile": row.approval_status == "approved",
                "profile_version": row.profile_version,
                "profile_hash": row.profile_hash or "",
            },
        )
        return get_customer_profile(customer)
    finally:
        db.close()
