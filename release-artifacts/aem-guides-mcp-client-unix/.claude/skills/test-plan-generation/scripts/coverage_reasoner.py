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
``evidence_ids``, ``research_ids``, ``priority``, ``coverage_class``,
``contract_type`` (POSITIVE / NEGATIVE / PRESERVATION), ``surface``,
``state_or_transition``, ``configuration``, ``applicability``, ``variants``,
``reason``, ``acceptance_impact``, and ``dimensions_considered``.

Rules enforced (all generic):

- priority: ``P0`` proves the primary ticket contract and prevents the direct
  customer regression (class ACCEPTANCE); ``P1`` is materially related
  regression behavior (class QE_REGRESSION); ``SUPPORTING`` covers
  regression/investigation support; ``EXCLUDED`` records an explicit exclusion
  with a reason and never reaches the Writer.
- coverage_class: ACCEPTANCE / QE_REGRESSION / INVESTIGATION.  INVESTIGATION
  never becomes an AC; QE_REGRESSION never silently becomes Acceptance.
- Do not promote generic test ideas: every decision traces to at least one
  resolved question or evidence id, and a decision may stand only on questions
  whose resolution and research permit it (an unresolved, TBD, conflicted, or
  investigation-only question cannot ground acceptance coverage; NOT_FOUND or
  incomplete required research cannot ground ACCEPTANCE; a DUPLICATE question
  contributes linkage through its surviving question, never duplicate
  coverage).
- Reason about the dimension axes when applicable
  (``dimensions_considered``); the field must be present (an empty list
  asserts none apply).
- Variants proving the SAME product outcome stay variants of one coverage
  decision (``variants`` carry their own label and evidence).
- Writer handoff integrity: the Writer receives an explicit admitted package
  (``writer_handoff``) containing only accepted (non-EXCLUDED) decisions and
  every P0 decision; when ``writer_package`` is declared, every AC binds to
  admitted ACCEPTANCE coverage ids, every P0 decision is represented, and no
  QE_REGRESSION/INVESTIGATION/EXCLUDED decision or unapproved variant leaks
  into an AC.

Backward-compatible: absent `coverage_decisions` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

COVERAGE_PRIORITIES = ("P0", "P1", "SUPPORTING", "EXCLUDED")

COVERAGE_CLASSES = ("ACCEPTANCE", "QE_REGRESSION", "INVESTIGATION")

# C1 canonical name; the earlier positive_or_negative field remains accepted
# as an alias for POSITIVE/NEGATIVE.
CONTRACT_TYPES = ("POSITIVE", "NEGATIVE", "PRESERVATION")

