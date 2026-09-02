# Signal-Activated Manifest Completeness

## Why this gate exists

Several reasoning gates remain backward-compatible: when their manifest block is
absent, they return a clean "not declared" result. That behavior is safe only when
the block is genuinely not applicable. It is unsafe when the plan or behavior model
already contains a reliable applicability signal.

`scripts/manifest_completeness_gate.py` closes that omission path. It reuses the
existing signal detectors; it does not add Jira-specific keywords or a second
reasoning route.

## Registry

The public `SIGNAL_REQUIRED_BLOCKS` registry maps these generic signals to existing
manifest blocks:

- Explicit behavioral reasoning (`behaviour_matters=true`, `behavior_model`, or
  `coverage_hypotheses`) requires the canonical semantic pipeline blocks:
  `contract_facts`, `issue_domains`, `behavior_model`, `behavior_graph`,
  `semantic_closure`, `coverage_hypotheses`, `missing_questions`,
  `evidence_lifecycle`, `verifications`, `dispositions`, and
  `acceptance_promotions`.
- Behavioral reasoning also requires `clarification`.
- The existing publishing/preset detector requires `publishing_scope`.
- The existing value-write detector requires `clarification`.
- The existing shared-code-path detector requires `clarification`, `change_impact`,
  `scope_applicability`, and `entry_point_equivalence`.
- A populated `behavior_model.versioned_models` signal requires
  `temporal_evidence`.
- Populated `behavior_model.generated_artifacts` or `artifact_shapes` requires
  `generated_output_contract`.

`behaviour_matters=false` keeps the established opt-out for the canonical behavior
pipeline. It does not erase independent publishing, value-write, or shared-path
signals already present in the plan.

## Presence rule

A required top-level block must be a non-empty JSON object or array. Empty objects,
empty arrays, `null`, strings, booleans, and numbers do not satisfy the gate. A
schema-bearing object is non-empty, but it must still pass its owning validator.

The completeness gate does not validate the internal schema of the required block.
It only prevents the owning gate from being skipped. An explicit empty
`missing_questions` list is allowed when investigation found no remaining question;
the material-gap and retrieval validators still run. `run_gates.py` continues to run
the owning validator afterward.

## Migration waivers and reviewed escapes

New behavioral plans must follow `v3-reasoning-authoring.md`, not use a v2 fixture
and blanket waivers. When behavior matters, `behavior_model`,
`coverage_hypotheses`, and `verifications` cannot use ordinary author waivers in
either schema. Omitting them hard-fails.

A reasoning waiver in v3, or a protected core-block waiver in v2, requires a
recorded `reviewed_escape` object with `decision: APPROVED`, a non-empty
`reviewed_by` distinct from `waived_by`, and a non-empty `review_ref` identifying
the actual review. This records Human review; it cannot authenticate the reviewer.
Never invent that approval. The escape remains REVIEW and **non-postable**.

For the transition window, other structural v2 waivers retain their existing
presence behavior. Every reasoning waiver, even an unused or reviewed one, emits
`REVIEW REASONING WAIVER` and makes the receipt non-postable. This includes semantic,
retrieval, disposition, promotion, shared-path, and applicability blocks. A waiver
does not turn off validation of a populated block or authorize a partial record.

Example of an attributable non-core legacy omission (not a new authoring template):

```json
{
  "block_waivers": [
    {
      "block": "publishing_scope",
      "reason": "No version-scoped source was available in this legacy captured run.",
      "waived_by": "author"
    }
  ]
}
```

Every waiver must be an object with string-valued, non-empty `block`, `reason`, and `waived_by`.
Duplicate waivers for one block fail. A waiver is traceability, not acceptance truth:
it neither creates evidence nor makes the omitted gate pass semantically.

## Failure contract

Every hard failure begins with `COMPLETENESS GATE:` and names the missing block plus
the signal or signals that activated it. Populate real reasoning to clear it.
An exceptional reviewed omission is an incomplete review record, not a passing
reasoning pipeline or permission to post. Missing-source honesty still applies.

Run the gate directly with:

```text
python scripts/manifest_completeness_gate.py --plan <full-plan.md> --manifest <evidence-manifest.json>
```

The same check runs automatically inside `scripts/run_gates.py`.
