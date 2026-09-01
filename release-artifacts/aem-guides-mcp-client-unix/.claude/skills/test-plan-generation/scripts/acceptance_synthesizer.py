"""Acceptance-contract synthesizer gate (UACFIX-06), backward-compatible.

WHY THIS EXISTS
---------------
Turn the finalized Candidate Ledger into a concise, QE-readable acceptance contract
WITHOUT losing distinct material coverage. Internal completeness stays detailed;
external UAC wording stays simple. Candidates are grouped by CUSTOMER-OBSERVABLE
CONTRACT (not by tag/file/symbol/words), merged only when they describe the same
customer-observable contract, and every synthesized AC retains its internal->external
trace so simplification never destroys traceability.

This complements `ac_language_policy.py` (which enforces MATERIAL_CANDIDATE_LOSS=0,
merge-safety, and language lints on the same `ac_synthesis` block). This gate adds the
grouping vocabulary and the required trace fields. It activates only when a final AC
declares a `synthesis_group`, so plans that do not use the synthesizer are unaffected.

Backward-compatible: absent `ac_synthesis`, or no `synthesis_group` declared -> pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

# Groups are CUSTOMER-OBSERVABLE contract classes, not implementation buckets.
SYNTHESIS_GROUPS = (
    "CORE_CUSTOMER_CONTRACT",
    "DIRECT_FIX_BEHAVIOR",
    "SHARED_REGRESSION",
    "NEGATIVE_BOUNDARY",
    "CONFIGURATION_BRANCH",
    "ORDERING_OR_ASSOCIATION",
    "LIFECYCLE",
    "FAILURE_RECOVERY",
)

# Internal->external trace fields every synthesized AC must retain.
REQUIRED_TRACE_FIELDS = ("candidate_ids", "evidence_ids", "scope_basis", "oracle")


def _final_acs(manifest):
    block = manifest.get("ac_synthesis") if isinstance(manifest, dict) else None
    if not isinstance(block, dict):
        return None
    acs = block.get("final_acs")
    return acs if isinstance(acs, list) else []


def is_present(manifest):
    acs = _final_acs(manifest)
    if not acs:
        return False
    return any(isinstance(a, dict) and a.get("synthesis_group") for a in acs)


def _nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(isinstance(x, str) and x.strip() for x in v)
    return bool(v)


def validate(manifest):
    if not is_present(manifest):
        return []
    acs = _final_acs(manifest)
    problems = []
    for i, ac in enumerate(acs):
        tag = f"ac_synthesis.final_acs[{i}]"
        if not isinstance(ac, dict):
            problems.append(f"{tag}: each final AC must be an object")
            continue

        group = ac.get("synthesis_group")
        if group is None:
            problems.append(
                f"{tag}: every synthesized AC must declare a synthesis_group "
                f"(customer-observable contract), not be grouped by tag/file/symbol/words"
            )
        elif group not in SYNTHESIS_GROUPS:
            problems.append(f"{tag}: synthesis_group '{group}' must be one of {', '.join(SYNTHESIS_GROUPS)}")

        # Internal->external trace must survive synthesis.
        for field in REQUIRED_TRACE_FIELDS:
            if not _nonempty(ac.get(field)):
                problems.append(
                    f"{tag}: missing trace field '{field}' - synthesis must retain "
                    f"candidate_ids, evidence_ids, scope_basis, and oracle so simplification "
                    f"never destroys traceability"
                )

        # Merged candidates must be part of this AC's candidate set.
        merged = ac.get("merged_candidate_ids") or []
        cand = ac.get("candidate_ids") or []
        if isinstance(merged, list) and isinstance(cand, list):
            cand_set = {str(x) for x in cand}
            missing = [str(x) for x in merged if str(x) not in cand_set]
            if missing:
                problems.append(
                    f"{tag}: merged_candidate_ids {missing} are not in candidate_ids - a "
                    f"merged AC must list every folded candidate in its candidate_ids"
                )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "AcceptanceSynthesizer: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(_final_acs(manifest) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"AcceptanceSynthesizer: {status} ({n} synthesized AC(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Acceptance-contract synthesizer gate (UACFIX-06)")
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
