"""Final UAC linter and testability gate (UACFIX-07), backward-compatible.

WHY THIS EXISTS
---------------
A final quality gate after synthesis, before presentation. Internally every AC should
resolve to CONDITION_OR_STATE, EXPECTED_BEHAVIOR, OBSERVABLE_ORACLE, SCOPE, EVIDENCE
(the labels are not required in the final prose). The linter detects unclear language,
unsupported assertions, scope mismatch, implementation leakage, duplicate ACs,
untestable statements, AC/OQ contradictions, missing oracle, and overly broad wording.

Division of labour (to avoid duplicate/false-positive failures):
  * VAGUE_BEHAVIOR, EXCESSIVE_LENGTH, UNNECESSARY_JARGON, IMPLEMENTATION_LEAKAGE
    are advisory REVIEW findings already produced by `ac_readability.py`.
  * UNSUPPORTED_ASSERTION is enforced by `source_requirement_fidelity`;
    SCOPE name-only expansion by `scope_applicability`; MATERIAL_CANDIDATE_LOSS by
    `ac_language_policy`; EXAMPLE/REFERENCE/HISTORICAL misuse by the anti-hardcoding and
    UAC-fidelity gates.
  * This module hard-enforces the safe, unambiguous rules: DUPLICATE_AC on the final
    plan ACs (always on), and - when the author opts in with a `uac_linter` block -
    the per-AC TESTABILITY contract, AC/OQ contradictions, and scope mismatch.

Auto-fix policy: a linter may safely rewrite grammar, duplication, and verbosity, but
must NEVER auto-change scope, a product decision, a technical expectation, or a
candidate disposition - those route back upstream. This gate therefore only flags
material issues; it does not silently rewrite them.

Backward-compatible: no duplicate ACs and no `uac_linter` block -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

import re

AC_LINE_RE = re.compile(r"^-\s*(AC-\d+)\b(.*)$")
THEN_RE = re.compile(r"\|\s*Then\s*(.*?)\s*\|\s*Evidence", re.IGNORECASE | re.DOTALL)

REQUIRED_TESTABILITY_FIELDS = (
    "condition_or_state", "expected_behavior", "observable_oracle", "scope", "evidence",
)


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _plan_acs(plan_text):
    """Return {ac_id: then_text or full_text} from the plan Acceptance Criteria."""
    out = {}
    if not plan_text:
        return out
    in_ac = False
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**"):
            in_ac = "acceptance criteria" in stripped.lower()
            continue
        if not in_ac:
            continue
        m = AC_LINE_RE.match(stripped)
        if m:
            rest = m.group(2)
            then = THEN_RE.search(rest)
            out[m.group(1)] = _norm(then.group(1)) if then else _norm(rest)
    return out


def _duplicate_acs(plan_text):
    acs = _plan_acs(plan_text)
    problems = []
    seen = {}
    for ac_id, text in acs.items():
        if not text:
            continue
        if text in seen:
            problems.append(
                f"DUPLICATE_AC: {ac_id} repeats the same outcome as {seen[text]}; "
                f"merge them or make each AC a distinct product contract"
            )
        else:
            seen[text] = ac_id
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("uac_linter"), dict)


def _nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(isinstance(x, str) and x.strip() for x in v)
    return bool(v)


def _validate_block(manifest, plan_ac_ids):
    problems = []
    block = manifest["uac_linter"]

    testability = block.get("testability", [])
    if not isinstance(testability, list):
        problems.append("uac_linter.testability must be a list")
        testability = []
    for i, t in enumerate(testability):
        tag = f"uac_linter.testability[{i}]"
        if not isinstance(t, dict):
            problems.append(f"{tag}: each testability record must be an object")
            continue
        ac_ref = str(t.get("ac_ref", "")).strip()
        if not ac_ref:
            problems.append(f"{tag}: missing ac_ref")
        elif plan_ac_ids and ac_ref not in plan_ac_ids:
            problems.append(f"{tag}: ac_ref '{ac_ref}' is not an AC in the plan")
        for field in REQUIRED_TESTABILITY_FIELDS:
            if not _nonempty(t.get(field)):
                problems.append(
                    f"{tag}: missing '{field}' - every AC must resolve to condition, "
                    f"expected behaviour, an observable oracle, scope, and evidence"
                )

    # AC/OQ contradictions and scope mismatches must be resolved before rendering.
    for key, label in (("oq_ac_contradictions", "OQ_CONTRADICTS_AC"),
                       ("scope_mismatch_acs", "SCOPE_MISMATCH")):
        vals = block.get(key, [])
        if not isinstance(vals, list):
            problems.append(f"uac_linter.{key} must be a list")
        elif vals:
            problems.append(
                f"{label}: {sorted(str(v) for v in vals)} must be resolved upstream before "
                f"rendering (an AC must not contradict an Open Question or fall outside declared Scope)"
            )
    return problems


def validate(manifest, plan_text=""):
    problems = list(_duplicate_acs(plan_text))
    if is_present(manifest):
        problems.extend(_validate_block(manifest, set(_plan_acs(plan_text).keys())))
    return problems


def summarize(manifest, plan_text=""):
    problems = validate(manifest, plan_text)
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"UacLinter: {status}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Final UAC linter and testability gate (UACFIX-07)")
    ap.add_argument("--manifest")
    ap.add_argument("--plan")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    plan_text = ""
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as fh:
            plan_text = fh.read()
    print(summarize(manifest, plan_text))
    return 0 if not validate(manifest, plan_text) else 1


if __name__ == "__main__":
    raise SystemExit(main())
