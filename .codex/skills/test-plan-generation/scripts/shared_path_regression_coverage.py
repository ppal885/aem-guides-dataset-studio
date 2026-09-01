"""Shared-path regression coverage gate (generic anti-miss), backward-compatible.

WHY THIS EXISTS
---------------
A recurring, damaging miss class: the plan proves (from code) that an implementation
path is SHARED across multiple consumers - a base class or method extended/used by
several output types, engines, callers, or UI surfaces - and then marks the OTHER
consumers "out of scope". If the code is shared, those other consumers are a
SHARED-PATH REGRESSION surface (their behaviour/output can change), not out of scope.
Marking them OOS silently under-covers the fix.

This is a HARD, signal-activated forcing gate (like publishing_scope_coverage and
value_provenance_coverage): when the plan evidences a shared implementation path across
consumers, it MUST cover those consumers as shared-path regression, and MUST NOT mark
them out of scope. Plans with no shared-path evidence are unaffected.

Generic only. Stdlib only.
"""
from __future__ import annotations

import re

# Evidence that an implementation path is shared across multiple consumers.
SHARED_SIGNALS = (
    r"shared by both", r"shared by the", r"used by both", r"extends [A-Z][A-Za-z0-9_]+",
    r"shared code", r"shared implementation", r"shared [A-Za-z ]*path",
    r"same (?:handler|method|code|class|path|service|pipeline) used by",
    r"base class", r"common (?:handler|method|code|path|service)",
)
SHARED_RE = re.compile("|".join(SHARED_SIGNALS), re.IGNORECASE)

# Shared-path regression coverage present.
REGRESSION_RE = re.compile(
    r"shared[\s-]?path regression|shared[\s-]?path .*regress|regress[a-z]* .*shared[\s-]?path",
    re.IGNORECASE,
)
# A regression bullet re-testing the other consumers/outputs also satisfies coverage.
OTHER_CONSUMER_REGRESSION_RE = re.compile(
    r"re-?run|re-?test|regress[a-z]*", re.IGNORECASE)

OOS_RE = re.compile(r"\bout[\s-]?of[\s-]?scope\b", re.IGNORECASE)
OUTPUT_CONSUMER_RE = re.compile(
    r"\b(preset|output type|aem site|html5|dita-ot|json|consumer|surface|caller|engine)\b",
    re.IGNORECASE)


def _section(plan_text, name):
    m = re.search(rf"\*\*{re.escape(name)}\*\*(.*?)(?:\n\*\*|\Z)", plan_text or "", re.S)
    return m.group(1) if m else ""


def is_shared_path_plan(plan_text):
    # Look in the substance sections, not the boilerplate.
    hay = "\n".join(_section(plan_text, s) for s in
                    ("Acceptance Criteria", "Expected Behaviour", "Regression Areas", "Code Touched"))
    return bool(SHARED_RE.search(hay))


def validate(manifest, plan_text=""):
    if not is_shared_path_plan(plan_text):
        return []
    problems = []
    acc = _section(plan_text, "Acceptance Criteria")
    regr = _section(plan_text, "Regression Areas")
    combined = acc + "\n" + regr

    has_regression = bool(REGRESSION_RE.search(combined)) or (
        bool(OTHER_CONSUMER_REGRESSION_RE.search(regr)) and bool(OUTPUT_CONSUMER_RE.search(regr))
    )
    if not has_regression:
        problems.append(
            "shared implementation path is evidenced across consumers, but no shared-path "
            "regression coverage is present - the other consumers (output types / callers / "
            "surfaces) that share the code must be re-tested as regression, not omitted"
        )

    # OOS for a consumer while the path is shared and no regression covers it is the miss.
    if OOS_RE.search(acc) and OUTPUT_CONSUMER_RE.search(acc) and not has_regression:
        problems.append(
            "an acceptance criterion marks a consumer out of scope while shared code is "
            "evidenced - consumers on a shared implementation path are shared-path regression, "
            "not out of scope"
        )
    return problems


def summarize(manifest, plan_text=""):
    if not is_shared_path_plan(plan_text):
        return "SharedPathRegressionCoverage: NOT_APPLICABLE (no shared-path evidence)"
    problems = validate(manifest, plan_text)
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"SharedPathRegressionCoverage: {status}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Shared-path regression coverage gate")
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
