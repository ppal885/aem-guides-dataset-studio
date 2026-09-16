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
    if classification == "CONFLICT" and not (
        _nonempty(item.get("conflict_summary")) or item.get("conflicts")
    ):
        problems.append(
            f"{tag}: CONFLICT requires conflict_summary/conflicts keeping the "
            "contradiction visible"
        )
    merge_allowed = item.get("merge_allowed")
    if not isinstance(merge_allowed, bool):
        problems.append(
            f"{tag}: merge_allowed must be declared (true only when a merge "
            "is legitimate)"
        )
    elif merge_allowed and classification != "SAME_OUTCOME_VARIANT":
        problems.append(
            f"{tag}: merge_allowed is true only for SAME_OUTCOME_VARIANT - "
            "distinct, dependent, and conflicting outcomes never merge"
        )
    return problems


def _merge_fields(item):
    """Normalize the E1 group contract and the earlier merge field names."""

    return {
        "id": item.get("equivalence_id") or item.get("merge_id"),
        "members": item.get("coverage_refs") or item.get("merged_coverage_ids") or [],
        "question_ids": item.get("question_refs") or item.get("question_ids") or [],
        "evidence_ids": item.get("evidence_refs") or item.get("evidence_ids") or [],
        "research_ids": item.get("research_refs") or item.get("research_ids") or [],
        "variants": item.get("variant_refs") or item.get("variants") or [],
        "source_lineage": item.get("source_lineage") or item.get("lineage") or [],
        "priority": item.get("priority"),
        "canonical_outcome": item.get("canonical_outcome"),
        "applicability": item.get("applicability"),
        "partial_members": item.get("partial_members") or [],
        "classification": item.get("classification"),
    }


