"""Semantic Coverage/AC Equivalence gate (backward-compatible).

WHY THIS EXISTS
---------------
After the Coverage Reasoner emits coverage decisions, semantic equivalence
decides which decisions describe the same outcome and may share one AC.  The
primary comparison happens on **Coverage Decisions**, not merely Writer prose:
each equivalence decision compares two `coverage_id`s across structured
dimensions (coverage IDs, question IDs, expected outcome, state transition,
scope, configuration, applicability) instead of textual similarity.

Classifications:

- ``SAME_OUTCOME_VARIANT`` - the same expected outcome observed through variant
  phrasing/polarity (e.g. "the state remains after refresh" and "refresh does
  not return the state to the prior one").  The Writer should normally create
  one AC; a merge is allowed only under this classification.
- ``DISTINCT_OUTCOME`` - different expected outcomes; never merge.
- ``DEPENDENT_OUTCOME`` - one outcome depends on the other; keep separate and
  record the dependency.
- ``CONFLICT`` - the same outcome is asserted contradictorily; never merge,
  keep the conflict visible.

Merge discipline (``merges[]``): a merge preserves all question IDs, all
evidence IDs, all applicable variants, and the source lineage of every merged
decision, keeps the highest priority of its members, never includes an
EXCLUDED decision, and must cite a SAME_OUTCOME_VARIANT decision between its
members.  Distinct behavior is never merged simply to reduce AC count.

Backward-compatible: absent `coverage_equivalence` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

EQUIVALENCE_CLASSES = (
    "SAME_OUTCOME_VARIANT",
    "DISTINCT_OUTCOME",
    "DEPENDENT_OUTCOME",
    "CONFLICT",
)

# The structured dimensions the comparison is declared on - never text alone.
COMPARISON_DIMENSIONS = (
    "COVERAGE_IDS",
    "QUESTION_IDS",
    "EXPECTED_OUTCOME",
    "STATE_TRANSITION",
    "SCOPE",
    "CONFIGURATION",
    "APPLICABILITY",
)

_PRIORITY_RANK = {"P0": 0, "P1": 1, "SUPPORTING": 2, "EXCLUDED": 3}


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("coverage_equivalence"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_dimensions(tag, shared, differing):
    problems = []
    for name, values in (("shared_dimensions", shared), ("differing_dimensions", differing)):
        if not isinstance(values, list):
            problems.append(f"{tag}: {name} must be a list")
            continue
        unknown = [value for value in values if value not in COMPARISON_DIMENSIONS]
        if unknown:
            problems.append(
                f"{tag}: unknown {name} {unknown} - use "
                f"{', '.join(COMPARISON_DIMENSIONS)}"
            )
    if isinstance(shared, list) and isinstance(differing, list):
        overlap = set(shared) & set(differing)
        if overlap:
            problems.append(
                f"{tag}: dimensions cannot be both shared and differing: "
                f"{sorted(overlap)}"
            )
        if not shared and not differing:
            problems.append(
                f"{tag}: declare at least one shared or differing comparison "
                "dimension - the comparison is structural, not textual"
            )
    return problems


def _validate_decision(i, item, known_coverage_ids):
    problems = []
    tag = f"coverage_equivalence.decisions[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each equivalence decision must be an object"]

    if not _nonempty(item.get("decision_id")):
        problems.append(f"{tag}: missing decision_id")
    left = item.get("left_coverage_id")
    right = item.get("right_coverage_id")
    if not _nonempty(left) or not _nonempty(right):
        problems.append(
            f"{tag}: equivalence compares coverage decisions - "
            "left_coverage_id and right_coverage_id are required"
        )
    elif left == right:
        problems.append(f"{tag}: a coverage decision cannot compare to itself")
    elif known_coverage_ids is not None:
        for endpoint in (left, right):
            if endpoint not in known_coverage_ids:
                problems.append(
                    f"{tag}: '{endpoint}' is not a known coverage decision - "
                    "the primary comparison happens on coverage decisions, not "
                    "Writer prose"
                )
    classification = item.get("classification")
    if classification not in EQUIVALENCE_CLASSES:
        problems.append(
            f"{tag}: classification '{classification}' must be one of "
            f"{', '.join(EQUIVALENCE_CLASSES)}"
        )
        return problems
    if not _nonempty(item.get("reason")):
        problems.append(f"{tag}: missing reason")

    shared = item.get("shared_dimensions", [])
    differing = item.get("differing_dimensions", [])
    problems.extend(_validate_dimensions(tag, shared, differing))
    if isinstance(shared, list) and isinstance(differing, list):
        if classification == "SAME_OUTCOME_VARIANT" and (
            "EXPECTED_OUTCOME" not in shared
        ):
            problems.append(
                f"{tag}: SAME_OUTCOME_VARIANT requires EXPECTED_OUTCOME in "
                "shared_dimensions - the outcome is the same, only the variant "
                "differs"
            )
        if classification == "DISTINCT_OUTCOME" and (
            "EXPECTED_OUTCOME" not in differing
        ):
            problems.append(
                f"{tag}: DISTINCT_OUTCOME requires EXPECTED_OUTCOME in "
                "differing_dimensions - the outcomes differ"
            )
        if classification == "DEPENDENT_OUTCOME" and (
            "EXPECTED_OUTCOME" not in differing
        ):
            problems.append(
                f"{tag}: DEPENDENT_OUTCOME requires EXPECTED_OUTCOME in "
                "differing_dimensions - one outcome depends on the other"
            )
        if classification == "CONFLICT" and "EXPECTED_OUTCOME" not in shared:
            problems.append(
                f"{tag}: CONFLICT requires EXPECTED_OUTCOME in "
                "shared_dimensions - the same outcome is asserted "
                "contradictorily"
            )
    if classification == "DEPENDENT_OUTCOME" and not _nonempty(item.get("dependency")):
        problems.append(
            f"{tag}: DEPENDENT_OUTCOME requires dependency naming which "
            "decision depends on which"
        )
    if classification == "CONFLICT" and not _nonempty(item.get("conflict_summary")):
        problems.append(
            f"{tag}: CONFLICT requires conflict_summary keeping the "
            "contradiction visible"
        )
    return problems


def _validate_merge(i, item, coverage_by_id, basis_pairs):
    problems = []
    tag = f"coverage_equivalence.merges[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each merge must be an object"]

    if not _nonempty(item.get("merge_id")):
        problems.append(f"{tag}: missing merge_id")
    merged = item.get("merged_coverage_ids")
    if not isinstance(merged, list) or len(merged) < 2:
        problems.append(f"{tag}: merged_coverage_ids must list at least two ids")
        merged = merged if isinstance(merged, list) else []
    classification = item.get("classification")
    if classification != "SAME_OUTCOME_VARIANT":
        problems.append(
            f"{tag}: only SAME_OUTCOME_VARIANT decisions may merge - distinct "
            "behavior is never merged simply to reduce AC count"
        )

    for field in ("question_ids", "evidence_ids", "variants", "source_lineage"):
        value = item.get(field)
        if not isinstance(value, list) or not value:
            problems.append(
                f"{tag}: {field} must be a non-empty list - a merge preserves "
                "all question IDs, all evidence IDs, all applicable variants, "
                "and the source lineage"
            )

    members = (
        [coverage_by_id[cid] for cid in merged if cid in coverage_by_id]
        if coverage_by_id is not None
        else []
    )
    if coverage_by_id is not None:
        for cid in merged:
            if cid not in coverage_by_id:
                problems.append(f"{tag}: unknown merged coverage_id '{cid}'")
        excluded = [cid for cid in merged
                    if coverage_by_id.get(cid, {}).get("priority") == "EXCLUDED"]
        if excluded:
            problems.append(
                f"{tag}: EXCLUDED coverage cannot be merged: {excluded}"
            )
        if members and isinstance(item.get("question_ids"), list):
            expected_questions = sorted({
                qid for row in members for qid in (row.get("question_ids") or [])
            })
            if sorted(set(item["question_ids"])) != expected_questions:
                problems.append(
                    f"{tag}: merge must preserve all member question IDs "
                    f"(expected {expected_questions})"
                )
        if members and isinstance(item.get("evidence_ids"), list):
            expected_evidence = sorted({
                eid for row in members for eid in (row.get("evidence_ids") or [])
            })
            if sorted(set(item["evidence_ids"])) != expected_evidence:
                problems.append(
                    f"{tag}: merge must preserve all member evidence IDs "
                    f"(expected {expected_evidence})"
                )
        if members and _nonempty(item.get("priority")):
            expected_priority = min(
                (_PRIORITY_RANK.get(row.get("priority"), 99) for row in members),
                default=99,
            )
            expected_priority = next(
                (name for name, rank in _PRIORITY_RANK.items()
                 if rank == expected_priority),
                None,
            )
            if expected_priority and item.get("priority") != expected_priority:
                problems.append(
                    f"{tag}: merge priority must keep the highest member "
                    f"priority ({expected_priority})"
                )
    if merged and not any(
        pair <= set(merged) for pair in basis_pairs
    ):
        problems.append(
            f"{tag}: a merge requires a SAME_OUTCOME_VARIANT decision between "
            "its members - comparison on coverage decisions comes before any "
            "merge"
        )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["coverage_equivalence"]
    decisions = block.get("decisions", [])
    merges = block.get("merges", [])
    if not isinstance(decisions, list):
        return ["coverage_equivalence.decisions must be a list"]
    if not isinstance(merges, list):
        return ["coverage_equivalence.merges must be a list"]

    coverage = manifest.get("coverage_decisions")
    coverage_by_id = None
    if isinstance(coverage, dict) and isinstance(coverage.get("items"), list):
        coverage_by_id = {
            row.get("coverage_id"): row
            for row in coverage["items"]
            if isinstance(row, dict) and row.get("coverage_id")
        }
    known_ids = set(coverage_by_id) if coverage_by_id is not None else None

    problems = []
    seen_decisions = set()
    seen_pairs = set()
    basis_pairs = set()
    for i, item in enumerate(decisions):
        problems.extend(_validate_decision(i, item, known_ids))
        if not isinstance(item, dict):
            continue
        did = item.get("decision_id")
        if did:
            if did in seen_decisions:
                problems.append(
                    f"coverage_equivalence.decisions[{i}]: duplicate decision_id "
                    f"'{did}'"
                )
            seen_decisions.add(did)
        pair = frozenset(
            {item.get("left_coverage_id"), item.get("right_coverage_id")}
        )
        if len(pair) == 2:
            if pair in seen_pairs:
                problems.append(
                    f"coverage_equivalence.decisions[{i}]: duplicate comparison "
                    f"of {sorted(pair)}"
                )
            seen_pairs.add(pair)
            if item.get("classification") == "SAME_OUTCOME_VARIANT":
                basis_pairs.add(pair)

    seen_merges = set()
    merged_so_far = set()
    for i, item in enumerate(merges):
        problems.extend(
            _validate_merge(
                i,
                item,
                coverage_by_id,
                basis_pairs,
            )
        )
        if not isinstance(item, dict):
            continue
        mid = item.get("merge_id")
        if mid:
            if mid in seen_merges:
                problems.append(
                    f"coverage_equivalence.merges[{i}]: duplicate merge_id '{mid}'"
                )
            seen_merges.add(mid)
        overlap = set(item.get("merged_coverage_ids") or []) & merged_so_far
        if overlap:
            problems.append(
                f"coverage_equivalence.merges[{i}]: coverage decisions "
                f"{sorted(overlap)} are already merged elsewhere - one "
                "decision survives into exactly one AC"
            )
        merged_so_far.update(item.get("merged_coverage_ids") or [])
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "CoverageEquivalence: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["coverage_equivalence"]
    d = len(block.get("decisions", []) or [])
    m = len(block.get("merges", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"CoverageEquivalence: {status} ({d} decision(s), {m} merge(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Semantic Coverage/AC Equivalence gate"
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