# Authorities that can never establish acceptance behavior - actual results,
# observations, suspected root causes, diagnostics, historical tickets, and
# inference are not requirement authority (defense in depth behind the
# resolver's own rule).
_NON_ESTABLISHING_AUTHORITIES = frozenset({
    "ACTUAL_RESULT",
    "SUSPECTED_ROOT_CAUSE",
    "ATTACHMENT_OBSERVATION",
    "HISTORICAL_JIRA",
    "AI_INFERENCE",
})

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

    polarity = item.get("contract_type")
    if polarity is None and item.get("positive_or_negative") is not None:
        polarity = item.get("positive_or_negative")
    if polarity not in CONTRACT_TYPES:
        problems.append(
            f"{tag}: contract_type '{polarity}' must be one of "
            f"{', '.join(CONTRACT_TYPES)}"
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
    research_ids = item.get("research_ids")
    if research_ids is not None and not isinstance(research_ids, list):
        problems.append(f"{tag}: research_ids must be a list when present")

    if "state_or_transition" not in item and "state" not in item:
        problems.append(
            f"{tag}: missing state_or_transition (declare it, empty when not "
            "applicable)"
        )
    for field in ("surface", "configuration"):
        if field not in item:
            problems.append(
                f"{tag}: missing {field} (declare it, empty when not applicable)"
            )

    variants = item.get("variants")
    if variants is not None:
        if not isinstance(variants, list):
            problems.append(f"{tag}: variants must be a list when present")
            variants = []
        for j, variant in enumerate(variants):
            vtag = f"{tag}.variants[{j}]"
            if not isinstance(variant, dict):
                problems.append(f"{vtag}: each variant must be an object")
                continue
            if not _nonempty(variant.get("label")):
                problems.append(f"{vtag}: missing label")
            if not isinstance(variant.get("evidence_ids"), list) or not (
                variant.get("evidence_ids")
            ):
                problems.append(
                    f"{vtag}: a variant stays bound to the same expected "
                    "outcome through its own evidence_ids"
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
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    resolutions_by_ref[ref] = row

    research_by_ref = {}
    research = manifest.get("question_research")
    if isinstance(research, dict):
        for row in research.get("items", []):
            if isinstance(row, dict):
                research_by_ref[row.get("question_ref")] = row

    doc_research = manifest.get("doc_research")

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
                status = resolution.get("status") or resolution.get(
                    "disposition"
                )
                if status == "DUPLICATE":
                    # Linkage only: the surviving question grounds coverage;
                    # the dedicated duplicate-linkage rule below guards the
                    # duplicate standing alone.
                    continue
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
        item_contract = item.get("contract_type") or item.get(
            "positive_or_negative"
        )
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
            if (
                behavior_class == "NEW_REQUIREMENT"
                and item_contract == "PRESERVATION"
            ):
                problems.append(
                    f"{tag}: behavior '{behavior_ref}' is a NEW_REQUIREMENT - "
                    "a new requirement is not a preservation contract"
                )
        # Observation/root-cause safety: an acceptance decision cannot rest on
        # non-establishing answer authority, even if a resolution predates the
        # resolver's own rule.
        if coverage_class == "ACCEPTANCE":
            for qid in item.get("question_ids") or []:
                resolution = resolutions_by_ref.get(qid)
                if resolution is None:
                    continue
                answer = resolution.get("answer")
                authority = (
                    answer.get("source_authority")
                    if isinstance(answer, dict)
                    else resolution.get("source_authority")
                )
                if authority in _NON_ESTABLISHING_AUTHORITIES:
                    problems.append(
                        f"{tag}: question '{qid}' was answered from "
                        f"{authority} - actual results, observations, "
                        "suspected root causes, and history cannot establish "
                        "acceptance behavior"
                    )
        # DUPLICATE linkage: a duplicate contributes its evidence through
        # the surviving question and never creates duplicate coverage.
        for qid in item.get("question_ids") or []:
            resolution = resolutions_by_ref.get(qid)
            if resolution is None:
                continue
            resolution_status = resolution.get("status") or resolution.get(
                "disposition"
            )
            if resolution_status != "DUPLICATE":
                continue
            surviving = resolution.get("duplicate_of")
            if surviving and surviving not in (item.get("question_ids") or []):
                problems.append(
                    f"{tag}: question '{qid}' is a DUPLICATE of "
                    f"'{surviving}' - coverage must link the surviving "
                    "question instead of creating duplicate coverage"
                )
        # Research binding: coverage cites the admitted research behind its
        # underlying questions.
        research_ids = item.get("research_ids") or []
        if isinstance(doc_research, dict):
            known_research = {
                row.get("research_id")
                for row in doc_research.get("results", [])
                if isinstance(row, dict)
            }
            for rid in research_ids:
                if rid not in known_research:
                    problems.append(
                        f"{tag}: research '{rid}' is not a Doc Researcher "
                        "result"
                    )
        underlying_research = set()
        for qid in item.get("question_ids") or []:
            resolution = resolutions_by_ref.get(qid)
            if resolution is not None:
                underlying_research.update(resolution.get("research_ids") or [])
        missing_research = sorted(underlying_research - set(research_ids))
        if missing_research:
            problems.append(
                f"{tag}: research binding must cover the underlying "
                f"resolutions' research {missing_research}"
            )

    # Writer boundary: a question is never rendered directly as coverage/AC
    # text - the Writer consumes resolved coverage decisions, not raw
    # questions.
    question_texts = {}
    if isinstance(plan, dict):
        for source in (plan.get("items"), (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                for row in source:
                    if isinstance(row, dict) and row.get("question_id"):
                        question_texts[row["question_id"]] = str(
                            row.get("question") or ""
                        ).strip()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        behavior = str(item.get("behavior") or "").strip()
        if not behavior:
            continue
        for qid in item.get("question_ids") or []:
            if question_texts.get(qid) and behavior == question_texts[qid]:
                problems.append(
                    f"coverage_decisions.items[{i}]: question '{qid}' is "
                    "rendered directly as coverage text - a question is never "
                    "an AC; the Writer consumes resolved decisions only"
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

    # The Writer receives an explicit admitted package; the Reviewer verifies
    # every P0 decision is represented in that handoff.
    handoff = block.get("writer_handoff")
    if items and handoff is None:
        problems.append(
            "coverage_decisions: the Writer must receive an explicit admitted "
            "coverage package - declare writer_handoff"
        )
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

    # Reviewer binding: when the Writer's draft ACs are declared, every AC
    # maps to admitted ACCEPTANCE coverage, every P0 decision is represented,
    # and nothing EXCLUDED / regression / investigation leaks into an AC.
    writer_package = manifest.get("writer_package")
    if isinstance(writer_package, dict):
        acs = writer_package.get("acs", [])
        if not isinstance(acs, list):
            problems.append("writer_package.acs must be a list")
            acs = []
        by_id = {
            item.get("coverage_id"): item
            for item in items
            if isinstance(item, dict)
        }
        admitted = set(handoff) if isinstance(handoff, list) else {
            cid
            for cid, row in by_id.items()
            if row.get("priority") != "EXCLUDED"
        }
        referenced = set()
        seen_acs = set()
        for j, ac in enumerate(acs):
            atag = f"writer_package.acs[{j}]"
            if not isinstance(ac, dict):
                problems.append(f"{atag}: each AC must be an object")
                continue
            ac_id = ac.get("ac_id")
            if not _nonempty(ac_id):
                problems.append(f"{atag}: missing ac_id")
            elif ac_id in seen_acs:
                problems.append(f"{atag}: duplicate ac_id '{ac_id}'")
            seen_acs.add(ac_id)
            coverage_ids = ac.get("coverage_ids")
            if not isinstance(coverage_ids, list) or not coverage_ids:
                problems.append(
                    f"{atag}: every AC maps to admitted coverage_ids - the "
                    "Writer cannot add behavior absent from admitted coverage"
                )
                continue
            for cid in coverage_ids:
                target = by_id.get(cid)
                if target is None:
                    problems.append(f"{atag}: unknown coverage_id '{cid}'")
                    continue
                if cid not in admitted:
                    problems.append(
                        f"{atag}: coverage '{cid}' is not in the admitted "
                        "writer package"
                    )
                if target.get("coverage_class") != "ACCEPTANCE":
                    problems.append(
                        f"{atag}: coverage '{cid}' is "
                        f"{target.get('coverage_class')} - QE_REGRESSION and "
                        "INVESTIGATION never leak into an AC"
                    )
                referenced.add(cid)
            approved_variants = {
                variant.get("label")
                for cid in coverage_ids
                for variant in (by_id.get(cid, {}).get("variants") or [])
                if isinstance(variant, dict)
            }
            for label in ac.get("variants") or []:
                if label not in approved_variants:
                    problems.append(
                        f"{atag}: variant '{label}' is not an approved variant "
                        "of the bound coverage"
                    )
        for cid, row in sorted(by_id.items()):
            if (
                row.get("priority") == "P0"
                and row.get("coverage_class") == "ACCEPTANCE"
                and cid in admitted
                and cid not in referenced
            ):
                problems.append(
                    f"writer_package: P0 acceptance coverage '{cid}' is not "
                    "represented by any AC - P0 accepted behavior cannot "
                    "disappear from the final draft"
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
