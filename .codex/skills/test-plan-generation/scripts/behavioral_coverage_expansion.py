"""Behavioral coverage expansion gate (backward-compatible).

WHY THIS EXISTS
---------------
Evidence authority was strong, but coverage *discovery* stayed too literal: the
plan captured the explicit ask and silently dropped the behaviors that depend on
it.  A named value is not atomic.  Before it can be accepted as covered, the
plan must also have considered where the value comes from, what is shown when it
is absent, whether it can be supplied indirectly through referenced or reused
content, what a move or rename does to it, whether it can go stale, and whether
every consumer surface agrees.

This gate validates the optional ``behavioral_coverage_expansion`` manifest
block produced by the canonical ``BehavioralCoverageExpander`` stage.  It
enforces the four invariants that make the expansion safe:

1. **Triggers are requirement-shaped.**  Every candidate names the generic
   trigger that activated it, so discovery is derived from what the requirement
   *does*, never from a product feature name.
2. **Discovery is bounded and deterministic.**  One candidate per
   (axis, subject); no duplicates.
3. **Discovery is not acceptance.**  A candidate may never be cited as the
   authority for an acceptance criterion; it only makes a dimension material.
4. **No silent loss.**  Every dimension a material candidate activates must
   receive an explicit disposition - covered, investigated and rejected, exposed
   as unresolved, or explicitly not applicable with a reason.  Omission is not
   a disposition.

Backward-compatible: absent ``behavioral_coverage_expansion`` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

AXES = (
    "VALUE_PROVENANCE",
    "FALLBACK_AND_ABSENCE",
    "VALUE_RESOLUTION_OR_INDIRECTION",
    "IDENTITY_AND_LIFECYCLE",
    "CONTEXT_AND_SCOPE",
    "CONSUMER_SURFACE_PARITY",
    "MUTATION_AND_FRESHNESS",
    "NEGATIVE_AND_BROKEN_RESOLUTION",
)

TRIGGERS = (
    "DISPLAYED_VALUE",
    "EXPORTED_VALUE",
    "ORDERING_RULE",
    "COMPARED_OR_FILTERED_VALUE",
    "PERSISTED_VALUE",
    "RESOLVED_REFERENCE",
    "IDENTITY_REFERENCE",
    "MULTIPLE_CONSUMER_SURFACES",
    "STATE_TRANSITION",
    "CONFIGURATION_DEPENDENCY",
)

DISPOSITIONS = (
    "COVERED",
    "INVESTIGATED_AND_REJECTED",
    "UNRESOLVED_AND_EXPOSED",
    "NOT_APPLICABLE",
    "RESEARCH_REQUIRED",
    "OPEN_QUESTION",
)

# The dependency dimensions a materially affected subject must answer. A
# subject is covered only when every one of these is decided, so a dependency
# can never be dropped by staying silent about it.
DEPENDENCY_KINDS = (
    "PROVENANCE",
    "PRECEDENCE_AND_FALLBACK",
    "INDIRECTION_AND_RESOLUTION",
    "CONTEXT_DEPENDENCY",
    "IDENTITY",
    "LIFECYCLE_MUTATION",
    "FRESHNESS_AND_STALENESS",
    "CONSUMER_PARITY",
    "UNRESOLVED_OR_NEGATIVE_BRANCH",
)

# A NOT_APPLICABLE dependency must say why. These all collapse to the same
# empty assertion and would restore the silence the record exists to prevent.
PLACEHOLDER_REASONS = frozenset(
    {
        "",
        "na",
        "none",
        "nonapplicable",
        "notapplicable",
        "notrelevant",
        "notneeded",
        "notrequired",
        "unknown",
        "tbd",
    }
)

# A disposition that closes a dimension without testing it has to say why.
REASON_REQUIRED = frozenset({"NOT_APPLICABLE", "INVESTIGATED_AND_REJECTED"})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("behavioral_coverage_expansion"), dict
    )


def _nonempty(value):
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def _validate_candidate(index, candidate):
    tag = f"behavioral_coverage_expansion.candidates[{index}]"
    if not isinstance(candidate, dict):
        return [f"{tag}: must be an object"]

    problems = []
    axis = candidate.get("axis")
    trigger = candidate.get("trigger")
    dimensions = candidate.get("dimensions")

    if axis not in AXES:
        problems.append(f"{tag}: axis must be one of {', '.join(AXES)}")
    if trigger not in TRIGGERS:
        problems.append(
            f"{tag}: trigger must be one of {', '.join(TRIGGERS)} - a candidate "
            "records the generic requirement shape that activated it, never a "
            "product feature name"
        )
    if not _nonempty(candidate.get("subject")):
        problems.append(f"{tag}: subject is required")
    if not isinstance(dimensions, list) or not dimensions:
        problems.append(f"{tag}: dimensions must be a non-empty list")
    if not _nonempty(candidate.get("question")):
        problems.append(f"{tag}: question is required")
    if not _nonempty(candidate.get("rationale")):
        problems.append(
            f"{tag}: rationale is required - it states why this behavior can "
            "regress with the stated ask"
        )

    candidate_id = candidate.get("candidate_id")
    if _nonempty(candidate_id) and not str(candidate_id).startswith("covexp:"):
        problems.append(
            f"{tag}: candidate_id must stay in the 'covexp:' namespace so a "
            "discovery candidate can never be mistaken for an acceptance "
            "candidate"
        )
    if candidate.get("promoted") or candidate.get("acceptance_ref"):
        problems.append(
            f"{tag}: a coverage-expansion candidate has no acceptance "
            "authority - discovery is not acceptance"
        )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []

    block = manifest["behavioral_coverage_expansion"]
    candidates = block.get("candidates", [])
    if not isinstance(candidates, list):
        return ["behavioral_coverage_expansion.candidates must be a list"]

    problems = []
    seen_pairs = set()
    seen_ids = set()
    activated = set()
    material_subjects = set()

    for index, candidate in enumerate(candidates):
        problems.extend(_validate_candidate(index, candidate))
        if not isinstance(candidate, dict):
            continue

        pair = (candidate.get("axis"), candidate.get("subject"))
        if pair in seen_pairs:
            problems.append(
                f"behavioral_coverage_expansion.candidates[{index}]: duplicate "
                f"(axis, subject) pair {pair} - discovery is bounded"
            )
        seen_pairs.add(pair)

        candidate_id = candidate.get("candidate_id")
        if _nonempty(candidate_id):
            if candidate_id in seen_ids:
                problems.append(
                    f"behavioral_coverage_expansion.candidates[{index}]: "
                    f"duplicate candidate_id '{candidate_id}'"
                )
            seen_ids.add(candidate_id)

        if candidate.get("material", True):
            subject = candidate.get("subject")
            if _nonempty(subject):
                material_subjects.add(subject.strip())
            if isinstance(candidate.get("dimensions"), list):
                activated.update(
                    row for row in candidate["dimensions"] if isinstance(row, str)
                )

    problems.extend(_validate_dispositions(block, activated))
    problems.extend(_validate_dependency_records(block, material_subjects))
    return problems


def _validate_dependency_slot(tag, slot):
    """One dependency kind's decision for one subject."""

    if not isinstance(slot, dict):
        return [f"{tag}: must be an object"]

    problems = []
    kind = slot.get("kind")
    disposition = slot.get("disposition")
    reason = slot.get("reason")

    if kind not in DEPENDENCY_KINDS:
        problems.append(f"{tag}: kind must be one of {', '.join(DEPENDENCY_KINDS)}")
    if disposition not in DISPOSITIONS:
        problems.append(
            f"{tag}: disposition must be one of {', '.join(DISPOSITIONS)}"
        )
    if not _nonempty(reason):
        problems.append(
            f"{tag}: a concrete reason is required - a dependency is never "
            "decided silently"
        )
    elif disposition == "NOT_APPLICABLE":
        collapsed = "".join(
            character for character in str(reason).casefold() if character.isalnum()
        )
        if collapsed in PLACEHOLDER_REASONS:
            problems.append(
                f"{tag}: NOT_APPLICABLE with a placeholder reason restores the "
                "silence this record prevents - state why this subject cannot "
                "exercise the dependency"
            )
    if disposition == "RESEARCH_REQUIRED" and not (
        slot.get("question_ids") or slot.get("candidate_ids")
    ):
        problems.append(
            f"{tag}: RESEARCH_REQUIRED names no question or candidate to carry "
            "the research"
        )
    return problems


