"""Verify structured UAC claims against Jira evidence (anchors, overlap, generics, duplicates)."""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Sequence, TypedDict

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from app.services.uac_evidence_gate import (
    _as_enriched,
    _enriched_anchors,
    _evidence_blob,
    _generic_allowed,
    _JIRA_KEY_RE,
    _normalize_for_dedupe,
    _overlap_with_evidence,
    _point_mentions_any_anchor,
    _retrieved_anchors,
    _risk_blob,
    _tokens,
    is_generic_statement,
    uac_claim_passes,
)


class UacEvidenceStore(TypedDict, total=False):
    """Bundle passed to ``verify_uac_claims`` (same inputs as the markdown evidence gate)."""

    enriched_jira: JiraEnrichedDocument | dict[str, Any]
    similar_jiras: Sequence[RetrievedJira | dict[str, Any]]


def _similar_row_as_retrieved(row: RetrievedJira | dict[str, Any]) -> RetrievedJira:
    """Accept Copilot API similar rows (``document_excerpt``) or full ``RetrievedJira``."""
    if isinstance(row, RetrievedJira):
        return row
    d = dict(row)
    try:
        return RetrievedJira.model_validate(d)
    except Exception:
        md = d.get("metadata")
        return RetrievedJira(
            jira_key=str(d.get("jira_key") or "").strip(),
            title=str(d.get("title") or d.get("summary") or "").strip(),
            document=str(d.get("document") or d.get("document_excerpt") or "")[:8000],
            why_similar=str(d.get("why_similar") or d.get("why_relevant") or "").strip(),
            metadata=md if isinstance(md, dict) else {},
        )


_WS_RE = re.compile(r"\s+")


def _semantic_evidence_blob(en: JiraEnrichedDocument, similar: Sequence[RetrievedJira]) -> str:
    """Narrative + similar chunks only (keys still repeated in full blob for ``uac_claim_passes``)."""
    chunks: list[str] = [
        (en.raw_text or "")[:6000],
        (en.description or "")[:4000],
        (en.summary or "")[:500],
        " ".join(en.dita_entities or []),
        " ".join(en.affected_outputs or []),
        " ".join(en.components or []),
        " ".join(en.customer_names or []),
        _risk_blob(en),
    ]
    for r in similar:
        chunks.append(f"{(r.document or '')[:1200]} {(r.why_similar or '')}")
    return _WS_RE.sub(" ", " ".join(chunks).strip().lower())


_STRONG_LANG_RE = re.compile(
    r"\b("
    r"must\s+always|always\s+works|guaranteed|proven\b|definitely\b|"
    r"all\s+customers|every\s+customer|every\s+output|all\s+outputs|"
    r"without\s+exception|for\s+sure|certainly\b|"
    r"100\s*%\s*coverage|complete\s+coverage|zero\s+risk"
    r")\b",
    re.I,
)


def _scenario_evidence_supports(
    row: dict[str, Any],
    ev_lc: str,
    similar_keys_lc: set[str],
) -> bool:
    """True if scenario ``evidence`` cites content present in the evidence corpus or a known similar key."""
    ev = row.get("evidence")
    parts: list[str] = []
    if isinstance(ev, list):
        parts.extend(str(x).strip() for x in ev if x is not None and str(x).strip())
    elif isinstance(ev, str) and ev.strip():
        parts.append(ev.strip())
    if not parts:
        return False
    for p in parts:
        pl = p.lower()
        if pl in ev_lc:
            return True
        m = _JIRA_KEY_RE.search(p)
        if m:
            key = m.group(0).lower()
            if key in similar_keys_lc or key in ev_lc:
                return True
    return False


def _similar_jira_keys_lower(similar: Sequence[RetrievedJira]) -> set[str]:
    return {(r.jira_key or "").strip().lower() for r in similar if (r.jira_key or "").strip()}


def _weak_evidence_overlap_only(claim_lc: str, ev_lc: str) -> bool:
    """True if overlap exists only via tokens shorter than 5 chars (weak grounding)."""
    ptoks = set(_tokens(claim_lc))
    if not ptoks:
        return False
    hitting = {t for t in ptoks if t in ev_lc}
    if not hitting:
        return False
    return all(len(t) < 5 for t in hitting)


def _strong_overlap(claim_lc: str, ev_lc: str) -> bool:
    """Non-weak overlap: at least one token len>=5 in evidence."""
    for tok in _tokens(claim_lc):
        if len(tok) >= 5 and tok in ev_lc:
            return True
    return False


