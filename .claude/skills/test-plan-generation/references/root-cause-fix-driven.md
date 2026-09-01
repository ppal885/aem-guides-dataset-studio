# Root-Cause / Fix-Driven Authoring

Use this contract whenever current evidence contains a positive root-cause or
implementation signal. The gate stays inactive for tickets that have no fix evidence,
including explicit statements that no PR, branch, commit, diff, or root cause is
available.

## Activation

Any of these signals activates `scripts/root_cause_fix_driven.py`:

- a concrete root-cause or RCA statement;
- a linked pull request, implementation commit, fix branch, or supplied diff;
- a positive merged, cherry-picked, hotfix, fixed-in, or verified-in-build claim; or
- an explicit `root_cause_fix` manifest block.

Activation is based on current evidence, not an issue key, customer, feature name, or
historical analogy. A negative availability statement such as "no development link or
PR is present" does not activate the gate.

## Manifest contract

Record the evidence-driven authoring decision under `root_cause_fix`:

```json
{
  "root_cause_fix": {
    "root_cause": "The resolver flattened child text without preserving semantic boundaries.",
    "fix_contract": "Collect eligible child text while keeping excluded semantic children separate.",
    "fix_adds": [
      "Labels include text from eligible non-primary children."
    ],
    "fix_preserves": [
      "AC-02: Nested primary children remain separate from the parent label."
    ],
    "fix_introduced_risks": [
      {
        "risk": "A sibling with its own display meaning could be appended to the label.",
        "mapped_ac": "AC-03",
        "open_question_ref": null
      }
    ],
    "added_tests": [
      {
        "path": "tests/unit/label-resolution.test",
        "layer": "unit",
        "proves": "Eligible child text is retained while nested primary content stays separate."
      }
    ],
    "verification_performed": "One local build and the added unit test.",
    "verification_gap": [
      "Other preset and processing-engine combinations",
      "Rendered end-to-end output",
      "Consumers that share the resolver"
    ],
    "lifecycle_stage": "Post-Fix Validation"
  }
}
```

Each `fix_preserves` entry must name the real `AC-##` that guards the invariant. A
fix-introduced risk must map to a real Negative AC or a real `OQ-##`. Do not leave the
risk only in narrative regression text.

If inspection finds no plausible new risk, use an empty `fix_introduced_risks` list
only with a concrete `no_new_risk_reason`. A placeholder such as `none`, `N/A`, or
`unknown` is not a disposition.

## Required authoring behavior

1. Use `Implementation Review` while the fix is being reviewed, or `Post-Fix
   Validation` after a candidate fix/build exists. Positive fix evidence is
   incompatible with `Pre-Development`.
2. Convert the fix contract into observable acceptance outcomes. Map every preserved
   invariant to a real AC so the broader change cannot erase old behavior.
3. Derive risks from what the fix newly reads, writes, broadens, filters, caches,
   retries, or shares. Map each material risk to a Negative AC or expose the unresolved
   product decision as an Open Question.
4. When the fix adds a test, report the main feature as at least `Partially covered` at
   that layer. Separately name remaining end-to-end, configuration, engine, version,
   and shared-consumer gaps.
5. Treat developer verification as evidence of what ran, not proof of everything.
   When it covers only one build, unit test, or narrow smoke run, name the untested QA
   sign-off scope in `verification_gap`.

## Failure behavior

Every hard failure starts with `ROOT-CAUSE/FIX GATE:`. The gate fails when an activated
plan omits the block or fix contract, uses a pre-development lifecycle, drops a
preserved invariant or fix-introduced risk, understates automation despite an added
test, or treats narrow developer verification as complete QA sign-off.
