"""Dedicated UAC Coverage Reasoner gate (backward-compatible).

WHY THIS EXISTS
---------------
Coverage is decided by a dedicated Coverage Reasoner on top of resolved
Question-Based UAC evidence - never by the Writer.  The reasoner consumes
authoritative requirements, resolved questions, research findings,
applicability, conflicts, attachment observations, existing behavior, new
behavior, and preservation requirements, and emits one coverage decision per
candidate behavior in the manifest `coverage_decisions` block.  The Writer
receives only accepted coverage decisions; the Reviewer verifies all P0
coverage is represented and that P1 has not expanded scope.

Every decision carries: ``coverage_id``, ``behavior``, ``question_ids``,
``evidence_ids``, ``priority``, ``coverage_class``, ``positive_or_negative``,
``surface``, ``state``, ``configuration``, ``applicability``, ``reason``,
``acceptance_impact``, and ``dimensions_considered``.

Rules enforced (all generic):

- priority: ``P0`` proves the primary ticket contract and prevents the direct
  customer regression (class ACCEPTANCE); ``P1`` is materially related
  regression behavior (class QE_REGRESSION); ``SUPPORTING`` covers
  regression/investigation support; ``EXCLUDED`` records an explicit exclusion
  with a reason and never reaches the Writer.
- coverage_class: ACCEPTANCE / QE_REGRESSION / INVESTIGATION.
- Do not promote generic test ideas: every decision traces to at least one
  resolved question or evidence id, and a decision may stand only on questions
  whose resolution and research permit it (an unresolved, TBD, conflicted, or
  investigation-only question cannot ground acceptance coverage; NOT_FOUND or
  incomplete required research cannot ground ACCEPTANCE).
- Reason about the dimension axes when applicable
  (``dimensions_considered``); the field must be present (an empty list
  asserts none apply).
- Writer handoff integrity: when ``writer_handoff`` is declared it contains
  only accepted (non-EXCLUDED) decisions and every P0 decision.

Backward-compatible: absent `coverage_decisions` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

COVERAGE_PRIORITIES = ("P0", "P1", "SUPPORTING", "EXCLUDED")

COVERAGE_CLASSES = ("ACCEPTANCE", "QE_REGRESSION", "INVESTIGATION")

COVERAGE_POLARITY = ("POSITIVE", "NEGATIVE")

# Dimension axes the reasoner considers when applicable.
COVERAGE_AXES = (
    "SINGLE_BULK",
    "REFRESH_REVISIT",
    "STATE_TRANSITIONS",
    "NEGATIVE_CONTRACTS",
    "ALTERNATE_UI_PATHS",
    "CONFIGURATION_BRANCHES",
    "NEW_OLD_EDITOR",
    "AUTHOR_SOURCE",
    "COLLECTIONS_EXPLORER_MAP_CONSOLE",
    "CLOUD_65",
    "NATIVE_PDF_DITA_OT",
    "PREPROCESSING_ON_OFF",
    "SCALE",
    "PRESERVATION",
)

# The only coverage classes a resolver status may ground.  ACCEPTANCE_TBD
# keeps acceptance undecided, so it can ground only investigation coverage;
# NOT_APPLICABLE / DUPLICATE / CONFLICTED settle nothing and ground nothing.
_RESOLUTION_GROUNDING = {
    "ANSWERED": {"ACCEPTANCE", "QE_REGRESSION", "INVESTIGATION"},
    "PARTIALLY_ANSWERED": {"QE_REGRESSION", "INVESTIGATION"},
    "ACCEPTANCE_TBD": {"INVESTIGATION"},
    "INVESTIGATION_ONLY": {"INVESTIGATION"},
}

# Research statuses that can never ground an ACCEPTANCE decision.
_NON_ACCEPTANCE_RESEARCH_STATUSES = frozenset({
    "PENDING",
    "PARTIAL",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "CONFLICTED",
})

_PRIORITY_CLASSES = {
    "P0": {"ACCEPTANCE"},
    "P1": {"QE_REGRESSION"},
    "SUPPORTING": {"QE_REGRESSION", "INVESTIGATION"},
    "EXCLUDED": set(COVERAGE_CLASSES),
}


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("coverage_decisions"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_item(i, item):
    problems = []
    tag = f"coverage_decisions.items[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each coverage decision must be an object"]

    for field in ("coverage_id", "behavior", "applicability", "reason",
                  "acceptance_impact"):
        if not _nonempty(item.get(field)):
            problems.append(f"{tag}: missing {field}")

    priority = item.get("priority")
    if priority not in COVERAGE_PRIORITIES:
        problems.append(
            f"{tag}: priority '{priority}' must be one of "
            f"{', '.join(COVERAGE_PRIORITIES)}"
        )
    coverage_class = item.get("coverage_class")
    if coverage_class not in COVERAGE_CLASSES:
        problems.append(
            f"{tag}: coverage_class '{coverage_class}' must be one of "
            f"{', '.join(COVERAGE_CLASSES)}"
        )
    elif priority in _PRIORITY_CLASSES and (
        coverage_class not in _PRIORITY_CLASSES[priority]
    ):
        expectation = {
            "P0": "P0 proves the primary ticket contract, so its class is "
                  "ACCEPTANCE",
            "P1": "P1 is materially related regression behavior, so its class "
                  "is QE_REGRESSION",
            "SUPPORTING": "SUPPORTING covers regression/investigation support",
        }[priority]
        problems.append(f"{tag}: {expectation} (got {coverage_class})")

    polarity = item.get("positive_or_negative")
    if polarity not in COVERAGE_POLARITY:
        problems.append(
            f"{tag}: positive_or_negative '{polarity}' must be POSITIVE or "
            "NEGATIVE"
        )

    question_ids = item.get("question_ids")
    evidence_ids = item.get("evidence_ids")
    if not isinstance(question_ids, list):
        problems.append(f"{tag}: question_ids must be a list")
        question_ids = []
    if not isinstance(evidence_ids, list):
        problems.append(f"{tag}: evidence_ids must be a list")
        evidence_ids = []
    if not question_ids and not evidence_ids:
        problems.append(
            f"{tag}: generic test ideas are not promoted - a coverage decision "
            "traces to at least one resolved question or evidence id"
        )

    for field in ("surface", "state", "configuration"):
        if field not in item:
            problems.append(
                f"{tag}: missing {field} (declare it, empty when not applicable)"
            )

    axes = item.get("dimensions_considered")
    if not isinstance(axes, list):
        problems.append(
            f"{tag}: dimensions_considered must be present as a list (empty "
            "asserts no axis applies)"
        )
    else:
        unknown = [axis for axis in axes if axis not in COVERAGE_AXES]
        if unknown:
            problems.append(
                f"{tag}: unknown dimensions_considered axes "
                f"{unknown} - use {', '.join(COVERAGE_AXES)}"
            )
    return problems


def _chain_problems(manifest, items):
    """Cross-check coverage decisions against the reasoning chain blocks."""

    problems = []
    question_ids = {
        qid
        for i, item in enumerate(items)
        if isinstance(item, dict)
        for qid in (item.get("question_ids") or [])
    }
    if not question_ids:
        return problems

    resolutions_by_ref = {}
    resolutions = manifest.get("question_resolutions")
    if isinstance(resolutions, dict):
        for row in resolutions.get("items", []):
            if isinstance(row, dict):
                resolutions_by_ref[row.get("question_ref")] = row

    research_by_ref = {}
    research = manifest.get("question_research")
    if isinstance(research, dict):
        for row in research.get("items", []):
            if isinstance(row, dict):
                research_by_ref[row.get("question_ref")] = row

    plan = manifest.get("question_plan")
    planned_ids = set()
    if isinstance(plan, dict):
        for source in (plan.get("items"),
                       (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                planned_ids.update(
                    row.get("question_id") for row in source
                    if isinstance(row, dict)
                )

    behaviors_by_ref = {}
    classification = manifest.get("behavior_classification")
    if isinstance(classification, dict):
        for row in classification.get("items", []):
            if isinstance(row, dict):
                behaviors_by_ref[row.get("target_ref")] = row

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        tag = f"coverage_decisions.items[{i}]"
        coverage_class = item.get("coverage_class")
        for qid in item.get("question_ids") or []:
            resolution = resolutions_by_ref.get(qid)
            if resolution is not None:
                status = resolution.get("status")
                allowed = _RESOLUTION_GROUNDING.get(status, set())
                if coverage_class in COVERAGE_CLASSES and (
                    coverage_class not in allowed
                ):
                    problems.append(
                        f"{tag}: question '{qid}' resolved {status} and cannot "
                        f"ground {coverage_class} coverage"
                    )
            elif planned_ids and qid in planned_ids:
                problems.append(
                    f"{tag}: question '{qid}' is planned but unresolved - "
                    "coverage cannot stand on an unresolved question"
                )
            elif planned_ids:
                problems.append(
                    f"{tag}: question '{qid}' was never planned"
                )
            route = research_by_ref.get(qid)
            if (
                route is not None
                and coverage_class == "ACCEPTANCE"
                and route.get("research_requirement") != "NONE"
                and route.get("research_status") in (
                    _NON_ACCEPTANCE_RESEARCH_STATUSES
                )
            ):
                problems.append(
                    f"{tag}: question '{qid}' has {route.get('research_status')} "
                    "required research - required research cannot be skipped, "
                    "and NOT_FOUND is not negative proof, so it cannot ground "
                    "an ACCEPTANCE decision"
                )
        behavior_ref = item.get("behavior_ref")
        if behavior_ref and behavior_ref in behaviors_by_ref:
            behavior_class = behaviors_by_ref[behavior_ref].get("behavior_class")
            if (
                behavior_class == "EXISTING_CONFIRMED"
                and coverage_class == "ACCEPTANCE"
            ):
                problems.append(
                    f"{tag}: behavior '{behavior_ref}' is EXISTING_CONFIRMED - "
                    "documented-today behavior must not be repackaged as new "
                    "acceptance coverage"
                )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["coverage_decisions"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["coverage_decisions.items must be a list"]
    problems = []
    seen_ids = set()
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        cid = item.get("coverage_id") if isinstance(item, dict) else None
        if cid:
            if cid in seen_ids:
                problems.append(
                    f"coverage_decisions.items[{i}]: duplicate coverage_id "
                    f"'{cid}'"
                )
            seen_ids.add(cid)

    problems.extend(_chain_problems(manifest, items))

    # The Writer receives only accepted coverage decisions; the Reviewer
    # verifies every P0 decision is represented in that handoff.
    handoff = block.get("writer_handoff")
    if handoff is not None:
        if not isinstance(handoff, list):
            problems.append("coverage_decisions.writer_handoff must be a list")
            handoff = []
        by_id = {
            item.get("coverage_id"): item
            for item in items
            if isinstance(item, dict)
        }
        for cid in handoff:
            target = by_id.get(cid)
            if target is None:
                problems.append(
                    f"coverage_decisions.writer_handoff: unknown coverage_id "
                    f"'{cid}'"
                )
            elif target.get("priority") == "EXCLUDED":
                problems.append(
                    f"coverage_decisions.writer_handoff: EXCLUDED decision "
                    f"'{cid}' never reaches the Writer"
                )
        for cid, item in sorted(by_id.items()):
            if item.get("priority") == "P0" and cid not in handoff:
                problems.append(
                    f"coverage_decisions.writer_handoff: P0 decision '{cid}' is "
                    "not represented for the Writer"
                )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "CoverageReasoner: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["coverage_decisions"].get("items", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"CoverageReasoner: {status} ({n} coverage decision(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Dedicated UAC Coverage Reasoner gate"
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
