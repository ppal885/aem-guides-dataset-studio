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

# Rule 11: PARTIAL research cannot produce a fully confirmed answer.  It can
# still ground a PARTIALLY_ANSWERED resolution for the established portion.
_ANSWERED_BLOCKING_RESEARCH_STATUSES = frozenset({
    "PENDING",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "CONFLICTED",
})

# Research requirements that route through the existing R1 Doc Researcher.
_DOC_DEPENDENT_REQUIREMENTS = frozenset({
    "DOCUMENTATION",
    "DOCUMENTATION_AND_IMPLEMENTATION",
    "MULTI_SOURCE",
    "DOC_RESEARCH_REQUIRED",
})


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


def _normalized(item):
    """Normalize the two accepted resolution shapes.

    Canonical Q1 shape: ``question_id`` + ``disposition`` with a flat
    ``answer`` claim and top-level ``source_ids`` / ``source_authority`` /
    ``applicability`` / ``limitations`` / ``contradictions``.  The earlier
    nested shape (``question_ref`` + ``status`` with an ``answer`` object) is
    accepted unchanged.
    """

    if not isinstance(item, dict):
        return None, None, None
    ref = item.get("question_ref") or item.get("question_id")
    status = item.get("status") or item.get("disposition")
    answer = item.get("answer")
    if isinstance(answer, str):
        answer = {
            "claim": answer,
            "source_ids": item.get("source_ids"),
            "source_authority": item.get("source_authority"),
            "applicability": item.get("applicability"),
            "limitations": item.get("limitations", []),
            "contradictions": item.get("contradictions", []),
        }
    return ref, status, answer


