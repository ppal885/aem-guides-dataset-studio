"""Human-feedback delta learner gate (UACFIX-08), backward-compatible.

WHY THIS EXISTS
---------------
Human edits (AI_BEFORE -> HUMAN_AFTER) must be classified into different learning
types, not all treated as discovery misses. Human feedback is the ONLY supervisory
learning truth: AI critique, FluffyJaws output, automated review, and model
suggestions are NOT learning truth and can never be promoted to an approved pattern.
Rendering/language feedback must not modify discovery logic; scope corrections improve
the scope gate, not disable valid investigation. Promotion is governed (multiple
independent Human cases, or a strong normative invariant, or a severe Human-confirmed
P0/P1 failure) and counterexample-mined before approval, and each coverage miss links
to the first failed pipeline stage so the lesson targets the right stage.

Backward-compatible: absent `human_feedback_delta` -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

DELTA_TYPES = (
    "COVERAGE_ADDED", "COVERAGE_REMOVED", "SCOPE_NARROWED", "SCOPE_EXPANDED",
    "DISPOSITION_CHANGED", "OPEN_QUESTION_ADDED", "OPEN_QUESTION_REMOVED",
    "LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT", "ORACLE_CHANGED",
    "PRIORITY_CHANGED", "IMPLEMENTATION_DETAIL_REMOVED",
)

PATTERN_CLASSES = (
    "DISCOVERY_PATTERN", "SCOPE_PATTERN", "DISPOSITION_PATTERN", "QUESTION_PATTERN",
    "RENDERING_LANGUAGE_PATTERN", "TESTABILITY_PATTERN", "NEGATIVE_BOUNDARY_PATTERN",
    "ENTRY_POINT_PATTERN", "REPRO_DIMENSION_PATTERN",
)

PROMOTION_STATES = ("CANDIDATE", "VALIDATING", "APPROVED", "REJECTED", "EXPLORATORY", "ROLLED_BACK")

# Only Human feedback is supervisory learning truth.
SOURCES = ("HUMAN", "AI_REVIEW", "FLUFFYJAWS", "MODEL")
HUMAN_SOURCE = "HUMAN"
PROMOTABLE_STATES = frozenset({"VALIDATING", "APPROVED"})

# Language/presentation deltas must not become discovery learning.
LANGUAGE_DELTAS = frozenset({"LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT", "IMPLEMENTATION_DETAIL_REMOVED"})
LANGUAGE_PATTERN_CLASSES = frozenset({"RENDERING_LANGUAGE_PATTERN", "TESTABILITY_PATTERN"})

# Pipeline stages a coverage miss can be attributed to (first_failed_stage).
PIPELINE_STAGES = frozenset({
    "DISCOVERY", "VERSION_EVIDENCE", "CONFLICT_RESOLUTION", "SCOPE", "ENTRY_POINT",
    "REPRO_DIMENSION", "CANDIDATE_COMPLETENESS", "SYNTHESIS", "RENDERING",
})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("human_feedback_delta"), dict)


def _nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(isinstance(x, str) and x.strip() for x in v)
    return bool(v)


def validate_delta(i, d):
    problems = []
    tag = f"human_feedback_delta.deltas[{i}]"
    if not isinstance(d, dict):
        return [f"{tag}: each delta must be an object"]

    dtype = d.get("delta_type")
    if dtype not in DELTA_TYPES:
        problems.append(f"{tag}: delta_type '{dtype}' must be one of {', '.join(DELTA_TYPES)}")

    pclass = d.get("pattern_class")
    if pclass not in PATTERN_CLASSES:
        problems.append(f"{tag}: pattern_class '{pclass}' must be one of {', '.join(PATTERN_CLASSES)}")

    source = d.get("source")
    if source not in SOURCES:
        problems.append(f"{tag}: source '{source}' must be one of {', '.join(SOURCES)}")

    state = d.get("promotion_state")
    if state not in PROMOTION_STATES:
        problems.append(f"{tag}: promotion_state '{state}' must be one of {', '.join(PROMOTION_STATES)}")

    # Human-only supervision: non-Human sources can never be promoted.
    if source in ("AI_REVIEW", "FLUFFYJAWS", "MODEL") and state in PROMOTABLE_STATES:
        problems.append(
            f"{tag}: a '{source}' delta cannot be VALIDATING/APPROVED - only Human feedback "
            f"is supervisory learning truth (AI review / FluffyJaws / model are not)"
        )

    # Language/presentation deltas must not become discovery learning.
    if dtype in LANGUAGE_DELTAS and pclass == "DISCOVERY_PATTERN":
        problems.append(
            f"{tag}: a presentation delta '{dtype}' must not be a DISCOVERY_PATTERN - route it "
            f"to RENDERING_LANGUAGE_PATTERN/TESTABILITY_PATTERN; keep reasoning completeness "
            f"separate from presentation simplicity"
        )

    # First-failure link for coverage misses.
    if dtype == "COVERAGE_ADDED":
        stage = str(d.get("first_failed_stage", "")).strip()
        if not stage:
            problems.append(f"{tag}: COVERAGE_ADDED must record first_failed_stage (run debug_qe_miss)")
        elif stage not in PIPELINE_STAGES:
            problems.append(f"{tag}: first_failed_stage '{stage}' must be one of {', '.join(sorted(PIPELINE_STAGES))}")

    # Promotion governance: APPROVED needs evidence and counterexample mining.
    if state == "APPROVED":
        if source != HUMAN_SOURCE:
            problems.append(f"{tag}: only a HUMAN-sourced delta may be APPROVED")
        cases = d.get("human_cases") or []
        multi = isinstance(cases, list) and len(cases) >= 2
        normative = bool(d.get("normative_invariant"))
        severe = bool(d.get("severe_p0_p1"))
        if not (multi or normative or severe):
            problems.append(
                f"{tag}: APPROVED requires >=2 independent Human cases, or a normative invariant, "
                f"or a severe Human-confirmed P0/P1 failure"
            )
        if not d.get("counterexample_search_done"):
            problems.append(f"{tag}: APPROVED requires counterexample_search_done=true (attach hard negatives)")
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["human_feedback_delta"]
    deltas = block.get("deltas", [])
    if not isinstance(deltas, list):
        return ["human_feedback_delta.deltas must be a list"]
    problems = []
    for i, d in enumerate(deltas):
        problems.extend(validate_delta(i, d))
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "HumanFeedbackDelta: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["human_feedback_delta"].get("deltas", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"HumanFeedbackDelta: {status} ({n} delta(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Human-feedback delta learner gate (UACFIX-08)")
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
