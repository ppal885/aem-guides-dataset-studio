"""Scope-applicability gate (UACFIX-03), backward-compatible.

WHY THIS EXISTS
---------------
Reasoning may investigate broadly, but the FINAL UAC scope must stay evidence-based
and minimal. A surface must not enter scope just because it shares a feature name,
product family, metadata name, DITA element, output category, a FluffyJaws
neighbouring doc, or a historical Jira analogy. Scope expansion requires SEMANTIC or
IMPLEMENTATION applicability. Final scope starts from the primary customer outcome +
the current Jira affected surface, and expands only with verified material
applicability. Unresolved shared-path applicability becomes an Open Question, not a
silent scope addition.

Backward-compatible: absent `scope_applicability` -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

SCOPE_STATES = (
    "DIRECT_SCOPE",
    "SHARED_PATH_REGRESSION",
    "REFERENCE_ONLY",
    "OPTIONAL_REGRESSION",
    "OUT_OF_SCOPE",
    "UNRESOLVED_SCOPE",
)

# States that place a surface INSIDE the accepted scope (need real applicability).
IN_SCOPE_STATES = frozenset({"DIRECT_SCOPE", "SHARED_PATH_REGRESSION"})

# Bases that are NEVER sufficient to expand scope on their own.
NAME_ONLY_BASES = frozenset({
    "SAME_FEATURE_NAME", "SAME_PRODUCT_FAMILY", "SAME_METADATA_NAME",
    "SAME_DITA_ELEMENT", "SAME_OUTPUT_CATEGORY", "FLUFFYJAWS_NEIGHBOR_DOC",
    "HISTORICAL_JIRA_ANALOGY",
})

# Bases that DO establish applicability.
APPLICABILITY_BASES = frozenset({
    "CURRENT_JIRA_AFFECTED_SURFACE", "HUMAN_REQUIREMENT", "VERIFIED_FIX_APPLICABILITY",
    "SEMANTIC_APPLICABILITY", "IMPLEMENTATION_APPLICABILITY",
    "SHARED_IMPLEMENTATION_PATH", "SHARED_SEMANTIC_PATH",
})

ALL_BASES = NAME_ONLY_BASES | APPLICABILITY_BASES

CONTRACT_RELATIONS = ("PRIMARY", "SECONDARY_SHARED", "NOT_CONTRACT")


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("scope_applicability"), dict)


def _nonempty_list(v):
    return isinstance(v, list) and any(isinstance(x, str) and x.strip() for x in v)


def validate_candidate(i, c):
    problems = []
    tag = f"scope_applicability.candidates[{i}]"
    if not isinstance(c, dict):
        return [f"{tag}: each candidate must be an object"]

    if not (c.get("candidate_ref") or "").strip():
        problems.append(f"{tag}: missing candidate_ref")

    status = c.get("scope_status")
    if status not in SCOPE_STATES:
        problems.append(f"{tag}: scope_status '{status}' must be one of {', '.join(SCOPE_STATES)}")

    basis = c.get("scope_basis")
    if basis not in ALL_BASES:
        problems.append(f"{tag}: scope_basis '{basis}' must be one of {', '.join(sorted(ALL_BASES))}")

    relation = c.get("customer_contract_relation")
    if relation not in CONTRACT_RELATIONS:
        problems.append(f"{tag}: customer_contract_relation must be one of {', '.join(CONTRACT_RELATIONS)}")

    # Core rule: a surface in scope needs real applicability, never a name-only basis.
    if status in IN_SCOPE_STATES:
        if basis in NAME_ONLY_BASES:
            problems.append(
                f"{tag}: '{status}' cannot rest on name-only basis '{basis}' - scope expansion "
                f"requires semantic or implementation applicability, not a shared name/family/element"
            )
        if not _nonempty_list(c.get("scope_evidence_ids")):
            problems.append(f"{tag}: '{status}' requires non-empty scope_evidence_ids")

    # SHARED_PATH_REGRESSION: shared path must be evidenced and kept distinct from the core contract.
    if status == "SHARED_PATH_REGRESSION":
        if not _nonempty_list(c.get("shared_path_evidence")):
            problems.append(f"{tag}: SHARED_PATH_REGRESSION requires shared_path_evidence (shared impl/semantic path)")
        if relation == "PRIMARY":
            problems.append(
                f"{tag}: SHARED_PATH_REGRESSION must stay distinct from the core customer contract "
                f"(customer_contract_relation must not be PRIMARY)"
            )

    # REFERENCE_ONLY / OPTIONAL_REGRESSION must not be promoted to an AC.
    if status in {"REFERENCE_ONLY", "OPTIONAL_REGRESSION"} and c.get("promotes_ac") is True:
        problems.append(f"{tag}: '{status}' must not promote an AC (it is not part of the accepted contract)")
    if status == "REFERENCE_ONLY" and relation == "PRIMARY":
        problems.append(f"{tag}: REFERENCE_ONLY cannot be the PRIMARY customer contract")

    # UNRESOLVED_SCOPE must become an Open Question, never a silent scope addition.
    if status == "UNRESOLVED_SCOPE":
        if not (c.get("open_question_ref") or "").strip():
            problems.append(
                f"{tag}: UNRESOLVED_SCOPE must reference an Open Question (open_question_ref); "
                f"do not silently add the surface to scope"
            )
        if c.get("promotes_ac") is True:
            problems.append(f"{tag}: UNRESOLVED_SCOPE must not promote an AC")

    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["scope_applicability"]
    problems = []

    if not (block.get("primary_customer_outcome") or "").strip():
        problems.append("scope_applicability.primary_customer_outcome is required (target surface first)")

    candidates = block.get("candidates", [])
    if not isinstance(candidates, list):
        return problems + ["scope_applicability.candidates must be a list"]

    for i, c in enumerate(candidates):
        problems.extend(validate_candidate(i, c))

    # Target-surface-first: at least one DIRECT_SCOPE candidate tied to the primary contract.
    has_primary_direct = any(
        isinstance(c, dict)
        and c.get("scope_status") == "DIRECT_SCOPE"
        and c.get("customer_contract_relation") == "PRIMARY"
        for c in candidates
    )
    if candidates and not has_primary_direct:
        problems.append(
            "scope_applicability: final scope must begin from a DIRECT_SCOPE candidate tied to the "
            "PRIMARY customer outcome / current Jira affected surface"
        )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "ScopeApplicability: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["scope_applicability"].get("candidates", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"ScopeApplicability: {status} ({n} candidate(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Scope-applicability gate (UACFIX-03)")
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
