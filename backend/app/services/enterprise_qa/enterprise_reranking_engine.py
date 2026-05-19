"""
Enterprise reranking for Jira QA retrieval: combines vector scores with structural and textual signals.

Used for related-ticket search, semantic historical retrieval, and regression-oriented ranking.
"""

from __future__ import annotations

import json
import re
from typing import Any

_API_PATH_RE = re.compile(r'(/api/[^\s"\'<>]+)', re.I)
_JAVA_STACK_RE = re.compile(
    r"\b(?:at\s+[\w$.]+\([\w.]+\:\d+\)|Caused by:|Exception|Error|Traceback)\b",
    re.I,
)
_CLOSED_STATUSES = frozenset(
    x.lower()
    for x in ("done", "closed", "resolved", "complete", "cancelled", "wont fix", "won't fix")
)
_REGRESSION_LABELS = frozenset({"regression", "regressions", "break", "break-fix", "regressed"})
_REOPEN_LABELS = frozenset({"reopened", "reopen", "re-open"})
_AUTOMATION_FAIL_TOKENS = frozenset(
    "failed failure flaky allure jenkins build assertion timeout npe oom stacktrace stderr".split()
)
_PRODUCT_BUCKETS: dict[str, frozenset[str]] = {
    "publishing": frozenset({"publish", "pdf", "output", "oat", "preset", "sites", "native-pdf"}),
    "reference": frozenset({"conref", "keyref", "xref", "keydef", "ditamap", "map", "href"}),
    "baseline": frozenset({"baseline", "version", "compare", "history", "audit", "versioning"}),
}


def _parse_labels(meta: dict[str, Any]) -> set[str]:
    raw = str(meta.get("labels") or "")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x).strip().lower() for x in data if str(x).strip()}
    except (json.JSONDecodeError, TypeError):
        pass
    return set()


def _parse_components(meta: dict[str, Any]) -> set[str]:
    raw = str(meta.get("components") or "")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x).strip().lower() for x in data if str(x).strip()}
    except (json.JSONDecodeError, TypeError):
        pass
    return set()


def _api_paths(text: str) -> set[str]:
    return {m.group(1).lower().rstrip(").,;")[:200] for m in _API_PATH_RE.finditer(text or "")}


def _error_tokens(text: str) -> set[str]:
    toks: set[str] = set()
    for line in (text or "").splitlines():
        if not _JAVA_STACK_RE.search(line) and "error" not in line.lower() and "exception" not in line.lower():
            continue
        for w in re.findall(r"[a-z][a-z0-9_]{3,}", line.lower()):
            if len(w) > 4:
                toks.add(w)
    return toks


def _text_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9_]{4,}", (text or "").lower()) if len(w) > 4}


def _product_hits(labels: set[str], blob: str) -> set[str]:
    blob_l = (blob or "").lower()
    out: set[str] = set()
    for bucket, kws in _PRODUCT_BUCKETS.items():
        if any(kw in blob_l for kw in kws) or labels & kws:
            out.add(bucket)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def build_rerank_base_from_issue_chunks(
    *,
    jira_key: str,
    rows: list[dict[str, Any]],
    extra_blob: str = "",
) -> dict[str, Any]:
    """
    Aggregate base-issue fields from indexed chunks (same shape as ``get_chunks_for_jira_key`` rows).
    """
    jk = (jira_key or "").strip().upper()
    labels: set[str] = set()
    components: set[str] = set()
    docs: list[str] = []
    issue_type = ""
    status = ""
    priority = ""
    customer = ""
    customer_key = ""
    chunk_types: set[str] = set()
    updated_at = ""

    for row in rows or []:
        m = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        labels |= _parse_labels(m)
        components |= _parse_components(m)
        ct = str(row.get("chunk_type") or m.get("chunk_type") or "")
        if ct:
            chunk_types.add(ct)
        if not issue_type:
            issue_type = str(m.get("issue_type") or "").strip().lower()
        if not status:
            status = str(m.get("status") or "").strip()
        if not priority:
            priority = str(m.get("priority") or "").strip()
        if not customer:
            customer = str(m.get("customer") or "").strip()
        if not customer_key:
            customer_key = str(m.get("customer_key") or "").strip().lower()
        doc = str(row.get("document") or "").strip()
        if doc:
            docs.append(doc)
        upd = str(m.get("updated_at") or "")
        if upd > updated_at:
            updated_at = upd

    blob = "\n".join(docs)[:24000]
    if extra_blob:
        blob = (blob + "\n\n" + (extra_blob or ""))[:26000]

    return {
        "jira_key": jk,
        "labels": labels,
        "components": components,
        "issue_type": issue_type.lower(),
        "status": status.lower(),
        "priority": priority.lower(),
        "customer": customer.lower(),
        "customer_key": customer_key,
        "blob": blob,
        "chunk_types": chunk_types,
        "updated_at": updated_at,
    }