def _validate_item(i, item):
    problems = []
    tag = f"question_resolutions.items[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each resolution must be an object"]

    ref, status, answer = _normalized(item)
    if not _nonempty(ref):
        problems.append(f"{tag}: missing question_id (question_ref)")
    if status not in RESOLUTION_STATUSES:
        problems.append(
            f"{tag}: disposition '{status}' must be one of "
            f"{', '.join(RESOLUTION_STATUSES)}"
        )
        return problems

    # Externalized semantic decision: every material decision records its
    # reason so downstream stages consume the artifact instead of
    # reconstructing the answer from raw ticket text.
    if not _nonempty(item.get("decision_reason")):
        problems.append(
            f"{tag}: missing decision_reason - every material semantic "
            "decision is recorded with its reason"
        )

    research_ids = item.get("research_ids")
    if research_ids is not None and not isinstance(research_ids, list):
        problems.append(f"{tag}: research_ids must be a list when present")

    if item.get("ac_id") or item.get("promoted_to_ac"):
        problems.append(
            f"{tag}: an answer is not automatically an AC - resolution records "
            "cannot declare acceptance identity"
        )

    problems.extend(_validate_answer(i, status, answer))

    # An equal-authority conflict remains unresolved: ANSWERED with retained
    # contradictions requires the higher-authority basis that settled it;
    # otherwise the question stays CONFLICTED.
    contradictions = (answer or {}).get("contradictions")
    if status == "ANSWERED" and contradictions and not _nonempty(
        item.get("conflict_resolution")
        or (answer or {}).get("conflict_resolution")
    ):
        problems.append(
            f"{tag}: an equal-authority conflict remains unresolved - stay "
            "CONFLICTED or record the higher-authority basis in "
            "conflict_resolution"
        )

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
        elif item.get("duplicate_of") == ref:
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
        elif status == "ACCEPTANCE_TBD":
            problems.append(
                f"{tag}: root-cause/diagnostic/mechanics uncertainty must not "
                "become ACCEPTANCE_TBD merely because it is important to "
                "engineering - it stays INVESTIGATION_ONLY"
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
    normalized_status = {}
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        ref, status, _answer = _normalized(item)
        if ref:
            if ref in seen_refs:
                problems.append(
                    f"question_resolutions.items[{i}]: duplicate question_ref "
                    f"'{ref}'"
                )
            seen_refs.add(ref)
            normalized_status[ref] = status

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
    # skipped, PARTIAL research cannot fully confirm, and NOT_FOUND is not
    # negative proof.
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
            ref, status, _answer = _normalized(item)
            route = research_by_ref.get(ref)
            if route is None:
                continue
            research_status = route.get("research_status")
            requirement = route.get("research_requirement")
            if requirement == "NONE":
                continue
            if research_status == "CONFLICTED" and status != "CONFLICTED":
                problems.append(
                    f"question_resolutions.items[{i}]: CONFLICTED research "
                    "keeps the question CONFLICTED until the conflict is "
                    "settled"
                )
            elif status == "ANSWERED" and research_status in (
                _ANSWERED_BLOCKING_RESEARCH_STATUSES
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: required "
                    f"{requirement} research is {research_status} - required "
                    "research cannot be skipped, PARTIAL research cannot "
                    "produce a fully confirmed answer, and NOT_FOUND is not "
                    "negative proof"
                )
            elif status == "PARTIALLY_ANSWERED" and research_status in (
                _NON_ANSWERING_RESEARCH_STATUSES
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: required "
                    f"{requirement} research is {research_status} - required "
                    "research cannot be skipped, and NOT_FOUND is not negative "
                    "proof"
                )

    # R1 reuse: documentation-requiring questions depend on the existing Doc
    # Researcher routing contract.  R1-required research cannot be skipped.
    doc_research = manifest.get("doc_research")
    doc_dependent: set[str] = set()
    research_block = manifest.get("question_research")
    if isinstance(research_block, dict):
        for row in research_block.get("items", []):
            if not isinstance(row, dict):
                continue
            if row.get("research_requirement") in (
                _DOC_DEPENDENT_REQUIREMENTS
            ) and row.get("material", True):
                doc_dependent.add(row.get("question_ref"))
    plan_block = manifest.get("question_plan")
    if isinstance(plan_block, dict):
        for source in (plan_block.get("items"),
                       (plan_block.get("overflow") or {}).get("items")):
            if not isinstance(source, list):
                continue
            for row in source:
                if isinstance(row, dict) and row.get(
                    "research_requirement"
                ) in _DOC_DEPENDENT_REQUIREMENTS:
                    doc_dependent.add(row.get("question_id"))
    doc_dependent.discard(None)
    if isinstance(doc_research, dict):
        routing = doc_research.get("routing") or {}
        routing_state = routing.get("state")
        if routing_state == "RESEARCH_NOT_REQUIRED" and doc_dependent:
            problems.append(
                "question_resolutions: documentation-requiring material "
                f"questions {sorted(doc_dependent)} exist, but doc research was "
                "routed RESEARCH_NOT_REQUIRED - R1-required research cannot be "
                "skipped"
            )
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ref, status, answer = _normalized(item)
            if ref not in doc_dependent:
                continue
            if routing_state == "DOC_RESEARCH_REQUIRED" and status in {
                "ANSWERED",
                "PARTIALLY_ANSWERED",
            }:
                problems.append(
                    f"question_resolutions.items[{i}]: R1-required doc research "
                    "has no terminal result - Coverage/Writer must not proceed, "
                    "so the question cannot resolve ANSWERED/PARTIALLY_ANSWERED"
                )
            if routing_state == "DOC_RESEARCH_UNAVAILABLE" and (
                status == "ANSWERED"
                and (answer or {}).get("source_authority")
                == "OFFICIAL_DOCUMENTATION"
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: doc research was "
                    "UNAVAILABLE - a documentation answer cannot be claimed"
                )
            if routing_state == "DOC_RESEARCH_CONFLICTED" and status == (
                "ANSWERED"
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: doc research is "
                    "CONFLICTED - the question stays CONFLICTED until the "
                    "conflict is settled"
                )

    # Research binding: a resolution may cite only admitted research that
    # actually researched this question - stale or wrong-bound research cannot
    # answer another question, and documentation is never cited without
    # admitted research.
    if isinstance(doc_research, dict):
        results_by_id = {
            row.get("research_id"): row
            for row in doc_research.get("results", [])
            if isinstance(row, dict)
        }
        admitted = doc_research.get("admitted_research_ids")
        admitted_ids = (
            set(admitted) if isinstance(admitted, list) else set(results_by_id)
        )
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ref, status, answer = _normalized(item)
            research_ids = item.get("research_ids") or []
            for rid in research_ids:
                result = results_by_id.get(rid)
                if result is None:
                    problems.append(
                        f"question_resolutions.items[{i}]: research '{rid}' is "
                        "not a Doc Researcher result - stale research cannot "
                        "answer a question"
                    )
                    continue
                if rid not in admitted_ids:
                    problems.append(
                        f"question_resolutions.items[{i}]: research '{rid}' "
                        "was never admitted to the reasoning path"
                    )
                bound = result.get("question_refs")
                if isinstance(bound, list) and bound and ref not in bound:
                    problems.append(
                        f"question_resolutions.items[{i}]: research '{rid}' is "
                        f"bound to {sorted(bound)} - wrong-bound research "
                        "cannot answer another question"
                    )
            if (
                status == "ANSWERED"
                and (answer or {}).get("source_authority")
                == "OFFICIAL_DOCUMENTATION"
                and ref in doc_dependent
                and not research_ids
            ):
                problems.append(
                    f"question_resolutions.items[{i}]: a documentation answer "
                    "must cite the admitted research_ids that produced it"
                )

    # Duplicate lineage: a DUPLICATE preserves its triggering evidence on the
    # surviving question.
    if isinstance(plan, dict):
        planned = []
        for source in (plan.get("items"), (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                planned.extend(row for row in source if isinstance(row, dict))
        planned_by_id = {row.get("question_id"): row for row in planned}
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ref, status, _answer = _normalized(item)
            if status != "DUPLICATE":
                continue
            surviving_ref = item.get("duplicate_of")
            duplicate = planned_by_id.get(ref)
            surviving = planned_by_id.get(surviving_ref)
            if duplicate is None or surviving is None:
                continue
            duplicate_evidence = set(
                duplicate.get("triggering_evidence_ids") or []
            )
            surviving_evidence = set(
                surviving.get("triggering_evidence_ids") or []
            )
            if not duplicate_evidence.issubset(surviving_evidence):
                problems.append(
                    f"question_resolutions.items[{i}]: DUPLICATE must preserve "
                    "all triggering evidence IDs on the surviving question - "
                    f"{sorted(duplicate_evidence - surviving_evidence)} lost"
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
