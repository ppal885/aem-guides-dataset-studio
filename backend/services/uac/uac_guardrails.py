"""Enterprise guardrails for UAC Copilot output (warnings + blocked claim audit)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.answer_quality_service import generic_phrase_patterns_in_text
from services.uac_evidence_gate import is_generic_statement
from services.uac.uac_output_validator import _evidence_ok, _MAX_SCENARIOS

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer_token", re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]{16,}")),
    ("api_secret_assignment", re.compile(r"(?i)(api[_-]?key|client_secret|api_secret)\s*[:=]\s*\S{8,}")),
    ("password_assignment", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S{4,}")),
    ("jwt_like", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("url_with_credentials", re.compile(r"(?i)https?://[^:]+:[^@\s]+@")),
    ("cookie_header", re.compile(r"(?i)cookie\s*:\s*[^\n]{8,}")),
    ("aws_key_like", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

_CUSTOMFIELD_RE = re.compile(r"\bcustomfield_\d+\b", re.I)

_CUSTOMER_IMPACT_RE = re.compile(
    r"\b(customers?|clients?|accounts?)\b.{0,120}\b(impact|blocked|blocker|escalat|"
    r"outage|sev-?1|production\s+down|revenue|sla)\b",
    re.I | re.S,
)

_HISTORICAL_REGRESSION_RE = re.compile(
    r"\b(historically|in\s+past\s+releases?|previous\s+versions?|"
    r"we\s+('ve|have)\s+seen|seen\s+before|long-?standing|years?\s+of|"
    r"known\s+regress|pattern\s+from\s+old|similar\s+bugs\s+before)\b",
    re.I,
)


def _enriched_blob(en: Mapping[str, Any]) -> str:
    parts = [
        str(en.get("description") or ""),
        str(en.get("raw_text") or ""),
        str(en.get("summary") or ""),
        " ".join(str(x) for x in (en.get("labels") or []) if x),
    ]
    return " ".join(parts).lower()


def _has_customer_evidence(en: Mapping[str, Any], blob: str) -> bool:
    if en.get("customer_names"):
        return True
    if any("customer" in str(l).lower() for l in (en.get("labels") or [])):
        return True
    if re.search(r"\bcustomer\b", blob) and re.search(r"\b(acme|corp|inc|ltd|enterprises?)\b", blob):
        return True
    return False


def _scan_secrets(text: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for code, pat in _SECRET_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append((code, m.group(0)[:80]))
    return hits


def check_uac_guardrails(
    payload: dict[str, Any],
    enriched: JiraEnrichedDocument | Mapping[str, Any],
) -> dict[str, Any]:
    """
    Audit UAC payload + prose for enterprise guardrails.

    Returns:
        ``warnings``: non-blocking issues (confidence, scenario count, automation fit).
        ``blocked_claims``: strings that should be stripped or rejected (secrets, invented fields,
        unsupported customer/history claims, generic filler).
    """
    en: Mapping[str, Any] = (
        enriched.model_dump() if isinstance(enriched, JiraEnrichedDocument) else dict(enriched)
    )
    blob_lc = _enriched_blob(en)
    customer_ok = _has_customer_evidence(en, blob_lc)
    similar = payload.get("similar_jiras") if isinstance(payload.get("similar_jiras"), list) else []
    n_similar = len(similar)
    thin_similar = bool(payload.get("insufficient_similar_evidence")) or n_similar == 0

    warnings: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    def add_blocked(text: str, reason: str, source: str, index: int | None = None) -> None:
        t = (text or "").strip()
        if not t:
            return
        blocked.append({"text": t[:800], "reason": reason, "source": source, "index": index})

    def add_warning(code: str, message: str, detail: str | None = None) -> None:
        w: dict[str, Any] = {"code": code, "message": message}
        if detail:
            w["detail"] = detail
        warnings.append(w)

    texts: list[tuple[str, str, int | None]] = []

    ans = str(payload.get("uac_answer") or "")
    for i, line in enumerate(ans.splitlines()):
        s = line.strip()
        if s and not s.startswith("#"):
            texts.append((s, "uac_answer", i))

    risk = payload.get("risk_summary")
    if isinstance(risk, dict):
        for i, d in enumerate(risk.get("drivers") or []):
            if isinstance(d, str) and d.strip():
                texts.append((d.strip(), "risk_summary.drivers", i))

    scen = payload.get("must_test_scenarios") if isinstance(payload.get("must_test_scenarios"), list) else []
    for i, row in enumerate(scen):
        if not isinstance(row, dict):
            continue
        sc = str(row.get("scenario") or "").strip()
        why = str(row.get("why") or "").strip()
        if sc:
            texts.append((sc, "must_test_scenarios.scenario", i))
        if why:
            texts.append((why, "must_test_scenarios.why", i))

    clar = payload.get("missing_clarifications") if isinstance(payload.get("missing_clarifications"), list) else []
    for i, row in enumerate(clar):
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        w = str(row.get("why") or "").strip()
        if q:
            texts.append((q, "missing_clarifications.question", i))
        if w:
            texts.append((w, "missing_clarifications.why", i))

    seen_block_norm: set[str] = set()
    for text, source, idx in texts:
        low = text.lower()

        for code, snippet in _scan_secrets(text):
            key = f"secret|{code}|{hash(text) & 0xFFFF}"
            if key not in seen_block_norm:
                seen_block_norm.add(key)
                add_blocked(text, f"secret_or_credential_pattern:{code}", source, idx)

        for cf in _CUSTOMFIELD_RE.findall(text):
            if cf.lower() not in blob_lc:
                key = f"jira_field|{cf}"
                if key not in seen_block_norm:
                    seen_block_norm.add(key)
                    add_blocked(
                        text,
                        "invented_or_unreferenced_jira_customfield",
                        source,
                        idx,
                    )

        if _CUSTOMER_IMPACT_RE.search(text) and not customer_ok:
            key = f"customer_impact|{hash(text) & 0xFFFFF}"
            if key not in seen_block_norm:
                seen_block_norm.add(key)
                add_blocked(text, "customer_impact_without_customer_evidence", source, idx)

        if _HISTORICAL_REGRESSION_RE.search(text) and n_similar == 0:
            key = f"history|{hash(text) & 0xFFFFF}"
            if key not in seen_block_norm:
                seen_block_norm.add(key)
                add_blocked(text, "historical_regression_without_similar_jira_evidence", source, idx)

        if generic_phrase_patterns_in_text(text) or is_generic_statement(text):
            key = f"generic|{hash(text) & 0xFFFFF}"
            if key not in seen_block_norm:
                seen_block_norm.add(key)
                add_blocked(text, "generic_qa_filler", source, idx)

    if len(scen) > _MAX_SCENARIOS:
        add_warning(
            "too_many_scenarios",
            f"UAC lists {len(scen)} scenarios; cap is {_MAX_SCENARIOS}.",
            "Trim lowest-priority rows for enterprise policy.",
        )
        for j in range(_MAX_SCENARIOS, len(scen)):
            row = scen[j]
            if isinstance(row, dict):
                fragment = str(row.get("scenario") or row.get("why") or "")[:400]
                if fragment.strip():
                    add_blocked(
                        fragment,
                        "scenario_over_policy_limit",
                        "must_test_scenarios",
                        j,
                    )

    fit = payload.get("automation_fit") if isinstance(payload.get("automation_fit"), dict) else {}
    fit_label = str(fit.get("fit") or "").strip()
    if fit_label == "Yes":
        if any(isinstance(r, dict) and not _evidence_ok(r.get("evidence")) for r in scen):
            add_warning(
                "automation_not_fully_deterministic",
                "Automation fit is 'Yes' while one or more scenarios lack concrete evidence anchors.",
                "Downgrade automation to Partial or attach reproducible evidence for deterministic checks.",
            )

    conf = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    level = str(conf.get("level") or "").strip().lower()
    qs = payload.get("quality_score")
    if level in ("high",) and thin_similar:
        add_warning(
            "confidence_vs_evidence",
            "Confidence marked high while similar-ticket evidence is thin or flagged insufficient.",
            "Cap narrative confidence to medium until retrieval strengthens.",
        )
    if isinstance(qs, int) and qs < 55 and level in ("high",):
        add_warning(
            "confidence_vs_quality_score",
            f"Answer quality score ({qs}) is low for a high-confidence label.",
            "Align confidence.signals with answer_quality-derived score.",
        )

    return {"warnings": warnings, "blocked_claims": blocked}


__all__ = ["check_uac_guardrails"]
