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

        if candidate.get("material", True) and isinstance(
            candidate.get("dimensions"), list
        ):
            activated.update(
                row for row in candidate["dimensions"] if isinstance(row, str)
            )

    problems.extend(_validate_dispositions(block, activated))
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
