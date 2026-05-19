"""Build a compact UAC decision record for Jira comments (evidence-grounded, no LLM)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.answer_quality_service import generic_phrase_patterns_in_text

_MAX_LINE = 220
_MAX_SUMMARY = 360
_MAX_ITEMS = 6

_DEV_HINT_RE = re.compile(
    r"\b(code|build|deploy|patch|api|server|repository|repo|config|bundle|package|plug-?in|sdk|branch|commit)\b",
    re.I,
)


def _as_enriched_dict(obj: JiraEnrichedDocument | Mapping[str, Any] | None) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, JiraEnrichedDocument):
        return obj.model_dump()
    return dict(obj)


def _generic(text: str) -> bool:
    return bool(generic_phrase_patterns_in_text(text or ""))


def _clip(s: str, n: int = _MAX_LINE) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0] + "…"


def _cls(payload: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    c = payload.get("classification")
    if isinstance(c, dict) and c:
        return c
    return {
        "jira_key": enriched.get("jira_key") or payload.get("jira_key"),
        "domain": enriched.get("domain") or "unknown",
        "dita_entities": enriched.get("dita_entities") or [],
        "affected_outputs": enriched.get("affected_outputs") or [],
        "customer_names": enriched.get("customer_names") or [],
        "components": enriched.get("components") or [],
    }


def _risk_level(payload: dict[str, Any]) -> str:
    risk = payload.get("risk_summary")
    if not isinstance(risk, dict):
        return "unspecified"
    for k in ("level", "message"):
        v = str(risk.get(k) or "").strip().lower()
        if v and v != "insufficient evidence from indexed jira data.":
            if k == "level":
                return v
    rs = risk.get("risk_score")
    if isinstance(rs, (int, float)):
        if rs >= 2.5:
            return "high"
        if rs >= 1.5:
            return "medium"
        return "low"
    return str(risk.get("level") or "unspecified").lower()


def build_uac_decision_record(
    uac_payload: dict[str, Any],
    enriched: JiraEnrichedDocument | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Produce a Jira-comment-friendly decision record from a finalized UAC API payload.

    Lists contain short, single-line strings suitable for paste into a comment (- bullets added by human if desired).
    """
    en = _as_enriched_dict(enriched)
    pl = uac_payload
    cls = _cls(pl, en)
    jk = str(cls.get("jira_key") or pl.get("jira_key") or en.get("jira_key") or "TICKET").strip()
    domain = str(cls.get("domain") or en.get("domain") or "unknown")
    ents = [str(x).strip() for x in (cls.get("dita_entities") or en.get("dita_entities") or []) if str(x).strip()][
        :4
    ]
    outs = [str(x).strip() for x in (cls.get("affected_outputs") or en.get("affected_outputs") or []) if str(x).strip()][
        :4
    ]
    cust = [str(x).strip() for x in (cls.get("customer_names") or en.get("customer_names") or []) if str(x).strip()][
        :2
    ]

    similar_n = len(pl.get("similar_jiras") or []) if isinstance(pl.get("similar_jiras"), list) else 0
    risk_lvl = _risk_level(pl)
    val_ok = bool(pl.get("uac_validation_ok", True))
    insuf = bool(pl.get("insufficient_similar_evidence"))

    ent_glue = ", ".join(ents) if ents else "—"
    out_glue = ", ".join(outs) if outs else "—"
    cust_glue = f"; customers: {', '.join(cust)}" if cust else ""

    summary_parts = [
        f"{jk} UAC snapshot ({domain}): entities «{ent_glue}», outputs «{out_glue}»{cust_glue}.",
        f"Indexed similar tickets: {similar_n}. Risk: {risk_lvl}. Payload validation: {'ok' if val_ok else 'needs review'}.",
    ]
    if insuf:
        summary_parts.append("Evidence gate: similar-ticket pool below threshold—add repro artifacts or targeted UAT before release sign-off.")
    summary = _clip(" ".join(summary_parts), _MAX_SUMMARY)

    decisions_needed: list[str] = []
    clar = pl.get("missing_clarifications") if isinstance(pl.get("missing_clarifications"), list) else []
    for row in clar[:_MAX_ITEMS]:
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        if not q or _generic(q):
            continue
        line = _clip(q, _MAX_LINE)
        if line not in decisions_needed:
            decisions_needed.append(line)

    cv = pl.get("claim_verification") if isinstance(pl.get("claim_verification"), dict) else {}
    dropped = cv.get("dropped_claims") if isinstance(cv.get("dropped_claims"), list) else []
    if len(dropped) > 0:
        reasons = {str(d.get("reason") or "") for d in dropped if isinstance(d, dict)}
        r_compact = ", ".join(sorted(x for x in reasons if x)[:3])
        if r_compact:
            decisions_needed.append(_clip(f"Claim verifier removed {len(dropped)} structured bullet(s) ({r_compact})—re-run scope or attach missing evidence.", _MAX_LINE))

    qa_commitments: list[str] = []
    scen = pl.get("must_test_scenarios") if isinstance(pl.get("must_test_scenarios"), list) else []
    for row in scen[:_MAX_ITEMS]:
        if not isinstance(row, dict):
            continue
        sc = str(row.get("scenario") or "").strip()
        if not sc or _generic(sc):
            continue
        pri = str(row.get("priority") or "P2").strip()
        layer = str(row.get("test_layer") or "").strip()
        extra = f" [{pri}" + (f", {layer}]" if layer else "]")
        body = _clip(f"{jk}: {sc}", max(40, _MAX_LINE - len(extra)))
        line = f"{body}{extra}"
        if line not in qa_commitments:
            qa_commitments.append(line)

    dev_questions: list[str] = []
    for row in clar[:_MAX_ITEMS]:
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        if not q or _generic(q):
            continue
        if not _DEV_HINT_RE.search(q):
            continue
        line = _clip(f"[Dev] {q}", _MAX_LINE)
        if line not in dev_questions and line not in decisions_needed:
            dev_questions.append(line)

    automation_plan: list[str] = []
    fit = pl.get("automation_fit") if isinstance(pl.get("automation_fit"), dict) else {}
    if fit:
        label = str(fit.get("fit") or "Partial").strip()
        layer = str(fit.get("primary_test_layer") or "").strip()
        reason = str(fit.get("framework") or "").strip()
        if reason and not _generic(reason):
            automation_plan.append(_clip(f"Automation fit {label}; layer {layer or 'TBD'} — {reason}", _MAX_LINE))
        else:
            automation_plan.append(_clip(f"Automation fit {label}; primary layer {layer or 'manual first'}.", _MAX_LINE))
        cls_jk = str(cls.get("jira_key") or jk).lower().replace("-", "_")
        automation_plan.append(_clip(f"Suggested automated name stem: `{cls_jk}_uac` (align with AEM Guides rubric).", 200))

    dataset_needed: list[str] = []
    if insuf:
        dataset_needed.append(
            "Dataset/fixture: add labelled DITA + map samples mirroring this ticket’s entity/output mix for regression replay."
        )
        errs = pl.get("uac_validation_errors") or []
        err_preview = errs[:2] if isinstance(errs, list) else []
        err_txt = ", ".join(str(e) for e in err_preview)
        if err_txt:
            dataset_needed.append(
                _clip(f"Repair bundle: address validator flags ({err_txt}) before freezing fixtures.", _MAX_LINE)
            )
    if similar_n >= 3 and ents:
        dataset_needed.append(
            _clip(
                f"Optional contrast set: pair {jk} with {similar_n} retrieved keys sharing «{ents[0]}» for fine-tune or eval negatives.",
                _MAX_LINE,
            )
        )

    parity = pl.get("output_parity") if isinstance(pl.get("output_parity"), dict) else {}
    pairs = parity.get("parity_pairs") if isinstance(parity.get("parity_pairs"), list) else []
    parity_on = bool(parity.get("parity_required")) and len(pairs) > 0

    release_bits = [f"Risk level {risk_lvl} per indexed enrichment + UAC drivers."]
    if parity_on:
        release_bits.append(
            f"Cross-output parity flagged ({len(pairs)} pair(s))—block ship if preview/native_pdf/sites diverge on {out_glue}."
        )
    if insuf:
        release_bits.append("Release: do not treat low-similar evidence as absence of defect—tighten customer UAT.")
    anti = pl.get("anti_repetition") if isinstance(pl.get("anti_repetition"), dict) else {}
    if anti.get("changed"):
        release_bits.append("Anti-repetition adjusted scenario/driver wording—diff against prior publish artifacts.")

    release_risk = _clip(" ".join(release_bits), _MAX_SUMMARY)

    return {
        "summary": summary,
        "decisions_needed": decisions_needed[:_MAX_ITEMS],
        "qa_commitments": qa_commitments[:_MAX_ITEMS],
        "dev_questions": dev_questions[:_MAX_ITEMS],
        "automation_plan": automation_plan[:4],
        "dataset_needed": dataset_needed[:_MAX_ITEMS],
        "release_risk": release_risk,
    }


__all__ = ["build_uac_decision_record"]
