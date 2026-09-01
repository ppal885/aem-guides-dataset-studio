"""CapabilityEligibilityExplorer - stop the reasoner assuming that several actions on
the same UI surface (toolbar / menu / entity) share one eligibility rule.

WHY THIS EXISTS
---------------
A whole class of wrong ACs comes from inferring eligibility from UI proximity: buttons
A, B, C sit in the same toolbar, so the reasoner assumes they apply to the same entity
types / states / surfaces and writes one predicate for all of them. In reality each
capability can depend on a DIFFERENT dimension (one on content type, one on content type
+ an identifier, one on permission, one on the current surface). This module makes the
reasoner decompose each capability and give it its own evidence-backed predicate, and it
refuses to let "same surface" stand in for "same predicate."

It is generic - it hardcodes no specific action, entity, or mapping. Stdlib only.
"""

import re

PREDICATE_DIMENSIONS = ("ENTITY_TYPE", "METADATA", "STATE", "SURFACE", "PERMISSION", "SELECTION", "CONFIG", "ENTRY_POINT")

# Provenance of a CONFIG term's config key: verified against product code/docs vs
# copied unverified from the reporter/ticket (often a typo/transposition). A CONFIG
# predicate that grounds an AC must be verified or carried as an Open Question.
VERIFIED_KEY_PROVENANCE = ("CODE", "PRODUCT_DOC", "OSGI_CONFIG", "DTD", "SPEC")
UNVERIFIED_KEY_PROVENANCE = ("REPORTER", "TICKET", "PARAPHRASE", "UNKNOWN")

# One capability can be exposed through several render forms / entry points on the SAME
# surface (a direct toolbar button, an overflow "more" menu, a context menu, a shortcut).
# A responsive condition - viewport width, browser zoom, density - selects which form
# renders, and each form may dispatch through a DIFFERENT code path. Divergence between
# render forms is a real defect class, so they must be enumerated and their behavioural
# consistency resolved, never assumed.
ENTRY_POINT_FORMS = ("DIRECT_BUTTON", "OVERFLOW_MENU", "CONTEXT_MENU", "KEYBOARD_SHORTCUT", "INLINE", "OTHER")
ENTRY_POINT_CONSISTENCY = ("VERIFIED_SAME", "OPEN_QUESTION")
# Signals that a capability has multiple render forms selected by a responsive condition.
RESPONSIVE_ENTRYPOINT_SIGNALS = (
    "overflow menu", "more menu", "kebab", "toolbar button", "direct button", "zoom",
    "responsive", "viewport", "collapse", "density", "hidden under more", "moves to more",
    "promoted to a", "shown as a button", "in the more", "overflow",
)
SELECTION_POLICIES = (
    "ALL_SELECTED_ITEMS_MUST_SUPPORT", "ANY_SELECTED_ITEM_SUPPORTS", "PRIMARY_ITEM_CONTROLS",
    "ACTION_DISABLED_FOR_MULTISELECT", "NOT_APPLICABLE", "UNKNOWN",
)
CAPABILITY_MATCH = ("SAME_CAPABILITY", "RELATED_CAPABILITY", "SEMANTIC_COLLISION", "UNRELATED")

# Signals that several actions share one surface (so per-capability decomposition applies).
MULTI_ACTION_SURFACE_SIGNALS = (
    "toolbar", "menu", "action bar", "quick actions", "buttons", "actions on the",
    "same surface", "same panel", "rail", "context menu", "options menu", "these actions",
    "each button", "the buttons", "action set",
)
# Signals that selection multiplicity is in play.
MULTISELECT_SIGNALS = (
    "multi-select", "multiselect", "multiple selection", "select multiple", "mixed selection",
    "more than one asset", "several items selected", "bulk selection",
)


def _text(manifest, plan_text=""):
    parts = [plan_text or ""]
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if isinstance(issue, dict):
        parts += [str(issue.get(k, "")) for k in ("summary", "description", "title")]
    elif issue:
        parts.append(str(issue))
    bm = manifest.get("behavior_model") if isinstance(manifest, dict) else None
    if isinstance(bm, dict):
        for f in ("trigger", "operations", "consumers", "outputs"):
            parts += [str(x) for x in (bm.get(f) or [])]
    return " ".join(parts).lower()


def detect_signals(manifest, plan_text=""):
    t = _text(manifest, plan_text)
    hits = [s for s in MULTI_ACTION_SURFACE_SIGNALS if s in t]
    return sorted(set(hits))


def is_active(manifest, plan_text=""):
    """Capability decomposition is expected when the evidence describes several actions
    sharing one surface. A single-action ticket does not activate it."""
    return bool(detect_signals(manifest, plan_text))


