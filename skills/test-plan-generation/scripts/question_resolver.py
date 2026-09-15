"""Question Resolver gate for Question-Based UAC reasoning (backward-compatible).

WHY THIS EXISTS
---------------
After the Question Planner emits material questions and the Research Router
drives the mandated research, the Question Resolver records a terminal
resolution per question.  The resolver is a coordinator/reasoning stage, not an
autonomous agent; the existing Writer and Reviewer keep their roles.  This gate
validates the resolver's manifest block, `question_resolutions`.

Resolution statuses: ANSWERED, PARTIALLY_ANSWERED, ACCEPTANCE_TBD,
INVESTIGATION_ONLY, NOT_APPLICABLE, DUPLICATE, CONFLICTED.

Every retained answer must keep: ``claim``, ``source_ids``,
``source_authority``, ``applicability``, ``limitations``, ``contradictions``.

Hard rules enforced (all generic):

- A question is not an AC, and an answer is not automatically an AC: resolution
  records cannot declare acceptance identity (`ac_id` / `promoted_to_ac`).
- Actual Result cannot establish Expected Result; a reported failure must not be
  reversed to invent desired behavior; a suspected root cause does not become
  acceptance behavior; an attachment observation does not establish desired
  behavior; historical Jira does not automatically establish current behavior.
  Structurally: none of ACTUAL_RESULT / SUSPECTED_ROOT_CAUSE /
  ATTACHMENT_OBSERVATION / HISTORICAL_JIRA / AI_INFERENCE may be the authority
  of an ANSWERED claim.
- NOT_FOUND is not negative proof: an ANSWERED resolution cannot stand on a
  research outcome of NOT_FOUND.
- Required research cannot be skipped: when the manifest also carries
  `question_research`, a question whose mandated research is PENDING or
  NOT_FOUND cannot resolve ANSWERED or PARTIALLY_ANSWERED.
- ACCEPTANCE_TBD only when different plausible answers materially change
  acceptance behavior/scope/configuration/applicability/compatibility/
  preservation: it requires at least two plausible answers and at least one of
  those material-impact areas.
- Root cause, diagnostics, and implementation mechanics are normally
  INVESTIGATION_ONLY: another status requires an explicit
  `acceptance_relevance` justification.

Backward-compatible: absent `question_resolutions` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

RESOLUTION_STATUSES = (
    "ANSWERED",
    "PARTIALLY_ANSWERED",
    "ACCEPTANCE_TBD",
    "INVESTIGATION_ONLY",
    "NOT_APPLICABLE",
    "DUPLICATE",
    "CONFLICTED",
)

ANSWER_AUTHORITIES = (
    "CURRENT_TICKET_REQUIREMENT",
    "ACCEPTED_UAC",
    "PRODUCT_DECISION",
    "OFFICIAL_DOCUMENTATION",
    "DITA_SPECIFICATION",
    "CURRENT_IMPLEMENTATION",
    "EXISTING_AUTOMATION",
    "HISTORICAL_JIRA",
    "ATTACHMENT_OBSERVATION",
    "ACTUAL_RESULT",
    "SUSPECTED_ROOT_CAUSE",
    "AI_INFERENCE",
    "HUMAN_PRODUCT",
)

# Authorities that can never establish an answered expectation on their own.
# ACTUAL_RESULT: an actual result cannot establish the expected result (and a
#   reported failure must not be reversed to invent desired behavior).
# SUSPECTED_ROOT_CAUSE: a suspected root cause does not become acceptance
#   behavior.
# ATTACHMENT_OBSERVATION: an attachment observation does not establish desired
#   behavior.
# HISTORICAL_JIRA: historical Jira does not automatically establish current
#   behavior.
# AI_INFERENCE: inference is not an authority.
NON_ESTABLISHING_AUTHORITIES = frozenset({
    "ACTUAL_RESULT",
    "SUSPECTED_ROOT_CAUSE",
    "ATTACHMENT_OBSERVATION",
    "HISTORICAL_JIRA",
    "AI_INFERENCE",
})

# The acceptance axes ACCEPTANCE_TBD must name: a different plausible answer
# must materially change at least one of these.
MATERIAL_IMPACT_AREAS = (
    "BEHAVIOR",
    "SCOPE",
    "CONFIGURATION",
    "APPLICABILITY",
    "COMPATIBILITY",
    "PRESERVATION",
)

# Root cause, diagnostics, and implementation mechanics are normally
# INVESTIGATION_ONLY.
INVESTIGATION_TOPICS = (
    "ROOT_CAUSE",
    "DIAGNOSTICS",
    "IMPLEMENTATION_MECHANICS",
)

# Research outcomes that can never ground an answered claim.
_NON_ANSWERING_RESEARCH_STATUSES = frozenset({"PENDING", "NOT_FOUND"})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("question_resolutions"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_answer(i, status, answer):
    problems = []
    tag = f"question_resolutions.items[{i}].answer"
    if answer is None:
        if status in {"ANSWERED", "PARTIALLY_ANSWERED", "CONFLICTED"}:
            problems.append(f"{tag}: {status} requires a retained answer")
        return problems
    if not isinstance(answer, dict):
        return [f"{tag}: answer must be an object"]
    if not _nonempty(answer.get("claim")):
        problems.append(f"{tag}: missing claim")
    source_ids = answer.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        problems.append(f"{tag}: source_ids must be a non-empty list")
    authority = answer.get("source_authority")
    if authority not in ANSWER_AUTHORITIES:
        problems.append(
            f"{tag}: source_authority '{authority}' must be one of "
            f"{', '.join(ANSWER_AUTHORITIES)}"
        )
    elif status == "ANSWERED" and authority in NON_ESTABLISHING_AUTHORITIES:
        problems.append(
            f"{tag}: {authority} cannot establish an ANSWERED expectation - "
            "observations, actual results, suspected root causes, historical "
            "tickets, and inference are not requirement authority"
        )
    if not _nonempty(answer.get("applicability")):
        problems.append(f"{tag}: missing applicability")
    for key in ("limitations", "contradictions"):
        if not isinstance(answer.get(key), list):
            problems.append(f"{tag}: {key} must be a list (empty allowed)")
    if status == "PARTIALLY_ANSWERED" and isinstance(answer.get("limitations"), list):
        if not answer["limitations"]:
            problems.append(
                f"{tag}: PARTIALLY_ANSWERED must record what remains unresolved "
                "in limitations"
            )
    if status == "CONFLICTED" and isinstance(answer.get("contradictions"), list):
        if not answer["contradictions"]:
            problems.append(
                f"{tag}: CONFLICTED must retain the competing claims in "
                "contradictions"
            )
    return problems


def _validate_item(i, item):
    problems = []
    tag = f"question_resolutions.items[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each resolution must be an object"]

    if not _nonempty(item.get("question_ref")):
        problems.append(f"{tag}: missing question_ref")
    status = item.get("status")
    if status not in RESOLUTION_STATUSES:
        problems.append(
            f"{tag}: status '{status}' must be one of "
            f"{', '.join(RESOLUTION_STATUSES)}"
        )
        return problems

    if item.get("ac_id") or item.get("promoted_to_ac"):
        problems.append(
            f"{tag}: an answer is not automatically an AC - resolution records "
            "cannot declare acceptance identity"
        )

    problems.extend(_validate_answer(i, status, item.get("answer")))

    if status == "ACCEPTANCE_TBD":
        impact = item.get("material_impact")
        if (
            not isinstance(impact, list)
            or not impact
            or any(area not in MATERIAL_IMPACT_AREAS for area in impact)
        ):
            problems.append(
                f"{tag}: ACCEPTANCE_TBD requires material_impact naming one or "
                f"more of {', '.join(MATERIAL_IMPACT_AREAS)} - it is allowed "
                "only when different plausible answers materially change "
                "acceptance behavior/scope/configuration/applicability/"
                "compatibility/preservation"
            )
        plausible = item.get("plausible_answers")
        if not isinstance(plausible, list) or len(plausible) < 2:
            problems.append(
                f"{tag}: ACCEPTANCE_TBD requires at least two plausible answers"
            )
    if status == "DUPLICATE":
        if not _nonempty(item.get("duplicate_of")):
            problems.append(
                f"{tag}: DUPLICATE requires duplicate_of pointing at the "
                "surviving question"
            )
        elif item.get("duplicate_of") == item.get("question_ref"):
            problems.append(f"{tag}: DUPLICATE cannot reference itself")
    if status == "NOT_APPLICABLE" and not _nonempty(item.get("reason")):
        problems.append(f"{tag}: NOT_APPLICABLE requires a reason")

    topic = item.get("investigation_topic")
    if topic is not None:
        if topic not in INVESTIGATION_TOPICS:
            problems.append(
                f"{tag}: investigation_topic '{topic}' must be one of "
                f"{', '.join(INVESTIGATION_TOPICS)}"
            )
        elif status not in {"INVESTIGATION_ONLY", "NOT_APPLICABLE"} and not (
            _nonempty(item.get("acceptance_relevance"))
        ):
            problems.append(
                f"{tag}: root cause, diagnostics, and implementation mechanics "
                "are normally INVESTIGATION_ONLY - another status requires an "
                "explicit acceptance_relevance justification"
            )

    outcome = item.get("research_outcome")
    if outcome == "NOT_FOUND" and status == "ANSWERED":
        problems.append(
            f"{tag}: NOT_FOUND is not negative proof - research that found no "
            "answer cannot ground an ANSWERED resolution"
        )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["question_resolutions"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["question_resolutions.items must be a list"]
    problems = []
    seen_refs = set()
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        ref = item.get("question_ref") if isinstance(item, dict) else None
        if ref:
            if ref in seen_refs:
                problems.append(
                    f"question_resolutions.items[{i}]: duplicate question_ref "
                    f"'{ref}'"
                )
            seen_refs.add(ref)

    # Chain integrity with the planner: every resolved question must have been
    # planned, and every applicable planned question must reach a terminal
    # resolution (never silently dropped).
    plan = manifest.get("question_plan")
    if isinstance(plan, dict):
        planned = []
        for source in (plan.get("items"), (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                planned.extend(row for row in source if isinstance(row, dict))
        planned_by_id = {row.get("question_id"): row for row in planned}
        for ref in sorted(seen_refs - set(planned_by_id)):
            problems.append(
                f"question_resolutions: '{ref}' was resolved but never planned"
            )
        for qid, row in sorted(planned_by_id.items()):
            if qid is None or row.get("applicability") == "NOT_APPLICABLE":
                continue
            if qid not in seen_refs:
                problems.append(
                    f"question_resolutions: planned material question '{qid}' has "
                    "no resolution - questions are never silently dropped"
                )

    # Chain integrity with the research router: required research cannot be
    # skipped, and NOT_FOUND is not negative proof.
    research = manifest.get("question_research")
    if isinstance(research, dict):
        research_by_ref = {
            row.get("question_ref"): row
            for row in research.get("items", [])
            if isinstance(row, dict)
        }
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            if status not in {"ANSWERED", "PARTIALLY_ANSWERED"}:
                continue
            route = research_by_ref.get(item.get("question_ref"))
            if route is None:
                continue
            research_status = route.get("research_status")
            requirement = route.get("research_requirement")
            if requirement != "NONE" and research_status in (
                _NON_ANSWERING_RESEARCH_STATUSES
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: required "
                    f"{requirement} research is {research_status} - required "
                    "research cannot be skipped, and NOT_FOUND is not negative "
                    "proof"
                )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "QuestionResolver: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["question_resolutions"].get("items", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"QuestionResolver: {status} ({n} resolution(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Question Resolver gate for Question-Based UAC reasoning"
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
