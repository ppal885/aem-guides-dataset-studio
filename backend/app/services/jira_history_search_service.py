"""Reusable, deterministic Jira-history retrieval for MCP and test-plan flows."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.customer_tokens import clean_customer_tokens
from app.services.jira_component_metadata_service import (
    CANONICAL_JIRA_COMPONENTS,
    canonical_component_name,
)


def _json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(value).strip() for value in raw if str(value).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(value).strip() for value in data if str(value).strip()]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return [text]


def _customer_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def search_jira_history_evidence(
    query: str,
    *,
    component: str = "",
    customer: str = "",
    exclude_jira_key: str = "",
    top_k: int = 10,
) -> dict[str, Any]:
    """Search indexed Jira evidence and expose whether retrieval actually ran."""
    query_text = str(query or "").strip()
    if not query_text:
        return {"error": "Provide a 'query' describing the defect or behaviour to search for."}

    requested_component = str(component or "").strip()
    canonical_component = canonical_component_name(requested_component)
    if requested_component and not canonical_component:
        return {
            "error": "Unsupported Jira component.",
            "component": requested_component,
            "allowed_components": list(CANONICAL_JIRA_COMPONENTS),
        }

    customer_filter = str(customer or "").strip()
    excluded_key = str(exclude_jira_key or "").strip().upper()
    try:
        bounded_top_k = max(1, min(int(top_k or 10), 30))
    except (TypeError, ValueError):
        bounded_top_k = 10

    from app.services.embedding_service import is_embedding_available
    from app.services.vector_store_service import (
        CHROMA_COLLECTION_JIRA_QA,
        get_collection_count,
        is_chroma_available,
    )

    chroma_ok = is_chroma_available()
    embedding_ok = is_embedding_available()
    indexed_chunks = get_collection_count(CHROMA_COLLECTION_JIRA_QA) if chroma_ok else 0
    searched = bool(chroma_ok and embedding_ok and indexed_chunks > 0)

    hits: list[dict[str, Any]] = []
    if searched:
        from app.services.jira_qa_retrieval_service import semantic_search_jira_qa

        hits = semantic_search_jira_qa(
            query_text,
            top_k=bounded_top_k + (1 if excluded_key else 0),
            exclude_jira_key=excluded_key or None,
            customer=customer_filter or None,
            base_components=[canonical_component] if canonical_component else None,
            customer_names=[customer_filter] if customer_filter else None,
        )

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if len(results) >= bounded_top_k:
            break
        jira_key = str(hit.get("jira_key") or "").strip().upper()
        if not jira_key or jira_key in seen or (excluded_key and jira_key == excluded_key):
            continue
        seen.add(jira_key)
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        learning = hit.get("learning") if isinstance(hit.get("learning"), dict) else {}
        matching_components = hit.get("matching_components") or []
        raw_customers: list[str] = []
        for field in (
            "customer_cohorts",
            "enrich_customers",
            "customer_names",
            "smart_customer_names",
            "customer_labels",
        ):
            raw_customers.extend(_json_list(metadata.get(field)))
        raw_customers.extend(_json_list(metadata.get("customer")))
        clean_customers = clean_customer_tokens(raw_customers)
        scalar_customer = clean_customer_tokens([metadata.get("customer") or ""])
        returned_customers = list(
            dict.fromkeys([*scalar_customer, *clean_customers])
        )
        if customer_filter and _customer_identity(customer_filter) not in {
            _customer_identity(value) for value in returned_customers
        }:
            continue
        results.append(
            {
                "jira_key": jira_key,
                "summary": hit.get("title") or metadata.get("title") or "",
                "status": metadata.get("status") or "",
                "resolution": metadata.get("resolution") or "",
                "components": list(matching_components) or _json_list(metadata.get("components")),
                "customer": (
                    scalar_customer[0]
                    if scalar_customer
                    else returned_customers[0]
                    if returned_customers
                    else ""
                ),
                "customers": returned_customers,
                "labels": _json_list(metadata.get("labels")),
                "fix_versions": _json_list(metadata.get("fix_versions")),
                "affected_versions": _json_list(metadata.get("affected_versions")),
                "score": round(float(hit.get("score") or 0.0), 4),
                "why_similar": hit.get("why_similar") or "",
                "historical_outcome": learning.get("historical_outcome") or "",
                "is_verified_fix": learning.get("is_verified_fix"),
                "root_cause": learning.get("root_cause") or "",
                "qa_oracle": learning.get("qa_oracle") or "",
                "observed_problem": learning.get("observed_problem") or "",
            }
        )

    if not searched:
        note = (
            f"jira_qa was NOT searched (chroma_available={chroma_ok}, "
            f"embedding_available={embedding_ok}, indexed_chunks={indexed_chunks}). "
            "Do NOT conclude any ticket is absent from history - retrieval was unavailable."
        )
    elif not results:
        note = (
            f"Searched {indexed_chunks} indexed jira_qa chunks and found no match above threshold for "
            "this query/filters. This means no similar ticket surfaced, NOT that the ticket does "
            "not exist. Broaden the query or intentionally drop the component/customer filter and retry "
            "before asserting there is no history."
        )
    else:
        note = (
            f"Searched {indexed_chunks} indexed jira_qa chunks; returning {len(results)} ranked "
            "matches (most-similar first)."
        )

    return {
        "searched_jira_qa": searched,
        "indexed_chunks": indexed_chunks,
        "component_filter": canonical_component or None,
        "customer_filter": customer_filter or None,
        "match_count": len(results),
        "results": results,
        "note": note,
    }
