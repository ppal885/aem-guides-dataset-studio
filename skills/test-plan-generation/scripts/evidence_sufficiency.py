"""Evidence Sufficiency gate per material question and coverage decision.

WHY THIS EXISTS
---------------
"Evidence exists" is not "evidence is sufficient to support this answer or
coverage."  Many retrieved sources do not automatically make evidence
sufficient; one applicable authoritative source may be sufficient.  This gate
extends the existing `evidence_sufficiency` manifest block: one assessment per
material resolved question and per coverage decision, so the Writer never
receives unsupported coverage as confirmed behavior and the Reviewer can verify
sufficiency lineage.

Question states: SUFFICIENT, PARTIAL, INSUFFICIENT, CONFLICTED.

Every question assessment evaluates the eight dimensions (AUTHORITY,
EXPECTED_BEHAVIOR, APPLICABILITY, MATERIAL_CONDITIONS, NEGATIVE_BEHAVIOR,
RESEARCH_COMPLETION, SOURCE_CURRENTNESS, CONTRADICTIONS) as free-text notes and
carries the structured sub-states `authority_status`, `research_completion`,
`applicability_status`, `currentness_status`, `contradiction_status`, plus
claim-level `supported_claims[]` / `unsupported_claims[]`, `limitations[]`,
`evidence_ids[]`, `research_ids[]`, and `decision_reason`.

Rules enforced (all generic; no numeric confidence as authority):

- One applicable authoritative source may be SUFFICIENT; volume alone is not -
  SUFFICIENT requires an ESTABLISHING authority_status and at least one
  supported claim.
- Research completion (R1/Q1 integration): PENDING / NOT_FOUND /
  SOURCE_UNAVAILABLE cannot be SUFFICIENT; PARTIAL cannot support a fully
  established answer unless the remaining limitation is demonstrably immaterial
  to that specific answer (`immaterial_limitation`); CONFLICTED research forces
  CONFLICTED; ANSWER_FOUND is not automatically SUFFICIENT (authority,
  applicability, and decisiveness are still evaluated).
- Applicability: WRONG_APPLICABILITY (wrong version / engine / surface) cannot
  be SUFFICIENT unless explicit `compatibility_evidence_ids` bridge it; UNCLEAR
  applicability is never confirmed applicability.  STALE currentness likewise
  needs the compatibility bridge.
- Contradictions: CONFLICTING evidence forces CONFLICTED; equal-authority
  conflicts are not resolved by convenience or confidence.
- INSUFFICIENT does not establish the opposite behavior.
- Claim binding: sufficiency binds to the specific question's evidence pool
  (research evidence, answer sources, admitted doc research, triggering
  evidence) - one claim's evidence cannot bleed into a neighboring claim;
  `research_ids` must cite admitted Doc Researcher results.
- PARTIAL names its established portion and its unsupported claims, and is
  never silently upgraded.
- Coverage sufficiency is computed from the underlying questions: any
  underlying CONFLICTED forces CONFLICTED; any underlying INSUFFICIENT or
  PARTIAL caps the coverage below SUFFICIENT; every underlying question must
  itself be assessed; cross-product coverage is not SUFFICIENT merely because
  each control exists (combination evidence required).
- Writer handoff: every admitted decision carries an assessment; INSUFFICIENT
  or CONFLICTED decisions never reach the Writer; ACCEPTANCE-class decisions in
  the handoff must be SUFFICIENT unless explicitly represented as
  ACCEPTANCE_TBD; PARTIAL decisions name the established portion the Writer
  may use.
- Reviewer: a writer-package AC never references INSUFFICIENT/CONFLICTED
  coverage or a PARTIAL coverage's unestablished portion; a stale assessment
  (question revision changed) is rejected.

Backward-compatible: absent `evidence_sufficiency` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

SUFFICIENCY_STATES = (
    "SUFFICIENT",
    "PARTIAL",
    "INSUFFICIENT",
    "CONFLICTED",
)

EVALUATION_DIMENSIONS = (
    "AUTHORITY",
    "EXPECTED_BEHAVIOR",
    "APPLICABILITY",
    "MATERIAL_CONDITIONS",
    "NEGATIVE_BEHAVIOR",
    "RESEARCH_COMPLETION",
    "SOURCE_CURRENTNESS",
    "CONTRADICTIONS",
)

AUTHORITY_STATUSES = ("ESTABLISHING", "NON_ESTABLISHING")

RESEARCH_COMPLETION_STATES = (
    "NOT_REQUIRED",
    "PENDING",
    "COMPLETED",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "CONFLICTED",
)

APPLICABILITY_STATUSES = ("APPLICABLE", "WRONG_APPLICABILITY", "UNCLEAR")

CURRENTNESS_STATUSES = ("CURRENT", "STALE", "UNKNOWN")

CONTRADICTION_STATUSES = ("NONE", "CONFLICTING")

# Authorities that can establish an expectation (the resolver's establishing
# set minus observation/inference roles).  One authoritative current-ticket AC
# may be SUFFICIENT; a pile of supporting passages is not automatically so.
ESTABLISHING_AUTHORITIES = frozenset({
    "CURRENT_TICKET_REQUIREMENT",
    "ACCEPTED_UAC",
    "PRODUCT_DECISION",
    "OFFICIAL_DOCUMENTATION",
    "DITA_SPECIFICATION",
    "CURRENT_IMPLEMENTATION",
    "EXISTING_AUTOMATION",
    "HUMAN_PRODUCT",
})

# Research statuses that can never support a SUFFICIENT assessment.  PARTIAL
# is handled separately: it caps at PARTIAL unless the remaining limitation is
# demonstrably immaterial to the specific answer.
_NON_SUFFICIENT_RESEARCH = frozenset({
    "PENDING",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
})

# question_research status -> research_completion sub-state.
_RESEARCH_STATUS_COMPLETION = {
    "NOT_REQUIRED": "NOT_REQUIRED",
    "PENDING": "PENDING",
    "ANSWER_FOUND": "COMPLETED",
    "PARTIAL": "PARTIAL",
    "NOT_FOUND": "NOT_FOUND",
    "SOURCE_UNAVAILABLE": "SOURCE_UNAVAILABLE",
    "CONFLICTED": "CONFLICTED",
}

# INSUFFICIENT evidence never establishes the opposite behavior.
_FORBIDDEN_INSUFFICIENT_FIELDS = (
    "proves_opposite",
    "establishes_opposite",
    "absence_proves",
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("evidence_sufficiency"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _question_ref(item):
    if not isinstance(item, dict):
        return None
    return item.get("question_ref") or item.get("question_id")


def _sufficiency(item):
    return item.get("sufficiency") or item.get("sufficiency_status")


def _validate_dimensions(tag, dimensions):
    if not isinstance(dimensions, dict):
        return [f"{tag}: dimensions must be an object covering "
                f"{', '.join(EVALUATION_DIMENSIONS)}"]
    problems = []
    for name in EVALUATION_DIMENSIONS:
        if name not in dimensions:
            problems.append(f"{tag}: dimension {name} was not evaluated")
        elif not isinstance(dimensions[name], str):
            problems.append(f"{tag}: dimension {name} must be a text note")
    unknown = sorted(set(dimensions) - set(EVALUATION_DIMENSIONS))
    if unknown:
        problems.append(f"{tag}: unknown evaluation dimensions {unknown}")
    return problems


def _question_evidence_ids(manifest, question_refs):
    """Evidence establishing each question: research evidence + answer sources."""

    evidence = {ref: set() for ref in question_refs}
    research = manifest.get("question_research")
    if isinstance(research, dict):
        for row in research.get("items", []):
            if isinstance(row, dict) and row.get("question_ref") in evidence:
                evidence[row["question_ref"]].update(
                    row.get("research_evidence_ids") or []
                )
    resolutions = manifest.get("question_resolutions")
    if isinstance(resolutions, dict):
        for row in resolutions.get("items", []):
            if not isinstance(row, dict):
                continue
            ref = row.get("question_ref") or row.get("question_id")
            if ref not in evidence:
                continue
            answer = row.get("answer")
            if isinstance(answer, dict):
                evidence[ref].update(answer.get("source_ids") or [])
            elif isinstance(answer, str):
                evidence[ref].update(row.get("source_ids") or [])
    plan = manifest.get("question_plan")
    if isinstance(plan, dict):
        for source in (plan.get("items"),
                       (plan.get("overflow") or {}).get("items")):
            if not isinstance(source, list):
                continue
            for row in source:
                if isinstance(row, dict) and row.get("question_id") in evidence:
                    evidence[row["question_id"]].update(
                        row.get("triggering_evidence_ids") or []
                    )
    doc_research = manifest.get("doc_research")
    if isinstance(doc_research, dict):
        admitted = doc_research.get("admitted_research_ids")
        admitted_ids = (
            set(admitted)
            if isinstance(admitted, list)
            else {
                row.get("research_id")
                for row in doc_research.get("results", [])
                if isinstance(row, dict)
            }
        )
        for row in doc_research.get("results", []):
            if not isinstance(row, dict):
                continue
            if row.get("research_id") not in admitted_ids:
                continue
            for ref in row.get("question_refs") or []:
                if ref in evidence:
                    evidence[ref].update(row.get("source_ids") or [])
    return evidence


def _validate_question_assessment(i, item, chain):
    problems = []
    tag = f"evidence_sufficiency.question_assessments[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each assessment must be an object"]

    ref = _question_ref(item)
    if not _nonempty(ref):
        problems.append(f"{tag}: missing question_id (question_ref)")
    sufficiency = _sufficiency(item)
    if sufficiency not in SUFFICIENCY_STATES:
        problems.append(
            f"{tag}: sufficiency_status '{sufficiency}' must be one of "
            f"{', '.join(SUFFICIENCY_STATES)}"
        )
        return problems
    if not _nonempty(item.get("decision_reason")):
        problems.append(
            f"{tag}: missing decision_reason - the sufficiency decision is "
            "recorded with its reason"
        )
    problems.extend(_validate_dimensions(tag, item.get("dimensions")))

    authority_status = item.get("authority_status")
    if authority_status not in AUTHORITY_STATUSES:
        problems.append(
            f"{tag}: authority_status '{authority_status}' must be one of "
            f"{', '.join(AUTHORITY_STATUSES)}"
        )
    research_completion = item.get("research_completion")
    if research_completion not in RESEARCH_COMPLETION_STATES:
        problems.append(
            f"{tag}: research_completion '{research_completion}' must be one "
            f"of {', '.join(RESEARCH_COMPLETION_STATES)}"
        )
    applicability_status = item.get("applicability_status")
    if applicability_status not in APPLICABILITY_STATUSES:
        problems.append(
            f"{tag}: applicability_status '{applicability_status}' must be "
            f"one of {', '.join(APPLICABILITY_STATUSES)}"
        )
    currentness_status = item.get("currentness_status")
    if currentness_status not in CURRENTNESS_STATUSES:
        problems.append(
            f"{tag}: currentness_status '{currentness_status}' must be one "
            f"of {', '.join(CURRENTNESS_STATUSES)}"
        )
    contradiction_status = item.get("contradiction_status")
    if contradiction_status not in CONTRADICTION_STATUSES:
        problems.append(
            f"{tag}: contradiction_status '{contradiction_status}' must be "
            f"one of {', '.join(CONTRADICTION_STATUSES)}"
        )

    for field in ("supported_claims", "unsupported_claims", "limitations",
                  "evidence_ids", "research_ids"):
        if not isinstance(item.get(field), list):
            problems.append(f"{tag}: {field} must be a list")

    if sufficiency == "SUFFICIENT":
        if not item.get("supported_claims"):
            problems.append(
                f"{tag}: SUFFICIENT requires at least one supported claim - "
                "sufficiency binds to the specific claim, not the ticket"
            )
        if authority_status == "NON_ESTABLISHING":
            problems.append(
                f"{tag}: SUFFICIENT requires ESTABLISHING authority_status - "
                "one applicable authoritative source may suffice; actual "
                "results, attachment observations, history, and inference do "
                "not"
            )
        if applicability_status == "UNCLEAR":
            problems.append(
                f"{tag}: UNCLEAR applicability cannot be treated as confirmed "
                "applicability"
            )
        if (
            applicability_status == "WRONG_APPLICABILITY"
            and not item.get("compatibility_evidence_ids")
        ):
            problems.append(
                f"{tag}: wrong-applicability evidence remains insufficient "
                "unless explicit compatibility evidence exists - wrong "
                "version/engine/surface evidence does not answer this claim"
            )
        if (
            currentness_status == "STALE"
            and not item.get("compatibility_evidence_ids")
        ):
            problems.append(
                f"{tag}: stale-currentness evidence remains insufficient "
                "unless explicit compatibility evidence exists"
            )
        if research_completion in _NON_SUFFICIENT_RESEARCH:
            problems.append(
                f"{tag}: research_completion {research_completion} cannot be "
                "SUFFICIENT"
            )
        if research_completion == "PARTIAL" and not _nonempty(
            item.get("immaterial_limitation")
        ):
            problems.append(
                f"{tag}: PARTIAL research cannot support a fully established "
                "answer unless the remaining limitation is demonstrably "
                "immaterial to this specific answer (immaterial_limitation)"
            )
        if contradiction_status == "CONFLICTING":
            problems.append(
                f"{tag}: CONFLICTING evidence forces CONFLICTED - the "
                "conflict is not resolved by convenience or confidence"
            )
    if sufficiency == "PARTIAL":
        if not _nonempty(item.get("established_portion")):
            problems.append(
                f"{tag}: PARTIAL answers may support only the established "
                "portion - name it in established_portion"
            )
        if not item.get("unsupported_claims"):
            problems.append(
                f"{tag}: PARTIAL must keep the unresolved portion visible in "
                "unsupported_claims"
            )
    if sufficiency == "INSUFFICIENT":
        for field in _FORBIDDEN_INSUFFICIENT_FIELDS:
            if item.get(field):
                problems.append(
                    f"{tag}: {field} is forbidden - INSUFFICIENT does not "
                    "establish the opposite behavior"
                )
    if sufficiency == "CONFLICTED":
        if not item.get("contradictions"):
            problems.append(
                f"{tag}: CONFLICTED must retain the competing claims in "
                "contradictions"
            )
        if contradiction_status == "NONE":
            problems.append(
                f"{tag}: CONFLICTED requires contradiction_status CONFLICTING"
            )
    elif contradiction_status == "CONFLICTING":
        problems.append(
            f"{tag}: CONFLICTING evidence forces a CONFLICTED assessment"
        )

    if chain["planned_ids"] is not None and ref and ref not in chain["planned_ids"]:
        problems.append(f"{tag}: assessed question '{ref}' was never planned")

    route = chain["research_by_ref"].get(ref)
    if route is not None:
        expected_completion = _RESEARCH_STATUS_COMPLETION.get(
            route.get("research_status")
        )
        if (
            expected_completion
            and research_completion in RESEARCH_COMPLETION_STATES
            and research_completion != expected_completion
        ):
            problems.append(
                f"{tag}: research_completion {research_completion} does not "
                f"match the mandatory research state "
                f"{route.get('research_status')}"
            )
    if route is not None and route.get("research_requirement") != "NONE":
        research_status = route.get("research_status")
        if sufficiency == "SUFFICIENT" and research_status in (
            _NON_SUFFICIENT_RESEARCH
        ):
            problems.append(
                f"{tag}: a question requiring "
                f"{route.get('research_requirement')} research cannot be "
                f"SUFFICIENT while its mandatory research is {research_status}"
            )
        if research_status == "CONFLICTED" and sufficiency != "CONFLICTED":
            problems.append(
                f"{tag}: CONFLICTED research forces a CONFLICTED assessment"
            )
        if research_status == "PARTIAL" and sufficiency == "SUFFICIENT" and (
            not _nonempty(item.get("immaterial_limitation"))
        ):
            problems.append(
                f"{tag}: PARTIAL research caps the assessment at PARTIAL "
                "unless the remaining limitation is demonstrably immaterial"
            )

    resolution = chain["resolutions_by_ref"].get(ref)
    if resolution is not None:
        resolution_status = resolution.get("status") or resolution.get(
            "disposition"
        )
        if resolution_status == "CONFLICTED" and sufficiency != "CONFLICTED":
            problems.append(
                f"{tag}: a CONFLICTED resolution forces a CONFLICTED assessment"
            )
        if sufficiency == "SUFFICIENT" and resolution_status == "ANSWERED":
            answer = resolution.get("answer")
            authority = (
                answer.get("source_authority")
                if isinstance(answer, dict)
                else resolution.get("source_authority")
            )
            if authority and authority not in ESTABLISHING_AUTHORITIES:
                problems.append(
                    f"{tag}: SUFFICIENT requires an establishing authority; "
                    f"{authority} is not one"
                )
    elif sufficiency == "SUFFICIENT" and (
        item.get("establishing_authority") not in ESTABLISHING_AUTHORITIES
    ):
        problems.append(
            f"{tag}: SUFFICIENT requires an establishing_authority in "
            f"{', '.join(sorted(ESTABLISHING_AUTHORITIES))} - one "
            "authoritative current-ticket AC may suffice, volume alone does "
            "not"
        )

    # Claim-level binding: evidence binds to this question's evidence pool;
    # one claim's evidence never bleeds into a neighboring claim.
    evidence_ids = item.get("evidence_ids") or []
    pool = chain["question_evidence_pool"].get(ref)
    if pool:
        foreign = sorted(set(evidence_ids) - pool)
        if foreign:
            problems.append(
                f"{tag}: evidence {foreign} is not bound to question '{ref}' "
                "- sufficiency for one claim cannot bleed into a neighboring "
                "claim"
            )
    research_ids = item.get("research_ids") or []
    if chain["admitted_research_ids"] is not None:
        for rid in research_ids:
            if rid not in chain["admitted_research_ids"]:
                problems.append(
                    f"{tag}: research '{rid}' is not an admitted Doc "
                    "Researcher result"
                )

    # Stale sufficiency records: a question revision change invalidates the
    # earlier assessment.
    question_revision = chain["question_revisions"].get(ref)
    if question_revision is not None and (
        item.get("question_revision") != question_revision
    ):
        problems.append(
            f"{tag}: the question was revised after this assessment - a stale "
            "sufficiency record cannot be reused"
        )
    return problems


def _validate_coverage_assessment(i, item, chain):
    problems = []
    tag = f"evidence_sufficiency.coverage_assessments[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each assessment must be an object"]

    ref = item.get("coverage_ref")
    if not _nonempty(ref):
        problems.append(f"{tag}: missing coverage_ref")
    sufficiency = _sufficiency(item)
    if sufficiency not in SUFFICIENCY_STATES:
        problems.append(
            f"{tag}: sufficiency_status '{sufficiency}' must be one of "
            f"{', '.join(SUFFICIENCY_STATES)}"
        )
        return problems
    if not _nonempty(item.get("sufficiency_reason") or item.get("reason")):
        problems.append(f"{tag}: missing sufficiency_reason")

    coverage = chain["coverage_by_id"].get(ref)
    if chain["coverage_by_id"] is not None and coverage is None:
        problems.append(f"{tag}: '{ref}' is not a known coverage decision")
    question_refs = item.get("question_refs")
    if not isinstance(question_refs, list):
        problems.append(f"{tag}: question_refs must be a list")
        question_refs = []
    if coverage is not None:
        expected_refs = sorted(coverage.get("question_ids") or [])
        if sorted(set(question_refs)) != expected_refs:
            problems.append(
                f"{tag}: question_refs must match the coverage decision's "
                f"underlying questions {expected_refs} - the Reviewer verifies "
                "sufficiency lineage"
            )
        evidence_ids = item.get("evidence_ids")
        if isinstance(evidence_ids, list) and sorted(set(evidence_ids)) != (
            sorted(set(coverage.get("evidence_ids") or []))
        ):
            problems.append(
                f"{tag}: evidence_ids must match the coverage decision's "
                "evidence bindings"
            )
        research_ids = item.get("research_ids")
        if isinstance(research_ids, list) and sorted(set(research_ids)) != (
            sorted(set(coverage.get("research_ids") or []))
        ):
            problems.append(
                f"{tag}: research_ids must match the coverage decision's "
                "research bindings"
            )
    if sufficiency == "PARTIAL" and not _nonempty(item.get("established_portion")):
        problems.append(
            f"{tag}: PARTIAL coverage may support only the established portion - "
            "name it in established_portion"
        )

    # Sufficiency is computed from the underlying questions.
    question_states = {
        qref: chain["question_sufficiency"].get(qref) for qref in question_refs
    }
    if chain["assessments_declared"]:
        unassessed = sorted(
            qref for qref, state in question_states.items() if state is None
        )
        if unassessed:
            problems.append(
                f"{tag}: sufficiency cannot be computed - underlying question(s) "
                f"{unassessed} have no assessment"
            )
    underlying = [state for state in question_states.values() if state]
    if "CONFLICTED" in underlying and sufficiency != "CONFLICTED":
        problems.append(
            f"{tag}: an underlying CONFLICTED question forces CONFLICTED "
            "coverage - a conflict cannot silently generate an AC"
        )
    elif sufficiency == "SUFFICIENT" and any(
        state in {"INSUFFICIENT", "PARTIAL"} for state in underlying
    ):
        problems.append(
            f"{tag}: coverage is only as strong as its underlying questions; "
            "INSUFFICIENT/PARTIAL underneath cannot surface as SUFFICIENT"
        )

    if coverage is not None:
        coverage_class = coverage.get("coverage_class")
        priority = coverage.get("priority")
        if coverage_class == "ACCEPTANCE" and sufficiency == "INSUFFICIENT":
            problems.append(
                f"{tag}: INSUFFICIENT evidence cannot generate Acceptance "
                "Coverage"
            )
        if coverage_class == "ACCEPTANCE" and sufficiency == "CONFLICTED":
            problems.append(
                f"{tag}: CONFLICTED evidence cannot silently generate an AC"
            )
        if (
            coverage_class == "ACCEPTANCE"
            and priority in {"P0", "P1"}
            and sufficiency != "SUFFICIENT"
            and not item.get("represented_as_acceptance_tbd")
        ):
            problems.append(
                f"{tag}: P0/P1 Acceptance Coverage requires SUFFICIENT "
                "evidence unless explicitly represented_as_acceptance_tbd"
            )
        # A combination is not sufficient merely because each control exists.
        if sufficiency == "SUFFICIENT" and len(set(question_refs)) >= 2:
            member_evidence = chain["question_evidence"](question_refs)
            combined = set(coverage.get("evidence_ids") or [])
            outside = sorted(combined - member_evidence)
            if not outside and not item.get("combination_evidence_ids"):
                problems.append(
                    f"{tag}: cross-product coverage is not SUFFICIENT merely "
                    "because each control exists - cite combination_evidence_ids "
                    "or evidence that actually covers the combination"
                )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["evidence_sufficiency"]
    question_assessments = block.get("question_assessments", [])
    coverage_assessments = block.get("coverage_assessments", [])
    if not isinstance(question_assessments, list):
        return ["evidence_sufficiency.question_assessments must be a list"]
    if not isinstance(coverage_assessments, list):
        return ["evidence_sufficiency.coverage_assessments must be a list"]

    # Assemble the chain context from the reasoning blocks when present.
    plan = manifest.get("question_plan")
    planned_ids = None
    if isinstance(plan, dict):
        planned_ids = {
            row.get("question_id")
            for row in plan.get("items", [])
            if isinstance(row, dict)
        }
    question_revisions = {}
    if isinstance(plan, dict):
        for row in plan.get("items", []):
            if isinstance(row, dict) and row.get("revision") is not None:
                question_revisions[row.get("question_id")] = row.get("revision")
    research_by_ref = {}
    research = manifest.get("question_research")
    if isinstance(research, dict):
        for row in research.get("items", []):
            if isinstance(row, dict):
                research_by_ref[row.get("question_ref")] = row
    resolutions_by_ref = None
    resolutions = manifest.get("question_resolutions")
    if isinstance(resolutions, dict):
        resolutions_by_ref = {}
        for row in resolutions.get("items", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    resolutions_by_ref[ref] = row
    coverage_by_id = None
    coverage = manifest.get("coverage_decisions")
    if isinstance(coverage, dict) and isinstance(coverage.get("items"), list):
        coverage_by_id = {
            row.get("coverage_id"): row
            for row in coverage["items"]
            if isinstance(row, dict) and row.get("coverage_id")
        }
    question_sufficiency = {}
    for row in question_assessments:
        if isinstance(row, dict):
            ref = _question_ref(row)
            if ref:
                question_sufficiency[ref] = _sufficiency(row)

    doc_research = manifest.get("doc_research")
    admitted_research_ids = None
    if isinstance(doc_research, dict):
        admitted = doc_research.get("admitted_research_ids")
        admitted_research_ids = (
            set(admitted)
            if isinstance(admitted, list)
            else {
                row.get("research_id")
                for row in doc_research.get("results", [])
                if isinstance(row, dict)
            }
        )

    all_known_refs = set(planned_ids or set()) | set(research_by_ref) | set(
        resolutions_by_ref or {}
    )
    if isinstance(doc_research, dict):
        for row in doc_research.get("results", []):
            if isinstance(row, dict):
                all_known_refs.update(row.get("question_refs") or [])

    def question_evidence(question_refs):
        ids = _question_evidence_ids(manifest, question_refs)
        combined = set()
        for ref in question_refs:
            combined |= ids.get(ref, set())
        return combined

    chain = {
        "planned_ids": planned_ids,
        "question_revisions": question_revisions,
        "research_by_ref": research_by_ref,
        "resolutions_by_ref": resolutions_by_ref or {},
        "coverage_by_id": coverage_by_id,
        "question_sufficiency": question_sufficiency,
        "assessments_declared": bool(question_assessments),
        "question_evidence": question_evidence,
        "question_evidence_pool": _question_evidence_ids(
            manifest, sorted(all_known_refs)
        ),
        "admitted_research_ids": admitted_research_ids,
    }

    problems = []
    seen_questions = set()
    for i, item in enumerate(question_assessments):
        problems.extend(_validate_question_assessment(i, item, chain))
        ref = _question_ref(item)
        if ref:
            if ref in seen_questions:
                problems.append(
                    f"evidence_sufficiency.question_assessments[{i}]: duplicate "
                    f"assessment for '{ref}'"
                )
            seen_questions.add(ref)

    # Every applicable planned material question carries an assessment.
    # Investigation-only, not-applicable, and duplicate resolutions have no
    # acceptance stake, so they need no sufficiency assessment.
    if planned_ids is not None and isinstance(plan, dict):
        resolutions_map = chain["resolutions_by_ref"]
        for row in plan.get("items", []):
            if not isinstance(row, dict):
                continue
            if row.get("applicability") == "NOT_APPLICABLE":
                continue
            qid = row.get("question_id")
            resolution = resolutions_map.get(qid)
            resolution_status = (
                resolution.get("status") or resolution.get("disposition")
                if resolution is not None
                else None
            )
            if resolution_status in {
                "INVESTIGATION_ONLY",
                "NOT_APPLICABLE",
                "DUPLICATE",
            }:
                continue
            if qid and qid not in seen_questions:
                problems.append(
                    f"evidence_sufficiency: planned material question '{qid}' "
                    "has no sufficiency assessment"
                )

    seen_coverage = set()
    for i, item in enumerate(coverage_assessments):
        problems.extend(_validate_coverage_assessment(i, item, chain))
        ref = item.get("coverage_ref") if isinstance(item, dict) else None
        if ref:
            if ref in seen_coverage:
                problems.append(
                    f"evidence_sufficiency.coverage_assessments[{i}]: duplicate "
                    f"assessment for '{ref}'"
                )
            seen_coverage.add(ref)

    if coverage_by_id is not None:
        # The Reviewer verifies sufficiency lineage: every non-EXCLUDED
        # decision is assessed.
        for cid, row in sorted(coverage_by_id.items()):
            if row.get("priority") == "EXCLUDED":
                continue
            if cid not in seen_coverage:
                problems.append(
                    f"evidence_sufficiency: coverage decision '{cid}' has no "
                    "sufficiency assessment"
                )
        # The Writer must not receive unsupported coverage as confirmed
        # behavior.
        handoff = coverage.get("writer_handoff")
        if isinstance(handoff, list):
            assessments_by_ref = {
                row.get("coverage_ref"): row
                for row in coverage_assessments
                if isinstance(row, dict)
            }
            for cid in handoff:
                assessment = assessments_by_ref.get(cid)
                if assessment is None:
                    problems.append(
                        f"evidence_sufficiency: writer handoff decision '{cid}' "
                        "has no sufficiency assessment"
                    )
                    continue
                state = _sufficiency(assessment)
                coverage_row = coverage_by_id.get(cid) or {}
                if state in {"INSUFFICIENT", "CONFLICTED"}:
                    problems.append(
                        f"evidence_sufficiency: writer handoff decision '{cid}' "
                        f"is {state} - the Writer must not receive unsupported "
                        "coverage as confirmed behavior"
                    )
                elif state == "PARTIAL" and not _nonempty(
                    assessment.get("established_portion")
                ):
                    problems.append(
                        f"evidence_sufficiency: writer handoff decision '{cid}' "
                        "is PARTIAL without a named established portion - the "
                        "Writer cannot reinterpret evidence to upgrade "
                        "sufficiency"
                    )
                if (
                    coverage_row.get("coverage_class") == "ACCEPTANCE"
                    and state != "SUFFICIENT"
                    and not assessment.get("represented_as_acceptance_tbd")
                ):
                    problems.append(
                        f"evidence_sufficiency: writer handoff ACCEPTANCE "
                        f"decision '{cid}' is {state} - confirmed acceptance "
                        "behavior requires SUFFICIENT evidence"
                    )

        # Reviewer: a writer-package AC never rests on insufficient or
        # conflicted coverage, and never absorbs an unestablished portion.
        writer_package = manifest.get("writer_package")
        if isinstance(writer_package, dict):
            assessments_by_ref = {
                row.get("coverage_ref"): row
                for row in coverage_assessments
                if isinstance(row, dict)
            }
            for j, ac in enumerate(writer_package.get("acs") or []):
                if not isinstance(ac, dict):
                    continue
                atag = f"writer_package.acs[{j}]"
                for cid in ac.get("coverage_ids") or []:
                    assessment = assessments_by_ref.get(cid)
                    if assessment is None:
                        continue
                    state = _sufficiency(assessment)
                    if state in {"INSUFFICIENT", "CONFLICTED"}:
                        problems.append(
                            f"evidence_sufficiency: {atag} references '{cid}' "
                            f"whose evidence is {state} - no AC on "
                            "INSUFFICIENT/CONFLICTED evidence"
                        )
                    elif state == "PARTIAL" and not _nonempty(
                        assessment.get("established_portion")
                    ):
                        problems.append(
                            f"evidence_sufficiency: {atag} references PARTIAL "
                            f"coverage '{cid}' without a named established "
                            "portion - PARTIAL evidence must not be presented "
                            "as complete"
                        )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "EvidenceSufficiency: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["evidence_sufficiency"]
    q = len(block.get("question_assessments", []) or [])
    c = len(block.get("coverage_assessments", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"EvidenceSufficiency: {status} ({q} question + {c} coverage "
             "assessment(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Evidence Sufficiency gate for questions and coverage"
    )
    ap.add_argument("--manifest")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    print(summarize(manifest))
    return 0 if not validate(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
