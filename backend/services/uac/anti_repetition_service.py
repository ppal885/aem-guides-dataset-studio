"""De-duplicate and re-ground UAC structured fields using recent per-domain memory (SQLite)."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.db.session import SessionLocal
from app.db.uac_memory_models import UacAntiRepetitionMemory
from services.answer_quality_service import generic_phrase_patterns_in_text
from services.uac_generation_service import INSUFFICIENT_EVIDENCE_MESSAGE
from services.uac.uac_output_validator import _sync_structured_from_top_level

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_:-]{2,}", re.I)
_MAX_SCENARIO_LEN = 220
_MAX_DRIVER_LEN = 260
_MAX_QUESTION_LEN = 240
_JACCARD_DUP = float(os.getenv("UAC_ANTI_REPETITION_JACCARD", "0.52"))
_LOOKBACK = int(os.getenv("UAC_ANTI_REPETITION_LOOKBACK", "35"))
_PRUNE_DOMAIN = int(os.getenv("UAC_ANTI_REPETITION_PRUNE_PER_DOMAIN", "200"))
_ANCHOR_RATIO = float(os.getenv("UAC_ANTI_REPETITION_ANCHOR_RATIO", "0.6"))
_ENABLED = os.getenv("UAC_ANTI_REPETITION_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AntiRepetitionMeta:
    changed: bool = False
    skipped: bool = False
    scenarios_deduped: int = 0
    scenarios_rewritten_memory: int = 0
    scenarios_strengthened_anchor: int = 0
    drivers_dropped_generic: int = 0
    drivers_rewritten: int = 0
    clarifications_rewritten: int = 0
    markdown_refreshed: bool = False
    reasons: list[str] = field(default_factory=list)


def _norm_domain(domain: str | None) -> str:
    d = (domain or "").strip().lower().replace(" ", "_")
    return d if d else "unknown"


def _normalize_phrase(s: str) -> str:
    t = re.sub(r"[^\w\s]", " ", (s or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _token_set(s: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(s or "") if len(m.group(0)) >= 4}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _truncate(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3].rsplit(" ", 1)[0] + "..."


def _jira_anchor_terms(enriched: JiraEnrichedDocument) -> set[str]:
    out: set[str] = set()
    jk = (enriched.jira_key or "").strip().lower()
    if jk:
        out.add(jk)
        # project prefix
        if "-" in jk:
            out.add(jk.split("-", 1)[0].lower())
    for x in enriched.dita_entities or []:
        t = str(x).strip().lower()
        if len(t) >= 3:
            out.add(t)
    for x in enriched.affected_outputs or []:
        t = str(x).strip().lower()
        if len(t) >= 3:
            out.add(t)
    for x in enriched.customer_names or []:
        t = str(x).strip().lower()
        if len(t) >= 4:
            out.add(t)
    for x in enriched.components or []:
        t = str(x).strip().lower()
        if len(t) >= 3:
            out.add(t)
    for w in (enriched.summary or "").split():
        wl = re.sub(r"[^\w]", "", w).lower()
        if len(wl) >= 5:
            out.add(wl)
    return {t for t in out if t}


def _primary_entity(enriched: JiraEnrichedDocument) -> str:
    ents = [str(x).strip() for x in (enriched.dita_entities or []) if str(x).strip()]
    return ents[0] if ents else "dita_topic"


def _primary_output(enriched: JiraEnrichedDocument) -> str:
    outs = [str(x).strip() for x in (enriched.affected_outputs or []) if str(x).strip()]
    return outs[0] if outs else "published_output"


def _scenario_anchor_hits(text: str, anchors: set[str]) -> int:
    low = (text or "").lower()
    return sum(1 for a in anchors if a and a in low)


def _anchor_ratio_ok(scenarios: list[dict[str, Any]], anchors: set[str]) -> tuple[float, list[int]]:
    if not scenarios:
        return 1.0, []
    hits: list[int] = []
    for row in scenarios:
        sc = str(row.get("scenario") or "")
        cnt = _scenario_anchor_hits(sc, anchors)
        hits.append(cnt)
    ok_count = sum(1 for h in hits if h > 0)
    ratio = ok_count / len(scenarios)
    # indices weak: anchor hit count ascending
    weak_idx = sorted(range(len(hits)), key=lambda i: (hits[i], -i))
    return ratio, weak_idx


def _phrases_from_memory_rows(
    rows: list[UacAntiRepetitionMemory],
) -> tuple[set[str], list[str], set[str], list[str], set[str], list[str]]:
    """Return norm sets + raw lists for Jaccard / substring checks (scenarios, drivers, questions)."""
    scen_norm: set[str] = set()
    driver_norm: set[str] = set()
    question_norm: set[str] = set()
    raw_scenarios: list[str] = []
    raw_drivers: list[str] = []
    raw_questions: list[str] = []
    for r in rows:
        for t in r.scenario_titles or []:
            if isinstance(t, str) and t.strip():
                scen_norm.add(_normalize_phrase(t))
                raw_scenarios.append(t)
        for t in r.risk_drivers or []:
            if isinstance(t, str) and t.strip():
                driver_norm.add(_normalize_phrase(t))
                raw_drivers.append(t)
        for t in r.clarification_questions or []:
            if isinstance(t, str) and t.strip():
                question_norm.add(_normalize_phrase(t))
                raw_questions.append(t)
    return scen_norm, raw_scenarios, driver_norm, raw_drivers, question_norm, raw_questions


def _near_duplicate_text(text: str, history_norms: set[str], history_raw: list[str]) -> bool:
    n = _normalize_phrase(text)
    if not n:
        return False
    if n in history_norms:
        return True
    tok = _token_set(text)
    for h in history_raw:
        if _jaccard(tok, _token_set(h)) >= _JACCARD_DUP:
            return True
    return False


def _rewrite_scenario(scenario: str, enriched: JiraEnrichedDocument, *, reason: str) -> str:
    jk = enriched.jira_key or "JIRA-KEY"
    ent = _primary_entity(enriched)
    out = _primary_output(enriched)
    suffix = f" — {jk}: {ent}/{out}"
    base = scenario.strip()
    if reason == "anchor":
        suffix = f" ({jk}: {ent} / {out})"
    room = _MAX_SCENARIO_LEN - len(suffix)
    if room < 40:
        room = 40
    trimmed = _truncate(base, max(40, room))
    combined = (trimmed + suffix).strip()
    return _truncate(combined, _MAX_SCENARIO_LEN)


def _rewrite_driver(driver: str, enriched: JiraEnrichedDocument) -> str:
    jk = enriched.jira_key or "current"
    ent = _primary_entity(enriched)
    out = _primary_output(enriched)
    d = driver.strip()
    low = d.lower()
    if jk.lower() in low and ent.lower() in low:
        return _truncate(d, _MAX_DRIVER_LEN)
    prefix = f"{jk}: {ent} in {out} — "
    return _truncate(prefix + d, _MAX_DRIVER_LEN)


def _rewrite_question(q: str, enriched: JiraEnrichedDocument) -> str:
    jk = enriched.jira_key or "this ticket"
    ent = _primary_entity(enriched)
    if jk.lower() in (q or "").lower():
        return _truncate(q.strip(), _MAX_QUESTION_LEN)
    return _truncate(f"For {jk} ({ent}): {q.strip()}", _MAX_QUESTION_LEN)


def _fetch_recent(session, domain: str, limit: int) -> list[UacAntiRepetitionMemory]:
    q = (
        session.query(UacAntiRepetitionMemory)
        .filter(UacAntiRepetitionMemory.domain == domain)
        .order_by(UacAntiRepetitionMemory.created_at.desc())
        .limit(limit)
    )
    return list(q.all())


def _prune_domain(session, domain: str, keep: int) -> None:
    ids = [
        row[0]
        for row in session.query(UacAntiRepetitionMemory.id)
        .filter(UacAntiRepetitionMemory.domain == domain)
        .order_by(UacAntiRepetitionMemory.created_at.desc())
        .limit(keep)
        .all()
    ]
    if not ids:
        return
    session.query(UacAntiRepetitionMemory).filter(
        UacAntiRepetitionMemory.domain == domain,
        ~UacAntiRepetitionMemory.id.in_(ids),
    ).delete(synchronize_session=False)


def _should_skip(payload: dict[str, Any], *, lenient: bool) -> bool:
    if payload.get("insufficient_similar_evidence"):
        return True
    scenarios = payload.get("must_test_scenarios") or []
    ans = (payload.get("uac_answer") or "").strip()
    if lenient and len(scenarios) == 0:
        return True
    if not scenarios and (INSUFFICIENT_EVIDENCE_MESSAGE in ans or ans.startswith(INSUFFICIENT_EVIDENCE_MESSAGE[:20])):
        return True
    return False


def _payload_snapshot(payload: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    titles = [
        str(r.get("scenario") or "").strip()
        for r in (payload.get("must_test_scenarios") or [])
        if isinstance(r, dict) and str(r.get("scenario") or "").strip()
    ]
    risk = payload.get("risk_summary") if isinstance(payload.get("risk_summary"), dict) else {}
    drivers = [str(d).strip() for d in (risk.get("drivers") or []) if isinstance(d, str) and d.strip()]
    qs = [
        str(r.get("question") or "").strip()
        for r in (payload.get("missing_clarifications") or [])
        if isinstance(r, dict) and str(r.get("question") or "").strip()
    ]
    return titles, drivers, qs


def apply_anti_repetition(
    payload: dict[str, Any],
    enriched: JiraEnrichedDocument,
    *,
    lenient: bool,
    session: Any | None = None,
    format_markdown_fn: Callable[[dict[str, Any]], str] | None = None,
) -> AntiRepetitionMeta:
    """
    Mutates ``payload`` top-level UAC fields in place (scenarios, risk_summary, missing_clarifications).
    Optionally refreshes ``uac_answer`` via ``format_markdown_fn`` when structural edits occur.
    """
    meta = AntiRepetitionMeta()
    if not _ENABLED:
        meta.skipped = True
        meta.reasons.append("disabled_by_env")
        return meta
    if _should_skip(payload, lenient=lenient):
        meta.skipped = True
        meta.reasons.append("insufficient_or_lenient_empty")
        return meta

    domain = _norm_domain(enriched.domain)
    anchors = _jira_anchor_terms(enriched)
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        recent_rows = _fetch_recent(session, domain, _LOOKBACK)
        scen_norm_set, raw_scen_hist, driver_norm_set, raw_drivers_hist, question_norm_set, raw_questions_hist = (
            _phrases_from_memory_rows(recent_rows)
        )

        scenarios = [dict(s) for s in (payload.get("must_test_scenarios") or []) if isinstance(s, dict)]
        seen_titles: set[str] = set()

        for row in scenarios:
            sc = str(row.get("scenario") or "")
            n = _normalize_phrase(sc)
            dup_in_payload = n in seen_titles
            seen_titles.add(n)
            collision_memory = _near_duplicate_text(sc, scen_norm_set, raw_scen_hist)
            if dup_in_payload or collision_memory:
                row["scenario"] = _rewrite_scenario(sc, enriched, reason="memory" if collision_memory else "dedupe")
                meta.changed = True
                if dup_in_payload:
                    meta.scenarios_deduped += 1
                    meta.reasons.append("dedupe_scenario_payload")
                if collision_memory:
                    meta.scenarios_rewritten_memory += 1
                    meta.reasons.append("rewrite_scenario_memory")

        payload["must_test_scenarios"] = scenarios

        risk = payload.get("risk_summary")
        if isinstance(risk, dict):
            drivers_in = [str(d).strip() for d in (risk.get("drivers") or []) if isinstance(d, str) and d.strip()]
            new_drivers: list[str] = []
            seen_d: set[str] = set()
            for d in drivers_in:
                if generic_phrase_patterns_in_text(d):
                    meta.drivers_dropped_generic += 1
                    meta.changed = True
                    continue
                nd = _normalize_phrase(d)
                if not nd:
                    continue
                if nd in seen_d:
                    meta.changed = True
                    continue
                seen_d.add(nd)
                if nd in driver_norm_set or _near_duplicate_text(d, driver_norm_set, raw_drivers_hist):
                    new_drivers.append(_rewrite_driver(d, enriched))
                    meta.drivers_rewritten += 1
                    meta.changed = True
                else:
                    new_drivers.append(_truncate(d, _MAX_DRIVER_LEN))
            risk["drivers"] = new_drivers[:5]
            payload["risk_summary"] = risk

        clar = [dict(c) for c in (payload.get("missing_clarifications") or []) if isinstance(c, dict)]
        for row in clar:
            q = str(row.get("question") or "")
            if generic_phrase_patterns_in_text(q):
                row["question"] = _rewrite_question("Clarify acceptance scope for the reported behavior.", enriched)
                meta.clarifications_rewritten += 1
                meta.changed = True
                continue
            nq = _normalize_phrase(q)
            if nq in question_norm_set or _near_duplicate_text(q, question_norm_set, raw_questions_hist):
                row["question"] = _rewrite_question(q, enriched)
                meta.clarifications_rewritten += 1
                meta.changed = True
            else:
                row["question"] = _truncate(q.strip(), _MAX_QUESTION_LEN)
        payload["missing_clarifications"] = clar

        ratio, weak_order = _anchor_ratio_ok(scenarios, anchors)
        if ratio < _ANCHOR_RATIO and scenarios and anchors:
            improved = list(scenarios)
            for idx in weak_order:
                if ratio >= _ANCHOR_RATIO:
                    break
                row = improved[idx]
                old = str(row.get("scenario") or "")
                row["scenario"] = _rewrite_scenario(old, enriched, reason="anchor")
                meta.scenarios_strengthened_anchor += 1
                meta.changed = True
                ratio, weak_order = _anchor_ratio_ok(improved, anchors)
            payload["must_test_scenarios"] = improved

        _sync_structured_from_top_level(payload)

        if meta.changed and format_markdown_fn is not None:
            payload["uac_answer"] = format_markdown_fn(payload)
            meta.markdown_refreshed = True

        titles, drivers, questions = _payload_snapshot(payload)
        blob = "|".join(titles + drivers + questions)
        phash = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
        row = UacAntiRepetitionMemory(
            id=str(uuid.uuid4()),
            domain=domain,
            jira_key=str(enriched.jira_key or "")[:48],
            scenario_titles=titles,
            risk_drivers=drivers,
            clarification_questions=questions,
            payload_hash=phash,
        )
        session.add(row)
        _prune_domain(session, domain, _PRUNE_DOMAIN)
        session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()

    return meta


def finalize_payload_with_anti_repetition(
    payload: dict[str, Any],
    enriched: JiraEnrichedDocument,
    *,
    lenient: bool,
    format_markdown_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Apply anti-repetition; attach small meta on payload for debugging."""
    meta = apply_anti_repetition(
        payload,
        enriched,
        lenient=lenient,
        format_markdown_fn=format_markdown_fn,
    )
    payload["anti_repetition"] = {
        "changed": meta.changed,
        "skipped": meta.skipped,
        "scenarios_deduped": meta.scenarios_deduped,
        "scenarios_rewritten_memory": meta.scenarios_rewritten_memory,
        "scenarios_strengthened_anchor": meta.scenarios_strengthened_anchor,
        "drivers_dropped_generic": meta.drivers_dropped_generic,
        "drivers_rewritten": meta.drivers_rewritten,
        "clarifications_rewritten": meta.clarifications_rewritten,
        "markdown_refreshed": meta.markdown_refreshed,
        "reasons": meta.reasons[:12],
    }
    return payload