def multiselect_in_scope(manifest, plan_text=""):
    return any(s in _text(manifest, plan_text) for s in MULTISELECT_SIGNALS)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("capability_eligibility"), dict)


def _validate_capability(cap, i):
    problems = []
    tag = f"capability_eligibility.capabilities[{i}]"
    if not isinstance(cap, dict):
        return [f"{tag} must be an object"]
    name = str(cap.get("capability", "")).strip()
    if not name:
        problems.append(f"{tag} is missing 'capability' (the action/capability name)")
    terms = cap.get("predicate_terms", []) or []
    unknowns = cap.get("unknowns", []) or []
    evidence = cap.get("eligibility_evidence", []) or []
    if not isinstance(terms, list):
        problems.append(f"{tag}.predicate_terms must be a list")
        terms = []
    # A capability must carry at least one evidence-backed predicate term OR explicitly
    # record what is unknown - it may never be left as an empty implied rule.
    if not terms and not unknowns:
        problems.append(f"{tag} ('{name or '?'}') has no predicate_terms and no unknowns - "
                        "decompose its eligibility or record what is unresolved; do not leave it implied")
    for j, term in enumerate(terms):
        ttag = f"{tag}.predicate_terms[{j}]"
        if not isinstance(term, dict):
            problems.append(f"{ttag} must be an object")
            continue
        dim = str(term.get("dimension", "")).strip()
        if dim not in PREDICATE_DIMENSIONS:
            problems.append(f"{ttag}.dimension must be one of {', '.join(PREDICATE_DIMENSIONS)}")
        if term.get("material", True) and not (term.get("evidence_ids") or []):
            problems.append(f"{ttag} is a material eligibility term but cites no evidence_ids - "
                            "eligibility must be evidence-backed, never inferred from UI proximity")
    # selection policy
    policy = cap.get("selection_policy")
    if policy is not None and str(policy) not in SELECTION_POLICIES:
        problems.append(f"{tag}.selection_policy must be one of {', '.join(SELECTION_POLICIES)}")
    # semantic collision: evidence flagged as a collision cannot support a predicate
    for k, ev in enumerate(evidence):
        if isinstance(ev, dict):
            m = str(ev.get("capability_match", "")).strip()
            if m and m not in CAPABILITY_MATCH:
                problems.append(f"{tag}.eligibility_evidence[{k}].capability_match must be one of {', '.join(CAPABILITY_MATCH)}")
            if m == "SEMANTIC_COLLISION" and ev.get("supports_predicate"):
                problems.append(f"{tag}.eligibility_evidence[{k}] is a SEMANTIC_COLLISION and must not support the "
                                "capability predicate - it describes a different capability that merely shares a term")

    # entry-point / render-form consistency: a capability exposed through several forms
    # (direct button vs overflow menu vs context menu, selected by a responsive condition)
    # must have each form's dispatch evidenced and their behavioural consistency resolved.
    eps = cap.get("entry_points")
    if eps is not None:
        if not isinstance(eps, list):
            problems.append(f"{tag}.entry_points must be a list")
        else:
            for e, ep in enumerate(eps):
                etag = f"{tag}.entry_points[{e}]"
                if not isinstance(ep, dict):
                    problems.append(f"{etag} must be an object")
                    continue
                if str(ep.get("form", "")).strip() not in ENTRY_POINT_FORMS:
                    problems.append(f"{etag}.form must be one of {', '.join(ENTRY_POINT_FORMS)}")
                if ep.get("material", True) and not (ep.get("evidence_ids") or []):
                    problems.append(f"{etag} is a material render form but cites no evidence_ids - each form's "
                                    "dispatch/behaviour must be evidence-backed, not assumed from the other form")
            real = [x for x in eps if isinstance(x, dict)]
            if len(real) >= 2:
                consistency = str(cap.get("entry_point_consistency", "")).strip()
                if consistency not in ENTRY_POINT_CONSISTENCY:
                    problems.append(f"{tag} exposes multiple entry points (render forms) but entry_point_consistency is "
                                    f"unresolved - set VERIFIED_SAME (with evidence) or OPEN_QUESTION; do not assume the "
                                    "forms behave the same")
                elif consistency == "VERIFIED_SAME" and not (cap.get("entry_point_consistency_evidence") or []):
                    problems.append(f"{tag} entry_point_consistency VERIFIED_SAME needs evidence that every render form "
                                    "dispatches the same behaviour")
                elif consistency == "OPEN_QUESTION" and not str(cap.get("entry_point_open_question_ref", "") or "").strip():
                    problems.append(f"{tag} entry_point_consistency OPEN_QUESTION needs an entry_point_open_question_ref")
    return problems


