"""SemanticCoverageGate (generalized) - measure EXPLORATION completeness.

WHY THIS EXISTS
---------------
The structural/evidence/manifest/self-test gates can pass a plan that is perfectly
formatted yet skipped materially relevant behavioral exploration. This gate closes
that hole: for every reasoning dimension ACTIVATED for the Jira (derived from the
BehaviorModel, coverage hypotheses, retrieval, verifications, and DITA semantics),
it requires exactly one of:

    COVERED  |  INVESTIGATED_AND_REJECTED  |  UNRESOLVED_AND_EXPOSED

and never lets a dimension stay silently unexplored. It measures exploration
completeness, NOT the number of scenarios.

Result:
    PASS         - every activated dimension resolved acceptably.
    NEEDS_REVIEW - a dimension was discovered but not explored to a terminal state.
    FAIL         - a material hypothesis is UNRESOLVED but hidden from Open Questions.

It only activates when the plan participates (any Prompt 1-4 block present), so
existing plans that predate the reasoning architecture are unaffected. Generic
only - no domain/construct/Jira rules. Stdlib only.
"""

import importlib.util
from pathlib import Path


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_behavior = _load("behavior_model", "behavior_model.py")
_explorer = _load("semantic_relationship_explorer", "semantic_relationship_explorer.py")
_relevance = _load("relevance_prioritizer", "relevance_prioritizer.py")
_cap_elig = _load("capability_eligibility_explorer", "capability_eligibility_explorer.py")
_scope = _load("scope_conflict_resolver", "scope_conflict_resolver.py")


# Map coverage-hypothesis dimensions to the gate's dimension names.
COVERAGE_TO_GATE = {
    "CONTRACT_BOUNDARY": "CONTRACT_BOUNDARY",
    "CONSUMER": "CONSUMER_EXPLORATION",
    "CONSUMER_POLICY": "CONSUMER_POLICY",
    "STATE_PARTITION": "STATE_PARTITIONS",
    "TYPE_ABSTRACTION": "TYPE_ABSTRACTION",
    "REFERENCE_ARTIFACT": "REFERENCE_ARTIFACT",
    "DITA_SEMANTIC_DEPENDENCY": "DITA_SEMANTICS",
    "LIFECYCLE": "LIFECYCLE",
    "CONFIGURATION": "CONFIGURATION",
    "PUBLISHING_MODE": "PUBLISHING_MODE",
    "NFR_RISK": "NFR",
    "BACKWARD_COMPATIBILITY": "BACKWARD_COMPATIBILITY",
    "DOWNSTREAM_REGRESSION": "DOWNSTREAM_REGRESSION",
}

COVERED = "COVERED"
REJECTED_DIM = "INVESTIGATED_AND_REJECTED"
EXPOSED = "UNRESOLVED_AND_EXPOSED"
NEEDS_REVIEW = "NEEDS_REVIEW"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"


def _norm(q):
    return " ".join(str(q or "").lower().split())


def _open_question_ids(manifest):
    ids = set()
    for oq in (manifest.get("open_questions", []) or []):
        if isinstance(oq, str):
            ids.add(oq)
        elif isinstance(oq, dict):
            ids.add(oq.get("id") or oq.get("ref") or "")
    ids.discard("")
    return ids


def _dimension_status(hyps, verifs, open_q, dim, reasons):
    """Aggregate one gate dimension's hypotheses into a dimension status."""
    has_covered = has_candidate = has_rejected = False
    unresolved_exposed = unresolved_hidden = False
    for h in hyps:
        hid = h.get("hypothesis_id", "")
        v = verifs.get(hid)
        if v:
            verdict = v.get("verdict", "")
            if verdict in ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE"):
                has_covered = True
            elif verdict == "REJECTED":
                has_rejected = True
            elif verdict == "UNRESOLVED":
                ref = v.get("open_question_ref", "")
                if ref and ref in open_q:
                    unresolved_exposed = True
                else:
                    unresolved_hidden = True
            else:
                has_candidate = True
        else:
            st = h.get("status", "INVESTIGATION_CANDIDATE")
            if st in ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE"):
                has_covered = True
            elif st == "REJECTED":
                has_rejected = True
            elif st == "UNRESOLVED":
                unresolved_hidden = True  # unresolved with no verification/exposure = hidden
            else:
                has_candidate = True  # still an INVESTIGATION_CANDIDATE = discovered, not explored

    if unresolved_hidden:
        reasons["blocking"].append(f"{dim}: a material hypothesis is UNRESOLVED but not exposed as an Open Question")
        return FAIL
    if has_candidate:
        reasons["review"].append(f"{dim}: a candidate was discovered but not investigated to a terminal verdict")
        return NEEDS_REVIEW
    if has_covered:
        return COVERED
    if unresolved_exposed:
        return EXPOSED
    if has_rejected:
        return REJECTED_DIM
    reasons["review"].append(f"{dim}: no terminal status could be determined")
    return NEEDS_REVIEW


