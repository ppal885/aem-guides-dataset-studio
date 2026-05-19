"""Build ``uac_ui`` structured payload from a finalized UAC analyze dict."""

from __future__ import annotations

from typing import Any


def _evidence_cell(ev: Any) -> str:
    if ev is None:
        return ""
    if isinstance(ev, str):
        return ev.strip()
    if isinstance(ev, list):
        return "; ".join(str(x).strip() for x in ev if x is not None and str(x).strip())
    return str(ev).strip()


def _risk_label(level: str) -> str:
    lv = (level or "").strip().lower()
    mapping = {
        "high": "High risk",
        "medium": "Medium risk",
        "low": "Low risk",
        "insufficient": "Insufficient evidence",
        "unspecified": "Unspecified",
    }
    if lv in mapping:
        return mapping[lv]
    return (level or "Unspecified").replace("_", " ").strip().title() or "Unspecified"


def _float_scores(scores: dict[str, Any]) -> dict[str, Any] | None:
    if not scores:
        return None
    out: dict[str, Any] = {}
    for k, v in scores.items():
        if isinstance(v, (int, float)):
            out[str(k)] = float(v)
        elif v is not None:
            out[str(k)] = v
    return out or None


def _qa_handoff_card(payload: dict[str, Any]) -> dict[str, Any]:
    empty_script = {"title": "", "preconditions": [], "steps": [], "expected_result": ""}
    qh = payload.get("qa_handoff")
    if not isinstance(qh, dict):
        return {
            "requested": False,
            "generated": False,
            "note": None,
            "regression_breadth": "",
            "smoke_checks": [],
            "deep_regression_focus": [],
            "blocking_for_signoff": [],
            "exit_criteria": [],
            "exploratory_angles": [],
            "jira_test_script": dict(empty_script),
            "qa_lead_note": "",
        }
    blocking: list[dict[str, str]] = []
    for row in qh.get("blocking_for_signoff") or []:
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        if not q:
            continue
        role = str(row.get("owner_role") or "other").strip() or "other"
        blocking.append({"question": q, "owner_role": role})
    script_raw = qh.get("jira_test_script") if isinstance(qh.get("jira_test_script"), dict) else {}
    script = {
        "title": str(script_raw.get("title") or "").strip(),
        "preconditions": [str(x).strip() for x in (script_raw.get("preconditions") or []) if str(x).strip()],
        "steps": [str(x).strip() for x in (script_raw.get("steps") or []) if str(x).strip()],
        "expected_result": str(script_raw.get("expected_result") or "").strip(),
    }
    raw_note = qh.get("note")
    if raw_note is None:
        note_out: str | None = None
    else:
        ns = str(raw_note).strip()
        note_out = ns if ns else None
    return {
        "requested": bool(qh.get("requested")),
        "generated": bool(qh.get("generated")),
        "note": note_out,
        "regression_breadth": str(qh.get("regression_breadth") or "").strip(),
        "smoke_checks": [str(x).strip() for x in (qh.get("smoke_checks") or []) if str(x).strip()],
        "deep_regression_focus": [str(x).strip() for x in (qh.get("deep_regression_focus") or []) if str(x).strip()],
        "blocking_for_signoff": blocking,
        "exit_criteria": [str(x).strip() for x in (qh.get("exit_criteria") or []) if str(x).strip()],
        "exploratory_angles": [str(x).strip() for x in (qh.get("exploratory_angles") or []) if str(x).strip()],
        "jira_test_script": script,
        "qa_lead_note": str(qh.get("qa_lead_note") or "").strip(),
    }


