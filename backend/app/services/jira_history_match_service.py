"""Deterministic same-mechanism qualification for historical Jira candidates."""

from __future__ import annotations

import re
from typing import Any

from app.services.evidence_graph_contract import (
    extract_api_routes,
    extract_config_keys,
    extract_error_signatures,
    normalize_text,
)


_TOKEN_RE = re.compile(r"[a-z][a-z0-9_.-]{2,}", re.I)
_DITA_RE = re.compile(r"(?:<\s*([a-z][\w.-]*)\b|@([a-z][\w.-]*))", re.I)
_GENERIC_TOKENS = frozenset(
    {
        "actual",
        "aem",
        "asset",
        "assets",
        "behavior",
        "behaviour",
        "bug",
        "component",
        "content",
        "customer",
        "dita",
        "expected",
        "fail",
        "failed",
        "failure",
        "feature",
        "file",
        "files",
        "fix",
        "fixed",
        "guides",
        "issue",
        "map",
        "maps",
        "output",
        "problem",
        "publish",
        "publishing",
        "result",
        "same",
        "test",
        "testing",
        "ticket",
        "topic",
        "topics",
        "user",
        "users",
        "verify",
        "when",
        "with",
    }
)
_OUTPUT_PATTERNS = {
    "native-pdf": re.compile(r"\bnative[-\s]?pdf\b", re.I),
    "pdf2": re.compile(r"\b(?:pdf2|dita[-\s]?ot\s+pdf)\b", re.I),
    "html5": re.compile(r"\bhtml5\b", re.I),
    "aem-sites": re.compile(r"\b(?:aem\s+sites|native[_\s-]?aemsite)\b", re.I),
}
_AUTHORING_VIEWPORT_RE = re.compile(
    r"\b(?:author(?:ing)?\s+(?:view|canvas)|editor\s+canvas|editing\s+location|active\s+element|caret)\b"
    r"[^.\n]{0,220}\b(?:scroll|viewport|jump|visible|cursor|selection|insertion\s+location)\b|"
    r"\b(?:scroll|viewport|jump)\b[^.\n]{0,160}\b(?:author(?:ing)?\s+(?:view|canvas)|editor\s+canvas)\b",
    re.I,
)
_MAP_PREVIEW_STATE_RE = re.compile(
    r"\bmap\s+preview\b[^.\n]{0,220}\b(?:scroll|refresh|selected\s+topic|condition|right\s+panel|return|edit)\b|"
    r"\bpreview\b[^.\n]{0,120}\bscroll\s+position\b",
    re.I,
)
_STATE_RESTORATION_RE = re.compile(
    r"\b(?:restore|restored|restoration|retain|retained|preserve|preserved|maintain|maintained)\b"
    r"[^.\n]{0,100}\b(?:state|position|location|selection|scroll|viewport)\b",
    re.I,
)
_EDITOR_SCROLL_RE = re.compile(
    r"\b(?:author(?:ing)?\s+(?:view|canvas)|editor\s+canvas|editing)\b"
    r"[^.\n]{0,160}\b(?:scroll|viewport|jump)\b",
    re.I,
)


def _specific_tokens(value: Any) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(normalize_text(value))
        if token.casefold() not in _GENERIC_TOKENS and not token.isdigit()
    }


def _dita_entities(value: Any) -> set[str]:
    result: set[str] = set()
    text = normalize_text(value)
    for match in _DITA_RE.finditer(text):
        if match.group(1):
            result.add(match.group(1).casefold())
        elif match.group(2):
            result.add("@" + match.group(2).casefold())
    for token in ("mathml", "ditaval", "xref", "keyref", "conref", "conkeyref", "topicref"):
        if re.search(rf"\b{re.escape(token)}\b", text, re.I):
            result.add(token)
    return result


def _outputs(value: Any) -> set[str]:
    text = normalize_text(value)
    return {name for name, pattern in _OUTPUT_PATTERNS.items() if pattern.search(text)}


def _contract_text(candidate: dict[str, Any]) -> str:
    learning = candidate.get("learning") if isinstance(candidate.get("learning"), dict) else {}
    contract = (
        candidate.get("historical_uac_contract")
        if isinstance(candidate.get("historical_uac_contract"), dict)
        else {}
    )
    clauses = "\n".join(
        str(clause.get("text") or "")
        for clause in contract.get("clauses") or []
        if isinstance(clause, dict)
    )
    return "\n".join(
        str(value or "")
        for value in (
            candidate.get("summary"),
            candidate.get("why_similar"),
            candidate.get("document"),
            candidate.get("root_cause"),
            candidate.get("qa_oracle"),
            candidate.get("observed_problem"),
            learning.get("behavior_contract"),
            learning.get("root_cause"),
            learning.get("qa_oracle"),
            (candidate.get("uac_evidence") or {}).get("source_text")
            if isinstance(candidate.get("uac_evidence"), dict)
            else "",
            clauses,
        )
        if str(value or "").strip()
    )