# A configuration-driven predicate must cite the real config KEY (an OSGi property like
# `xmleditor.autocheckout` or a PID/customfield), not a paraphrased mode name. This regex
# recognises a dotted config key, an OSGi PID, a customfield id, or an explicit "config key".
CONFIG_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*(?:\.[a-z0-9]+){1,}\b|customfield_\d+|\bOSGi\b|config key", re.IGNORECASE)


def config_terms_missing_key(block):
    """CONFIG predicate terms that name a mode/behaviour but cite no actual config key
    (e.g. `xmleditor.autocheckout`). Surfaced by the gate as NEEDS_REVIEW so config-driven
    ACs get grounded in the real key instead of a paraphrase."""
    out = []
    if not isinstance(block, dict):
        return out
    for cap in (block.get("capabilities") or []):
        if not isinstance(cap, dict):
            continue
        for term in (cap.get("predicate_terms") or []):
            if not isinstance(term, dict) or term.get("dimension") != "CONFIG":
                continue
            haystack = " ".join([str(term.get("config_key", "")), str(term.get("expected_value", ""))]
                                + [str(e) for e in (term.get("evidence_ids") or [])])
            if not CONFIG_KEY_RE.search(haystack):
                out.append(str(cap.get("capability", "?")))
                break
    return out


def config_terms_missing_provenance(block):
    """CONFIG predicate terms that name a key but declare no key_provenance. The
    gate surfaces these as NEEDS_REVIEW so each config key is explicitly marked
    verified (code/doc) vs unverified (reporter/ticket) before it grounds an AC."""
    out = []
    if not isinstance(block, dict):
        return out
    for cap in (block.get("capabilities") or []):
        if not isinstance(cap, dict):
            continue
        for term in (cap.get("predicate_terms") or []):
            if not isinstance(term, dict) or term.get("dimension") != "CONFIG":
                continue
            has_key = bool(str(term.get("config_key", "") or "").strip())
            if has_key and not str(term.get("key_provenance", "") or "").strip():
                out.append(str(cap.get("capability", "?")))
                break
    return out


def detect_responsive_signals(manifest, plan_text=""):
    """Signals that a capability renders through multiple forms selected by a responsive
    condition (viewport/zoom/density) - the direct-button vs overflow-menu situation."""
    t = _text(manifest, plan_text)
    return sorted(set(s for s in RESPONSIVE_ENTRYPOINT_SIGNALS if s in t))


def entrypoint_underexplored(block, manifest, plan_text=""):
    """Capabilities that show responsive/multi-form signals but enumerate fewer than two
    entry points - the reasoner may be testing only one render form and missing a divergent
    one (the direct-button-vs-overflow defect class). Surfaced by the gate as NEEDS_REVIEW."""
    if not isinstance(block, dict) or not detect_responsive_signals(manifest, plan_text):
        return []
    out = []
    for cap in (block.get("capabilities") or []):
        if isinstance(cap, dict) and len(cap.get("entry_points") or []) < 2:
            out.append(str(cap.get("capability", "?")))
    return out


