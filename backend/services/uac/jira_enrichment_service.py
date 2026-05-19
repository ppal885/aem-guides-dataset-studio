"""Jira enrichment mapping for Requirement Intelligence (wraps ``JiraEnrichedDocument``)."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

# Domains expected by enterprise UAC intelligence (normalize unknown → unknown)
INTELLIGENCE_DOMAINS: frozenset[str] = frozenset(
    {
        "assets",
        "aem_sites",
        "baseline",
        "conref",
        "ditaval",
        "editor",
        "glossary",
        "image_rendition",
        "keyref",
        "metadata",
        "migration",
        "native_pdf",
        "performance",
        "post_processing",
        "publishing",
        "subject_scheme",
        "uuid",
        "unknown",
    }
)


def normalized_domain(domain: str | None) -> str:
    d = (domain or "unknown").strip().lower()
    return d if d in INTELLIGENCE_DOMAINS else "unknown"


def enrichment_to_intelligence_dict(en: JiraEnrichedDocument) -> dict[str, Any]:
    """Structured enrichment payload aligned with PM/QA/Dev UAC discussion."""

    d = en.model_dump()
    dom = normalized_domain(en.domain)
    return {
        "jira_key": str(d.get("jira_key") or ""),
        "summary": str(d.get("summary") or ""),
        "description": str(d.get("description") or ""),
        "labels": list(d.get("labels") or []),
        "components": list(d.get("components") or []),
        "issue_type": str(d.get("issue_type") or ""),
        "priority": str(d.get("priority") or ""),
        "status": str(d.get("status") or ""),
        "customer_names": list(d.get("customer_names") or []),
        "domain": dom,
        "sub_domain": str(d.get("sub_domain") or "").strip() or None,
        "affected_outputs": list(d.get("affected_outputs") or []),
        "dita_entities": list(d.get("dita_entities") or []),
        "symptoms": list(d.get("symptoms") or []),
        "expected_behavior": str(d.get("expected_behavior") or ""),
        "actual_behavior": str(d.get("actual_behavior") or ""),
        "risk_tags": list(d.get("qa_risk_tags") or []),
        "automation_fit": str(d.get("automation_fit") or ""),
        "missing_requirements": list(d.get("missing_info") or []),
        "enrichment_debug": dict(d.get("enrichment_debug") or {}),
    }


def classification_from_enrichment(en: JiraEnrichedDocument) -> dict[str, Any]:
    row = enrichment_to_intelligence_dict(en)
    return {
        "jira_key": row["jira_key"],
        "domain": row["domain"],
        "sub_domain": row["sub_domain"],
        "issue_type": row["issue_type"],
        "priority": row["priority"],
        "status": row["status"],
        "customer_names": row["customer_names"],
        "affected_outputs": row["affected_outputs"],
        "dita_entities": row["dita_entities"],
        "labels": row["labels"][:40],
        "components": row["components"][:30],
        "risk_tags": row["risk_tags"][:25],
    }


__all__ = ["INTELLIGENCE_DOMAINS", "classification_from_enrichment", "enrichment_to_intelligence_dict", "normalized_domain"]