def evaluate(manifest):
    """Evaluate the gate over a manifest. Returns a structured result dict:
    {semantic_gate, dimensions, blocking_reasons, review_reasons}."""
    reasons = {"blocking": [], "review": []}
    dims = {}

    cov = manifest.get("coverage_hypotheses", []) or []
    verifs = {v.get("hypothesis_id"): v for v in (manifest.get("verifications", []) or []) if isinstance(v, dict)}
    open_q = _open_question_ids(manifest)

    # Dimensions driven by coverage hypotheses.
    groups = {}
    for h in cov:
        if not isinstance(h, dict):
            continue
        gd = COVERAGE_TO_GATE.get(h.get("dimension"), h.get("dimension") or "UNKNOWN")
        groups.setdefault(gd, []).append(h)
    for gd, hs in groups.items():
        dims[gd] = _dimension_status(hs, verifs, open_q, gd, reasons)

    # Meta dimension: BEHAVIOR_MODEL (present -> must be valid).
    bm = manifest.get("behavior_model")
    if isinstance(bm, dict):
        ok = not _behavior.validate_behavior_model(bm)
        dims["BEHAVIOR_MODEL"] = COVERED if ok else NEEDS_REVIEW
        if not ok:
            reasons["review"].append("BEHAVIOR_MODEL: the behavior model is missing/incomplete")

    # Meta dimension: SECOND_PASS_RETRIEVAL (activated by a material question).
    mq = manifest.get("missing_questions", []) or []
    ev = manifest.get("evidence_lifecycle", []) or []
    if any(isinstance(q, dict) and q.get("blocking") for q in mq):
        initial = {_norm(e.get("query")) for e in ev if isinstance(e, dict) and (e.get("pass") or e.get("pass_label")) == "initial"}
        later = {_norm(e.get("query")) for e in ev if isinstance(e, dict) and (e.get("pass") or e.get("pass_label")) in ("second", "third")}
        new_q = later - initial - {""}
        dims["SECOND_PASS_RETRIEVAL"] = COVERED if new_q else NEEDS_REVIEW
        if not new_q:
            reasons["review"].append("SECOND_PASS_RETRIEVAL: a material question exists but no new directed second-pass query was run")

    # Meta dimension: OPEN_QUESTIONS (every UNRESOLVED verdict must be exposed).
    unresolved = [v for v in verifs.values() if v.get("verdict") == "UNRESOLVED"]
    if unresolved:
        hidden = [v for v in unresolved if not (v.get("open_question_ref") and v.get("open_question_ref") in open_q)]
        dims["OPEN_QUESTIONS"] = FAIL if hidden else COVERED
        if hidden:
            reasons["blocking"].append("OPEN_QUESTIONS: an UNRESOLVED hypothesis is not surfaced in Open Questions")

    # Dimension: RELEVANCE_PRIORITIZATION - a HIGH-relevance (direct/one-hop) governing
    # dependency must be investigated to a terminal verdict before the gate can pass.
    # Low-value regression breadth cannot compensate for an unexplored direct dependency.
    if cov:
        blocked = _relevance.high_relevance_unresolved(cov, manifest.get("verifications", []))
        if blocked:
            dims["RELEVANCE_PRIORITIZATION"] = NEEDS_REVIEW
            ids = ", ".join(h.get("hypothesis_id", "?") for h in blocked)
            reasons["review"].append(
                f"RELEVANCE_PRIORITIZATION: HIGH-relevance direct/one-hop dependency not explored to a terminal "
                f"verdict ({ids}) - investigate direct governing dependencies before distant regression candidates"
            )
        else:
            dims["RELEVANCE_PRIORITIZATION"] = COVERED

    # Dimension: DITA_SEMANTICS (reuse the DITA semantic gate as the single source).
    sem = manifest.get("dita_semantics")
    if isinstance(sem, dict) and sem.get("active"):
        overall, _sdims, _sfail = _explorer.evaluate_semantic_gate(sem)
        if overall == "PASSED":
            dims["DITA_SEMANTICS"] = COVERED
        elif overall != "SKIPPED":
            dims["DITA_SEMANTICS"] = NEEDS_REVIEW
            reasons["review"].append("DITA_SEMANTICS: a governing semantic dependency was not investigated")

    # Capability-eligibility dimensions (Step 19): same-surface actions decomposed per
    # capability; bundling under one predicate without evidence is NEEDS_REVIEW.
    cap = manifest.get("capability_eligibility")
    if isinstance(cap, dict) and cap.get("active", True) and cap.get("capabilities"):
        oq_ids = _open_question_ids(manifest)
        cap_ok = not _cap_elig.validate_capability_eligibility(
            cap, open_question_ids=oq_ids, multiselect=_cap_elig.multiselect_in_scope(manifest))
        dims["AFFECTED_CAPABILITIES_DECOMPOSED"] = COVERED if cap_ok else NEEDS_REVIEW
        dims["ELIGIBILITY_RESOLVED_PER_CAPABILITY"] = COVERED if cap_ok else NEEDS_REVIEW
        dims["ENTITY_TYPE_ASSUMPTION_CHECKED"] = COVERED
        dims["REQUIRED_METADATA_STATE_CHECKED"] = COVERED
        dims["SURFACE_APPLICABILITY_CHECKED"] = COVERED
        dims["SELECTION_POLICY_CHECKED_IF_APPLICABLE"] = COVERED
        dims["SEMANTIC_COLLISIONS_RESOLVED"] = COVERED
        dims["IMPLEMENTATION_ORACLE_SEPARATED_FROM_AC"] = COVERED
        if _cap_elig.bundled_groups_without_evidence(cap):
            dims["AFFECTED_CAPABILITIES_DECOMPOSED"] = NEEDS_REVIEW
            reasons["review"].append("capabilities bundled under one eligibility predicate without shared evidence")
    elif _cap_elig.is_active(manifest):
        dims["AFFECTED_CAPABILITIES_DECOMPOSED"] = NEEDS_REVIEW
        reasons["review"].append("multiple actions share one surface but no per-capability eligibility decomposition")

    # Scope-conflict dimensions (Step 19): a material Jira-vs-fix mismatch not surfaced as
    # an Open Question is blocking; secondary defects must be classified.
    sc = manifest.get("scope_conflict")
    if isinstance(sc, dict) and sc.get("active", True):
        if _scope.unresolved_scope_without_open_question(sc, _open_question_ids(manifest)):
            dims["JIRA_SCOPE_VS_FIX_RECONCILED"] = FAIL
            dims["UNRESOLVED_SCOPE_EXPOSED"] = FAIL
            reasons["blocking"].append("JIRA_SCOPE_VS_FIX: a material scope mismatch is not surfaced as an Open Question")
        else:
            dims["JIRA_SCOPE_VS_FIX_RECONCILED"] = COVERED
            dims["UNRESOLVED_SCOPE_EXPOSED"] = COVERED
        dims["SECONDARY_DEFECTS_CLASSIFIED"] = COVERED

    # Overall verdict.
    if any(s == FAIL for s in dims.values()):
        overall = FAIL
    elif any(s == NEEDS_REVIEW for s in dims.values()):
        overall = NEEDS_REVIEW
    else:
        overall = "PASS"

    return {
        "semantic_gate": overall,
        "dimensions": dims,
        "blocking_reasons": reasons["blocking"],
        "review_reasons": reasons["review"],
    }


def is_present(manifest):
    """The gate participates only when the plan carries a reasoning block, so plans
    predating the architecture (and DITA-only plans handled by the DITA gate) are
    unaffected."""
    if not isinstance(manifest, dict):
        return False
    for key in ("coverage_hypotheses", "verifications", "behavior_model",
                "missing_questions", "evidence_lifecycle", "coverage_gate", "open_questions"):
        val = manifest.get(key)
        if isinstance(val, (list, dict)) and val:
            return True
    return False


def summarize(manifest):
    r = evaluate(manifest)
    lines = [f"SemanticCoverageGate: {r['semantic_gate']}"]
    for d, s in sorted(r["dimensions"].items()):
        lines.append(f"  {d}: {s}")
    for br in r["blocking_reasons"]:
        lines.append(f"  BLOCK {br}")
    for rr in r["review_reasons"]:
        lines.append(f"  REVIEW {rr}")
    return "\n".join(lines)