def _validate_dependency_records(block, material_subjects):
    """A materially affected subject must decide every dependency kind."""

    rows = block.get("dependency_records", [])
    if rows in (None, []) and not material_subjects:
        return []
    if not isinstance(rows, list):
        return ["behavioral_coverage_expansion.dependency_records must be a list"]

    problems = []
    covered = set()
    for index, record in enumerate(rows):
        tag = f"behavioral_coverage_expansion.dependency_records[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag}: must be an object")
            continue

        subject = record.get("subject")
        if not _nonempty(subject):
            problems.append(f"{tag}: subject is required")
            continue
        subject = subject.strip()
        if subject in covered:
            problems.append(f"{tag}: duplicate record for subject '{subject}'")
        covered.add(subject)

        if record.get("promoted") or record.get("acceptance_ref"):
            problems.append(
                f"{tag}: a dependency record is discovery and traceability "
                "only - it carries no acceptance authority"
            )

        slots = record.get("slots")
        if not isinstance(slots, list):
            problems.append(f"{tag}: slots must be a list")
            continue

        seen_kinds = []
        for slot_index, slot in enumerate(slots):
            problems.extend(
                _validate_dependency_slot(f"{tag}.slots[{slot_index}]", slot)
            )
            if isinstance(slot, dict) and slot.get("kind") in DEPENDENCY_KINDS:
                kind = slot["kind"]
                if kind in seen_kinds:
                    problems.append(
                        f"{tag}: dependency '{kind}' is dispositioned twice"
                    )
                seen_kinds.append(kind)

        missing = [kind for kind in DEPENDENCY_KINDS if kind not in seen_kinds]
        if missing:
            problems.append(
                f"{tag}: record for '{subject}' is silent about "
                + ", ".join(missing)
                + " - omission is not a disposition"
            )

    for subject in sorted(material_subjects - covered):
        problems.append(
            "behavioral_coverage_expansion: material subject "
            f"'{subject}' has no dependency record - its dependencies were "
            "never decided"
        )
    return problems


