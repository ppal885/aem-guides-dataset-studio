"""Strict validation and optional LLM repair for UAC Copilot API payloads."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, TYPE_CHECKING, Callable

from services.answer_quality_service import generic_phrase_patterns_in_text

if TYPE_CHECKING:
    from app.core.schemas_jira_enrichment import JiraEnrichedDocument

_MAX_SCENARIOS = 7
_MAX_CLARIFICATIONS = 5

_LEVEL_SCORE = {"high": 3, "medium": 2, "low": 1, "insufficient": 0}


def _forbidden_generic_hits(text: str) -> list[str]:
    return generic_phrase_patterns_in_text(text or "")


def _evidence_ok(ev: Any) -> bool:
    if ev is None:
        return False
    if isinstance(ev, str):
        return bool(ev.strip())
    if isinstance(ev, list):
        return len(ev) > 0
    return True


def _scenario_valid(row: Any, idx: int) -> list[str]:
    errs: list[str] = []
    if not isinstance(row, dict):
        return [f"scenario_{idx}_not_object"]
    sc = str(row.get("scenario") or "").strip()
    why = str(row.get("why") or "").strip()
    layer = str(row.get("test_layer") or "").strip()
    pri = str(row.get("priority") or "").strip()
    if not sc:
        errs.append(f"scenario_{idx}_empty_title")
    if not why:
        errs.append(f"scenario_{idx}_empty_why")
    if not _evidence_ok(row.get("evidence")):
        errs.append(f"scenario_{idx}_missing_evidence")
    if not layer:
        errs.append(f"scenario_{idx}_missing_test_layer")
    if not pri:
        errs.append(f"scenario_{idx}_missing_priority")
    blob = f"{sc}\n{why}"
    bad = _forbidden_generic_hits(blob)
    if bad:
        errs.append(f"scenario_{idx}_generic_phrase:{','.join(bad[:3])}")
    return errs


def ensure_risk_score(risk: dict[str, Any]) -> None:
    """Mutate ``risk_summary`` to include numeric ``risk_score`` when only ``level`` is set."""
    if not isinstance(risk, dict):
        return
    if isinstance(risk.get("risk_score"), (int, float)):
        return
    level = str(risk.get("level") or "").strip().lower()
    if level in _LEVEL_SCORE:
        risk["risk_score"] = _LEVEL_SCORE[level]


def validate_uac_payload(payload: dict[str, Any], *, lenient: bool = False) -> tuple[bool, list[str]]:
    """
    Validate final UAC API payload shape.

    When ``lenient`` is True (insufficient-evidence short paths): allow empty scenarios and
    minimal confidence; still require ``similar_jiras`` list and classification dict.
    """
    errs: list[str] = []

    cls = payload.get("classification")
    if not isinstance(cls, dict) or not cls:
        errs.append("missing_classification")

    risk = payload.get("risk_summary")
    if not isinstance(risk, dict):
        errs.append("risk_summary_not_object")
    else:
        has_score = isinstance(risk.get("risk_score"), (int, float))
        has_level = bool(str(risk.get("level") or "").strip())
        if not has_score and not has_level:
            errs.append("missing_risk_score_and_level")
        if not lenient:
            for i, d in enumerate(risk.get("drivers") or []):
                if not isinstance(d, str) or not d.strip():
                    errs.append(f"risk_driver_empty_{i}")
                    continue
                bad = _forbidden_generic_hits(d)
                if bad:
                    errs.append(f"risk_driver_{i}_generic:{','.join(bad[:2])}")

    sim = payload.get("similar_jiras")
    if not isinstance(sim, list):
        errs.append("similar_jiras_not_list")

    scenarios = payload.get("must_test_scenarios") or []
    if not isinstance(scenarios, list):
        errs.append("must_test_scenarios_not_list")
    elif not lenient:
        if len(scenarios) > _MAX_SCENARIOS:
            errs.append(f"too_many_scenarios:{len(scenarios)}")
        for i, row in enumerate(scenarios):
            errs.extend(_scenario_valid(row, i))
    else:
        if len(scenarios) > _MAX_SCENARIOS:
            errs.append(f"too_many_scenarios:{len(scenarios)}")
        if scenarios:
            for i, row in enumerate(scenarios):
                errs.extend(_scenario_valid(row, i))

    clar = payload.get("missing_clarifications") or []
    if not isinstance(clar, list):
        errs.append("missing_clarifications_not_list")
    elif len(clar) > _MAX_CLARIFICATIONS:
        errs.append(f"too_many_clarifications:{len(clar)}")
    else:
        for i, row in enumerate(clar):
            if not isinstance(row, dict):
                errs.append(f"clarification_{i}_not_object")
                continue
            q = str(row.get("question") or "").strip()
            if not q:
                if not lenient:
                    errs.append(f"clarification_{i}_empty_question")
            else:
                if not lenient:
                    bad = _forbidden_generic_hits(q)
                    if bad:
                        errs.append(f"clarification_{i}_generic:{','.join(bad[:2])}")

    conf = payload.get("confidence")
    if not isinstance(conf, dict):
        errs.append("confidence_not_object")
    elif not lenient and len(conf) == 0:
        errs.append("confidence_empty")

    return len(errs) == 0, errs


def _priority_default_from_layer(test_layer: str) -> str:
    tl = (test_layer or "").lower()
    if "publish" in tl:
        return "P1"
    if "ui" in tl or "manual" in tl:
        return "P3"
    return "P2"


def normalize_uac_payload_partial(payload: dict[str, Any], *, jira_key: str) -> dict[str, Any]:
    """
    Best-effort prune: cap lists, drop invalid scenarios, fill defaults.
    Mutates a deep copy and returns it.
    """
    out = copy.deepcopy(payload)
    scenarios = [s for s in (out.get("must_test_scenarios") or []) if isinstance(s, dict)]
    kept: list[dict[str, Any]] = []
    for row in scenarios:
        if len(kept) >= _MAX_SCENARIOS:
            break
        r = dict(row)
        if not str(r.get("priority") or "").strip():
            r["priority"] = _priority_default_from_layer(str(r.get("test_layer") or ""))
        errs = _scenario_valid(r, len(kept))
        if errs:
            continue
        kept.append(r)
    out["must_test_scenarios"] = kept

    clar = [c for c in (out.get("missing_clarifications") or []) if isinstance(c, dict)]
    out["missing_clarifications"] = clar[:_MAX_CLARIFICATIONS]

    risk = out.get("risk_summary") if isinstance(out.get("risk_summary"), dict) else {}
    risk = dict(risk)
    drivers = [d for d in (risk.get("drivers") or []) if isinstance(d, str) and d.strip()]
    risk["drivers"] = _dedupe_generic_drivers(drivers)
    ensure_risk_score(risk)
    out["risk_summary"] = risk

    conf = out.get("confidence") if isinstance(out.get("confidence"), dict) else {}
    if not conf:
        out["confidence"] = {"score": 0.0, "level": "low", "signals": ["partial_response"]}
    ensure_risk_score(out["risk_summary"])

    su = out.get("structured_uac") if isinstance(out.get("structured_uac"), dict) else {}
    su = copy.deepcopy(su)
    su["must_test_scenarios"] = out["must_test_scenarios"]
    su["missing_clarifications"] = out["missing_clarifications"]
    su["risk_summary"] = out["risk_summary"]
    su["confidence"] = out["confidence"]
    out["structured_uac"] = su
    out.setdefault("jira_key", jira_key)
    return out


def _dedupe_generic_drivers(drivers: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in drivers:
        t = re.sub(r"\s+", " ", (d or "").strip().lower())
        if not t or _forbidden_generic_hits(d):
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(d.strip())
    return out[:5]


def _sync_structured_from_top_level(payload: dict[str, Any]) -> None:
    """Keep ``structured_uac`` in sync with top-level UAC fields."""
    su = payload.get("structured_uac")
    if not isinstance(su, dict):
        su = {}
    for key in (
        "classification",
        "risk_summary",
        "similar_jiras",
        "must_test_scenarios",
        "missing_clarifications",
        "automation_fit",
        "evidence_summary",
        "confidence",
        "output_parity",
    ):
        if key in payload:
            su[key] = copy.deepcopy(payload[key])
    payload["structured_uac"] = su


async def repair_uac_payload_via_llm(
    payload: dict[str, Any],
    enriched: JiraEnrichedDocument,
    validation_errors: list[str],
) -> dict[str, Any] | None:
    """One LLM JSON pass to fix structured fields. Returns merged fragment or None."""
    from app.services.llm_service import generate_json

    blob = {
        "risk_summary": payload.get("risk_summary"),
        "must_test_scenarios": payload.get("must_test_scenarios"),
        "missing_clarifications": payload.get("missing_clarifications"),
        "confidence": payload.get("confidence"),
    }
    summary_ctx = {
        "jira_key": enriched.jira_key,
        "summary": (enriched.summary or "")[:500],
        "domain": enriched.domain,
        "dita_entities": list(enriched.dita_entities or [])[:12],
        "affected_outputs": list(enriched.affected_outputs or [])[:12],
    }
    system = (
        "You fix UAC JSON only. Output a single JSON object with keys: "
        "risk_summary, must_test_scenarios, missing_clarifications, confidence. "
        "Rules: risk_summary has level (high|medium|low|insufficient) and risk_score (0-3 integer), "
        "and drivers (array of strings, max 5, no generic phrases like 'verify UI' or 'test regression'). "
        "must_test_scenarios: array of objects with scenario, why, evidence (string OR non-empty array), "
        "test_layer, automation_fit, impacted_output, related_entity, priority (P0-P3). "
        "Max 7 scenarios. missing_clarifications: array of objects with question, why, evidence, related_entity; "
        "max 5. confidence: object with score (0-1 number), level (high|medium|low), signals (string array). "
        "Ground every item in the supplied Jira context; include jira_key in scenario titles where natural."
    )
    user = (
        f"Validation errors to fix: {validation_errors[:25]}\n"
        f"Jira context: {json.dumps(summary_ctx, ensure_ascii=False)}\n"
        f"Current JSON (fix in place, preserve good parts): {json.dumps(blob, ensure_ascii=False)[:28000]}"
    )
    try:
        fixed = await generate_json(
            system,
            user,
            max_tokens=6000,
            step_name="uac_output_repair",
            jira_id=enriched.jira_key,
        )
    except Exception:
        return None
    if not isinstance(fixed, dict):
        return None
    return fixed


def apply_sync_validation_only(
    payload: dict[str, Any],
    *,
    lenient: bool = False,
) -> dict[str, Any]:
    """Ensure risk_score and structured mirror; validate; set flags (sync)."""
    pl = copy.deepcopy(payload)
    risk = pl.get("risk_summary")
    if isinstance(risk, dict):
        ensure_risk_score(risk)
    ok, errs = validate_uac_payload(pl, lenient=lenient)
    pl["uac_validation_ok"] = ok
    pl["uac_validation_errors"] = errs
    if ok:
        pl.pop("uac_validation_warnings", None)
    _sync_structured_from_top_level(pl)
    return pl


async def apply_strict_uac_validation(
    payload: dict[str, Any],
    *,
    enriched: JiraEnrichedDocument,
    lenient: bool = False,
    format_markdown_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """
    Validate; optionally one LLM repair; then partial normalize + warnings if still invalid.
    """
    from app.services.llm_service import is_llm_available

    pl = copy.deepcopy(payload)
    risk = pl.get("risk_summary")
    if isinstance(risk, dict):
        ensure_risk_score(risk)

    ok, errs = validate_uac_payload(pl, lenient=lenient)
    repair_attempted = False

    if not ok and is_llm_available() and not lenient:
        repair_attempted = True
        fragment = await repair_uac_payload_via_llm(pl, enriched, errs)
        if isinstance(fragment, dict):
            for key in ("risk_summary", "must_test_scenarios", "missing_clarifications", "confidence"):
                if key in fragment and fragment[key] is not None:
                    pl[key] = fragment[key]
            if isinstance(pl.get("risk_summary"), dict):
                ensure_risk_score(pl["risk_summary"])
            _sync_structured_from_top_level(pl)
            ok, errs = validate_uac_payload(pl, lenient=lenient)

    if ok:
        pl["uac_validation_ok"] = True
        pl["uac_validation_errors"] = []
        pl["uac_repair_attempted"] = repair_attempted
        pl.pop("uac_validation_warnings", None)
        if repair_attempted:
            pl["uac_answer"] = format_markdown_fn(pl)
        _sync_structured_from_top_level(pl)
        return pl

    warnings = list(errs)
    if repair_attempted:
        warnings.insert(0, "uac_repair_pass_failed")
    pl_partial = normalize_uac_payload_partial(pl, jira_key=enriched.jira_key)
    ok2, errs2 = validate_uac_payload(pl_partial, lenient=lenient)

    pl_partial["uac_validation_ok"] = ok2
    pl_partial["uac_validation_errors"] = errs2
    pl_partial["uac_validation_warnings"] = warnings + (["partial_normalized"] if not ok2 else [])
    pl_partial["uac_repair_attempted"] = repair_attempted
    pl_partial["uac_answer"] = format_markdown_fn(pl_partial)
    _sync_structured_from_top_level(pl_partial)
    return pl_partial