def build_uac_ui_contract(payload: dict[str, Any], *, debug: bool) -> dict[str, Any]:
    """
    Map finalized ``run_uac_analyze`` output into the `UacUiContract` shape (plain dict for JSON).

    No Markdown is produced here; ``uac_answer`` at top level remains the legacy brief.
    """
    risk = payload.get("risk_summary") if isinstance(payload.get("risk_summary"), dict) else {}
    level_raw = str(risk.get("level") or "").strip().lower()
    if not level_raw:
        level_raw = "unspecified"
    rs = risk.get("risk_score")
    rs_f: float | None = float(rs) if isinstance(rs, (int, float)) else None
    msg = str(risk.get("message") or "").strip() or None
    risk_badge = {
        "level": level_raw,
        "label": _risk_label(level_raw),
        "risk_score": rs_f,
        "message": msg,
    }

    cls = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    jk = str(payload.get("jira_key") or cls.get("jira_key") or "").strip()
    classification_card = {"jira_key": jk, "classification": dict(cls)}

    dr = payload.get("uac_decision_record") if isinstance(payload.get("uac_decision_record"), dict) else {}
    executive_summary_card = {
        "summary": str(dr.get("summary") or ""),
        "release_risk": str(dr.get("release_risk") or ""),
        "decisions_needed_preview": [str(x) for x in (dr.get("decisions_needed") or []) if str(x).strip()][:6],
        "qa_commitments_preview": [str(x) for x in (dr.get("qa_commitments") or []) if str(x).strip()][:6],
    }

    sims = payload.get("similar_jiras") if isinstance(payload.get("similar_jiras"), list) else []
    similar_cards: list[dict[str, Any]] = []
    for row in sims:
        if not isinstance(row, dict):
            continue
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        conf = row.get("confidence_score")
        if not isinstance(conf, (int, float)) and isinstance(scores.get("confidence"), (int, float)):
            conf = scores["confidence"]
        similar_cards.append(
            {
                "jira_key": str(row.get("jira_key") or ""),
                "title": str(row.get("title") or row.get("summary") or ""),
                "why_relevant": str(row.get("why_similar") or row.get("why_relevant") or ""),
                "what_we_learned": str(row.get("what_we_learned") or ""),
                "confidence_score": float(conf) if isinstance(conf, (int, float)) else None,
                "scores": _float_scores(scores),
                "chunk_type": row.get("chunk_type") if row.get("chunk_type") is not None else None,
            }
        )

    scenarios = payload.get("must_test_scenarios") if isinstance(payload.get("must_test_scenarios"), list) else []
    must_test_rows: list[dict[str, Any]] = []
    for i, row in enumerate(scenarios):
        if not isinstance(row, dict):
            continue
        rid = f"mt-{i}"
        base = {
            "id": rid,
            "scenario": str(row.get("scenario") or ""),
            "why": str(row.get("why") or ""),
            "evidence": _evidence_cell(row.get("evidence")),
            "test_layer": str(row.get("test_layer") or ""),
            "priority": str(row.get("priority") or ""),
        }
        for k in ("automation_fit", "impacted_output", "related_entity"):
            if row.get(k) is not None:
                base[k] = row[k]
        must_test_rows.append(base)

    clar = payload.get("missing_clarifications") if isinstance(payload.get("missing_clarifications"), list) else []
    clar_rows: list[dict[str, Any]] = []
    for i, row in enumerate(clar):
        if not isinstance(row, dict):
            continue
        r: dict[str, Any] = {
            "id": f"mc-{i}",
            "question": str(row.get("question") or ""),
            "why": str(row.get("why") or ""),
            "evidence": _evidence_cell(row.get("evidence")),
        }
        re = row.get("related_entity")
        if re is not None:
            r["related_entity"] = str(re) if not isinstance(re, list) else ", ".join(str(x) for x in re)
        clar_rows.append(r)

    fit = payload.get("automation_fit") if isinstance(payload.get("automation_fit"), dict) else {}
    jk_slug = str(cls.get("jira_key") or jk or "jira").lower().replace("-", "_")
    automation_strategy_card = {
        "fit": str(fit.get("fit") or "Partial"),
        "primary_test_layer": str(fit.get("primary_test_layer") or ""),
        "framework": str(fit.get("framework") or ""),
        "suggested_test_name": f"{jk_slug}_uac",
    }

    dataset_needed = [str(x) for x in (dr.get("dataset_needed") or []) if str(x).strip()]
    guard = payload.get("uac_guardrails") if isinstance(payload.get("uac_guardrails"), dict) else {}
    gwarn = guard.get("warnings") if isinstance(guard.get("warnings"), list) else []
    dataset_extra: list[str] = []
    for w in gwarn[:5]:
        if isinstance(w, dict):
            m = w.get("message")
            if m:
                dataset_extra.append(str(m))
    dataset_recommendation_card = {
        "items": dataset_needed,
        "hints_from_guardrails": dataset_extra,
        "insufficient_similar_pool": bool(payload.get("insufficient_similar_evidence")),
    }

    conf = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    cv = payload.get("claim_verification") if isinstance(payload.get("claim_verification"), dict) else {}
    dropped = cv.get("dropped_claims") if isinstance(cv.get("dropped_claims"), list) else []
    down = cv.get("downgraded_claims") if isinstance(cv.get("downgraded_claims"), list) else []
    unsup = cv.get("unsupported_claims") if isinstance(cv.get("unsupported_claims"), list) else []

    val_ok = bool(payload.get("uac_validation_ok", True))
    val_errs = payload.get("uac_validation_errors")
    if not isinstance(val_errs, list):
        val_errs = []

    aq = payload.get("answer_quality") if isinstance(payload.get("answer_quality"), dict) else None

    warnings_out: list[dict[str, Any]] = []
    for w in gwarn:
        if isinstance(w, dict):
            warnings_out.append(
                {
                    "code": w.get("code"),
                    "message": w.get("message"),
                    "detail": w.get("detail"),
                }
            )
    blocked = guard.get("blocked_claims") if isinstance(guard.get("blocked_claims"), list) else []

    confidence_warnings_card = {
        "confidence": dict(conf),
        "quality_score": payload.get("quality_score") if payload.get("quality_score") is not None else None,
        "answer_quality": dict(aq) if aq else None,
        "uac_validation_ok": val_ok,
        "uac_validation_errors": [str(e) for e in val_errs],
        "insufficient_similar_evidence": bool(payload.get("insufficient_similar_evidence")),
        "claim_verification": {
            "dropped_count": len(dropped),
            "downgraded_count": len(down),
            "unsupported_count": len(unsup),
        },
        "guardrails_warnings": warnings_out,
        "blocked_claims_count": len(blocked),
    }

    rd = payload.get("retrieval_debug") if isinstance(payload.get("retrieval_debug"), dict) else {}
    anti = payload.get("anti_repetition") if isinstance(payload.get("anti_repetition"), dict) else None

    if debug:
        debug_accordion: dict[str, Any] = {
            "debug_mode": True,
            "retrieval_debug": dict(rd),
            "anti_repetition": anti,
            "claim_verification_detail": dict(cv) if cv else None,
            "uac_guardrails_detail": dict(guard) if guard else None,
            "dropped_generic_points": list(payload.get("dropped_generic_points") or [])
            if payload.get("dropped_generic_points")
            else None,
            "generic_phrases_removed": list(payload.get("generic_phrases_removed") or [])
            if payload.get("generic_phrases_removed")
            else None,
            "regeneration_used": payload.get("regeneration_used"),
            "structured_uac_available": isinstance(payload.get("structured_uac"), dict),
        }
    else:
        scores = rd.get("scores") if isinstance(rd.get("scores"), list) else []
        debug_accordion = {
            "debug_mode": False,
            "retrieval_debug": {
                "note": "Set debug=true on the request for the full retrieval sink, candidate lists, and expanded dumps.",
                "extracted": rd.get("extracted") if isinstance(rd.get("extracted"), dict) else None,
                "scores_count": len(scores),
                "domain": rd.get("domain"),
            },
            "anti_repetition": anti,
            "claim_verification_detail": None,
            "uac_guardrails_detail": {
                "warnings_count": len(warnings_out),
                "blocked_claims_count": len(blocked),
            },
            "dropped_generic_points": None,
            "generic_phrases_removed": None,
            "regeneration_used": payload.get("regeneration_used"),
            "structured_uac_available": isinstance(payload.get("structured_uac"), dict),
        }

    return {
        "version": 1,
        "risk_badge": risk_badge,
        "classification_card": classification_card,
        "executive_summary_card": executive_summary_card,
        "similar_jira_learning_cards": similar_cards,
        "must_test_scenario_table": {"rows": must_test_rows},
        "missing_clarification_table": {"rows": clar_rows},
        "automation_strategy_card": automation_strategy_card,
        "dataset_recommendation_card": dataset_recommendation_card,
        "confidence_warnings_card": confidence_warnings_card,
        "debug_accordion": debug_accordion,
        "qa_handoff_card": _qa_handoff_card(payload),
    }


__all__ = ["build_uac_ui_contract"]