class EnterpriseRerankingEngine:
    """Rerank Jira QA vector hits using enterprise structural and textual overlap signals."""

    def score_candidate(
        self,
        *,
        base: dict[str, Any],
        candidate: dict[str, Any],
        vector_score: float,
    ) -> dict[str, Any]:
        boosts: list[str] = []
        penalties: list[str] = []
        delta = 0.0

        meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        c_jk = str(candidate.get("jira_key") or meta.get("jira_key") or "").strip().upper()
        b_jk = str(base.get("jira_key") or "").strip().upper()
        if c_jk and b_jk and c_jk == b_jk:
            boosts.append("exact_jira_key_match")
            delta += 0.25

        c_labels = _parse_labels(meta)
        b_labels: set[str] = set(base.get("labels") or [])
        c_comps = _parse_components(meta)
        b_comps: set[str] = set(base.get("components") or [])

        if b_labels & c_labels:
            boosts.append("shared_jira_labels")
            delta += 0.04 * min(5, len(b_labels & c_labels))
        if b_comps & c_comps:
            boosts.append("shared_components")
            delta += 0.05 * min(4, len(b_comps & c_comps))

        bcust = str(base.get("customer") or "").strip().lower()
        bck = str(base.get("customer_key") or "").strip().lower()
        mcust = str(meta.get("customer") or "").lower()
        mck = str(meta.get("customer_key") or "").strip().lower()
        if bcust and (bcust == mcust or bcust in mcust or mcust in bcust):
            boosts.append("same_customer_field")
            delta += 0.08
        elif bck and mck and (bck == mck or bck.replace("_", "") == mck.replace("_", "")):
            boosts.append("same_customer_key")
            delta += 0.08

        bit = str(base.get("issue_type") or "")
        cit = str(meta.get("issue_type") or "").strip().lower()
        if bit and cit and bit == cit:
            boosts.append("same_issue_type")
            delta += 0.05

        b_chunk_types: set[str] = set(base.get("chunk_types") or [])
        c_ct = str(candidate.get("chunk_type") or meta.get("chunk_type") or "")
        if b_chunk_types & {"regression_risks"} and c_ct == "regression_risks":
            boosts.append("regression_chunk_alignment")
            delta += 0.04
        if (b_labels & _REGRESSION_LABELS) and (c_labels & _REGRESSION_LABELS):
            boosts.append("shared_regression_labels")
            delta += 0.06

        base_blob = str(base.get("blob") or "")
        cand_doc = str(candidate.get("document") or "") + "\n" + str(meta.get("title") or "")
        b_paths = _api_paths(base_blob)
        c_paths = _api_paths(cand_doc)
        if b_paths & c_paths:
            boosts.append("shared_api_paths")
            delta += 0.07 * min(3, len(b_paths & c_paths))

        et = _error_tokens(base_blob)
        ec = _error_tokens(cand_doc)
        jac = _jaccard(et, ec)
        if jac >= 0.12:
            boosts.append("similar_error_tokens")
            delta += min(0.12, jac * 0.35)

        if (b_labels | c_labels) & _REOPEN_LABELS or "reopen" in cand_doc.lower():
            boosts.append("reopen_pattern_signal")
            delta += 0.03

        btoks = _text_tokens(base_blob) & _AUTOMATION_FAIL_TOKENS
        ctoks = _text_tokens(cand_doc) & _AUTOMATION_FAIL_TOKENS
        if btoks & ctoks:
            boosts.append("similar_automation_failure_language")
            delta += 0.04

        b_prod = _product_hits(b_labels, base_blob)
        c_prod = _product_hits(c_labels, cand_doc)
        if b_prod & c_prod:
            boosts.append("same_publishing_or_reference_or_baseline_area")
            delta += 0.05

        feat_overlap = (b_labels | b_comps) & (c_labels | c_comps)
        if not feat_overlap and b_labels and c_labels:
            if vector_score < 0.52 and len(c_labels) >= 2:
                penalties.append("weak_label_overlap_vs_distinct_candidate_labels")
                delta -= 0.05

        cstat = str(meta.get("status") or "").strip().lower()
        bstat = str(base.get("status") or "").strip().lower()
        if cstat in _CLOSED_STATUSES and bstat and bstat not in _CLOSED_STATUSES and vector_score < 0.48:
            penalties.append("closed_candidate_while_base_active_low_vector")
            delta -= 0.04

        if not (b_prod & c_prod) and not (b_comps & c_comps) and vector_score < 0.5 and not (b_labels & c_labels):
            penalties.append("unrelated_product_area_heuristic")
            delta -= 0.05

        final = max(0.0, min(1.0, vector_score + delta))
        return {
            "final_score": round(final, 4),
            "boost_reasons": boosts[:24],
            "penalty_reasons": penalties[:24],
            "vector_score": round(float(vector_score), 4),
            "delta": round(delta, 4),
        }

    def rerank_hits(self, *, base: dict[str, Any], hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in hits:
            vec = float(h.get("score") or 0.0)
            rr = self.score_candidate(base=base, candidate=h, vector_score=vec)
            nh = dict(h)
            nh["score"] = rr["final_score"]
            nh["rerank"] = {
                "final_score": rr["final_score"],
                "boost_reasons": rr["boost_reasons"],
                "penalty_reasons": rr["penalty_reasons"],
                "vector_score": rr["vector_score"],
                "delta": rr["delta"],
            }
            out.append(nh)
        return sorted(out, key=lambda x: -float(x.get("score") or 0.0))
