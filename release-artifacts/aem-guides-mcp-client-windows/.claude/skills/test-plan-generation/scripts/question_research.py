"""Mandatory research routing for question-based coverage (backward-compatible).

WHY THIS EXISTS
---------------
Material questions can be identified from the current ticket and configuration,
but Coverage and the Writer must not answer documentation-dependent questions
from inference.  This gate validates the optional ``question_research`` manifest
block, which keeps the whole chain traceable:

    question -> research requirement -> research request -> research evidence
             -> resolution -> coverage decision

Discipline enforced (all generic, no domain/construct rules):

- every material question carries a ``research_requirement``
  (NONE | DOCUMENTATION | IMPLEMENTATION | HISTORICAL |
  DOCUMENTATION_AND_IMPLEMENTATION | MULTI_SOURCE)
  and a ``research_status``
  (NOT_REQUIRED | PENDING | ANSWER_FOUND | PARTIAL | NOT_FOUND |
  SOURCE_UNAVAILABLE | CONFLICTED | NOT_APPLICABLE);
- ``NONE`` means the current ticket authority (for example an explicit Human
  Accepted AC) is sufficient on its own and terminates as ``NOT_REQUIRED``
  without issuing research requests;
- hard gate: a material question whose requirement is not ``NONE`` and whose
  status is ``PENDING`` was classified but never researched - the Reviewer
  rejects the plan, and Coverage must not finalize it;
- ``NOT_FOUND`` means the mandated research executed and found no answer; it
  never means the opposite behavior is true, so it cannot ground an
  investigated-and-rejected or otherwise finalizing disposition;
- ``PARTIAL`` / ``SOURCE_UNAVAILABLE`` / ``CONFLICTED`` are incomplete: the
  question stays an open question.

Backward-compatible: absent ``question_research`` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

RESEARCH_REQUIREMENTS = (
    "NONE",
    "DOCUMENTATION",
    "IMPLEMENTATION",
    "HISTORICAL",
    "DOCUMENTATION_AND_IMPLEMENTATION",
    "MULTI_SOURCE",
)

RESEARCH_STATUSES = (
    "NOT_REQUIRED",
    "PENDING",
    "ANSWER_FOUND",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "CONFLICTED",
    "NOT_APPLICABLE",
)

# Dispositions that keep a question visibly open instead of finalizing it.
OPEN_DISPOSITIONS = frozenset({
    "OPEN_QUESTION",
    "PRODUCT_SCOPE_QUESTION",
    "ENGINEERING_DESIGN_DECISION",
    "PRODUCT_DECISION",
    "NEEDS_CURRENT_VERIFICATION",
})

# Dispositions that assert the opposite behavior on the basis of research.
REJECTING_DISPOSITIONS = frozenset({
    "INVESTIGATED_AND_REJECTED",
    "REJECTED",
    "CONFIRMED_NEGATED",
})

# Statuses that leave a material question without a terminal answer.
INCOMPLETE_STATUSES = frozenset({
    "PENDING",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "CONFLICTED",
})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("question_research"), dict)


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_item(i, item):
    problems = []
    tag = f"question_research.items[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each item must be an object"]

    if not _nonempty(item.get("question_ref")):
        problems.append(f"{tag}: missing question_ref")

    requirement = item.get("research_requirement")
    if requirement not in RESEARCH_REQUIREMENTS:
        problems.append(
            f"{tag}: research_requirement '{requirement}' must be one of "
            f"{', '.join(RESEARCH_REQUIREMENTS)}"
        )
    status = item.get("research_status")
    if status not in RESEARCH_STATUSES:
        problems.append(
            f"{tag}: research_status '{status}' must be one of "
            f"{', '.join(RESEARCH_STATUSES)}"
        )
    if requirement not in RESEARCH_REQUIREMENTS or status not in RESEARCH_STATUSES:
        return problems

    material = item.get("material", True)
    requests = item.get("research_requests") or []
    evidence = item.get("research_evidence_ids") or []
    disposition = (item.get("coverage_disposition") or "").upper() or None

    if requirement == "NONE":
        if status != "NOT_REQUIRED":
            problems.append(
                f"{tag}: a NONE research requirement must terminate as NOT_REQUIRED"
            )
        if requests or evidence:
            problems.append(
                f"{tag}: a NONE research requirement cannot issue research requests"
            )
    if status == "NOT_REQUIRED" and requirement != "NONE":
        problems.append(
            f"{tag}: NOT_REQUIRED research status requires a NONE research requirement"
        )
    if status == "NOT_APPLICABLE":
        if material:
            problems.append(
                f"{tag}: NOT_APPLICABLE research routing applies only to "
                "non-material questions"
            )
        if requests or evidence:
            problems.append(
                f"{tag}: NOT_APPLICABLE research cannot cite requests or evidence"
            )
    if status == "PENDING" and (requests or evidence):
        problems.append(
            f"{tag}: PENDING research has not executed and cannot cite requests "
            "or evidence"
        )
    if status == "ANSWER_FOUND" and not requests:
        problems.append(
            f"{tag}: ANSWER_FOUND requires the research request that found the "
            "answer"
        )

    if material and requirement != "NONE":
        if status == "PENDING":
            problems.append(
                f"{tag}: mandatory {requirement} research is still PENDING for a "
                "material question - the Reviewer treats skipped mandatory "
                "research as a failure"
            )
        elif status != "NOT_APPLICABLE" and not requests:
            problems.append(
                f"{tag}: mandatory research for a material question has no "
                "research request"
            )
        if status in INCOMPLETE_STATUSES and disposition and (
            disposition not in OPEN_DISPOSITIONS
        ):
            problems.append(
                f"{tag}: coverage cannot finalize a material question whose "
                f"mandatory {requirement} research is {status} - disposition must "
                f"be one of {', '.join(sorted(OPEN_DISPOSITIONS))}"
            )
        if status == "NOT_FOUND" and (
            disposition in REJECTING_DISPOSITIONS or item.get("asserts_opposite")
        ):
            problems.append(
                f"{tag}: NOT_FOUND means the mandated research found no answer; "
                "absence of evidence never means the opposite behavior is true"
            )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["question_research"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["question_research.items must be a list"]
    problems = []
    seen_refs = set()
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        ref = item.get("question_ref") if isinstance(item, dict) else None
        if ref:
            if ref in seen_refs:
                problems.append(
                    f"question_research.items[{i}]: duplicate question_ref '{ref}'"
                )
            seen_refs.add(ref)
    # Cross-check against the missing-question block when both are declared:
    # every material missing question must carry a research routing entry.
    missing = manifest.get("missing_questions")
    questions = []
    if isinstance(missing, dict):
        questions = missing.get("questions", [])
    elif isinstance(missing, list):
        questions = missing
    if isinstance(questions, list):
        for j, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            if not (question.get("blocking") or question.get("material")):
                continue
            qid = question.get("question_id") or question.get("question_ref")
            if qid and qid not in seen_refs:
                problems.append(
                    f"missing_questions[{j}]: material question "
                    f"'{qid}' has no question_research routing entry"
                )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "QuestionResearchRouting: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["question_research"].get("items", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"QuestionResearchRouting: {status} ({n} routed question(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Mandatory research routing gate for question-based coverage"
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
