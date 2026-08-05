"""Build aggregate customer behavior profiles from enriched Jira CSV issues."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Iterable

from app.db.jira_enrichment_models import JiraEnrichedIssue
from app.db.session import SessionLocal
from app.services.embedding_service import embed_texts_batched
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, add_documents


PROFILE_VERSION = "jira-customer-profile-v1"


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _counter(rows: list[Any], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(_values(getattr(row, field, None)))
    return counts


def _scalar_counter(rows: list[Any], field: str) -> Counter[str]:
    return Counter(str(getattr(row, field, None) or "Unspecified") for row in rows)


def _format_counts(counts: Counter[str], *, limit: int = 12) -> str:
    return ", ".join(f"{name} ({count})" for name, count in counts.most_common(limit)) or "No signal"


def _issue_blob(row: Any) -> str:
    values = [
        getattr(row, "summary", ""),
        getattr(row, "domain", ""),
        getattr(row, "sub_domain", ""),
        *_values(getattr(row, "components", None)),
        *_values(getattr(row, "affected_outputs", None)),
        *_values(getattr(row, "affected_features", None)),
        *_values(getattr(row, "dita_entities", None)),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _jira_categories(row: Any) -> set[str]:
    blob = _issue_blob(row)
    categories: set[str] = set()
    rules = {
        "Publishing failure or output correctness": r"publish|dita-ot|aem sites|output|generation|log",
        "DITA references, links, or dependency handling": r"keyref|key-ref|topicref|mapref|conref|reference|section link|parent map",
        "Baseline, versioning, or incremental publishing": r"baseline|version-history|incremental",
        "Asset, repository, or metadata handling": r"asset|repository|metadata|dc:format|mimetype|property|deletion|move operation",
        "Performance or scalability": r"performance|20\+ min|thousands|post processing|indexing|stuck",
        "Authoring or Oxygen integration": r"oxygen|authoring|editor|navigation panel|loading the dita content",
        "Enhancement or product behavior request": r"enhancement|implement|categorize|retain temporary|overlaying",
    }
    for category, pattern in rules.items():
        if re.search(pattern, blob):
            categories.add(category)
    return categories or {"Other customer-reported behavior"}


def _data_types(row: Any) -> set[str]:
    blob = _issue_blob(row)
    data_types: set[str] = set()
    rules = {
        "DITA maps, topics, and nested topic structures": r"ditamap|dita document|dita content|topicref|mapref|nested topic|parent map",
        "DITA references and reusable content": r"keyref|key-ref|keydef|conref|reference",
        "Conditional content and DITAVAL configuration": r"ditaval",
        "Metadata, MIME types, and asset properties": r"metadata|dc:format|mimetype|asset propert|navtitle",
        "Baselines, versions, and repository history": r"baseline|version-history",
        "Publishing presets, logs, and generated output": r"output preset|dita-ot|aem sites|html5|publishworkflow|publish workflow|publish log",
        "DAM assets, folders, and repository relationships": r"asset|folder|repository|guidesparentmaps|guidesdirectparentmaps",
        "Oxygen editor/plugin integration data": r"oxygen|plugin|navigation panel",
    }
    for data_type, pattern in rules.items():
        if re.search(pattern, blob):
            data_types.add(data_type)
    return data_types or {"General AEM Guides content or configuration"}


def build_customer_profile_chunks(
    rows: Iterable[Any],
    *,
    customer: str,
    source_file_hash: str,
) -> list[dict[str, Any]]:
    issues = list(rows)
    if not issues:
        return []

    customer_key = re.sub(r"[^a-z0-9]+", "_", customer.lower()).strip("_") or "customer"
    jira_categories: Counter[str] = Counter()
    data_types: Counter[str] = Counter()
    for issue in issues:
        jira_categories.update(_jira_categories(issue))
        data_types.update(_data_types(issue))

    components = _counter(issues, "components")
    domains = _scalar_counter(issues, "domain")
    outputs = _counter(issues, "affected_outputs")
    features = _counter(issues, "affected_features")
    entities = _counter(issues, "dita_entities")
    priorities = _scalar_counter(issues, "priority")
    statuses = _scalar_counter(issues, "status")
    resolutions = _scalar_counter(issues, "resolution")
    issue_types = _scalar_counter(issues, "issue_type")
    risks = _counter(issues, "qa_risk_tags")
    issue_keys = sorted(str(getattr(issue, "jira_key", "")) for issue in issues if getattr(issue, "jira_key", ""))
    evidence = ", ".join(issue_keys)

    documents = {
        "customer_area_profile": (
            f"{customer} customer Jira product-area profile based on {len(issues)} labeled issues.\n\n"
            f"Most affected components: {_format_counts(components)}.\n"
            f"Most observed domains: {_format_counts(domains)}.\n"
            f"Affected outputs: {_format_counts(outputs)}.\n"
            f"Affected workflows/features: {_format_counts(features)}.\n"
            "Interpretation: counts describe areas represented in this Jira dataset, not measured production usage."
        ),
        "customer_jira_type_profile": (
            f"{customer} reported Jira pattern profile based on {len(issues)} labeled issues. Categories may overlap.\n\n"
            f"Reported Jira issue types: {_format_counts(issue_types)}.\n"
            f"Behavior categories: {_format_counts(jira_categories)}.\n"
            f"Priority mix: {_format_counts(priorities)}.\n"
            f"Status mix: {_format_counts(statuses)}.\n"
            f"Resolution mix: {_format_counts(resolutions)}."
        ),
        "customer_data_workflow_profile": (
            f"{customer} data and workflow profile inferred conservatively from {len(issues)} labeled Jira issues. Categories may overlap.\n\n"
            f"Content and configuration types: {_format_counts(data_types)}.\n"
            f"Observed DITA/product entities: {_format_counts(entities, limit=18)}.\n"
            f"Observed outputs: {_format_counts(outputs)}.\n"
            "These signals show the kinds of data involved in reported cases; they do not prove the customer's complete content inventory."
        ),
        "customer_qa_risk_profile": (
            f"{customer} QA and regression profile based on {len(issues)} labeled Jira issues.\n\n"
            f"Risk tags: {_format_counts(risks)}.\n"
            f"High-priority reports: Critical ({priorities.get('Critical', 0)}), Blocker ({priorities.get('Blocker', 0)}), Major ({priorities.get('Major', 0)}).\n"
            f"Primary regression targets: {_format_counts(jira_categories, limit=7)}.\n"
            "Use these areas to prioritize publishing, reference integrity, baseline, metadata, repository cleanup, performance, and editor-integration coverage when relevant."
        ),
    }

    chunks: list[dict[str, Any]] = []
    for chunk_type, document in documents.items():
        chunk_id = f"customer-profile::{customer_key}::{source_file_hash[:16]}::{chunk_type}::{PROFILE_VERSION}"
        chunks.append(
            {
                "id": chunk_id,
                "document": document + f"\n\nEvidence Jira keys: {evidence}",
                "metadata": {
                    "source_type": "jira_customer_learning",
                    "customer": customer[:200],
                    "customer_key": customer_key[:120],
                    "customer_labels": json.dumps([customer], ensure_ascii=False),
                    "customer_type": "enterprise",
                    "customer_escalation": 0,
                    "chunk_type": chunk_type,
                    "source_file_hash": source_file_hash[:64],
                    "issue_count": len(issues),
                    "profile_version": PROFILE_VERSION,
                    "labels": json.dumps([customer], ensure_ascii=False),
                },
            }
        )
    return chunks


def index_customer_jira_profile(
    *,
    customer: str,
    source_file_hash: str,
    required_label: str | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        rows = (
            db.query(JiraEnrichedIssue)
            .filter(JiraEnrichedIssue.source_file_hash == source_file_hash)
            .order_by(JiraEnrichedIssue.jira_key.asc())
            .all()
        )
    finally:
        db.close()

    if required_label:
        expected = required_label.casefold()
        invalid = [
            row.jira_key
            for row in rows
            if expected not in {label.casefold() for label in _values(row.labels)}
        ]
        if invalid:
            raise ValueError(f"Issues missing required label {required_label}: {', '.join(invalid[:20])}")

    chunks = build_customer_profile_chunks(rows, customer=customer, source_file_hash=source_file_hash)
    if not chunks:
        return {"customer": customer, "issues": 0, "chunks": 0, "indexed": False}

    embeddings = embed_texts_batched([chunk["document"] for chunk in chunks], batch_size=16)
    if embeddings is None:
        raise RuntimeError("Embedding model is not available")
    stored = add_documents(
        CHROMA_COLLECTION_JIRA_QA,
        [chunk["id"] for chunk in chunks],
        [chunk["document"] for chunk in chunks],
        [chunk["metadata"] for chunk in chunks],
        [embeddings[index].tolist() for index in range(len(chunks))],
    )
    if not stored:
        raise RuntimeError("Customer Jira profile Chroma upsert failed")
    return {
        "customer": customer,
        "source_file_hash": source_file_hash,
        "issues": len(rows),
        "chunks": len(chunks),
        "chunk_ids": [chunk["id"] for chunk in chunks],
        "indexed": True,
    }