def validate_capability_eligibility(block, *, open_question_ids=None, multiselect=False):
    if not isinstance(block, dict):
        return ["capability_eligibility must be a JSON object"]
    if not isinstance(block.get("active", True), bool):
        return ["capability_eligibility.active must be a boolean"]
    if not block.get("active", True):
        return []
    problems = []
    caps = block.get("capabilities")
    if not isinstance(caps, list) or not caps:
        return ["capability_eligibility.capabilities must be a non-empty list (decompose each action on the surface)"]
    names = set()
    open_ids = None if open_question_ids is None else set(open_question_ids)
    for i, cap in enumerate(caps):
        problems += _validate_capability(cap, i)
        if isinstance(cap, dict) and cap.get("capability"):
            names.add(str(cap["capability"]).strip())
        if isinstance(cap, dict) and cap.get("entry_point_consistency") == "OPEN_QUESTION":
            ref = str(cap.get("entry_point_open_question_ref", "") or "").strip()
            if ref and open_ids is not None and ref not in open_ids:
                problems.append(f"capability_eligibility.capabilities[{i}].entry_point_open_question_ref '{ref}' "
                                "is not in the plan's open_questions")

    # multi-select: an UNKNOWN or absent selection policy while multi-select is in scope
    # must be surfaced as an open question, never invented and never silently dropped.
    if multiselect:
        for i, cap in enumerate(caps):
            if not isinstance(cap, dict):
                continue
            policy = str(cap.get("selection_policy", "") or "").strip()
            if policy in ("", "UNKNOWN"):
                ref = str(cap.get("selection_open_question_ref", "") or "").strip()
                if not ref:
                    problems.append(f"capability_eligibility.capabilities[{i}] has UNKNOWN/absent selection_policy "
                                    "while multi-selection is in scope - resolve it with evidence or record a "
                                    "selection_open_question_ref; do not invent a mixed-selection AC")
                elif open_ids is not None and ref not in open_ids:
                    problems.append(f"capability_eligibility.capabilities[{i}].selection_open_question_ref '{ref}' "
                                    "is not in the plan's open_questions")

    # Config PREREQUISITE product decision: when a CONFIG term is a prerequisite (the fix is
    # a no-op unless the setting is ON - a decision usually taken during UAC), it must be
    # surfaced as an Open Question so QA verifies the environment and it is documented, not
    # buried in a boundary AC.
    for i, cap in enumerate(caps):
        if not isinstance(cap, dict):
            continue
        for j, term in enumerate(cap.get("predicate_terms") or []):
            if isinstance(term, dict) and term.get("dimension") == "CONFIG" and term.get("prerequisite"):
                ref = str(term.get("prerequisite_open_question_ref", "") or "").strip()
                if not ref:
                    problems.append(f"capability_eligibility.capabilities[{i}].predicate_terms[{j}] is a CONFIG "
                                    "prerequisite (the fix does not work unless the setting is on) - surface it with a "
                                    "prerequisite_open_question_ref in Open Questions; a config prerequisite/product "
                                    "decision must be visible, not assumed")
                elif open_ids is not None and ref not in open_ids:
                    problems.append(f"capability_eligibility.capabilities[{i}].predicate_terms[{j}] "
                                    f"prerequisite_open_question_ref '{ref}' is not in the plan's open_questions")

    # Config-key provenance: a CONFIG predicate that names a key copied unverified
    # from the reporter/ticket must be code/doc-verified or made an Open Question.
    for i, cap in enumerate(caps):
        if not isinstance(cap, dict):
            continue
        for j, term in enumerate(cap.get("predicate_terms") or []):
            if not isinstance(term, dict) or term.get("dimension") != "CONFIG":
                continue
            prov = str(term.get("key_provenance", "") or "").strip()
            if prov and prov not in VERIFIED_KEY_PROVENANCE + UNVERIFIED_KEY_PROVENANCE:
                problems.append(f"capability_eligibility.capabilities[{i}].predicate_terms[{j}].key_provenance "
                                f"must be one of {', '.join(VERIFIED_KEY_PROVENANCE + UNVERIFIED_KEY_PROVENANCE)}")
            elif prov in UNVERIFIED_KEY_PROVENANCE:
                ref = str(term.get("verification_open_question_ref", "") or "").strip()
                if not ref:
                    problems.append(f"capability_eligibility.capabilities[{i}].predicate_terms[{j}] is a CONFIG "
                                    f"predicate with UNVERIFIED provenance ({prov}) - a reporter/ticket-supplied key "
                                    "is frequently a typo/transposition; verify it against product code/docs or carry "
                                    "it as an Open Question via verification_open_question_ref")
                elif open_ids is not None and ref not in open_ids:
                    problems.append(f"capability_eligibility.capabilities[{i}].predicate_terms[{j}] "
                                    f"verification_open_question_ref '{ref}' is not in the plan's open_questions")

    # shared-predicate groups must carry shared evidence and reference known capabilities.
    for g, group in enumerate(block.get("shared_predicate_groups", []) or []):
        gtag = f"capability_eligibility.shared_predicate_groups[{g}]"
        if not isinstance(group, dict):
            problems.append(f"{gtag} must be an object")
            continue
        gcaps = group.get("capabilities", []) or []
        if len([c for c in gcaps if str(c).strip()]) < 2:
            problems.append(f"{gtag} must name at least two capabilities that genuinely share a predicate")
        unknown = [c for c in gcaps if str(c).strip() and str(c).strip() not in names]
        if unknown:
            problems.append(f"{gtag} references capabilities not decomposed above: {', '.join(unknown)}")
    return problems


def bundled_groups_without_evidence(block):
    """Groups that assert several capabilities share one predicate WITHOUT shared evidence.
    Surfaced by the gate as NEEDS_REVIEW (same surface != same predicate)."""
    out = []
    if not isinstance(block, dict):
        return out
    for group in block.get("shared_predicate_groups", []) or []:
        if not isinstance(group, dict):
            continue
        gcaps = [str(c).strip() for c in (group.get("capabilities") or []) if str(c).strip()]
        if len(gcaps) >= 2 and not (group.get("evidence") or []):
            out.append(", ".join(gcaps))
    return out


def summarize(manifest, plan_text=""):
    lines = [f"CapabilityEligibilityExplorer: active={is_active(manifest, plan_text)} "
             f"signals={detect_signals(manifest, plan_text)} multiselect={multiselect_in_scope(manifest, plan_text)}"]
    if is_present(manifest):
        for p in validate_capability_eligibility(manifest["capability_eligibility"]):
            lines.append(f"  {p}")
    return "\n".join(lines)