def _validate_dispositions(block, activated):
    """Invariant 4: a discovered dimension may never silently disappear."""

    rows = block.get("dispositions", [])
    if not activated:
        return []
    if not isinstance(rows, list):
        return ["behavioral_coverage_expansion.dispositions must be a list"]
    if not rows:
        return [
            "behavioral_coverage_expansion: "
            f"{len(activated)} dimension(s) were activated by material "
            "candidates but none was dispositioned - omission is not a "
            "disposition"
        ]

    problems = []
    decided = {}
    for index, row in enumerate(rows):
        tag = f"behavioral_coverage_expansion.dispositions[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{tag}: must be an object")
            continue
        dimension = row.get("dimension")
        disposition = row.get("disposition")
        if not _nonempty(dimension):
            problems.append(f"{tag}: dimension is required")
            continue
        if disposition not in DISPOSITIONS:
            problems.append(
                f"{tag}: disposition must be one of {', '.join(DISPOSITIONS)}"
            )
        if disposition in REASON_REQUIRED and not _nonempty(row.get("reason")):
            problems.append(
                f"{tag}: {disposition} requires a concrete reason - a dimension "
                "cannot be closed without testing it and without saying why"
            )
        decided[dimension] = disposition

    for dimension in sorted(activated - set(decided)):
        problems.append(
            "behavioral_coverage_expansion: dimension "
            f"'{dimension}' was activated by a material candidate but never "
            "dispositioned - discovered behavior cannot silently disappear"
        )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "BehavioralCoverageExpansion: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["behavioral_coverage_expansion"]
    candidates = block.get("candidates", []) or []
    triggers = block.get("triggers", []) or []
    status = "CLEAN" if not problems else "ISSUES"
    lines = [
        f"BehavioralCoverageExpansion: {status} "
        f"({len(candidates)} candidate(s), {len(triggers)} trigger(s))"
    ]
    for problem in problems:
        lines.append(f"  {problem}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Behavioral coverage expansion gate"
    )
    parser.add_argument("--manifest")
    args = parser.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    print(summarize(manifest))
    return 0 if not validate(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
