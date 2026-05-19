"""Hybrid Jira QA retrieval: metadata boosts, token overlap, vector similarity, rerank, diversity."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from typing import Any

from pydantic import BaseModel, Field

from app.core.structured_logging import get_structured_logger
from app.services.embedding_service import embed_query, is_embedding_available
from app.services.jira_qa_copilot_cache import cache_get_embedding_vector, cache_set_embedding_vector
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, is_chroma_available, query_collection

logger = get_structured_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{3,}", re.I)
_CHUNK_TYPE_WEIGHT: dict[str, float] = {
    "similar_ticket_signals": 0.04,
    "full_ticket_summary": 0.035,
    "customer_problem": 0.035,
    "comments_discussion": 0.015,
    "attachment_log_signals": 0.015,
    "live_jira_snapshot": 0.02,
}

# Enterprise hybrid fusion weights.  Keep these aligned with the documented
# retrieval contract: vector first after metadata gating, then keyword overlap.
_W_VECTOR = float(os.getenv("JIRA_RETRIEVAL_W_VECTOR", "0.45"))
_W_METADATA = float(os.getenv("JIRA_RETRIEVAL_W_METADATA", "0.35"))
_W_KEYWORD = float(os.getenv("JIRA_RETRIEVAL_W_KEYWORD", "0.20"))

# Evidence controls (also read legacy env aliases for compatibility).
MIN_VECTOR_SCORE = float(
    os.getenv("MIN_VECTOR_SCORE", os.getenv("JIRA_UAC_MIN_SIMILARITY_SCORE", os.getenv("MIN_SIMILARITY_SCORE", "0.50")))
)
MIN_METADATA_SCORE = float(os.getenv("MIN_METADATA_SCORE", os.getenv("JIRA_UAC_MIN_METADATA_SCORE", "0.18")))
MIN_FINAL_SCORE = float(
    os.getenv(
        "MIN_FINAL_SCORE",
        os.getenv("JIRA_UAC_MINIMUM_EVIDENCE_THRESHOLD", os.getenv("MINIMUM_EVIDENCE_THRESHOLD", str(MIN_VECTOR_SCORE))),
    )
)
MIN_ENTITY_OVERLAP = int(
    os.getenv("MIN_ENTITY_OVERLAP", os.getenv("JIRA_UAC_MIN_METADATA_OVERLAP", os.getenv("MIN_METADATA_OVERLAP", "1")))
)

# Backward-compatible names used by UAC analyze and existing callers.
JIRA_UAC_MIN_SIMILARITY_SCORE = MIN_VECTOR_SCORE
JIRA_UAC_MINIMUM_EVIDENCE_THRESHOLD = MIN_FINAL_SCORE
JIRA_UAC_MIN_METADATA_OVERLAP = MIN_ENTITY_OVERLAP
JIRA_UAC_MAX_SIMILAR_PER_DOMAIN = int(
    os.getenv("JIRA_UAC_MAX_SIMILAR_PER_DOMAIN", os.getenv("MAX_SIMILAR_PER_DOMAIN", "3"))
)
JIRA_UAC_MIN_STRONG_SIMILAR = int(os.getenv("JIRA_UAC_MIN_STRONG_SIMILAR", "2"))
JIRA_UAC_VECTOR_ONLY_PENALTY = float(os.getenv("JIRA_UAC_VECTOR_ONLY_PENALTY", "0.14"))
JIRA_UAC_ENTITY_MATCH_BOOST = float(os.getenv("JIRA_UAC_ENTITY_MATCH_BOOST", "0.04"))
JIRA_UAC_ENTITY_MATCH_BOOST_CAP = float(os.getenv("JIRA_UAC_ENTITY_MATCH_BOOST_CAP", "0.12"))
JIRA_UAC_OUTPUT_MATCH_BOOST = float(os.getenv("JIRA_UAC_OUTPUT_MATCH_BOOST", "0.06"))
JIRA_UAC_OUTPUT_MATCH_EXTRA = float(os.getenv("JIRA_UAC_OUTPUT_MATCH_EXTRA", "0.03"))
JIRA_MAX_SIMILAR_PER_CUSTOMER = int(os.getenv("JIRA_MAX_SIMILAR_PER_CUSTOMER", "2"))
JIRA_NEAR_DUPLICATE_JACCARD = float(os.getenv("JIRA_NEAR_DUPLICATE_JACCARD", "0.86"))
JIRA_RECENT_REPEAT_PENALTY = float(os.getenv("JIRA_RECENT_REPEAT_PENALTY", "0.06"))
INSUFFICIENT_EVIDENCE_MESSAGE = "Insufficient evidence from indexed Jira data."

_GENERIC_OVERLAP_TOKENS = frozenset(
    {
        "aem",
        "guide",
        "guides",
        "jira",
        "issue",
        "issues",
        "ticket",
        "tickets",
        "bug",
        "bugs",
        "error",
        "failure",
        "failed",
        "fix",
        "fixed",
        "test",
        "tests",
        "testing",
        "regression",
        "customer",
        "content",
        "dita",
        "topic",
        "topics",
        "map",
        "maps",
        "output",
        "publish",
        "publishing",
    }
)
_RECENT_RETURNED_JIRA_KEYS: deque[str] = deque(maxlen=80)


class RetrievedJira(BaseModel):
    """One deduped Jira issue after hybrid retrieval."""

    model_config = {"extra": "forbid"}

    jira_key: str
    title: str = ""
    chunk_type: str = ""
    document: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    vector_score: float = 0.0
    keyword_score: float = 0.0
    metadata_score: float = 0.0
    final_score: float = 0.0
    confidence_score: float = 0.0
    why_similar: str = ""
    matching_entities: list[str] = Field(default_factory=list)
    matching_outputs: list[str] = Field(default_factory=list)
    matching_customers: list[str] = Field(default_factory=list)
    matching_components: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    evidence_overlap_signals: int = 0
    strong_evidence: bool = False
    rejection_reasons: list[dict[str, Any]] = Field(default_factory=list)


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).lower() for x in data if str(x).strip()]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_json_list_preserve(raw: str | None) -> list[str]:
    """Parse JSON list without lowercasing (display / enrichment paths)."""
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _overlap_boost(meta: dict[str, Any], base_labels: set[str], base_components: set[str]) -> float:
    boost = 0.0
    labels = set(_parse_json_list(str(meta.get("labels") or "")))
    comps = set(_parse_json_list(str(meta.get("components") or "")))
    if base_labels & labels:
        boost += 0.04 * min(4, len(base_labels & labels))
    if base_components & comps:
        boost += 0.05 * min(3, len(base_components & comps))
    return min(boost, 0.2)


def _label_intel_boost(meta: dict[str, Any], expanded: frozenset[str]) -> float:
    if not expanded:
        return 0.0
    labels = set(_parse_json_list(str(meta.get("labels") or "")))
    hit = len(expanded & labels)
    if not hit:
        return 0.0
    return min(0.12, 0.028 * min(hit, 5))


def _norm_token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "") if len(m.group(0)) >= 4}


def _norm_domain(d: str | None) -> str:
    s = (d or "").strip().lower().replace(" ", "_").replace("-", "_")
    return s


def _norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _metadata_lists(meta: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    entities = {
        _norm_label(x)
        for x in (
            _parse_json_list_preserve(str(meta.get("enrich_entities") or ""))
            + _parse_json_list_preserve(str(meta.get("smart_dita_entities") or ""))
        )
    }
    outputs = {
        _norm_label(x)
        for x in (
            _parse_json_list_preserve(str(meta.get("enrich_outputs") or ""))
            + _parse_json_list_preserve(str(meta.get("smart_affected_outputs") or ""))
        )
    }
    customers: set[str] = set()
    for x in _parse_json_list_preserve(str(meta.get("enrich_customers") or "")):
        customers.add(_norm_label(x))
    for x in _parse_json_list_preserve(str(meta.get("smart_customer_names") or "")):
        customers.add(_norm_label(x))
    for x in _parse_json_list_preserve(str(meta.get("customer_labels") or "")):
        customers.add(_norm_label(x))
    mc = str(meta.get("customer") or "").strip()
    if mc:
        customers.add(_norm_label(mc))
    return entities, outputs, customers


def _metadata_components(meta: dict[str, Any]) -> set[str]:
    return {_norm_label(x) for x in _parse_json_list_preserve(str(meta.get("components") or "")) if _norm_label(x)}


def _metadata_issue_type(meta: dict[str, Any]) -> str:
    return _norm_label(str(meta.get("issue_type") or meta.get("issuetype") or ""))


def _metadata_sub_domain(meta: dict[str, Any]) -> str:
    return _norm_domain(str(meta.get("enrich_sub_domain") or meta.get("sub_domain") or ""))


def _display_overlap(current: list[str], candidate_norm: set[str]) -> list[str]:
    cur_map = {_norm_label(x): str(x).strip() for x in (current or []) if str(x).strip()}
    return [cur_map[k] for k in cur_map if k in candidate_norm]


def _customer_overlap_display(current_customers: list[str], candidate_customers: set[str]) -> list[str]:
    found: list[str] = []
    for current in current_customers or []:
        cn = _norm_label(current)
        if not cn:
            continue
        for candidate in candidate_customers:
            if cn == candidate or cn in candidate or candidate in cn:
                found.append(str(current).strip())
                break
    return sorted(set(found))


def _keyword_overlap_score(query_tokens: set[str], doc: str, meta: dict[str, Any]) -> float:
    if not query_tokens:
        return 0.0
    blob_parts = [
        doc or "",
        str(meta.get("title") or ""),
        str(meta.get("enrich_domain") or ""),
        str(meta.get("enrich_sub_domain") or ""),
        " ".join(_parse_json_list(str(meta.get("enrich_entities") or ""))),
        " ".join(_parse_json_list(str(meta.get("enrich_outputs") or ""))),
    ]
    doc_tokens = _norm_token_set("\n".join(blob_parts))
    if not doc_tokens:
        return 0.0
    inter = query_tokens & doc_tokens
    union = query_tokens | doc_tokens
    return len(inter) / len(union) if union else 0.0


def _metadata_match_details(
    meta: dict[str, Any],
    *,
    domain: str | None,
    sub_domain: str | None = None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    components: list[str] | None = None,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """Return exact metadata overlaps, score in [0,1], and explanation phrases."""
    reasons: list[str] = []

    dom_m = _norm_domain(str(meta.get("enrich_domain") or "unknown"))
    sub_m = _metadata_sub_domain(meta)
    dom_q = _norm_domain(domain) if domain else ""
    sub_q = _norm_domain(sub_domain) if sub_domain else ""
    issue_q = _norm_label(issue_type or "")
    issue_m = _metadata_issue_type(meta)

    ent_meta, out_meta, cust_meta = _metadata_lists(meta)
    comp_meta = _metadata_components(meta)
    ent_q = {_norm_label(x) for x in dita_entities if str(x).strip()}
    out_q = {_norm_label(x) for x in affected_outputs if str(x).strip()}
    cust_q = {_norm_label(x) for x in customer_names if str(x).strip()}
    comp_q = {_norm_label(x) for x in (components or []) if str(x).strip()}

    ent_overlap = ent_q & ent_meta
    out_overlap = out_q & out_meta
    comp_overlap = comp_q & comp_meta
    customer_overlap_norm: set[str] = set()
    if cust_q and cust_meta:
        for cq in cust_q:
            for cm in cust_meta:
                if cq == cm or cq in cm or cm in cq:
                    customer_overlap_norm.add(cq)
                    break

    domain_match = bool(dom_q and dom_q not in ("", "unknown") and dom_m == dom_q)
    sub_domain_match = bool(sub_q and sub_m and sub_m == sub_q)
    issue_type_match = bool(issue_q and issue_m and issue_q == issue_m)

    scored_parts: list[tuple[str, float, float]] = []
    if dom_q and dom_q not in ("", "unknown"):
        scored_parts.append(("domain", 0.22, 1.0 if domain_match else 0.0))
        if domain_match:
            reasons.append(f"exact domain match ({dom_m.replace('_', ' ')})")
    if sub_q:
        scored_parts.append(("sub_domain", 0.08, 1.0 if sub_domain_match else 0.0))
        if sub_domain_match:
            reasons.append(f"exact sub-domain match ({sub_m.replace('_', ' ')})")
    if ent_q:
        ratio = len(ent_overlap) / max(len(ent_q), 1)
        scored_parts.append(("entities", 0.25, ratio))
        if ent_overlap:
            reasons.append("exact entity overlap: " + ", ".join(sorted(ent_overlap)[:5]))
    if out_q:
        ratio = len(out_overlap) / max(len(out_q), 1)
        scored_parts.append(("outputs", 0.20, ratio))
        if out_overlap:
            reasons.append("exact output overlap: " + ", ".join(sorted(out_overlap)[:5]))
    if cust_q:
        ratio = len(customer_overlap_norm) / max(len(cust_q), 1)
        scored_parts.append(("customers", 0.13, ratio))
        if customer_overlap_norm:
            reasons.append("exact customer overlap: " + ", ".join(sorted(customer_overlap_norm)[:5]))
    if comp_q:
        ratio = len(comp_overlap) / max(len(comp_q), 1)
        scored_parts.append(("components", 0.09, ratio))
        if comp_overlap:
            reasons.append("component overlap: " + ", ".join(sorted(comp_overlap)[:5]))
    if issue_q:
        scored_parts.append(("issue_type", 0.03, 1.0 if issue_type_match else 0.0))
        if issue_type_match:
            reasons.append(f"same issue type ({issue_m})")

    if not scored_parts:
        score = 0.0
    else:
        weight_total = sum(weight for _, weight, _ in scored_parts)
        weighted = sum(weight * value for _, weight, value in scored_parts)
        score = weighted / max(weight_total, 0.0001)

    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "reasons": reasons,
        "domain_match": domain_match,
        "sub_domain_match": sub_domain_match,
        "issue_type_match": issue_type_match,
        "issue_type_query": issue_q,
        "issue_type_candidate": issue_m,
        "entity_overlap": sorted(ent_overlap),
        "output_overlap": sorted(out_overlap),
        "customer_overlap": sorted(customer_overlap_norm),
        "component_overlap": sorted(comp_overlap),
        "query_entities": sorted(ent_q),
        "candidate_entities": sorted(ent_meta),
        "query_outputs": sorted(out_q),
        "candidate_outputs": sorted(out_meta),
        "query_customers": sorted(cust_q),
        "candidate_customers": sorted(cust_meta),
        "query_components": sorted(comp_q),
        "candidate_components": sorted(comp_meta),
        "domain_query": dom_q,
        "domain_candidate": dom_m,
        "sub_domain_query": sub_q,
        "sub_domain_candidate": sub_m,
    }


def _metadata_match_score(
    meta: dict[str, Any],
    *,
    domain: str | None,
    sub_domain: str | None = None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    components: list[str] | None = None,
    issue_type: str | None = None,
) -> tuple[float, list[str]]:
    """Returns score in [0,1] and human-readable signal phrases."""
    details = _metadata_match_details(
        meta,
        domain=domain,
        sub_domain=sub_domain,
        dita_entities=dita_entities,
        affected_outputs=affected_outputs,
        customer_names=customer_names,
        components=components,
        issue_type=issue_type,
    )
    return float(details["score"]), list(details["reasons"])


def _count_evidence_signals(
    meta: dict[str, Any],
    *,
    domain: str | None,
    sub_domain: str | None = None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    components: list[str] | None = None,
    issue_type: str | None = None,
) -> int:
    """Count structural overlap signals across metadata dimensions."""
    details = _metadata_match_details(
        meta,
        domain=domain,
        sub_domain=sub_domain,
        dita_entities=dita_entities,
        affected_outputs=affected_outputs,
        customer_names=customer_names,
        components=components,
        issue_type=issue_type,
    )
    n = 0
    if details.get("domain_match"):
        n += 1
    if details.get("sub_domain_match"):
        n += 1
    if details.get("entity_overlap"):
        n += 1
    if details.get("output_overlap"):
        n += 1
    if details.get("customer_overlap"):
        n += 1
    if details.get("component_overlap"):
        n += 1
    if details.get("issue_type_match"):
        n += 1
    return n


def _overlap_gate_signals(
    meta: dict[str, Any],
    *,
    domain: str | None,
    sub_domain: str | None = None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    components: list[str] | None = None,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """Concrete structural overlap used by gates, scoring, and debug logging."""
    details = _metadata_match_details(
        meta,
        domain=domain,
        sub_domain=sub_domain,
        dita_entities=dita_entities,
        affected_outputs=affected_outputs,
        customer_names=customer_names,
        components=components,
        issue_type=issue_type,
    )
    ent_q = set(details["query_entities"])
    out_q = set(details["query_outputs"])
    cust_q = set(details["query_customers"])
    comp_q = set(details["query_components"])
    cust_meta = set(details["candidate_customers"])
    dom_m = str(details["domain_candidate"])
    sub_m = str(details["sub_domain_candidate"])
    dom_q = str(details["domain_query"])
    domain_known = bool(dom_m and dom_m != "unknown")
    domain_match = bool(details.get("domain_match") or (dom_q and sub_m and sub_m == dom_q))
    domain_mismatch = bool(dom_q and dom_q not in ("", "unknown") and domain_known and not domain_match)

    customer_match = bool(details.get("customer_overlap"))
    issue_type_query = str(details.get("issue_type_query") or "")
    issue_type_candidate = str(details.get("issue_type_candidate") or "")
    issue_type_mismatch = bool(issue_type_query and issue_type_candidate and issue_type_query != issue_type_candidate)
    component_inter = set(details["component_overlap"])
    ent_inter = set(details["entity_overlap"])
    out_inter = set(details["output_overlap"])
    return {
        "query_entities": sorted(ent_q),
        "candidate_entities": list(details["candidate_entities"]),
        "entity_overlap": sorted(ent_inter),
        "entity_overlap_count": len(ent_inter),
        "query_outputs": sorted(out_q),
        "candidate_outputs": list(details["candidate_outputs"]),
        "output_overlap": sorted(out_inter),
        "output_overlap_count": len(out_inter),
        "query_customers": sorted(cust_q),
        "candidate_customers": sorted(cust_meta),
        "customer_overlap": list(details["customer_overlap"]),
        "customer_overlap_count": len(details["customer_overlap"]),
        "customer_match": customer_match,
        "customer_conflict": bool(cust_q and cust_meta and not customer_match),
        "query_components": sorted(comp_q),
        "candidate_components": list(details["candidate_components"]),
        "component_overlap": sorted(component_inter),
        "component_overlap_count": len(component_inter),
        "issue_type_query": issue_type_query,
        "issue_type_candidate": issue_type_candidate,
        "issue_type_match": bool(details.get("issue_type_match")),
        "issue_type_mismatch": issue_type_mismatch,
        "domain_query": dom_q,
        "domain_candidate": dom_m,
        "sub_domain_candidate": sub_m,
        "sub_domain_query": str(details.get("sub_domain_query") or ""),
        "sub_domain_match": bool(details.get("sub_domain_match")),
        "domain_known": domain_known,
        "domain_match": domain_match,
        "domain_mismatch": domain_mismatch,
    }


def _candidate_confidence_score(
    *,
    vector_score: float,
    metadata_score: float,
    final_score: float,
    gate_signals: dict[str, Any],
    label_component_boost: float,
) -> float:
    """Confidence is separate from rank: it estimates whether evidence is reusable for UAC."""
    structural_hits = 0
    structural_hits += 1 if gate_signals.get("domain_match") else 0
    structural_hits += 1 if gate_signals.get("entity_overlap_count", 0) > 0 else 0
    structural_hits += 1 if gate_signals.get("output_overlap_count", 0) > 0 else 0
    structural_hits += 1 if gate_signals.get("customer_match") else 0
    structural_hits += 1 if gate_signals.get("component_overlap_count", 0) > 0 else 0
    structural_hits += 1 if gate_signals.get("issue_type_match") else 0
    structural_hits += 1 if label_component_boost > 0 else 0
    structural = min(1.0, structural_hits / 5.0)
    score = 0.34 * final_score + 0.26 * metadata_score + 0.22 * vector_score + 0.18 * structural
    if gate_signals.get("customer_conflict"):
        score -= 0.2
    if gate_signals.get("domain_mismatch") and gate_signals.get("entity_overlap_count", 0) == 0:
        score -= 0.12
    return round(max(0.0, min(1.0, score)), 4)


def _candidate_rejection_reasons(
    *,
    vector_score: float,
    keyword_score: float,
    metadata_score: float,
    final_score: float,
    gate_signals: dict[str, Any],
    evidence_gate_enabled: bool,
    require_non_vector_evidence: bool = True,
) -> list[dict[str, Any]]:
    """Hard gates for candidate rejection — kept minimal to avoid false negatives.

    Removed gates (all converted to soft penalties in _penalty_breakdown):
    - final_score < MIN_FINAL_SCORE  → double-penalises after score already incorporates penalties
    - metadata_score < MIN_METADATA_SCORE → too strict when small index has sparse entity metadata
    - customer_conflict              → already penalised in scoring; hard gate incorrectly blocked
                                       tickets where customer tokens leaked from cloud env IDs
    - component_gate_failed         → same reasoning as entity/output gates removed earlier
    - issue_type_mismatch           → Bug ≠ Story should not hard-reject; just lower score
    """
    # Below minimum embedding similarity — always reject regardless of metadata.
    if vector_score < MIN_VECTOR_SCORE:
        return [
            {
                "reason": "below_min_vector_score",
                "detail": f"vector_score={round(vector_score, 4)} < MIN_VECTOR_SCORE={MIN_VECTOR_SCORE}",
            }
        ]

    # Cross-domain with zero entity override — clearly wrong domain unless forced by fallback.
    if (
        evidence_gate_enabled
        and gate_signals.get("domain_mismatch")
        and gate_signals.get("entity_overlap_count", 0) == 0
        and gate_signals.get("output_overlap_count", 0) == 0
    ):
        return [
            {
                "reason": "domain_gate_failed",
                "detail": (
                    f"query_domain={gate_signals.get('domain_query')}; "
                    f"candidate_domain={gate_signals.get('domain_candidate')}; "
                    "no entity or output overlap to override domain mismatch"
                ),
            }
        ]

    return []


def _build_why_similar(
    *,
    vector_score: float,
    keyword_score: float,
    meta_reasons: list[str],
    keyword_hits: list[str],
    dom_meta: str,
    out_overlap: set[str],
    ent_overlap: set[str],
    customer_overlap: set[str] | None = None,
    component_overlap: set[str] | None = None,
    score_breakdown: dict[str, Any] | None = None,
) -> str:
    """Concrete overlap first; avoid generic 'semantic similarity' only explanations."""
    mo = sorted(out_overlap)[:5]
    me = sorted(ent_overlap)[:5]
    mc = sorted(customer_overlap or set())[:4]
    mcomp = sorted(component_overlap or set())[:4]
    parts: list[str] = []
    if mo and me:
        parts.append(f"Both tickets involve {', '.join(mo)} and {', '.join(me)}.")
    elif mo:
        parts.append(f"Both tickets involve the same output area: {', '.join(mo)}.")
    elif me:
        parts.append(f"Both tickets reference the same DITA/AEM entities: {', '.join(me)}.")
    if mc:
        parts.append(f"Customer overlap: {', '.join(mc)}.")
    if mcomp:
        parts.append(f"Component overlap: {', '.join(mcomp)}.")
    if meta_reasons:
        tail = "; ".join(meta_reasons[:2])
        if tail:
            parts.append(tail + ".")
    if keyword_hits and ((not mo and not me) or keyword_score >= 0.1):
        parts.append("Shared wording includes " + ", ".join(keyword_hits[:6]) + ".")
    if dom_meta and str(dom_meta).lower() != "unknown" and not mo and not me:
        parts.append(f"Indexed domain for the candidate is {str(dom_meta).replace('_', ' ')}.")
    if not parts:
        parts.append(
            "Thin structured overlap; retrieval surfaced this ticket mainly from overlapping summary language—validate scope manually."
        )
    else:
        if vector_score >= 0.6:
            parts.append("Chunk embedding distance also ranks this issue near the query text.")
        elif vector_score >= 0.45 and keyword_score < 0.06:
            parts.append("Embedding rank is moderate but token overlap is thin; treat as a weak signal.")
    if score_breakdown:
        parts.append(
            "Score blend: vector={vector}, metadata={metadata}, keyword={keyword}, final={final}.".format(
                vector=score_breakdown.get("vector_score", 0),
                metadata=score_breakdown.get("metadata_score", 0),
                keyword=score_breakdown.get("keyword_score", 0),
                final=score_breakdown.get("final_score", score_breakdown.get("final_fused_score", 0)),
            )
        )
    return " ".join(p.strip() for p in parts if p).strip()[:520]


def _top_overlap_tokens(query_tokens: set[str], doc_tokens: set[str], *, limit: int = 8) -> list[str]:
    inter = sorted(query_tokens & doc_tokens)
    return inter[:limit]


def _generic_overlap_only(query_tokens: set[str], doc_tokens: set[str], gate_signals: dict[str, Any]) -> bool:
    overlap = query_tokens & doc_tokens
    if not overlap:
        return False
    if any(
        [
            gate_signals.get("domain_match"),
            gate_signals.get("entity_overlap_count", 0) > 0,
            gate_signals.get("output_overlap_count", 0) > 0,
            gate_signals.get("customer_match"),
            gate_signals.get("component_overlap_count", 0) > 0,
        ]
    ):
        return False
    return bool(overlap) and overlap <= _GENERIC_OVERLAP_TOKENS


def _recent_penalty(jira_key: str, recent_jira_keys: list[str] | None) -> float:
    recent = recent_jira_keys if recent_jira_keys is not None else list(_RECENT_RETURNED_JIRA_KEYS)
    recent_norm = {str(k).strip().upper() for k in recent if str(k).strip()}
    return JIRA_RECENT_REPEAT_PENALTY if jira_key.strip().upper() in recent_norm else 0.0


def _penalty_breakdown(
    *,
    jira_key: str,
    query_tokens: set[str],
    doc_tokens: set[str],
    gate_signals: dict[str, Any],
    recent_jira_keys: list[str] | None,
) -> dict[str, float]:
    penalties: dict[str, float] = {}
    if _generic_overlap_only(query_tokens, doc_tokens, gate_signals):
        penalties["generic_overlap_only"] = 0.1
    if gate_signals.get("query_entities") and gate_signals.get("entity_overlap_count", 0) == 0:
        penalties["no_entity_overlap"] = 0.08
    if gate_signals.get("query_outputs") and gate_signals.get("output_overlap_count", 0) == 0:
        penalties["no_output_overlap"] = 0.08
    if gate_signals.get("customer_conflict"):
        penalties["customer_conflict"] = 0.12
    if gate_signals.get("issue_type_mismatch"):
        penalties["issue_type_mismatch"] = 0.05
    recent = _recent_penalty(jira_key, recent_jira_keys)
    if recent > 0:
        penalties["recently_returned_jira"] = recent
    return penalties


def _score_formula(vector_score: float, metadata_score: float, keyword_score: float) -> float:
    return (_W_VECTOR * vector_score) + (_W_METADATA * metadata_score) + (_W_KEYWORD * keyword_score)


def _customer_bucket(meta: dict[str, Any]) -> str:
    _, _, customers = _metadata_lists(meta)
    if customers:
        return sorted(customers)[0]
    c = _norm_label(str(meta.get("customer") or ""))
    return c


def _near_duplicate_fingerprint(row: RetrievedJira) -> set[str]:
    text = " ".join([row.title or "", row.document or ""])[:1200]
    toks = _norm_token_set(text) - _GENERIC_OVERLAP_TOKENS
    return toks


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def _is_broad_query(
    query_text: str,
    domain: str | None,
    dita_entities: list[str],
    affected_outputs: list[str],
) -> bool:
    q = (query_text or "").strip()
    dom = _norm_domain(domain)
    if not dom or dom == "unknown":
        return True
    if len(q) < 28 and len(q.split()) < 5:
        return True
    if len(dita_entities) < 2 and len(affected_outputs) < 2:
        return True
    return False


def extract_hybrid_filters_from_issue_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pull domain / entities / outputs / customers from indexed chunks for hybrid retrieval."""
    domain = ""
    entities: list[str] = []
    outputs: list[str] = []
    customers: list[str] = []
    seen_e: set[str] = set()
    seen_o: set[str] = set()
    seen_c: set[str] = set()

    for row in rows or []:
        m = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if not domain:
            d = str(m.get("enrich_domain") or "").strip()
            if d and _norm_domain(d) != "unknown":
                domain = d
        for x in _parse_json_list_preserve(str(m.get("enrich_entities") or "")):
            k = _norm_label(x)
            if k and k not in seen_e:
                seen_e.add(k)
                entities.append(x.strip())
        for x in _parse_json_list_preserve(str(m.get("enrich_outputs") or "")):
            k = _norm_label(x)
            if k and k not in seen_o:
                seen_o.add(k)
                outputs.append(x.strip())
        for x in _parse_json_list_preserve(str(m.get("enrich_customers") or "")):
            k = _norm_label(x)
            if k and k not in seen_c:
                seen_c.add(k)
                customers.append(x.strip())
        if not customers:
            c0 = str(m.get("customer") or "").strip()
            if c0:
                k = _norm_label(c0)
                if k not in seen_c:
                    seen_c.add(k)
                    customers.append(c0)
    return {
        "domain": domain or None,
        "dita_entities": entities[:40],
        "affected_outputs": outputs[:20],
        "customer_names": customers[:20],
    }


