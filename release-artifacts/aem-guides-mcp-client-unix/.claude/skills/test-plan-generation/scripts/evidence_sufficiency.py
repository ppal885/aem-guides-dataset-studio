"""Evidence Sufficiency gate per material question and coverage decision.

WHY THIS EXISTS
---------------
A resolved question or a coverage decision is only as strong as the evidence
under it.  This gate validates the manifest `evidence_sufficiency` block:
one assessment per material question and per coverage decision, so the Writer
never receives unsupported coverage as confirmed behavior and the Reviewer can
verify sufficiency lineage.

States: SUFFICIENT, PARTIAL, INSUFFICIENT, CONFLICTED.

Every assessment evaluates the eight dimensions: AUTHORITY, EXPECTED_BEHAVIOR,
APPLICABILITY, MATERIAL_CONDITIONS, NEGATIVE_BEHAVIOR, RESEARCH_COMPLETION,
SOURCE_CURRENTNESS, CONTRADICTIONS.

Rules enforced (all generic):

- One authoritative current-ticket AC may be SUFFICIENT; volume alone is not -
  a SUFFICIENT assessment must rest on an establishing authority.
- A question requiring research cannot be SUFFICIENT while that research is
  PENDING, NOT_FOUND, or SOURCE_UNAVAILABLE; PARTIAL research caps the
  assessment at PARTIAL; CONFLICTED research forces CONFLICTED.
- PARTIAL answers may support only the established portion - PARTIAL requires
  the established portion to be named.
- INSUFFICIENT answers cannot generate Acceptance Coverage; CONFLICTED
  questions cannot silently generate an AC.
- Coverage sufficiency is computed from the underlying questions/evidence: any
  underlying CONFLICTED forces CONFLICTED; any underlying INSUFFICIENT or
  PARTIAL caps the coverage below SUFFICIENT; every underlying question must
  itself be assessed.
- P0 ACCEPTANCE coverage requires SUFFICIENT evidence unless explicitly
  represented as ACCEPTANCE_TBD.
- A cross-product coverage decision is not SUFFICIENT merely because each
  control exists: it needs evidence that actually covers the combination.

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

# Research statuses that cap or force the question-level assessment.
_NON_SUFFICIENT_RESEARCH = frozenset({
    "PENDING",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("evidence_sufficiency"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


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
            if not isinstance(row, dict) or row.get("question_ref") not in evidence:
                continue
            answer = row.get("answer")
            if isinstance(answer, dict):
                evidence[row["question_ref"]].update(answer.get("source_ids") or [])
    return evidence


def _validate_question_assessment(i, item, chain):
    problems = []
    tag = f"evidence_sufficiency.question_assessments[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each assessment must be an object"]

    ref = item.get("question_ref")
    if not _nonempty(ref):
        problems.append(f"{tag}: missing question_ref")
    sufficiency = item.get("sufficiency")
    if sufficiency not in SUFFICIENCY_STATES:
        problems.append(
            f"{tag}: sufficiency '{sufficiency}' must be one of "
            f"{', '.join(SUFFICIENCY_STATES)}"
        )
        return problems
    if not _nonempty(item.get("reason")):
        problems.append(f"{tag}: missing reason")
    problems.extend(_validate_dimensions(tag, item.get("dimensions")))

    if sufficiency == "PARTIAL" and not _nonempty(item.get("established_portion")):
        problems.append(
            f"{tag}: PARTIAL answers may support only the established portion - "
            "name it in established_portion"
        )
    if sufficiency == "CONFLICTED" and not item.get("contradictions"):
        problems.append(
            f"{tag}: CONFLICTED must retain the competing claims in contradictions"
        )

    if chain["planned_ids"] is not None and ref and ref not in chain["planned_ids"]:
        problems.append(f"{tag}: assessed question '{ref}' was never planned")

    route = chain["research_by_ref"].get(ref)
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
        if research_status == "PARTIAL" and sufficiency == "SUFFICIENT":
            problems.append(
                f"{tag}: PARTIAL research caps the assessment at PARTIAL"
            )

    resolutions_by_ref = chain["resolutions_by_ref"] or {}
    resolution = resolutions_by_ref.get(ref)
    if resolution is not None:
        if resolution.get("status") == "CONFLICTED" and sufficiency != "CONFLICTED":
            problems.append(
                f"{tag}: a CONFLICTED resolution forces a CONFLICTED assessment"
            )
        if sufficiency == "SUFFICIENT" and resolution.get("status") == "ANSWERED":
            answer = resolution.get("answer") or {}
            authority = answer.get("source_authority")
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
    return problems


def _validate_coverage_assessment(i, item, chain):
    problems = []
    tag = f"evidence_sufficiency.coverage_assessments[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each assessment must be an object"]

    ref = item.get("coverage_ref")
    if not _nonempty(ref):
        problems.append(f"{tag}: missing coverage_ref")
    sufficiency = item.get("sufficiency")
    if sufficiency not in SUFFICIENCY_STATES:
        problems.append(
            f"{tag}: sufficiency '{sufficiency}' must be one of "
            f"{', '.join(SUFFICIENCY_STATES)}"
        )
        return problems
    if not _nonempty(item.get("reason")):
        problems.append(f"{tag}: missing reason")

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
            and priority == "P0"
            and sufficiency != "SUFFICIENT"
            and not item.get("represented_as_acceptance_tbd")
        ):
            problems.append(
                f"{tag}: P0 Acceptance Coverage requires SUFFICIENT evidence "
                "unless explicitly represented_as_acceptance_tbd"
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
                resolutions_by_ref[row.get("question_ref")] = row
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
        if isinstance(row, dict) and row.get("question_ref"):
            question_sufficiency[row["question_ref"]] = row.get("sufficiency")

    def question_evidence(question_refs):
        ids = _question_evidence_ids(manifest, question_refs)
        combined = set()
        for ref in question_refs:
            combined |= ids.get(ref, set())
        return combined

    chain = {
        "planned_ids": planned_ids,
        "research_by_ref": research_by_ref,
        "resolutions_by_ref": resolutions_by_ref,
        "coverage_by_id": coverage_by_id,
        "question_sufficiency": question_sufficiency,
        "assessments_declared": bool(question_assessments),
        "question_evidence": question_evidence,
    }

    problems = []
    seen_questions = set()
    for i, item in enumerate(question_assessments):
        problems.extend(_validate_question_assessment(i, item, chain))
        ref = item.get("question_ref") if isinstance(item, dict) else None
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
        resolutions_map = chain["resolutions_by_ref"] or {}
        for row in plan.get("items", []):
            if not isinstance(row, dict):
                continue
            if row.get("applicability") == "NOT_APPLICABLE":
                continue
            qid = row.get("question_id")
            resolution = resolutions_map.get(qid)
            if resolution is not None and resolution.get("status") in {
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
                state = assessment.get("sufficiency")
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
                        "is PARTIAL without a named established portion"
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