def _has_strong_assertion_language(text: str) -> bool:
    return bool(_STRONG_LANG_RE.search(text or ""))


def _confidence_snapshot(conf: dict[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(conf[k]) for k in ("level", "score", "overall", "signals") if k in conf}


def _apply_confidence_downgrade(conf: dict[str, Any]) -> None:
    level = str(conf.get("level") or "").strip().lower()
    if level in ("high", "medium"):
        conf["level"] = "low"
    score = conf.get("score")
    if isinstance(score, (int, float)):
        conf["score"] = max(0.0, float(score) * 0.65)
    overall = conf.get("overall")
    if isinstance(overall, (int, float)):
        conf["overall"] = max(0.0, min(1.0, float(overall) * 0.75))
    sig = conf.get("signals")
    if isinstance(sig, list):
        if "claim_verifier_downgrade" not in sig:
            sig.append("claim_verifier_downgrade")
    else:
        conf["signals"] = ["claim_verifier_downgrade"]


def _claim_for_scenario(row: dict[str, Any]) -> str:
    sc = str(row.get("scenario") or "").strip()
    why = str(row.get("why") or "").strip()
    if sc and why:
        return f"{sc} {why}"
    return sc or why


def _claim_for_clarification(row: dict[str, Any]) -> str:
    q = str(row.get("question") or "").strip()
    why = str(row.get("why") or "").strip()
    if q and why:
        return f"{q} {why}"
    return q or why


def verify_uac_claims(
    generated_uac_response: dict[str, Any],
    evidence_store: UacEvidenceStore | dict[str, Any],
    *,
    drop_strong_unsupported: bool = True,
    downgrade_weak: bool = True,
    allow_warn_keep: bool = True,
    refresh_markdown: bool = False,
    format_markdown_fn: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """
    Deep-copy ``generated_uac_response``, drop or annotate structured claims that fail evidence checks.

    Returns a dict with ``verified_response``, ``dropped_claims``, ``downgraded_claims``,
    ``unsupported_claims``.
    """
    if not isinstance(evidence_store, dict):
        raise TypeError("evidence_store must be a dict-like mapping")
    en = _as_enriched(evidence_store.get("enriched_jira") or {})
    similar = [_similar_row_as_retrieved(x) for x in (evidence_store.get("similar_jiras") or [])]

    structural = _enriched_anchors(en) | _retrieved_anchors(similar)
    ev_lc = _evidence_blob(en, similar)
    semantic_lc = _semantic_evidence_blob(en, similar)
    risk_lc = _risk_blob(en)
    similar_keys_lc = _similar_jira_keys_lower(similar)

    verified = copy.deepcopy(generated_uac_response)
    dropped_claims: list[dict[str, Any]] = []
    downgraded_claims: list[dict[str, Any]] = []
    unsupported_claims: list[dict[str, Any]] = []

    global_downgrade_once = False
    prior_conf = verified.get("confidence") if isinstance(verified.get("confidence"), dict) else {}
    prior_snapshot = _confidence_snapshot(prior_conf) if prior_conf else {}

    dedupe_seen: set[str] = set()

    def process_claim(
        *,
        kind: str,
        field: str,
        index: int,
        text: str,
        row: dict[str, Any] | None = None,
        is_scenario: bool = False,
    ) -> str | None:
        """Return ``None`` to drop the item; otherwise keep (``text`` unchanged for drivers)."""
        nonlocal global_downgrade_once
        pl = (text or "").strip()
        if not pl:
            return None

        nd = _normalize_for_dedupe(pl)
        if nd in dedupe_seen:
            dropped_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reason": "duplicate_claim",
                }
            )
            return None
        dedupe_seen.add(nd)

        p_lc = pl.lower()
        has_anchor = _point_mentions_any_anchor(p_lc, structural)
        has_overlap = _overlap_with_evidence(p_lc, ev_lc)
        struct_ev_ok = bool(is_scenario and row and _scenario_evidence_supports(row, ev_lc, similar_keys_lc))

        if struct_ev_ok:
            has_overlap = True

        if (
            drop_strong_unsupported
            and _has_strong_assertion_language(pl)
            and has_anchor
            and not _strong_overlap(p_lc, semantic_lc)
            and not struct_ev_ok
        ):
            dropped_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reason": "strong_assertion_without_evidence_overlap",
                }
            )
            return None

        if struct_ev_ok or uac_claim_passes(pl, en, similar):
            return pl

        if allow_warn_keep and (not has_anchor) and _strong_overlap(p_lc, ev_lc):
            if row is not None:
                row["claim_verifier_warning"] = (
                    "No explicit entity/output/customer anchor; grounded only by token overlap with indexed evidence."
                )
            unsupported_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reasons": ["missing_structural_anchor", "strong_token_overlap_kept"],
                }
            )
            return pl

        if (
            downgrade_weak
            and has_anchor
            and has_overlap
            and _weak_evidence_overlap_only(p_lc, ev_lc)
            and not struct_ev_ok
        ):
            if row is not None:
                row["claim_verifier_warning"] = "Weak evidence overlap (short tokens only); confidence downgraded."
            dc_entry: dict[str, Any] = {
                "kind": kind,
                "field": field,
                "index": index,
                "reason": "weak_token_overlap",
                "prior_confidence": prior_snapshot or None,
                "new_confidence": None,
            }
            downgraded_claims.append(dc_entry)
            if not global_downgrade_once and isinstance(verified.get("confidence"), dict):
                _apply_confidence_downgrade(verified["confidence"])
                snap_after = _confidence_snapshot(verified["confidence"])
                dc_entry["new_confidence"] = snap_after
                global_downgrade_once = True
            return pl

        generic = is_generic_statement(pl)
        gen_ok = generic and _generic_allowed(p_lc, en, risk_lc, ev_lc)
        if generic and not gen_ok:
            dropped_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reason": "generic_qa_without_jira_specific_risk",
                }
            )
            return None

        if not has_anchor:
            dropped_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reason": "no_mention_of_ticket_entities_outputs_components_customers_or_similar_jira",
                }
            )
            return None

        if not has_overlap and not struct_ev_ok:
            dropped_claims.append(
                {
                    "kind": kind,
                    "field": field,
                    "index": index,
                    "text": pl[:500],
                    "reason": "unsupported_by_current_or_retrieved_evidence",
                }
            )
            return None

        dropped_claims.append(
            {
                "kind": kind,
                "field": field,
                "index": index,
                "text": pl[:500],
                "reason": "failed_claim_verifier",
            }
        )
        return None

    risk = verified.get("risk_summary")
    if isinstance(risk, dict):
        drivers_in = risk.get("drivers")
        if isinstance(drivers_in, list):
            new_drivers: list[str] = []
            for i, d in enumerate(drivers_in):
                if not isinstance(d, str):
                    continue
                kept = process_claim(kind="driver", field="risk_summary.drivers", index=i, text=d, row=None)
                if kept is not None:
                    new_drivers.append(kept)
            risk["drivers"] = new_drivers

    scenarios_in = verified.get("must_test_scenarios")
    if isinstance(scenarios_in, list):
        new_scen: list[dict[str, Any]] = []
        for i, row in enumerate(scenarios_in):
            if not isinstance(row, dict):
                continue
            claim = _claim_for_scenario(row)
            if process_claim(
                kind="scenario",
                field="must_test_scenarios",
                index=i,
                text=claim,
                row=row,
                is_scenario=True,
            ) is not None:
                new_scen.append(row)
        verified["must_test_scenarios"] = new_scen

    clar_in = verified.get("missing_clarifications")
    if isinstance(clar_in, list):
        new_clar: list[dict[str, Any]] = []
        for i, row in enumerate(clar_in):
            if not isinstance(row, dict):
                continue
            claim = _claim_for_clarification(row)
            if process_claim(
                kind="clarification",
                field="missing_clarifications",
                index=i,
                text=claim,
                row=row,
            ) is not None:
                new_clar.append(row)
        verified["missing_clarifications"] = new_clar

    for dc in downgraded_claims:
        if dc.get("new_confidence") is None and isinstance(verified.get("confidence"), dict):
            dc["new_confidence"] = _confidence_snapshot(verified["confidence"])

    if refresh_markdown and format_markdown_fn is not None:
        verified["uac_answer"] = format_markdown_fn(verified)

    return {
        "verified_response": verified,
        "dropped_claims": dropped_claims,
        "downgraded_claims": downgraded_claims,
        "unsupported_claims": unsupported_claims,
    }


__all__ = ["UacEvidenceStore", "verify_uac_claims"]
