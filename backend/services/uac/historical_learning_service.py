"""Derive concrete QA learnings from a historical Jira vs the current ticket (UAC / copilot)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira, explain_similarity


def _current_as_dict(current_jira: JiraEnrichedDocument | dict[str, Any]) -> dict[str, Any]:
    if isinstance(current_jira, JiraEnrichedDocument):
        return current_jira.model_dump()
    return dict(current_jira) if isinstance(current_jira, dict) else {}


def _similar_meta(similar_jira: RetrievedJira | dict[str, Any]) -> dict[str, Any]:
    if isinstance(similar_jira, RetrievedJira):
        m = similar_jira.metadata
        return m if isinstance(m, dict) else {}
    raw = dict(similar_jira) if isinstance(similar_jira, dict) else {}
    m = raw.get("metadata")
    return m if isinstance(m, dict) else {}


def _snippet(text: str, max_chars: int = 400) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3].rsplit(" ", 1)[0] + "..."


def _profile_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("enrich_profile_json")
    if not raw or not isinstance(raw, str):
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _historical_failure_pattern(
    meta: dict[str, Any],
    *,
    document: str,
    title: str,
) -> str:
    prof = _profile_from_meta(meta)
    symptoms = prof.get("symptoms") if isinstance(prof.get("symptoms"), list) else []
    sym_txt = "; ".join(str(s).strip() for s in symptoms[:6] if str(s).strip())
    if sym_txt:
        return _snippet(f"Recorded symptoms on the historical ticket: {sym_txt}", 500)
    actual = str(prof.get("actual_behavior") or "").strip()
    if actual:
        return _snippet(f"Historical actual behavior: {actual}", 500)
    blob = (document or title or "").strip()
    if blob:
        return _snippet(f"From indexed historical excerpt: {blob}", 500)
    return (
        "No structured symptom or behavior fields on the historical chunk; treat overlap as directional only "
        "and read the full ticket in Jira before mining root cause."
    )


def _risk_relevance_sentence(
    cur: dict[str, Any],
    expl: dict[str, Any],
    *,
    jira_key: str,
) -> str:
    cur_outs = list((cur.get("affected_outputs") or []))[:5]
    cur_dom = str(cur.get("domain") or "").strip() or "unknown"
    me = expl.get("matching_entities") or []
    mo = expl.get("matching_outputs") or []
    mc = expl.get("matching_customers") or []
    parts: list[str] = []
    if mo:
        parts.append(
            f"The current ticket targets outputs {', '.join(str(x) for x in cur_outs[:3]) or '—'}; "
            f"{jira_key} already showed failure modes around {', '.join(str(x) for x in mo[:4])}."
        )
    elif cur_outs:
        parts.append(f"Current outputs of focus: {', '.join(str(x) for x in cur_outs[:4])}.")
    if me:
        parts.append(
            f"Shared DITA/AEM surface includes {', '.join(str(x) for x in me[:4])}, so regressions may cluster there."
        )
    if mc:
        parts.append(f"Customer pressure or config overlap mirrors {', '.join(str(x) for x in mc[:2])}.")
    if cur_dom and cur_dom != "unknown":
        parts.append(f"Domain context: {cur_dom.replace('_', ' ')}.")
    if not parts:
        return (
            f"Risk transfer from {jira_key} is uncertain without entity/output/customer overlap; "
            f"use the historical ticket as a checklist, not proof the same defect recurs."
        )
    return " ".join(parts)[:900]


def _qa_learning_line(expl: dict[str, Any], *, jira_key: str, conf_bucket: str) -> str:
    base = str(expl.get("what_we_learned") or "").strip()
    me = expl.get("matching_entities") or []
    mo = expl.get("matching_outputs") or []
    mc = expl.get("matching_customers") or []
    comps = expl.get("matching_components") or []
    bits: list[str] = []
    if base:
        bits.append(base)
    if comps:
        bits.append(f"Historical components touched: {', '.join(str(c) for c in comps[:4])}.")
    if conf_bucket == "low":
        bits.append(
            "Because retrieval confidence is low, validate any assumptions from this ticket against the current repro "
            "and environment before expanding test scope."
        )
    elif mc and not mo:
        bits.append("Customer overlap suggests validating licensing/tenant-specific paths, not only core product paths.")
    elif mo and not me:
        bits.append("Output overlap without entity overlap: focus tests on Publish/PDF/_SITES/Web paths first, then narrow to constructs.")
    elif me and mo:
        bits.append("Re-run the historical failure recipe on the same entity+output pair, then add deltas from the current summary.")
    if not bits:
        bits.append(
            f"Use {jira_key} as a human-reviewed precedent: extract explicit repro and fixed-version notes from Jira, "
            "then map only the steps that still apply."
        )
    return " ".join(bits)[:1200]


def _reusable_test_idea(
    cur: dict[str, Any],
    expl: dict[str, Any],
    *,
    jira_key: str,
    conf_bucket: str,
) -> str:
    me = expl.get("matching_entities") or []
    mo = expl.get("matching_outputs") or []
    comps = expl.get("matching_components") or []
    cur_summary = _snippet(str(cur.get("summary") or ""), 120)
    mo_s = ", ".join(str(x) for x in (mo[:2] or ["the shared output surface"]))
    ent_s = ", ".join(str(x) for x in (me[:3] or ["relevant DITA constructs from the current map/topic"]))
    comp_s = f" under components {', '.join(str(c) for c in comps[:3])}" if comps else ""
    idea = (
        f"Regression: publish/validate {mo_s} with content that stresses {ent_s}{comp_s}. "
        f"Compare against the closure notes for {jira_key}; extend with current scenario: {cur_summary or 'current summary'}."
    )
    if conf_bucket == "low":
        idea += (
            f" Mark as exploratory until at least one of entity, output, or component overlap is confirmed in Jira."
        )
    return _snippet(idea, 700)


def _confidence_bucket(score: float, expl: dict[str, Any]) -> str:
    me = list(expl.get("matching_entities") or [])
    mo = list(expl.get("matching_outputs") or [])
    mc = list(expl.get("matching_customers") or [])
    comps = list(expl.get("matching_components") or [])
    struct_dims = sum(bool(x) for x in (me, mo, mc, comps))
    if score >= 0.62 and me and mo:
        return "high"
    if score >= 0.55 and struct_dims >= 2:
        return "high"
    if score >= 0.45 and (me or mo) and struct_dims >= 1:
        return "medium"
    if score >= 0.40 and struct_dims >= 1:
        return "medium"
    if score >= 0.35 or struct_dims >= 1:
        return "medium"
    return "low"


def extract_learning(
    current_jira: JiraEnrichedDocument | dict[str, Any],
    similar_jira: RetrievedJira | dict[str, Any],
) -> dict[str, Any]:
    """
    For one retrieved historical ticket, produce concrete overlap-driven learning for QA.

    ``current_jira`` is the enriched current issue; ``similar_jira`` is one hybrid retrieval row
    (``RetrievedJira`` or compatible dict).
    """
    cur = _current_as_dict(current_jira)
    expl = explain_similarity(cur, similar_jira)
    jk = str(expl.get("jira_key") or "").strip() or "UNKNOWN"

    meta = _similar_meta(similar_jira)
    if isinstance(similar_jira, RetrievedJira):
        doc = similar_jira.document or ""
        title = similar_jira.title or ""
    else:
        raw = dict(similar_jira) if isinstance(similar_jira, dict) else {}
        doc = str(raw.get("document") or "")
        title = str(raw.get("title") or "")

    conf_num = float(expl.get("confidence_score") or 0.0)
    bucket = _confidence_bucket(conf_num, expl)

    why = str(expl.get("why_similar") or "").strip()
    if not why or len(why) < 24:
        why = (
            f"Concrete overlap signals for {jk}: entities={expl.get('matching_entities') or []}, "
            f"outputs={expl.get('matching_outputs') or []}, customers={expl.get('matching_customers') or []}, "
            f"components={expl.get('matching_components') or []}."
        )

    return {
        "jira_key": jk,
        "why_similar": why[:2000],
        "historical_failure_pattern": _historical_failure_pattern(meta, document=doc, title=title),
        "qa_learning": _qa_learning_line(expl, jira_key=jk, conf_bucket=bucket),
        "risk_relevance": _risk_relevance_sentence(cur, expl, jira_key=jk),
        "reusable_test_idea": _reusable_test_idea(cur, expl, jira_key=jk, conf_bucket=bucket),
        "confidence": bucket,
    }
