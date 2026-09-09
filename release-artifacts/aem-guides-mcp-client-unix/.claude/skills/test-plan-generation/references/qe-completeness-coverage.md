# QE Completeness Coverage

Use this contract before calling a QE-owned UAC complete. It prevents checkable
acceptance behavior from being parked in `Open Questions`, `Regression Areas`,
or a `P3 [Regression]` scenario.

The gate does not guess intent from prose. When the plan contains at least one
real Open Question or regression item, the evidence manifest must explicitly
classify every such item in `qe_completeness`.

## Activation

The gate activates when either condition is true:

- `Open Questions` contains a real question; or
- `Regression Areas`, `P3 Regression`, or a `P3 [Regression]` scenario contains
  an item; or
- a QE/QA/reviewer-checks section contains an item (see the rule below).

The exact sentinel `No open questions from current evidence` is not a real
question. A plan with that sentinel and no regression items passes without a
`qe_completeness` block.

## Manifest Contract

```json
{
  "qe_completeness": {
    "schema_version": "aem-guides-qe-completeness-v1",
    "open_question_classification": [
      {
        "oq_ref": "OQ-01",
        "category": "GENUINE_PRODUCT_DECISION",
        "reason": "The product contract does not define which outcome is accepted.",
        "promoted_ac_ref": "AC-04",
        "can_be_ac_with_expected": false
      }
    ],
    "regression_classification": [
      {
        "item": "Exact regression bullet text from the plan",
        "category": "SAFETY_RETEST",
        "ac_ref": ""
      }
    ]
  }
}
```

`promoted_ac_ref` is required after a coverage item is promoted. `ac_ref` is
required for an `IN_SCOPE_BEHAVIOR`. Empty optional references may be omitted.

## Open Question Decisions

Use `GENUINE_PRODUCT_DECISION` only when QE cannot state the expected result
from the current acceptance contract and an authorized product, scope, or
engineering decision is required.

Use `DEFERRED_COVERAGE` when the item is checkable behavior and QE could write
an expected result. This category intentionally hard-fails: add a real AC,
record it in `promoted_ac_ref`, and remove or rewrite the Open Question so that
the checkable behavior is no longer deferred.

If a genuine decision still has `can_be_ac_with_expected=true`, prefer an AC
containing the QE-expected contract and allow development to down-scope it in
review. Without `promoted_ac_ref`, the gate emits `QE COMPLETENESS REVIEW:`. The
command keeps exit code 0, but the gate receipt is non-postable.

## Reviewer-requested Coverage Is Acceptance Coverage

For a UAC request, put each checkable, in-scope reviewer requirement in the
Acceptance Criteria. Do not move it to a separate `QE checks`, `QA checks`,
`Reviewer checks`, or `QE regression coverage` section instead. An unchanged
behavior explicitly required by the reviewer also belongs in the ACs.

Use a short setup/action and a clear expected result. Merge checks only when
they verify the same behavior; do not drop distinct coverage to shorten the
list. Keep unresolved product decisions in Open Questions. Do not invent an
expected result just to turn a question into an AC.

Before responding, map every requested check to an AC or a genuinely unresolved
Open Question. For UAC-only output, remove the separate checklist after this
review; no coverage should exist only there.

The gate recognizes QE/QA/reviewer check headings, including qualifiers such as
"retained from the review", and checks their bullet, numbered, or plain-text
items through the existing `regression_classification` ledger. Each such item
must be `IN_SCOPE_BEHAVIOR` with an `ac_ref` to an AC in the Acceptance Criteria
or Acceptance Contract section. A mention of an AC inside the checklist or a
code example does not count. Mislabeling these items as `SAFETY_RETEST` fails.
A mapped execution checklist may remain in a full test plan, but cannot
substitute for its ACs.

This is a structural guard, not a semantic proof: the author must still check
that the referenced AC actually covers the requirement. The gate never writes
ACs or decides unresolved product behavior.

## Regression Decisions

In a full test plan, use `SAFETY_RETEST` for optional, unchanged adjacent behavior
re-tested because the fix may affect it. It does not need an AC reference.
This exception does not apply to reviewer-required checks.

Use `IN_SCOPE_BEHAVIOR` when the item itself states behavior the ticket must
deliver. It must name a real plan AC in `ac_ref`; otherwise the item is only a
bare regression bullet and the gate fails.

Classify the exact normalized bullet text. Each plan Open Question and
regression item is classified exactly once. An Open Question reference must
also exist in `manifest.open_questions`.

## Illustrative Example

For an illustrative example, a changed shared formatter may require an
unchanged secondary output to be re-tested. That is `SAFETY_RETEST`. If the
ticket explicitly requires the secondary output to gain the new behavior, it
is `IN_SCOPE_BEHAVIOR` and needs its own AC.

## Gate Behavior

Hard failures start with `QE COMPLETENESS GATE:`. Advisory findings start with
`QE COMPLETENESS REVIEW:`. Run the full compatibility preflight after updating
the ledger:

```text
python scripts/run_gates.py --plan <body.md> --combined <combined.md> --manifest <manifest.json> --receipt <receipt.json>
```
