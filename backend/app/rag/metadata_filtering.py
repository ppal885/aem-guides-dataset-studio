"""Metadata filtering helpers for Jira QA retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JiraMetadataCriteria:
    customer: str | None = None
    feature: str | None = None
    issue_type: str | None = None
    environment: str | None = None
    editor_type: str | None = None
    output_type: str | None = None
    time_window_days: int | None = None
    source_jira_key: str | None = None
    escalation_only: bool = False

    def query_text(self) -> str:
        return " ".join(
            x
            for x in (
                self.customer,
                self.feature,
                self.issue_type,
                self.environment,
                self.editor_type,
                self.output_type,
                "customer escalation" if self.escalation_only else None,
            )
            if x
        ).strip()


def normalize_token(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def normalize_compact(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def parse_json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return [x.strip() for x in re.split(r"[,;|]", text) if x.strip()]


def metadata_text(meta: dict[str, Any], document: str = "") -> str:
    parts = [document or ""]
    for key in (
        "customer",
        "customer_key",
        "customer_labels",
        "labels",
        "enrich_customers",
        "enrich_entities",
        "enrich_outputs",
        "enrich_domain",
        "enrich_sub_domain",
        "issue_type",
        "component",
        "components",
        "environment",
        "editor_type",
        "build_type",
        "fix_version",
        "title",
        "summary",
    ):
        value = meta.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(x) for x in value)
        elif value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def metadata_contains(value: str | None, meta: dict[str, Any], document: str = "", *, fields: tuple[str, ...] = ()) -> bool:
    if not value:
        return True
    target = normalize_token(value)
    target_compact = normalize_compact(value)
    haystacks: list[str] = []
    if fields:
        for field in fields:
            raw = meta.get(field)
            if isinstance(raw, (list, tuple)):
                haystacks.extend(str(x) for x in raw)
            else:
                haystacks.append(str(raw or ""))
                haystacks.extend(parse_json_list(raw))
    else:
        haystacks = [metadata_text(meta, document)]
    for item in haystacks:
        norm = normalize_token(item)
        compact = normalize_compact(item)
        # The requested value must be contained in the metadata value, never the reverse: a short
        # label such as "ID" or "Org" in the haystack would otherwise satisfy any customer or
        # environment filter.
        if target and norm and _contains_value(target, norm):
            return True
        if target_compact and compact and _contains_value(target_compact, compact):
            return True
    return False


def _contains_value(needle: str, haystack: str) -> bool:
    """``needle`` equals ``haystack`` or appears in it as a whole word.

    Short values (under four characters, such as ``EY`` or ``GM``) must match a whole word so that
    ``ey`` never matches ``keyref``; longer values may also match inside a compact token
    (``experienceleague`` in ``experienceleaguecloud``).
    """
    if needle == haystack:
        return True
    if len(needle) < 4:
        return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", haystack) is not None
    return needle in haystack


def metadata_has_escalation(meta: dict[str, Any], document: str = "") -> bool:
    text = normalize_token(
        " ".join(
            [
                metadata_text(meta, document),
                " ".join(parse_json_list(meta.get("labels"))),
                " ".join(parse_json_list(meta.get("customer_labels"))),
            ]
        )
    )
    compact = normalize_compact(text)
    return any(
        needle in text or needle.replace(" ", "") in compact
        for needle in (
            "customer escalation",
            "p1 escalation",
            "sev 1",
            "sev1",
            "escalation",
            "blocker",
            "critical",
        )
    )


def matches_metadata(criteria: JiraMetadataCriteria, meta: dict[str, Any], document: str = "") -> bool:
    """Match only explicit hard constraints.

    ``feature`` can be sourced from domain metadata, which is frequently unknown.
    It therefore remains a reranking signal in :func:`metadata_score` and never
    excludes a semantically relevant Jira here.
    """
    checks = [
        metadata_contains(
            criteria.customer,
            meta,
            document,
            fields=("customer", "customer_key", "customer_labels", "labels", "enrich_customers"),
        ),
        metadata_contains(criteria.issue_type, meta, document, fields=("issue_type",)),
        metadata_contains(criteria.environment, meta, document, fields=("environment", "labels", "build_type")),
        metadata_has_escalation(meta, document) if criteria.escalation_only else True,
    ]
    return all(checks)


def metadata_score(criteria: JiraMetadataCriteria, meta: dict[str, Any], document: str = "") -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    weighted = (
        ("customer", criteria.customer, 0.3, ("customer", "customer_key", "customer_labels", "labels", "enrich_customers")),
        ("feature", criteria.feature, 0.3, ("enrich_domain", "enrich_sub_domain", "enrich_entities", "enrich_outputs", "labels", "title", "summary")),
        ("issue_type", criteria.issue_type, 0.15, ("issue_type",)),
        ("environment", criteria.environment, 0.15, ("environment", "labels", "build_type")),
        ("output_type", criteria.output_type, 0.1, ("enrich_outputs", "component", "components", "labels", "title")),
    )
    for label, value, weight, fields in weighted:
        if value and metadata_contains(value, meta, document, fields=fields):
            score += weight
            reasons.append(f"{label}_match")
    if criteria.escalation_only and metadata_has_escalation(meta, document):
        score += 0.1
        reasons.append("customer_escalation_match")
    return min(score, 1.0), reasons
