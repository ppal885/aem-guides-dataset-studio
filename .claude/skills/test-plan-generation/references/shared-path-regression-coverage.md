# Shared-Path Regression Coverage (generic anti-miss gate)

A recurring, high-cost miss: the plan proves from code that an implementation path is
SHARED across multiple consumers (a base class or method extended/used by several output
types, engines, callers, or UI surfaces) and then marks the OTHER consumers "out of
scope". If the code is shared, those consumers are a **shared-path regression** surface
- their behaviour/output can change - not out of scope.

Illustrative example: a metadata.xml builder method on a base executor class extended by
BOTH the DITA-OT and native output executors. When that shared builder changes, every
output type that extends it (site, HTML5, DITA-OT PDF) is shared-path regression - their
retained output (checked via their own Retain temporary files) must stay unchanged - not
out of scope.

## Rule the gate enforces (`scripts/shared_path_regression_coverage.py`)

The check activates when the Acceptance Criteria / Expected Behaviour / Regression Areas
/ Code Touched sections evidence a shared implementation path (signals: "shared by both",
"used by both", "extends <Class>", "shared code", "shared ... path", "base class",
"common handler/method/...", "same handler/method/... used by"). When active:

1. The plan MUST contain shared-path regression coverage of the other consumers - a
   "shared-path regression" statement, or a Regression Areas bullet that re-runs/re-tests
   the other output types / callers / surfaces.
2. An acceptance criterion MUST NOT mark a consumer "out of scope" while shared code is
   evidenced and no regression covers it.

Plans with no shared-path evidence are unaffected.

## The deeper lesson

Structural/consistency gates cannot force discovery of a dimension the author skipped.
When code shows a shared path, the correct disposition for other consumers is
SHARED_PATH_REGRESSION (see `scope_applicability` and `entry_point_equivalence`), never a
silent OUT_OF_SCOPE. This forcing gate makes that non-optional. When a new recurring miss
class is found, add a signal-activated forcing gate, prove it catches the exact miss with
a negative fixture, and confirm existing gated plans still pass.

Backward-compatible: no shared-path evidence -> clean pass.