def _validate_merge(i, item, coverage_by_id, basis_pairs, sufficiency_by_coverage,
                    resolution_status_by_question):
    problems = []
    tag = f"coverage_equivalence.merges[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each merge must be an object"]
    fields = _merge_fields(item)

    if not _nonempty(fields["id"]):
        problems.append(f"{tag}: missing equivalence_id (merge_id)")
    merged = fields["members"]
    if not isinstance(merged, list) or len(merged) < 2:
        problems.append(f"{tag}: coverage_refs must list at least two ids")
        merged = merged if isinstance(merged, list) else []
    if fields["classification"] != "SAME_OUTCOME_VARIANT":
        problems.append(
            f"{tag}: only SAME_OUTCOME_VARIANT decisions may merge - distinct "
            "behavior is never merged simply to reduce AC count"
        )
    if not _nonempty(fields["canonical_outcome"]):
        problems.append(
            f"{tag}: canonical_outcome is required - the normalized grouping "
            "outcome; it is internal only and never becomes evidence"
        )

    for field in ("question_ids", "evidence_ids", "variants", "source_lineage"):
        value = fields[field]
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
                problems.append(f"{tag}: unknown coverage_ref '{cid}'")
        excluded = [cid for cid in merged
                    if coverage_by_id.get(cid, {}).get("priority") == "EXCLUDED"]
        if excluded:
            problems.append(
                f"{tag}: EXCLUDED coverage cannot be merged: {excluded}"
            )
        if members and isinstance(fields["question_ids"], list):
            expected_questions = sorted({
                qid for row in members for qid in (row.get("question_ids") or [])
            })
            if sorted(set(fields["question_ids"])) != expected_questions:
                problems.append(
                    f"{tag}: merge must preserve all member question IDs "
                    f"(expected {expected_questions})"
                )
        if members and isinstance(fields["evidence_ids"], list):
            expected_evidence = sorted({
                eid for row in members for eid in (row.get("evidence_ids") or [])
            })
            if sorted(set(fields["evidence_ids"])) != expected_evidence:
                problems.append(
                    f"{tag}: merge must preserve all member evidence IDs "
                    f"(expected {expected_evidence})"
                )
        # Research preservation: all member research refs survive the merge.
        member_research = sorted({
            rid for row in members for rid in (row.get("research_ids") or [])
        })
        if member_research:
            if sorted(set(fields["research_ids"])) != member_research:
                problems.append(
                    f"{tag}: merge must preserve all member research IDs "
                    f"(expected {member_research})"
                )
        # Variant preservation: every approved member variant survives; nothing
        # unapproved is introduced.
        member_variants = sorted({
            variant.get("label")
            for row in members
            for variant in (row.get("variants") or [])
            if isinstance(variant, dict) and variant.get("label")
        })
        if member_variants and isinstance(fields["variants"], list):
            declared = sorted(
                v.get("label") if isinstance(v, dict) else v
                for v in fields["variants"]
            )
            if declared != member_variants:
                problems.append(
                    f"{tag}: merge must preserve all approved member variants "
                    f"(expected {member_variants}); a variant is never omitted "
                    "or invented"
                )
        # Parity guard: merges never cross applicability, configuration, state,
        # or surface.  Same-looking behavior under a different engine, version,
        # surface, or material configuration is not the same outcome; such
        # differences belong to variants of one decision, not a cross-decision
        # merge.
        for field in ("applicability", "configuration", "state_or_transition",
                      "state", "surface"):
            values = {
                str(row.get(field) or "")
                for row in members
                if row.get(field) is not None or field in row
            }
            if len(values) > 1:
                problems.append(
                    f"{tag}: merge members disagree on {field} "
                    f"({sorted(values)}) - same-looking behavior under "
                    "different applicability/surface/configuration is never "
                    "merged; parity is never inferred"
                )
        if members and _nonempty(fields["priority"]):
            expected_priority = min(
                (_PRIORITY_RANK.get(row.get("priority"), 99) for row in members),
                default=99,
            )
            expected_priority = next(
                (name for name, rank in _PRIORITY_RANK.items()
                 if rank == expected_priority),
                None,
            )
            if expected_priority and fields["priority"] != expected_priority:
                problems.append(
                    f"{tag}: merge priority must keep the highest member "
                    f"priority ({expected_priority})"
                )

    # Sufficiency boundary (S1): only sufficiently established portions may
    # participate in a confirmed merge.
    for cid in merged:
        state = sufficiency_by_coverage.get(cid)
        if state == "INSUFFICIENT":
            problems.append(
                f"{tag}: coverage '{cid}' is INSUFFICIENT - it cannot merge "
                "into confirmed acceptance"
            )
        elif state == "CONFLICTED":
            problems.append(
                f"{tag}: coverage '{cid}' is CONFLICTED - conflicting outcomes "
                "never merge"
            )
        elif state == "PARTIAL" and cid not in fields["partial_members"]:
            problems.append(
                f"{tag}: coverage '{cid}' is PARTIAL - only its established "
                "portion may participate; list it in partial_members"
            )
    # ACCEPTANCE_TBD must not disappear into a confirmed merge.
    member_questions = {
        qid
        for row in members
        for qid in (row.get("question_ids") or [])
    }
    for qid in sorted(member_questions):
        if resolution_status_by_question.get(qid) == "ACCEPTANCE_TBD":
            problems.append(
                f"{tag}: question '{qid}' is ACCEPTANCE_TBD - a merge never "
                "absorbs an unresolved acceptance dimension"
            )
    if merged and not any(
        pair <= set(merged) and allowed for pair, allowed in basis_pairs
    ):
        problems.append(
            f"{tag}: a merge requires a SAME_OUTCOME_VARIANT decision with "
            "merge_allowed between its members - comparison on coverage "
            "decisions comes before any merge"
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

    # S1/S1-resolution context for the merge boundary rules.
    sufficiency_by_coverage = {}
    sufficiency = manifest.get("evidence_sufficiency")
    if isinstance(sufficiency, dict):
        for row in sufficiency.get("coverage_assessments", []):
            if isinstance(row, dict) and row.get("coverage_ref"):
                sufficiency_by_coverage[row["coverage_ref"]] = (
                    row.get("sufficiency") or row.get("sufficiency_status")
                )
    resolution_status_by_question = {}
    resolutions = manifest.get("question_resolutions")
    if isinstance(resolutions, dict):
        for row in resolutions.get("items", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    resolution_status_by_question[ref] = (
                        row.get("status") or row.get("disposition")
                    )

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
                basis_pairs.add((pair, bool(item.get("merge_allowed"))))

    seen_merges = set()
    merged_so_far = set()
    for i, item in enumerate(merges):
        fields = _merge_fields(item)
        problems.extend(
            _validate_merge(
                i,
                item,
                coverage_by_id,
                basis_pairs,
                sufficiency_by_coverage,
                resolution_status_by_question,
            )
        )
        if not isinstance(item, dict):
            continue
        mid = fields["id"]
        if mid:
            if mid in seen_merges:
                problems.append(
                    f"coverage_equivalence.merges[{i}]: duplicate equivalence_id "
                    f"'{mid}'"
                )
            seen_merges.add(mid)
        overlap = set(fields["members"]) & merged_so_far
        if overlap:
            problems.append(
                f"coverage_equivalence.merges[{i}]: coverage decisions "
                f"{sorted(overlap)} are already merged elsewhere - one "
                "decision survives into exactly one AC"
            )
        merged_so_far.update(fields["members"])
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