def _metadata_where_plan(
    *,
    domain: str | None,
    sub_domain: str | None,
    issue_type: str | None,
    customer_names: list[str] | None,
) -> list[dict[str, Any]]:
    """Build Chroma metadata-first vector query passes for scalar metadata fields.

    JSON-list fields such as enrich_entities/enrich_outputs/components are scored
    after retrieval because exact Chroma filters cannot reliably query inside
    encoded arrays across all deployed Chroma versions.
    """
    passes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(label: str, where: dict[str, Any]) -> None:
        key = json.dumps(where, sort_keys=True)
        marker = (label, key)
        if marker in seen:
            return
        seen.add(marker)
        passes.append({"label": label, "where": where})

    dom_f = _norm_domain(domain) if domain else ""
    if dom_f and dom_f != "unknown":
        add("domain_filtered", {"enrich_domain": dom_f})
    sub_f = _norm_domain(sub_domain) if sub_domain else ""
    if sub_f:
        add("sub_domain_filtered", {"enrich_sub_domain": sub_f})
    issue_f = str(issue_type or "").strip()
    if issue_f:
        add("issue_type_filtered", {"issue_type": issue_f})
    for customer in (customer_names or [])[:2]:
        c = str(customer or "").strip()
        if c:
            add("customer_filtered", {"customer": c})
    if not passes:
        add("unfiltered", {})
    return passes


