"""Backward compatibility and migration risk signals (evidence-grounded, conservative)."""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore

_BREAKING_RE = re.compile(
    r"\b(breaking|bc\b|backward compat|backwards compat|regression|behavior change|changed default)\b",
    re.I,
)
_SCHEMA_RE = re.compile(r"\b(schema|dtd|rng|specialization|specializ|shell)\b", re.I)


def analyze_backward_compatibility(
    en: JiraEnrichedDocument,
    similar_payload: list[dict[str, Any]],
    store: RequirementEvidenceStore,
) -> dict[str, Any]:
    eid = store.add(
        "current_jira",
        f"Backward compatibility scan {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )
    text = f"{en.summary} {en.description}"[:12000]
    behavior: list[str] = []
    publishing: list[str] = []
    schema: list[str] = []
    migration: list[str] = []
    customer: list[str] = []

    if _BREAKING_RE.search(text):
        behavior.append(
            "Ticket language suggests behavioral or compatibility sensitivity — enumerate supported upgrade paths."
        )
    if _SCHEMA_RE.search(text):
        schema.append("Schema/specialization mentioned — validate older content instances still parse/resolve.")

    if "migration" in text.lower():
        migration.append("Migration context — define rollback criteria and content volume class (e.g. repo size).")

    if en.customer_names:
        customer.append(
            "Named customers elevate risk for undocumented workflow dependencies — require explicit sign-off scope."
        )

    evidence_ids: list[str] = [eid]
    for row in similar_payload[:3]:
        sk = str(row.get("jira_key") or "")
        if not sk:
            continue
        e_sim = store.add(
            "similar_jira",
            f"Historical ticket {sk} for compatibility context",
            sk,
            {"excerpt": (row.get("document_excerpt") or "")[:400]},
        )
        evidence_ids.append(e_sim)
        publishing.append(f"Cross-check publishing outputs against patterns observed in {sk} (indexed chunk).")

    return {
        "behavior_change_signals": behavior[:8],
        "publishing_compatibility_risks": publishing[:8],
        "schema_compatibility_risks": schema[:8],
        "migration_risks": migration[:8],
        "customer_workflow_risks": customer[:6],
        "evidence": evidence_ids[:12],
    }


__all__ = ["analyze_backward_compatibility"]