def _cross_viewport_mismatch(query_text: str, candidate_text: str) -> bool:
    query_authoring = bool(_AUTHORING_VIEWPORT_RE.search(query_text))
    candidate_authoring = bool(_AUTHORING_VIEWPORT_RE.search(candidate_text))
    query_preview = bool(_MAP_PREVIEW_STATE_RE.search(query_text))
    candidate_preview = bool(_MAP_PREVIEW_STATE_RE.search(candidate_text))
    cross_surface = (query_authoring and candidate_preview) or (query_preview and candidate_authoring)
    if not cross_surface:
        return False
    shared_restoration = bool(
        _STATE_RESTORATION_RE.search(query_text)
        and _STATE_RESTORATION_RE.search(candidate_text)
    )
    shared_editor_scroll = bool(
        _EDITOR_SCROLL_RE.search(query_text) and _EDITOR_SCROLL_RE.search(candidate_text)
    )
    return not (shared_restoration or shared_editor_scroll)


def _candidate_values(candidate: dict[str, Any], field: str) -> set[str]:
    raw = candidate.get(field) or []
    if isinstance(raw, str):
        raw = [raw]
    return {normalize_text(value).casefold() for value in raw if normalize_text(value)}


def build_historical_match_contract(
    query: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Qualify only exact or structural mechanisms; area overlap never suffices."""
    query_text = normalize_text(query)
    candidate_text = _contract_text(candidate)
    learning = candidate.get("learning") if isinstance(candidate.get("learning"), dict) else {}
    contract = (
        candidate.get("historical_uac_contract")
        if isinstance(candidate.get("historical_uac_contract"), dict)
        else {}
    )

    query_routes = set(extract_api_routes(query_text))
    candidate_routes = set(extract_api_routes(candidate_text))
    query_configs = set(extract_config_keys(query_text))
    candidate_configs = set(extract_config_keys(candidate_text))
    query_errors = set(extract_error_signatures(query_text))
    candidate_errors = set(extract_error_signatures(candidate_text))
    query_dita = _dita_entities(query_text)
    candidate_dita = _dita_entities(candidate_text) | _candidate_values(candidate, "matching_entities")
    query_outputs = _outputs(query_text)
    candidate_outputs = _outputs(candidate_text) | _candidate_values(candidate, "matching_outputs")
    shared_terms = sorted(_specific_tokens(query_text) & _specific_tokens(candidate_text))

    exact_signals: list[str] = []
    for label, values in (
        ("API route", query_routes & candidate_routes),
        ("configuration key", query_configs & candidate_configs),
        ("error signature", query_errors & candidate_errors),
    ):
        exact_signals.extend(f"{label}: {value}" for value in sorted(values))

    shared_dita = sorted(query_dita & candidate_dita)
    shared_outputs = sorted(query_outputs & candidate_outputs)
    verified_contract = bool(
        learning.get("is_verified_fix")
        or contract.get("reuse_mode") == "historical_verified_contract"
        or contract.get("trust_tier") == "historical_verified"
    )
    root_cause_present = bool(candidate.get("root_cause") or learning.get("root_cause"))
    contract_present = bool(contract.get("clauses") or learning.get("behavior_contract"))

    evidence_types: list[str] = []
    if _cross_viewport_mismatch(query_text, candidate_text):
        strength = "unproven"
        qualified = False
        evidence_types.append("cross_surface_scroll_overlap_only")
        reason = (
            "Map Preview state restoration and Author-canvas viewport stability are different "
            "mechanisms; no shared state-restoration or editor-scroll evidence was established."
        )
        mechanism_score = 0.2
    elif exact_signals:
        strength = "exact"
        qualified = True
        evidence_types.append("exact_technical_identifier")
        reason = "Shared exact technical identifier proves a common defect mechanism."
        mechanism_score = 1.0
    elif verified_contract and root_cause_present and len(shared_terms) >= 2:
        strength = "structural"
        qualified = True
        evidence_types.extend(["verified_root_cause", "specific_term_overlap"])
        reason = "Verified historical root cause overlaps the current failure with specific terms."
        mechanism_score = 0.9
    elif verified_contract and contract_present and shared_dita and shared_outputs and shared_terms:
        strength = "structural"
        qualified = True
        evidence_types.extend(["verified_behavior_contract", "dita_output_symptom_combination"])
        reason = "Verified behaviour shares a DITA entity, output, and specific failure signal."
        mechanism_score = 0.86
    elif shared_dita and shared_outputs and len(shared_terms) >= 2:
        strength = "structural"
        qualified = True
        evidence_types.append("dita_output_symptom_combination")
        reason = "Candidate shares the same DITA/output failure combination and specific symptoms."
        mechanism_score = 0.78
    else:
        strength = "unproven"
        qualified = False
        evidence_types.append("area_or_semantic_overlap_only")
        reason = (
            "No shared root cause, behaviour contract, error signature, API route, config key, "
            "or strong DITA/output/symptom combination was established."
        )
        mechanism_score = 0.35

    mechanisms = list(dict.fromkeys([*exact_signals, *shared_dita, *shared_outputs, *shared_terms[:8]]))
    return {
        "schema_version": "jira-history-match-v2",
        "qualified": qualified,
        "strength": strength,
        "mechanism_score": mechanism_score,
        "evidence_types": evidence_types,
        "shared_mechanisms": mechanisms,
        "shared_exact_signals": exact_signals,
        "shared_dita_entities": shared_dita,
        "shared_outputs": shared_outputs,
        "shared_specific_terms": shared_terms[:12],
        "verified_historical_contract": verified_contract,
        "area_only_rejected": not qualified,
        "domain_is_ranking_only": True,
        "customer_component_are_ranking_only": True,
        "reason": reason,
    }