def _apply_diversity(
    ranked: list[RetrievedJira],
    *,
    limit: int,
    broad: bool,
    diversity_drops: list[dict[str, Any]] | None = None,
) -> list[RetrievedJira]:
    if not broad or len(ranked) <= 1:
        res = ranked[:limit]
        if diversity_drops is not None:
            for i, r in enumerate(ranked[limit:], start=limit + 1):
                diversity_drops.append(
                    {
                        "jira_key": r.jira_key,
                        "chunk_type": r.chunk_type,
                        "reason": "below_result_limit",
                        "detail": f"sorted_rank={i}, limit={limit}, broad_query=false",
                        "final_score": round(r.final_score, 4),
                    }
                )
        return res
    cap = max(2, (limit + 2) // 3)
    per_bucket: dict[str, int] = {}
    out: list[RetrievedJira] = []
    bucket_skipped: list[tuple[RetrievedJira, str, int]] = []
    for r in ranked:
        m = r.metadata or {}
        dom = str(m.get("enrich_domain") or "unknown")
        sub = str(m.get("enrich_sub_domain") or "")
        bucket = f"{dom}::{sub}"
        if per_bucket.get(bucket, 0) >= cap:
            bucket_skipped.append((r, bucket, cap))
            continue
        out.append(r)
        per_bucket[bucket] = per_bucket.get(bucket, 0) + 1
        if len(out) >= limit:
            break
    if len(out) < limit:
        seen = {x.jira_key for x in out}
        for r in ranked:
            if r.jira_key in seen:
                continue
            out.append(r)
            seen.add(r.jira_key)
            if len(out) >= limit:
                break
    final = out[:limit]
    if diversity_drops is not None:
        dropped_keys: set[str] = set()
        picked = {x.jira_key for x in final}
        for r, bucket, c in bucket_skipped:
            if r.jira_key in picked:
                continue
            diversity_drops.append(
                {
                    "jira_key": r.jira_key,
                    "chunk_type": r.chunk_type,
                    "reason": "diversity_bucket_cap",
                    "detail": f"bucket={bucket}, per_bucket_cap={c}",
                    "final_score": round(r.final_score, 4),
                }
            )
            dropped_keys.add(r.jira_key)
        for i, r in enumerate(ranked):
            if r.jira_key in picked or r.jira_key in dropped_keys:
                continue
            diversity_drops.append(
                {
                    "jira_key": r.jira_key,
                    "chunk_type": r.chunk_type,
                    "reason": "not_in_final_top_after_diversity",
                    "detail": f"sorted_rank={i + 1}, limit={limit}",
                    "final_score": round(r.final_score, 4),
                }
            )
            dropped_keys.add(r.jira_key)
    return final


def _apply_max_per_domain(
    ranked: list[RetrievedJira],
    *,
    limit: int,
    max_per_domain: int,
    domain_drops: list[dict[str, Any]] | None = None,
) -> list[RetrievedJira]:
    if max_per_domain <= 0:
        return ranked[:limit]
    per: dict[str, int] = {}
    out: list[RetrievedJira] = []
    skipped: list[tuple[RetrievedJira, str]] = []
    for r in ranked:
        dom = _norm_domain(str((r.metadata or {}).get("enrich_domain") or "unknown"))
        if per.get(dom, 0) >= max_per_domain:
            skipped.append((r, dom))
            continue
        out.append(r)
        per[dom] = per.get(dom, 0) + 1
        if len(out) >= limit:
            break
    final = out[:limit]
    if domain_drops is not None:
        picked = {x.jira_key for x in final}
        for r, dom in skipped:
            if r.jira_key in picked:
                continue
            domain_drops.append(
                {
                    "jira_key": r.jira_key,
                    "chunk_type": r.chunk_type,
                    "reason": "max_similar_per_domain",
                    "detail": f"domain={dom}, cap={max_per_domain}",
                    "final_score": round(r.final_score, 4),
                }
            )
    return final


def _apply_enterprise_diversity(
    ranked: list[RetrievedJira],
    *,
    limit: int,
    max_per_domain: int,
    max_per_customer: int,
    diversity_drops: list[dict[str, Any]] | None = None,
) -> list[RetrievedJira]:
    """Apply production diversity caps after reranking.

    Caps:
    - max N per domain
    - max N per customer when customer metadata is present
    - skip near-duplicate title/document fingerprints
    """
    per_domain: dict[str, int] = {}
    per_customer: dict[str, int] = {}
    fingerprints: list[tuple[str, set[str]]] = []
    out: list[RetrievedJira] = []

    for r in ranked:
        meta = r.metadata or {}
        dom = _norm_domain(str(meta.get("enrich_domain") or "unknown"))
        customer = _customer_bucket(meta)

        if max_per_domain > 0 and per_domain.get(dom, 0) >= max_per_domain:
            if diversity_drops is not None:
                diversity_drops.append(
                    {
                        "jira_key": r.jira_key,
                        "chunk_type": r.chunk_type,
                        "reason": "max_similar_per_domain",
                        "detail": f"domain={dom}, cap={max_per_domain}",
                        "final_score": round(r.final_score, 4),
                    }
                )
            continue

        if customer and max_per_customer > 0 and per_customer.get(customer, 0) >= max_per_customer:
            if diversity_drops is not None:
                diversity_drops.append(
                    {
                        "jira_key": r.jira_key,
                        "chunk_type": r.chunk_type,
                        "reason": "max_similar_per_customer",
                        "detail": f"customer={customer}, cap={max_per_customer}",
                        "final_score": round(r.final_score, 4),
                    }
                )
            continue

        fp = _near_duplicate_fingerprint(r)
        duplicate_of = ""
        if len(fp) >= 6:
            for kept_key, kept_fp in fingerprints:
                if len(kept_fp) >= 6 and _jaccard(fp, kept_fp) >= JIRA_NEAR_DUPLICATE_JACCARD:
                    duplicate_of = kept_key
                    break
        if duplicate_of:
            if diversity_drops is not None:
                diversity_drops.append(
                    {
                        "jira_key": r.jira_key,
                        "chunk_type": r.chunk_type,
                        "reason": "near_duplicate_jira",
                        "detail": f"near_duplicate_of={duplicate_of}; jaccard>={JIRA_NEAR_DUPLICATE_JACCARD}",
                        "final_score": round(r.final_score, 4),
                    }
                )
            continue

        out.append(r)
        per_domain[dom] = per_domain.get(dom, 0) + 1
        if customer:
            per_customer[customer] = per_customer.get(customer, 0) + 1
        fingerprints.append((r.jira_key, fp))
        if len(out) >= limit:
            break

    if diversity_drops is not None:
        picked = {x.jira_key for x in out}
        already = {str(x.get("jira_key") or "") for x in diversity_drops}
        for i, r in enumerate(ranked):
            if r.jira_key in picked or r.jira_key in already:
                continue
            diversity_drops.append(
                {
                    "jira_key": r.jira_key,
                    "chunk_type": r.chunk_type,
                    "reason": "not_in_final_top_after_diversity",
                    "detail": f"sorted_rank={i + 1}, limit={limit}",
                    "final_score": round(r.final_score, 4),
                }
            )
    return out


def _resolve_embedding(query_text: str, query_embedding: list[float] | None) -> list[float] | None:
    if query_embedding is not None and query_embedding:
        return query_embedding
    qt = (query_text or "")[:12000]
    if not qt.strip():
        return None
    cached = cache_get_embedding_vector(qt)
    if cached is not None:
        return cached
    qv = embed_query(qt)
    if qv is None:
        return None
    emb = qv.tolist() if hasattr(qv, "tolist") else list(qv)
    cache_set_embedding_vector(qt, emb)
    return emb


def retrieve_similar_jiras(
    query_text: str,
    domain: str | None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    limit: int = 8,
    *,
    query_embedding: list[float] | None = None,
    exclude_jira_key: str | None = None,
    base_labels: list[str] | None = None,
    base_components: list[str] | None = None,
    label_expanded_tokens: frozenset[str] | None = None,
    retrieval_debug_sink: dict[str, Any] | None = None,
    sub_domain: str | None = None,
    issue_type: str | None = None,
    recent_jira_keys: list[str] | None = None,
    require_non_vector_evidence: bool = True,
) -> list[RetrievedJira]:
    """
    Hybrid retrieval over ``jira_qa`` Chroma: optional domain filter on vector query, token overlap,
    enrichment metadata boosts, dedupe by ``jira_key``, diversity when the query is broad.

    When ``retrieval_debug_sink`` is a dict, it is cleared and filled with retrieval diagnostics
    (query text, extracted filters, Chroma hits, score breakdowns, diversity / dedupe drops).
    """
    sink = retrieval_debug_sink
    if sink is not None:
        sink.clear()
        sink["retrieval_query"] = {
            "text_preview": (query_text or "")[:3000],
            "char_length": len(query_text or ""),
        }
        sink["extracted"] = {
            "domain": domain,
            "sub_domain": sub_domain,
            "dita_entities": list(dita_entities or []),
            "affected_outputs": list(affected_outputs or []),
            "customer_names": list(customer_names or []),
            "issue_type": issue_type,
            "exclude_jira_key": exclude_jira_key,
            "base_labels": list(base_labels or [])[:40],
            "base_components": list(base_components or [])[:40],
            "recent_jira_keys": list(recent_jira_keys or [])[:40],
        }
        sink["fusion_weights"] = {
            "w_vector": _W_VECTOR,
            "w_metadata": _W_METADATA,
            "w_keyword": _W_KEYWORD,
            "chunk_type_weights": dict(_CHUNK_TYPE_WEIGHT),
        }
        sink["uac_evidence_controls"] = {
            "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
            "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
            "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
            "MIN_ENTITY_OVERLAP": MIN_ENTITY_OVERLAP,
            "min_similarity_score": JIRA_UAC_MIN_SIMILARITY_SCORE,
            "minimum_evidence_threshold": JIRA_UAC_MINIMUM_EVIDENCE_THRESHOLD,
            "min_metadata_overlap": JIRA_UAC_MIN_METADATA_OVERLAP,
            "max_similar_per_domain": JIRA_UAC_MAX_SIMILAR_PER_DOMAIN,
            "vector_only_penalty": JIRA_UAC_VECTOR_ONLY_PENALTY,
        }

    if not (query_text or "").strip() or not is_chroma_available() or not is_embedding_available():
        if sink is not None:
            sink["early_exit_reason"] = "empty_query_or_chroma_or_embed_unavailable"
            sink["chroma_available"] = is_chroma_available()
            sink["embedding_available"] = is_embedding_available()
        return []

    emb = _resolve_embedding(query_text, query_embedding)
    if not emb:
        if sink is not None:
            sink["early_exit_reason"] = "embedding_resolve_failed"
        return []

    fetch_k = min(max(limit * 20, 40), 160)
    dom_f = _norm_domain(domain) if domain else ""
    raw_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    duplicate_drops: list[dict[str, Any]] = []
    row_skip_drops: list[dict[str, Any]] = []
    unfiltered_fallback = False
    metadata_query_plan = _metadata_where_plan(
        domain=domain,
        sub_domain=sub_domain,
        issue_type=issue_type,
        customer_names=customer_names or [],
    )

    def _extend(rows: list[dict[str, Any]], *, pass_label: str) -> None:
        for row in rows or []:
            rid = str(row.get("id") or "")
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            jk = str(meta.get("jira_key") or "").strip()
            if rid and rid in seen_ids:
                duplicate_drops.append(
                    {
                        "reason": "duplicate_chroma_chunk_id",
                        "chunk_id": rid,
                        "jira_key": jk,
                        "chroma_pass": pass_label,
                    }
                )
                continue
            if rid:
                seen_ids.add(rid)
            raw_rows.append(row)

    for plan in metadata_query_plan:
        where = plan.get("where") or None
        filtered = query_collection(
            CHROMA_COLLECTION_JIRA_QA,
            emb,
            k=fetch_k,
            where=where,
        )
        _extend(filtered, pass_label=str(plan.get("label") or "metadata_filtered"))

    unique_filtered_keys = {str((r.get("metadata") or {}).get("jira_key") or "") for r in raw_rows if r.get("metadata")}
    if metadata_query_plan and metadata_query_plan[0].get("where") and len(unique_filtered_keys) < max(3, limit // 2):
        unfiltered_fallback = True
        _extend(
            query_collection(CHROMA_COLLECTION_JIRA_QA, emb, k=fetch_k, where=None),
            pass_label="unfiltered_fallback",
        )

    if sink is not None:
        sink["chroma"] = {
            "collection": CHROMA_COLLECTION_JIRA_QA,
            "fetch_k": fetch_k,
            "vector_query_domain_normalized": dom_f or None,
            "metadata_filter_plan": [
                {"label": str(plan.get("label") or ""), "where": plan.get("where") or None}
                for plan in metadata_query_plan
            ],
            "domain_chroma_filter_applied": any(
                (plan.get("where") or {}).get("enrich_domain") for plan in metadata_query_plan
            ),
            "unfiltered_fallback_query": unfiltered_fallback,
            "merged_hit_count": len(raw_rows),
        }
        sink["candidates_before_rerank"] = [
            {
                "chroma_order_index": i,
                "chunk_id": str(row.get("id") or ""),
                "jira_key": str((row.get("metadata") or {}).get("jira_key") or ""),
                "distance": float(row.get("distance") or 0.0),
                "chunk_type": str((row.get("metadata") or {}).get("chunk_type") or ""),
                "enrich_domain": str((row.get("metadata") or {}).get("enrich_domain") or ""),
            }
            for i, row in enumerate(raw_rows)
        ]

    qt_tokens = _norm_token_set(query_text[:12000])
    bl = {x.lower().strip() for x in (base_labels or []) if x}
    bc = {x.lower().strip() for x in (base_components or []) if x}
    lex = label_expanded_tokens if label_expanded_tokens is not None else frozenset()
    evidence_gate_enabled = bool(
        domain
        or sub_domain
        or dita_entities
        or affected_outputs
        or customer_names
        or issue_type
        or base_labels
        or base_components
        or label_expanded_tokens
    )
    candidates: list[RetrievedJira] = []
    scoring_trace: list[dict[str, Any]] = []

    for row in raw_rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        jk = str(meta.get("jira_key") or "").strip()
        chunk_id = str(row.get("id") or "")
        dist = float(row.get("distance") or 0.0)
        if not jk:
            row_skip_drops.append(
                {"reason": "missing_jira_key_in_metadata", "chunk_id": chunk_id, "distance": dist}
            )
            continue
        if exclude_jira_key and jk.upper() == (exclude_jira_key or "").strip().upper():
            row_skip_drops.append({"reason": "excluded_source_issue", "jira_key": jk, "chunk_id": chunk_id})
            continue
        vector_score = max(0.0, min(1.0, 1.0 - dist))
        doc = str(row.get("document") or "")
        kw = _keyword_overlap_score(qt_tokens, doc, meta)
        doc_toks = _norm_token_set(
            "\n".join(
                [
                    doc,
                    str(meta.get("title") or ""),
                    " ".join(_parse_json_list(str(meta.get("enrich_entities") or ""))),
                    " ".join(_parse_json_list(str(meta.get("enrich_outputs") or ""))),
                ]
            )
        )
        md, md_reasons = _metadata_match_score(
            meta,
            domain=domain,
            sub_domain=sub_domain,
            dita_entities=dita_entities or [],
            affected_outputs=affected_outputs or [],
            customer_names=customer_names or [],
            components=base_components or [],
            issue_type=issue_type,
        )
        gate_signals = _overlap_gate_signals(
            meta,
            domain=domain,
            sub_domain=sub_domain,
            dita_entities=dita_entities or [],
            affected_outputs=affected_outputs or [],
            customer_names=customer_names or [],
            components=base_components or [],
            issue_type=issue_type,
        )
        ent_m, out_m, cust_m = _metadata_lists(meta)
        comp_m = _metadata_components(meta)
        ent_q = {_norm_label(x) for x in (dita_entities or []) if str(x).strip()}
        out_q = {_norm_label(x) for x in (affected_outputs or []) if str(x).strip()}
        cust_q = {_norm_label(x) for x in (customer_names or []) if str(x).strip()}
        comp_q = {_norm_label(x) for x in (base_components or []) if str(x).strip()}
        ent_inter = ent_q & ent_m
        out_inter = out_q & out_m
        comp_inter = comp_q & comp_m
        customer_inter = set(gate_signals.get("customer_overlap") or [])
        dom_m = _norm_domain(str(meta.get("enrich_domain") or "unknown"))
        sub_m = _norm_domain(str(meta.get("enrich_sub_domain") or ""))
        dom_q = _norm_domain(domain) if domain else ""
        has_structural = bool(ent_inter) or bool(out_inter)
        if not has_structural and cust_q and cust_m:
            dom_aligned = bool(
                dom_q and dom_q not in ("", "unknown") and (dom_m == dom_q or sub_m == dom_q)
            )
            if dom_aligned:
                for cq in cust_q:
                    for cm in cust_m:
                        if not cq or not cm:
                            continue
                        if cq == cm or cq in cm or cm in cq:
                            has_structural = True
                            break
                    if has_structural:
                        break
        ct = str(meta.get("chunk_type") or "")
        chunk_w = _CHUNK_TYPE_WEIGHT.get(ct, 0.0)
        ob = _overlap_boost(meta, bl, bc)
        lb = _label_intel_boost(meta, lex)
        base_formula_score = _score_formula(vector_score, md, kw)
        penalties = _penalty_breakdown(
            jira_key=jk,
            query_tokens=qt_tokens,
            doc_tokens=doc_toks,
            gate_signals=gate_signals,
            recent_jira_keys=recent_jira_keys,
        )
        if vector_score >= 0.52 and not has_structural and kw < 0.07:
            penalties["vector_only_semantic_match"] = max(
                penalties.get("vector_only_semantic_match", 0.0),
                JIRA_UAC_VECTOR_ONLY_PENALTY,
            )
        penalty_total = sum(penalties.values())
        fused_raw = base_formula_score - penalty_total
        fused = max(0.0, min(1.0, fused_raw))
        evidence_overlap = _count_evidence_signals(
            meta,
            domain=domain,
            sub_domain=sub_domain,
            dita_entities=dita_entities or [],
            affected_outputs=affected_outputs or [],
            customer_names=customer_names or [],
            components=base_components or [],
            issue_type=issue_type,
        )
        confidence_score = _candidate_confidence_score(
            vector_score=vector_score,
            metadata_score=md,
            final_score=fused,
            gate_signals=gate_signals,
            label_component_boost=ob,
        )
        rejection_reasons = _candidate_rejection_reasons(
            vector_score=vector_score,
            keyword_score=kw,
            metadata_score=md,
            final_score=fused,
            gate_signals=gate_signals,
            evidence_gate_enabled=evidence_gate_enabled,
            require_non_vector_evidence=require_non_vector_evidence,
        )
        strong_evidence = not rejection_reasons

        kw_hits = _top_overlap_tokens(qt_tokens, doc_toks)
        score_breakdown = {
            "formula": "vector_score * 0.45 + metadata_score * 0.35 + keyword_score * 0.20 - penalties",
            "vector_weight": _W_VECTOR,
            "metadata_weight": _W_METADATA,
            "keyword_weight": _W_KEYWORD,
            "vector_score": round(vector_score, 4),
            "metadata_score": round(md, 4),
            "keyword_score": round(kw, 4),
            "weighted_vector": round(_W_VECTOR * vector_score, 4),
            "weighted_metadata": round(_W_METADATA * md, 4),
            "weighted_keyword": round(_W_KEYWORD * kw, 4),
            "base_formula_score": round(base_formula_score, 4),
            "penalties": {k: round(v, 4) for k, v in penalties.items()},
            "penalty_total": round(penalty_total, 4),
            "final_score": round(fused, 4),
            "chunk_type_weight_observed": round(chunk_w, 4),
            "label_component_overlap_observed": round(ob, 4),
            "label_intel_observed": round(lb, 4),
            "evidence_overlap_signals": evidence_overlap,
            "strong_evidence": strong_evidence,
            "metadata_match_reasons": list(md_reasons),
            "top_keyword_token_overlap": list(kw_hits[:12]),
            "confidence_score": confidence_score,
        }
        why = _build_why_similar(
            vector_score=vector_score,
            keyword_score=kw,
            meta_reasons=md_reasons,
            keyword_hits=kw_hits,
            dom_meta=str(meta.get("enrich_domain") or ""),
            out_overlap=out_q & out_m,
            ent_overlap=ent_q & ent_m,
            customer_overlap=customer_inter,
            component_overlap=comp_inter,
            score_breakdown=score_breakdown,
        )
        trace = {
            "jira_key": jk,
            "chunk_id": chunk_id,
            "chunk_type": ct,
            "distance": round(dist, 6),
            "score_breakdown": score_breakdown | {
                "keyword_overlap_score": round(kw, 4),
                "metadata_match_score": round(md, 4),
                "fusion_sum_before_clip": round(fused_raw, 4),
                "final_fused_score": round(fused, 4),
            },
            "gate_signals": gate_signals,
            "selected": strong_evidence,
            "rejection_reasons": rejection_reasons,
            "why_similar": why[:400],
        }
        scoring_trace.append(trace)
        logger.debug_structured(
            "jira_retrieval_candidate_scored",
            extra_fields={
                "jira_key": jk,
                "chunk_id": chunk_id,
                "selected": strong_evidence,
                "rejection_reasons": rejection_reasons,
                "score_breakdown": trace["score_breakdown"],
                "gate_signals": gate_signals,
            },
        )

        candidates.append(
            RetrievedJira(
                jira_key=jk,
                title=str(meta.get("title") or "")[:500],
                chunk_type=ct,
                document=doc[:600],
                metadata=meta,
                vector_score=round(vector_score, 4),
                keyword_score=round(kw, 4),
                metadata_score=round(md, 4),
                final_score=round(fused, 4),
                confidence_score=confidence_score,
                why_similar=why,
                matching_entities=_display_overlap(dita_entities or [], ent_m),
                matching_outputs=_display_overlap(affected_outputs or [], out_m),
                matching_customers=_customer_overlap_display(customer_names or [], cust_m),
                matching_components=_display_overlap(base_components or [], comp_m),
                score_breakdown=trace["score_breakdown"],
                evidence_overlap_signals=evidence_overlap,
                strong_evidence=strong_evidence,
                rejection_reasons=rejection_reasons,
            )
        )

    by_key_lists: dict[str, list[RetrievedJira]] = {}
    for c in candidates:
        by_key_lists.setdefault(c.jira_key, []).append(c)
    dedupe_drops: list[dict[str, Any]] = []
    for jkey, lst in by_key_lists.items():
        lst.sort(key=lambda x: (-x.final_score, -x.vector_score, -x.keyword_score))
        for loser in lst[1:]:
            dedupe_drops.append(
                {
                    "reason": "dedupe_lower_scoring_chunk",
                    "jira_key": jkey,
                    "detail": (
                        f"kept_chunk_type={lst[0].chunk_type}@{lst[0].final_score}; "
                        f"dropped_chunk_type={loser.chunk_type}@{loser.final_score}"
                    ),
                    "winner_final_score": lst[0].final_score,
                    "loser_final_score": loser.final_score,
                }
            )

    per_key: dict[str, RetrievedJira] = {}
    for c in candidates:
        prev = per_key.get(c.jira_key)
        if prev is None or c.final_score > prev.final_score:
            per_key[c.jira_key] = c

    ranked_full = sorted(
        per_key.values(), key=lambda x: (-x.final_score, -x.vector_score, -x.keyword_score)
    )
    evidence_drops: list[dict[str, Any]] = []
    ranked = [r for r in ranked_full if r.strong_evidence]
    if not ranked and ranked_full:
        # Fallback: strict gates filtered everything — return best-effort top candidates
        # with a lower floor so QA engineers always see something useful.
        _FALLBACK_FLOOR = 0.35
        fallback = [r for r in ranked_full if r.vector_score >= _FALLBACK_FLOOR]
        if not fallback:
            fallback = ranked_full
        ranked = fallback[:limit]
        logger.info_structured(
            "jira_retrieval_fallback_used",
            extra_fields={
                "candidates_before_fallback": len(ranked_full),
                "fallback_count": len(ranked),
                "floor": _FALLBACK_FLOOR,
            },
        )
    for r in ranked_full:
        if r.strong_evidence:
            continue
        if r.rejection_reasons:
            for reason in r.rejection_reasons:
                evidence_drops.append(
                    {
                        "jira_key": r.jira_key,
                        "chunk_type": r.chunk_type,
                        "reason": str(reason.get("reason") or "weak_evidence_rejected"),
                        "detail": str(reason.get("detail") or ""),
                        "final_score": r.final_score,
                        "vector_score": r.vector_score,
                        "metadata_score": r.metadata_score,
                        "confidence_score": r.confidence_score,
                        "evidence_overlap_signals": r.evidence_overlap_signals,
                    }
                )
        else:
            evidence_drops.append(
                {
                    "jira_key": r.jira_key,
                    "chunk_type": r.chunk_type,
                    "reason": "weak_evidence_rejected",
                    "detail": "Candidate did not meet retrieval evidence gates.",
                    "final_score": r.final_score,
                    "vector_score": r.vector_score,
                    "metadata_score": r.metadata_score,
                    "confidence_score": r.confidence_score,
                    "evidence_overlap_signals": r.evidence_overlap_signals,
                }
            )
    broad = _is_broad_query(query_text, domain, dita_entities or [], affected_outputs or [])
    div_drops: list[dict[str, Any]] | None = [] if sink is not None else None
    result = _apply_enterprise_diversity(
        ranked,
        limit=limit,
        max_per_domain=JIRA_UAC_MAX_SIMILAR_PER_DOMAIN,
        max_per_customer=JIRA_MAX_SIMILAR_PER_CUSTOMER,
        diversity_drops=div_drops,
    )
    if recent_jira_keys is None:
        for row in result:
            if row.jira_key:
                _RECENT_RETURNED_JIRA_KEYS.append(row.jira_key.upper())
    reason_counts: dict[str, int] = {}
    for row in evidence_drops:
        reason = str(row.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    logger.info_structured(
        "jira_retrieval_rerank_complete",
        extra_fields={
            "query_preview": (query_text or "")[:240],
            "domain": domain,
            "candidate_count": len(ranked_full),
            "selected_count": len(result),
            "rejected_count": len(evidence_drops),
            "rejection_reason_counts": reason_counts,
            "thresholds": {
                "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
                "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
                "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
                "MIN_ENTITY_OVERLAP": MIN_ENTITY_OVERLAP,
            },
        },
    )

    if sink is not None:
        sink["broad_query_diversity_enabled"] = broad
        sink["evidence_gate_enabled"] = evidence_gate_enabled
        sink["diversity_limits"] = {
            "max_per_domain": JIRA_UAC_MAX_SIMILAR_PER_DOMAIN,
            "max_per_customer": JIRA_MAX_SIMILAR_PER_CUSTOMER,
            "near_duplicate_jaccard": JIRA_NEAR_DUPLICATE_JACCARD,
            "recent_repeat_penalty": JIRA_RECENT_REPEAT_PENALTY,
        }
        sink["thresholds"] = {
            "MIN_VECTOR_SCORE": MIN_VECTOR_SCORE,
            "MIN_METADATA_SCORE": MIN_METADATA_SCORE,
            "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
            "MIN_ENTITY_OVERLAP": MIN_ENTITY_OVERLAP,
        }
        sink["rejection_reason_counts"] = reason_counts
        sink["candidates_after_scoring"] = scoring_trace
        sink["candidates_after_rerank"] = [
            {
                "sorted_rank": i + 1,
                "jira_key": r.jira_key,
                "chunk_type": r.chunk_type,
                "title_preview": (r.title or "")[:160],
                "final_score": r.final_score,
                "vector_score": r.vector_score,
                "keyword_score": r.keyword_score,
                "metadata_score": r.metadata_score,
                "confidence_score": r.confidence_score,
                "matching_entities": list(r.matching_entities),
                "matching_outputs": list(r.matching_outputs),
                "matching_customers": list(r.matching_customers),
                "matching_components": list(r.matching_components),
                "score_breakdown": dict(r.score_breakdown or {}),
                "why_similar": r.why_similar,
                "strong_evidence": r.strong_evidence,
                "evidence_overlap_signals": r.evidence_overlap_signals,
                "rejection_reasons": list(r.rejection_reasons or []),
            }
            for i, r in enumerate(ranked_full)
        ]
        sink["candidates_after_evidence_filter"] = [
            {
                "sorted_rank": i + 1,
                "jira_key": r.jira_key,
                "chunk_type": r.chunk_type,
                "title_preview": (r.title or "")[:160],
                "final_score": r.final_score,
                "confidence_score": r.confidence_score,
                "matching_entities": list(r.matching_entities),
                "matching_outputs": list(r.matching_outputs),
                "matching_customers": list(r.matching_customers),
                "matching_components": list(r.matching_components),
                "evidence_overlap_signals": r.evidence_overlap_signals,
                "why_similar": r.why_similar,
            }
            for i, r in enumerate(ranked)
        ]
        sink["candidates_final"] = [
            {
                "final_rank": i + 1,
                "jira_key": r.jira_key,
                "chunk_type": r.chunk_type,
                "title_preview": (r.title or "")[:160],
                "final_score": r.final_score,
                "vector_score": r.vector_score,
                "keyword_score": r.keyword_score,
                "metadata_score": r.metadata_score,
                "confidence_score": r.confidence_score,
                "matching_entities": list(r.matching_entities),
                "matching_outputs": list(r.matching_outputs),
                "matching_customers": list(r.matching_customers),
                "matching_components": list(r.matching_components),
                "score_breakdown": dict(r.score_breakdown or {}),
                "strong_evidence": r.strong_evidence,
                "evidence_overlap_signals": r.evidence_overlap_signals,
                "why_similar": r.why_similar,
            }
            for i, r in enumerate(result)
        ]
        dropped_candidates = [
            *duplicate_drops,
            *row_skip_drops,
            *dedupe_drops,
            *evidence_drops,
            *(div_drops or []),
        ]
        sink["dropped_candidates"] = dropped_candidates
        sink["rejected_candidates"] = dropped_candidates

    return result


def retrieve_similar_jiras_debug(
    query_text: str,
    domain: str | None,
    dita_entities: list[str],
    affected_outputs: list[str],
    customer_names: list[str],
    limit: int = 8,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run hybrid retrieval and return both selected rows and full diagnostics."""

    sink: dict[str, Any] = {}
    kwargs.pop("retrieval_debug_sink", None)
    rows = retrieve_similar_jiras(
        query_text,
        domain=domain,
        dita_entities=dita_entities,
        affected_outputs=affected_outputs,
        customer_names=customer_names,
        limit=limit,
        retrieval_debug_sink=sink,
        **kwargs,
    )
    return {
        "results": [r.model_dump() for r in rows],
        "debug": sink,
    }


def _overlap_display_strings(current_list: list[str], candidate_list: list[str]) -> list[str]:
    cur_map = {_norm_label(x): x.strip() for x in current_list if str(x).strip()}
    cand_map = {_norm_label(x): x.strip() for x in candidate_list if str(x).strip()}
    inter = set(cur_map.keys()) & set(cand_map.keys())
    return [cur_map[k] if k in cur_map else cand_map[k] for k in sorted(inter)]


def _matching_customers_display(current_customers: list[str], cust_meta_norm: set[str]) -> list[str]:
    found: list[str] = []
    for c in current_customers:
        cn = _norm_label(c)
        if not cn:
            continue
        for cm in cust_meta_norm:
            if not cm:
                continue
            if cn == cm or cn in cm or cm in cn:
                found.append(c.strip())
                break
    return sorted(set(found))


def _meta_label_component_hits(
    cur_labels: list[str], cur_components: list[str], meta: dict[str, Any]
) -> tuple[list[str], list[str]]:
    meta_labels = set(_parse_json_list(str(meta.get("labels") or "")))
    cur_l = {x.lower().strip() for x in cur_labels if x}
    lab_inter = meta_labels & cur_l
    label_overlap = [x for x in cur_labels if x.lower().strip() in lab_inter][:8]

    meta_comps = set(_parse_json_list(str(meta.get("components") or "")))
    cur_c = {x.lower().strip() for x in cur_components if x}
    comp_inter = meta_comps & cur_c
    component_overlap = [x for x in cur_components if x.lower().strip() in comp_inter][:8]
    return label_overlap, component_overlap


def _confidence_from_signals(
    *,
    final_score: float,
    metadata_score: float,
    matching_entities: list[str],
    matching_outputs: list[str],
    matching_customers: list[str],
    domain_aligned: bool,
    label_overlap: list[str],
    component_overlap: list[str],
    keyword_score: float,
) -> float:
    struct_hits = (
        (1 if matching_entities else 0)
        + (1 if matching_outputs else 0)
        + (1 if matching_customers else 0)
        + (1 if domain_aligned else 0)
        + (1 if label_overlap else 0)
        + (1 if component_overlap else 0)
    )
    structural = min(1.0, struct_hits / 4.0)
    confidence = 0.38 * float(final_score) + 0.32 * float(metadata_score) + 0.30 * structural
    if not matching_entities and not matching_outputs and not matching_customers:
        if metadata_score < 0.28:
            confidence = min(confidence, 0.45)
        if keyword_score < 0.05 and struct_hits <= 1:
            confidence = min(confidence, 0.38)
    return round(max(0.0, min(1.0, confidence)), 3)


def _what_we_learned_heuristic(
    jira_key: str,
    matching_entities: list[str],
    matching_outputs: list[str],
    confidence: float,
) -> str:
    if confidence >= 0.62 and matching_entities and matching_outputs:
        e = ", ".join(matching_entities[:3])
        o = ", ".join(matching_outputs[:3])
        return (
            f"{jira_key} is a close precedent: prior QA focused where {e} meets {o}; "
            f"reuse those layers and extend for any deltas in the current summary."
        )
    if confidence >= 0.5 and matching_outputs:
        return (
            f"{jira_key} aligns on outputs ({matching_outputs[0]}); "
            f"mine it for regression ideas, then narrow to the current repro steps."
        )
    if matching_entities:
        return (
            f"Weak-to-moderate precedent: {jira_key} shares entity signals ({', '.join(matching_entities[:3])}); "
            f"confirm output path and environment before copying tests wholesale."
        )
    return (
        f"Weak overlap only—read {jira_key}'s excerpt for wording or symptom parallels; "
        f"do not assume the same root cause."
    )


def explain_similarity(
    current_jira: dict[str, Any],
    candidate_jira: RetrievedJira | dict[str, Any],
) -> dict[str, Any]:
    """
    Explain why a retrieved ticket relates to the current issue using concrete overlaps.

    Returns keys: jira_key, summary, domain, matching_entities, matching_outputs,
    matching_customers, why_similar, what_we_learned, confidence_score (0..1).
    """
    if isinstance(candidate_jira, RetrievedJira):
        meta = candidate_jira.metadata if isinstance(candidate_jira.metadata, dict) else {}
        jira_key = candidate_jira.jira_key
        title = candidate_jira.title
        vector_score = float(candidate_jira.vector_score)
        keyword_score = float(candidate_jira.keyword_score)
        metadata_score = float(candidate_jira.metadata_score)
        final_score = float(candidate_jira.final_score)
        prior_why = candidate_jira.why_similar
        doc_blob = candidate_jira.document or ""
    else:
        raw = dict(candidate_jira) if isinstance(candidate_jira, dict) else {}
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        jira_key = str(raw.get("jira_key") or meta.get("jira_key") or "").strip()
        title = str(raw.get("title") or meta.get("title") or "").strip()
        vector_score = float(raw.get("vector_score") or 0.0)
        keyword_score = float(raw.get("keyword_score") or 0.0)
        metadata_score = float(raw.get("metadata_score") or 0.0)
        final_score = float(raw.get("final_score") or raw.get("score") or 0.0)
        prior_why = str(raw.get("why_similar") or "")
        doc_blob = str(raw.get("document") or "")

    cur_ents = [str(x).strip() for x in (current_jira.get("dita_entities") or []) if str(x).strip()]
    cur_outs = [str(x).strip() for x in (current_jira.get("affected_outputs") or []) if str(x).strip()]
    cur_cust = [str(x).strip() for x in (current_jira.get("customer_names") or []) if str(x).strip()]
    cur_domain = str(current_jira.get("domain") or "unknown").strip()
    cur_sub = str(current_jira.get("sub_domain") or "").strip()
    cur_summary = str(current_jira.get("summary") or "")
    cur_desc = str(current_jira.get("description") or "")
    cur_labels = [str(x) for x in (current_jira.get("labels") or []) if x]
    cur_components = [str(x) for x in (current_jira.get("components") or []) if x]

    cand_ents_raw = _parse_json_list_preserve(str(meta.get("enrich_entities") or ""))
    cand_outs_raw = _parse_json_list_preserve(str(meta.get("enrich_outputs") or ""))
    _, _, cust_meta_norm = _metadata_lists(meta)

    matching_entities = _overlap_display_strings(cur_ents, cand_ents_raw)
    matching_outputs = _overlap_display_strings(cur_outs, cand_outs_raw)
    matching_customers = _matching_customers_display(cur_cust, cust_meta_norm)
    label_overlap, component_overlap = _meta_label_component_hits(cur_labels, cur_components, meta)

    dom_q = _norm_domain(cur_domain)
    dom_m = _norm_domain(str(meta.get("enrich_domain") or "unknown"))
    sub_m = _norm_domain(str(meta.get("enrich_sub_domain") or ""))
    domain_aligned = bool(
        dom_q
        and dom_q not in ("", "unknown")
        and (dom_m == dom_q or sub_m == dom_q)
    )
    cand_domain = str(meta.get("enrich_domain") or "").strip() or "unknown"

    md, md_reasons = _metadata_match_score(
        meta,
        domain=cur_domain if dom_q not in ("", "unknown") else None,
        dita_entities=cur_ents,
        affected_outputs=cur_outs,
        customer_names=cur_cust,
    )

    qt_tokens = _norm_token_set((cur_summary + "\n" + cur_desc)[:8000])
    doc_toks = _norm_token_set(
        "\n".join(
            [
                title,
                doc_blob[:4000],
                str(meta.get("title") or ""),
                " ".join(cand_ents_raw),
                " ".join(cand_outs_raw),
            ]
        )
    )
    keyword_hits = _top_overlap_tokens(qt_tokens, doc_toks, limit=8)

    why_parts: list[str] = []
    if matching_outputs and matching_entities:
        why_parts.append(
            f"Both tickets involve {', '.join(matching_outputs[:4])} and {', '.join(matching_entities[:4])}."
        )
    elif matching_outputs:
        why_parts.append(f"Both tickets involve {', '.join(matching_outputs[:5])} in the delivery path.")
    elif matching_entities:
        why_parts.append(
            f"Both tickets surface overlapping DITA/AEM work: {', '.join(matching_entities[:5])}."
        )
    if matching_customers:
        why_parts.append(f"Shared customer context: {', '.join(matching_customers[:3])}.")
    if domain_aligned and dom_q not in ("", "unknown"):
        why_parts.append(f"Same indexed domain ({cand_domain.replace('_', ' ')}) as the current issue.")
    if label_overlap:
        why_parts.append(f"Matching labels: {', '.join(label_overlap[:5])}.")
    if component_overlap:
        why_parts.append(f"Same components: {', '.join(component_overlap[:4])}.")
    if md_reasons and len(" ".join(why_parts)) < 40:
        why_parts.append("Concrete signals: " + "; ".join(md_reasons[:3]) + ".")
    if keyword_hits and (len(why_parts) < 2 or keyword_score >= 0.08):
        why_parts.append(
            "Overlapping language in summaries or indexed excerpts includes "
            + ", ".join(keyword_hits[:6])
            + "."
        )
    if not why_parts:
        why_parts.append(
            "Structured metadata overlap is thin; this link is mainly from overlapping ticket text in retrieval—verify manually."
        )
    else:
        if vector_score >= 0.58:
            why_parts.append("Embedding rank places this ticket near the current issue text.")
        elif vector_score >= 0.42 and keyword_score < 0.06 and not matching_entities and not matching_outputs:
            why_parts.append("Embedding rank is only moderate and entity/output overlap is weak.")

    why_similar = " ".join(p for p in why_parts if p).strip()
    if len(why_similar) < 32 and prior_why:
        why_similar = (prior_why + " " + why_similar).strip()[:900]

    confidence_score = _confidence_from_signals(
        final_score=final_score,
        metadata_score=metadata_score,
        matching_entities=matching_entities,
        matching_outputs=matching_outputs,
        matching_customers=matching_customers,
        domain_aligned=domain_aligned,
        label_overlap=label_overlap,
        component_overlap=component_overlap,
        keyword_score=keyword_score,
    )

    what_we_learned = _what_we_learned_heuristic(
        jira_key, matching_entities, matching_outputs, confidence_score
    )

    return {
        "jira_key": jira_key,
        "summary": title,
        "domain": cand_domain,
        "matching_entities": matching_entities[:25],
        "matching_outputs": matching_outputs[:20],
        "matching_customers": matching_customers[:15],
        "matching_components": component_overlap[:15],
        "why_similar": why_similar[:900],
        "what_we_learned": what_we_learned[:600],
        "confidence_score": confidence_score,
        "score_breakdown": {
            "vector_score": round(vector_score, 4),
            "metadata_score": round(metadata_score or md, 4),
            "keyword_score": round(keyword_score, 4),
            "final_score": round(final_score, 4),
        },
    }


def retrieved_to_legacy_hit(r: RetrievedJira) -> dict[str, Any]:
    """Map hybrid row to the shape expected by ``EnterpriseRerankingEngine`` and Jira QA UI."""
    return {
        "jira_key": r.jira_key,
        "title": r.title,
        "chunk_type": r.chunk_type,
        "score": r.final_score,
        "document": r.document,
        "metadata": r.metadata,
        "vector_score": r.vector_score,
        "keyword_score": r.keyword_score,
        "metadata_score": r.metadata_score,
        "confidence_score": r.confidence_score,
        "why_similar": r.why_similar,
        "matching_entities": list(r.matching_entities),
        "matching_outputs": list(r.matching_outputs),
        "matching_customers": list(r.matching_customers),
        "matching_components": list(r.matching_components),
        "score_breakdown": dict(r.score_breakdown or {}),
        "rejection_reasons": list(r.rejection_reasons or []),
        "retrieval": {
            "vector_score": r.vector_score,
            "keyword_score": r.keyword_score,
            "metadata_score": r.metadata_score,
            "final_score": r.final_score,
            "confidence_score": r.confidence_score,
            "why_similar": r.why_similar,
            "matching_entities": list(r.matching_entities),
            "matching_outputs": list(r.matching_outputs),
            "matching_customers": list(r.matching_customers),
            "matching_components": list(r.matching_components),
            "score_breakdown": dict(r.score_breakdown or {}),
        },
    }
