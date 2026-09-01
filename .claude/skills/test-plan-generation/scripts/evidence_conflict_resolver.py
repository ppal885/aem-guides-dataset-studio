"""Deterministic evidence-conflict resolver gate (UACFIX-02), backward-compatible.

WHY THIS EXISTS
---------------
When normative semantics, current Human requirement, documented product behaviour,
current implementation, historical Human patterns, and AI hypotheses conflict, the
QE Reasoner must NOT silently choose one. This gate validates a `conflict_resolution`
block: each conflict records its type, the competing evidence, a QUESTION-SPECIFIC
winning authority, an output state, and remaining uncertainty. It extends (does not
replace) `evidence_authority_resolver.py`.

Two invariants it hard-enforces:
  1. Implementation mismatch with the contract does NOT rewrite the contract to the
     bug. A doc/spec/Human-vs-code conflict where code differs is a DEFECT
     (IMPLEMENTATION_DEVIATES_FROM_CONTRACT), not "current implementation wins".
  2. FluffyJaws / SUPPORTING_DISCOVERY evidence can never be the winning authority
     over a current Human decision, normative DITA meaning, or a verified current
     Jira product decision (no FluffyJaws -> AC).

Backward-compatible: absent `conflict_resolution` -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

CONFLICT_TYPES = (
    "PRODUCT_DOC_VS_CODE",
    "HUMAN_DECISION_VS_DOC",
    "CURRENT_VS_HISTORICAL",
    "NORMATIVE_VS_IMPLEMENTATION",
    "CUSTOMER_EXPECTATION_VS_DOCUMENTED_BEHAVIOR",
    "VERSION_CONFLICT",
    "SCOPE_CONFLICT",
    "CONFIGURATION_CONFLICT",
    "UNKNOWN_CONFLICT",
)

OUTPUT_STATES = (
    "RESOLVED_BY_HIGHER_AUTHORITY",
    "RESOLVED_BY_CURRENT_VERSION",
    "IMPLEMENTATION_DEVIATES_FROM_CONTRACT",
    "PRODUCT_DECISION_REQUIRED",
    "CURRENT_APPLICABILITY_REQUIRED",
    "REFERENCE_ONLY",
    "UNRESOLVED",
)

# Question-specific authority classes (highest-level distinctions, not a global order).
AUTHORITY_CLASSES = (
    "CURRENT_HUMAN_DECISION",
    "NORMATIVE_SEMANTIC",
    "CURRENT_PRODUCT_DOC",
    "VERIFIED_CURRENT_IMPLEMENTATION",
    "HISTORICAL_HUMAN_ANALOGY",
    "AI_INFERENCE",
    "SUPPORTING_DISCOVERY",  # FluffyJaws et al. - never a winner over the top three
)

# Output states that do NOT settle current truth; a material AC-supporting claim
# resting on them must be dispositioned as an open question, not silently promoted.
NON_SETTLING_STATES = frozenset({
    "PRODUCT_DECISION_REQUIRED", "CURRENT_APPLICABILITY_REQUIRED",
    "REFERENCE_ONLY", "UNRESOLVED",
})

SAFE_OPEN_DISPOSITIONS = frozenset({"OPEN_QUESTION", "NEEDS_CURRENT_VERIFICATION", "PRODUCT_DECISION"})

# Question type -> authority classes that may legitimately WIN for it. Question-
# specific: a normative question is settled by DITA semantics, not by code; a
# product-promise question by Human/current docs; a "what does the code do"
# question by verified implementation.
QUESTION_TYPE_WINNERS = {
    "NORMATIVE_SEMANTIC": {"NORMATIVE_SEMANTIC", "CURRENT_HUMAN_DECISION"},
    "PRODUCT_PROMISE": {"CURRENT_HUMAN_DECISION", "CURRENT_PRODUCT_DOC"},
    "IMPLEMENTATION_BEHAVIOR": {"VERIFIED_CURRENT_IMPLEMENTATION", "CURRENT_HUMAN_DECISION"},
    "GENERAL": set(AUTHORITY_CLASSES),  # no restriction
}


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("conflict_resolution"), dict)


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def validate_conflict(i, c):
    problems = []
    tag = f"conflict_resolution.conflicts[{i}]"
    if not isinstance(c, dict):
        return [f"{tag}: each conflict must be an object"]

    if not _nonempty(c.get("claim_id")):
        problems.append(f"{tag}: missing claim_id")
    if not _nonempty(c.get("normalized_claim")):
        problems.append(f"{tag}: missing normalized_claim")

    ctype = c.get("conflict_type")
    if ctype not in CONFLICT_TYPES:
        problems.append(f"{tag}: conflict_type '{ctype}' must be one of {', '.join(CONFLICT_TYPES)}")

    state = c.get("resolution")
    if state not in OUTPUT_STATES:
        problems.append(f"{tag}: resolution '{state}' must be one of {', '.join(OUTPUT_STATES)}")

    for key in ("supporting_evidence_ids", "conflicting_evidence_ids"):
        v = c.get(key)
        if not isinstance(v, list) or not v:
            problems.append(f"{tag}: {key} must be a non-empty list (preserve competing evidence)")

    winner = c.get("winning_authority")
    if state in {"RESOLVED_BY_HIGHER_AUTHORITY", "RESOLVED_BY_CURRENT_VERSION"}:
        if winner not in AUTHORITY_CLASSES:
            problems.append(f"{tag}: a RESOLVED conflict needs a winning_authority in {', '.join(AUTHORITY_CLASSES)}")
        if not _nonempty(c.get("resolution_reason")):
            problems.append(f"{tag}: a RESOLVED conflict must give resolution_reason")

    # Question-specific authority: the winner must be legitimate for the question type.
    qtype = c.get("question_type", "GENERAL")
    if qtype not in QUESTION_TYPE_WINNERS:
        problems.append(f"{tag}: question_type '{qtype}' must be one of {', '.join(QUESTION_TYPE_WINNERS)}")
    elif winner and winner in AUTHORITY_CLASSES and winner not in QUESTION_TYPE_WINNERS[qtype]:
        problems.append(
            f"{tag}: winning_authority '{winner}' is not appropriate for question_type "
            f"'{qtype}' (authority is question-specific, not a global ordering)"
        )

    # INVARIANT 1: implementation deviation must not rewrite the contract to the bug.
    if ctype in {"PRODUCT_DOC_VS_CODE", "NORMATIVE_VS_IMPLEMENTATION", "HUMAN_DECISION_VS_DOC"}:
        if winner == "VERIFIED_CURRENT_IMPLEMENTATION" and state != "IMPLEMENTATION_DEVIATES_FROM_CONTRACT":
            problems.append(
                f"{tag}: code differing from doc/spec/Human is a DEFECT - resolution must be "
                f"IMPLEMENTATION_DEVIATES_FROM_CONTRACT, not implementation 'winning' (do not "
                f"normalize the contract to the bug)"
            )
    if state == "IMPLEMENTATION_DEVIATES_FROM_CONTRACT" and not _nonempty(c.get("remaining_uncertainty")) \
       and not _nonempty(c.get("resolution_reason")):
        problems.append(f"{tag}: IMPLEMENTATION_DEVIATES_FROM_CONTRACT must explain the deviation")

    # INVARIANT 2: FluffyJaws / SUPPORTING_DISCOVERY cannot win over Human/normative.
    if winner == "SUPPORTING_DISCOVERY":
        problems.append(
            f"{tag}: SUPPORTING_DISCOVERY (e.g. FluffyJaws) can never be the winning "
            f"authority - route candidate -> applicability -> evidence -> disposition"
        )
    # Non-settling states must not silently support an AC.
    if c.get("supports_ac") and state in NON_SETTLING_STATES:
        disp = (c.get("disposition") or "").upper()
        if disp not in SAFE_OPEN_DISPOSITIONS:
            problems.append(
                f"{tag}: resolution '{state}' does not settle current truth - a claim that "
                f"supports an AC must be dispositioned {', '.join(sorted(SAFE_OPEN_DISPOSITIONS))}"
            )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["conflict_resolution"]
    conflicts = block.get("conflicts", [])
    if not isinstance(conflicts, list):
        return ["conflict_resolution.conflicts must be a list"]
    problems = []
    for i, c in enumerate(conflicts):
        problems.extend(validate_conflict(i, c))
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "EvidenceConflictResolver: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["conflict_resolution"].get("conflicts", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"EvidenceConflictResolver: {status} ({n} conflict(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Evidence-conflict resolver gate (UACFIX-02)")
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
