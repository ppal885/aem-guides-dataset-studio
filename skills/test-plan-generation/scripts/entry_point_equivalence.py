"""Product entry-point equivalence reasoner gate (UACFIX-04), backward-compatible.

WHY THIS EXISTS
---------------
A customer operation can often be reached through several supported product entry
points (a toolbar action vs a context-menu action; Generate PDF vs Preview vs Download
PDF; the same backend API called from multiple UI surfaces). Those entry points must
NOT be assumed equivalent merely because the user-visible intent looks similar:

    SAME_USER_INTENT != SAME_IMPLEMENTATION.

An alternate entry point may enter a shared regression / AC only with
implementation-or-product evidence of a shared handler / pipeline / state / output.
The flow is: discovered entry point -> shared-path investigation -> applicability ->
Candidate Ledger -> scope gate -> AC / regression / OQ / rejected. Do not ask a Human
too early: search code / docs / tests first; only unresolved MATERIAL relationships
become an Open Question.

Backward-compatible: absent `entry_point_equivalence` -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

EQUIVALENCE_TYPES = (
    "SAME_USER_INTENT",
    "SAME_PRODUCT_ACTION",
    "SAME_HANDLER",
    "SAME_PROCESSING_PIPELINE",
    "SAME_STATE_MUTATION",
    "SAME_FINAL_OUTPUT",
    "DIFFERENT_IMPLEMENTATION",
    "UNKNOWN_RELATIONSHIP",
)

# Equivalence proven by implementation/product evidence of a shared path.
SHARED_PATH_TYPES = frozenset({
    "SAME_HANDLER", "SAME_PROCESSING_PIPELINE", "SAME_STATE_MUTATION", "SAME_FINAL_OUTPUT",
})
# Intent-level similarity that is NOT proof of shared implementation.
INTENT_ONLY_TYPES = frozenset({"SAME_USER_INTENT", "SAME_PRODUCT_ACTION"})

DISPOSITIONS = ("AC", "SHARED_REGRESSION", "OPEN_QUESTION", "REJECTED", "REFERENCE_ONLY")

# Dispositions that put the alternate entry point into sign-off/regression coverage.
COVERAGE_DISPOSITIONS = frozenset({"AC", "SHARED_REGRESSION"})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("entry_point_equivalence"), dict)


def _nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(isinstance(x, str) and x.strip() for x in v)
    return bool(v)


def validate_candidate(i, c, open_question_ids):
    problems = []
    tag = f"entry_point_equivalence.candidates[{i}]"
    if not isinstance(c, dict):
        return [f"{tag}: each candidate must be an object"]

    if not _nonempty(c.get("entry_point_id")):
        problems.append(f"{tag}: missing entry_point_id")
    if not _nonempty(c.get("product_action")):
        problems.append(f"{tag}: missing product_action")
    if not _nonempty(c.get("surface")):
        problems.append(f"{tag}: missing surface")

    etype = c.get("equivalence_type")
    if etype not in EQUIVALENCE_TYPES:
        problems.append(f"{tag}: equivalence_type '{etype}' must be one of {', '.join(EQUIVALENCE_TYPES)}")

    disp = c.get("disposition")
    if disp not in DISPOSITIONS:
        problems.append(f"{tag}: disposition '{disp}' must be one of {', '.join(DISPOSITIONS)}")

    if not _nonempty(c.get("evidence")):
        problems.append(f"{tag}: evidence is required")

    # CRITICAL: intent-level or unknown equivalence cannot enter AC/regression coverage
    # without implementation/product evidence of a shared path.
    if disp in COVERAGE_DISPOSITIONS:
        if etype in INTENT_ONLY_TYPES or etype == "UNKNOWN_RELATIONSHIP":
            problems.append(
                f"{tag}: '{etype}' cannot be promoted to {disp} - same user intent is not same "
                f"implementation; a shared handler/pipeline/state/output must be evidenced first"
            )
        if etype in SHARED_PATH_TYPES and not (
            _nonempty(c.get("shared_processing_path")) or _nonempty(c.get("implementation_handler"))
        ):
            problems.append(
                f"{tag}: {disp} on '{etype}' requires shared_processing_path or "
                f"implementation_handler evidence of the shared code path"
            )

    # DIFFERENT_IMPLEMENTATION must not become shared regression/AC.
    if etype == "DIFFERENT_IMPLEMENTATION" and disp in COVERAGE_DISPOSITIONS:
        problems.append(
            f"{tag}: DIFFERENT_IMPLEMENTATION must not be promoted to {disp}; use REFERENCE_ONLY or REJECTED"
        )

    # Only unresolved MATERIAL relationships become an Open Question, and only after
    # searching code/docs/tests first (do not ask the Human too early).
    if disp == "OPEN_QUESTION":
        oq = str(c.get("open_question_ref", "")).strip()
        if not oq:
            problems.append(f"{tag}: OPEN_QUESTION disposition requires open_question_ref")
        elif open_question_ids is not None and oq not in open_question_ids:
            problems.append(f"{tag}: open_question_ref '{oq}' is not a declared Open Question")
        if not _nonempty(c.get("searched_sources")):
            problems.append(
                f"{tag}: record searched_sources (code/docs/tests) before raising an Open Question - "
                f"do not ask the Human before searching"
            )
    return problems


def _open_question_ids(manifest):
    oqs = manifest.get("open_questions") if isinstance(manifest, dict) else None
    if not isinstance(oqs, list):
        return None
    return {str(o.get("id")).strip() for o in oqs if isinstance(o, dict) and o.get("id")}


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["entry_point_equivalence"]
    candidates = block.get("candidates", [])
    if not isinstance(candidates, list):
        return ["entry_point_equivalence.candidates must be a list"]
    oq_ids = _open_question_ids(manifest)
    problems = []
    seen = set()
    for i, c in enumerate(candidates):
        problems.extend(validate_candidate(i, c, oq_ids))
        if isinstance(c, dict) and c.get("entry_point_id"):
            if c["entry_point_id"] in seen:
                problems.append(f"entry_point_equivalence.candidates[{i}]: duplicate entry_point_id '{c['entry_point_id']}'")
            seen.add(c["entry_point_id"])
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "EntryPointEquivalence: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["entry_point_equivalence"].get("candidates", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"EntryPointEquivalence: {status} ({n} entry point(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Product entry-point equivalence reasoner gate (UACFIX-04)")
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
