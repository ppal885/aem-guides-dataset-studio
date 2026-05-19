"""Filter UAC draft answers so each point is grounded in the current or similar Jira evidence."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira

_WS_RE = re.compile(r"\s+")
_JIRA_KEY_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]+-\d+\b")

# Generic QA advice (rule 2) — substring match, case-insensitive
_GENERIC_PHRASES: tuple[str, ...] = (
    "test functional scenarios",
    "test regression",
    "test negative scenarios",
    "test positive scenarios",
    "positive and negative scenarios",
    "verify ui",
    "verify the ui",
    "validate functionality",
    "validate the functionality",
    "validate regression",
    "check regression",
    "validate end to end",
    "validate end-to-end",
    "ensure functionality works",
    "ensure the functionality works",
    "check all outputs",
    "perform smoke testing",
    "smoke testing",
    "smoke test",
    "validate error handling",
)

# Extra phrases from spec examples
_GENERIC_PHRASES_EXTRA: tuple[str, ...] = (
    "test positive and negative scenarios",
)

_STOP_ANCHORS = frozenset(
    {
        "pdf",
        "dita",
        "xml",
        "aem",
        "bug",
        "fix",
        "test",
        "ui",
        "qa",
        "uac",
    }
)


class DroppedPoint(BaseModel):
    """A removed bullet with a short reason for auditing."""

    model_config = ConfigDict(extra="forbid")

    text: str
    reason: str


class UacEvidenceGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleaned_answer: str
    dropped_points: list[DroppedPoint] = Field(default_factory=list)


def is_generic_statement(text: str) -> bool:
    """
    Return True if ``text`` looks like boilerplate QA/UAC advice (no product specifics required).
    Uses case-insensitive substring checks.
    """
    t = _WS_RE.sub(" ", (text or "").strip().lower())
    if not t:
        return False
    for p in _GENERIC_PHRASES + _GENERIC_PHRASES_EXTRA:
        if p in t:
            return True
    return False


def _as_enriched(obj: JiraEnrichedDocument | dict[str, Any]) -> JiraEnrichedDocument:
    if isinstance(obj, JiraEnrichedDocument):
        return obj
    return JiraEnrichedDocument.model_validate(obj)


def _as_retrieved(obj: RetrievedJira | dict[str, Any]) -> RetrievedJira:
    if isinstance(obj, RetrievedJira):
        return obj
    return RetrievedJira.model_validate(obj)


def _norm_anchor(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip().lower())


def _significant_anchor(tok: str) -> bool:
    t = _norm_anchor(tok)
    if len(t) < 3:
        return False
    if t in _STOP_ANCHORS and len(t) < 6:
        return False
    return True


def _enriched_anchors(en: JiraEnrichedDocument) -> set[str]:
    out: set[str] = set()
    jk = (en.jira_key or "").strip()
    if jk:
        out.add(jk.lower())
        out.add(jk.upper())
    for xs in (
        en.dita_entities,
        en.affected_outputs,
        en.components,
        en.customer_names,
        en.labels,
        en.affected_features,
        en.qa_risk_tags,
        en.symptoms or [],
    ):
        for x in xs or []:
            a = _norm_anchor(str(x))
            if a and _significant_anchor(a):
                out.add(a)
    dom = _norm_anchor(en.domain or "")
    if dom and dom != "unknown":
        out.add(dom)
    sub = _norm_anchor(en.sub_domain or "")
    if sub:
        out.add(sub)
    return out


def _retrieved_anchors(rows: Sequence[RetrievedJira]) -> set[str]:
    out: set[str] = set()
    for r in rows:
        jk = (r.jira_key or "").strip()
        if jk:
            out.add(jk.lower())
            out.add(jk.upper())
        t = _norm_anchor(r.title or "")
        for w in re.findall(r"[a-z][a-z0-9_-]{3,}", t, flags=re.I):
            ww = w.lower()
            if _significant_anchor(ww):
                out.add(ww)
        doc = (r.document or "")[:800]
        for w in re.findall(r"[a-z][a-z0-9_-]{4,}", doc.lower()):
            if _significant_anchor(w):
                out.add(w)
        why = _norm_anchor(r.why_similar or "")
        if why:
            for w in re.findall(r"[a-z][a-z0-9_-]{4,}", why):
                if _significant_anchor(w):
                    out.add(w)
        meta = r.metadata or {}
        for k in ("enrich_entities", "enrich_outputs", "enrich_domain"):
            raw = str(meta.get(k) or "")
            if raw and raw.startswith("["):
                try:
                    arr = json.loads(raw)
                    if isinstance(arr, list):
                        for item in arr:
                            a = _norm_anchor(str(item))
                            if a and _significant_anchor(a):
                                out.add(a)
                except (json.JSONDecodeError, TypeError):
                    pass
    return out


def _risk_blob(en: JiraEnrichedDocument) -> str:
    parts: list[str] = []
    parts.extend(en.symptoms or [])
    parts.extend(en.qa_risk_tags or [])
    if en.expected_behavior:
        parts.append(en.expected_behavior[:1500])
    if en.actual_behavior:
        parts.append(en.actual_behavior[:1500])
    parts.append((en.summary or "")[:500])
    return " ".join(parts).lower()


def _evidence_blob(en: JiraEnrichedDocument, similar: Sequence[RetrievedJira]) -> str:
    jk = (en.jira_key or "").strip()
    chunks: list[str] = [jk.lower(), jk.upper()]
    chunks.extend(
        [
            (en.raw_text or "")[:6000],
            (en.description or "")[:4000],
            (en.summary or "")[:500],
            " ".join(en.dita_entities or []),
            " ".join(en.affected_outputs or []),
            " ".join(en.components or []),
            " ".join(en.customer_names or []),
            _risk_blob(en),
        ]
    )
    for r in similar:
        chunks.append(f"{r.jira_key} {r.title} {(r.document or '')[:1200]} {(r.why_similar or '')}")
    return _WS_RE.sub(" ", " ".join(chunks).strip().lower())


def _point_mentions_any_anchor(point_lc: str, anchors: set[str]) -> bool:
    for a in anchors:
        if not a:
            continue
        if len(a) <= 2:
            continue
        if a.lower() in point_lc or a.upper() in point_lc:
            return True
    if _JIRA_KEY_RE.search(point_lc):
        return True
    return False


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_-]{4,}", (text or "").lower())


def _overlap_with_evidence(point_lc: str, ev_lc: str) -> bool:
    """True if point shares a non-trivial token with the evidence corpus."""
    ptoks = set(_tokens(point_lc))
    if not ptoks:
        return False
    for tok in ptoks:
        if tok in ev_lc:
            return True
    return False


def _generic_allowed(point_lc: str, en: JiraEnrichedDocument, risk_lc: str, ev_lc: str) -> bool:
    """Generic boilerplate is kept only when tied to a concrete ticket risk context."""
    rk = (en.jira_key or "").strip().lower()
    if rk and rk in point_lc:
        return _overlap_with_evidence(point_lc, risk_lc) or _overlap_with_evidence(
            point_lc, (en.description or "").lower()[:3500]
        )
    if _JIRA_KEY_RE.search(point_lc):
        return _overlap_with_evidence(point_lc, risk_lc) or _overlap_with_evidence(
            point_lc, (en.description or "").lower()[:3500]
        ) or _overlap_with_evidence(point_lc, ev_lc)
    for tag in en.qa_risk_tags or []:
        t = _norm_anchor(str(tag))
        if len(t) >= 4 and t in point_lc:
            return True
    for s in en.symptoms or []:
        t = _norm_anchor(str(s))
        if len(t) >= 6 and t in point_lc:
            return True
    return _overlap_with_evidence(point_lc, risk_lc)


def _split_points(draft: str) -> list[str]:
    """Split draft into bullet/numbered points; merge soft line wraps."""
    raw_lines = (draft or "").splitlines()
    points: list[str] = []
    buf: list[str] = []
    bullet_re = re.compile(r"^\s*(?:[-*•]|[\d]+[.)])\s+(.*)$")

    for line in raw_lines:
        line_stripped = line.strip()
        if not line_stripped:
            if buf:
                points.append(" ".join(buf))
                buf = []
            continue
        m = bullet_re.match(line)
        if m:
            if buf:
                points.append(" ".join(buf))
            buf = [m.group(1).strip()]
        else:
            if buf:
                buf.append(line_stripped)
            else:
                buf = [line_stripped]
    if buf:
        points.append(" ".join(buf))

    if not points and (draft or "").strip():
        return [(draft or "").strip()]
    return [p for p in points if p.strip()]


def _normalize_for_dedupe(text: str) -> str:
    t = _WS_RE.sub(" ", (text or "").strip().lower())
    t = re.sub(r"^\s*[\d]+[.)]\s+", "", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t)
    return t


def uac_claim_passes(
    claim: str,
    current_enriched_jira: JiraEnrichedDocument | dict[str, Any],
    retrieved_similar_jiras: Sequence[RetrievedJira | dict[str, Any]],
) -> bool:
    """
    Return True if ``claim`` meets the same grounding bar as ``apply_uac_evidence_gate`` (excluding dedupe).
    """
    en = _as_enriched(current_enriched_jira)
    similar = [_as_retrieved(x) for x in (retrieved_similar_jiras or [])]
    structural = _enriched_anchors(en) | _retrieved_anchors(similar)
    ev_blob = _evidence_blob(en, similar)
    risk_lc = _risk_blob(en)
    pl = (claim or "").strip()
    if not pl:
        return False
    p_lc = pl.lower()
    if not _point_mentions_any_anchor(p_lc, structural):
        return False
    if not _overlap_with_evidence(p_lc, ev_blob):
        return False
    if is_generic_statement(pl) and not _generic_allowed(p_lc, en, risk_lc, ev_blob):
        return False
    return True


def apply_uac_evidence_gate(
    current_enriched_jira: JiraEnrichedDocument | dict[str, Any],
    retrieved_similar_jiras: Sequence[RetrievedJira | dict[str, Any]],
    draft_llm_answer: str,
) -> UacEvidenceGateResult:
    """
    Remove UAC bullets that are ungrounded, generic, duplicated, or unsupported by Jira evidence.

    ``dropped_points`` lists removals with reasons for traceability.
    """
    en = _as_enriched(current_enriched_jira)
    similar = [_as_retrieved(x) for x in (retrieved_similar_jiras or [])]

    structural = _enriched_anchors(en) | _retrieved_anchors(similar)
    ev_blob = _evidence_blob(en, similar)
    risk_lc = _risk_blob(en)

    kept: list[str] = []
    dropped: list[DroppedPoint] = []
    seen_norm: set[str] = set()

    for point in _split_points(draft_llm_answer):
        pl = point.strip()
        if not pl:
            continue
        p_lc = pl.lower()

        nd = _normalize_for_dedupe(pl)
        if nd in seen_norm:
            dropped.append(DroppedPoint(text=pl, reason="duplicate_of_another_point"))
            continue
        if not uac_claim_passes(pl, en, similar):
            if not _point_mentions_any_anchor(p_lc, structural):
                dropped.append(
                    DroppedPoint(
                        text=pl,
                        reason="no_mention_of_ticket_entities_outputs_components_customers_or_similar_jira",
                    )
                )
            elif not _overlap_with_evidence(p_lc, ev_blob):
                dropped.append(DroppedPoint(text=pl, reason="unsupported_by_current_or_retrieved_evidence"))
            else:
                dropped.append(DroppedPoint(text=pl, reason="generic_qa_advice_without_jira_specific_risk"))
            continue

        seen_norm.add(nd)
        kept.append(pl)

    cleaned = "\n".join(f"- {p}" for p in kept) if kept else ""
    return UacEvidenceGateResult(cleaned_answer=cleaned, dropped_points=dropped)
