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
It only prevents the owning gate from being skipped. `run_gates.py` continues to run
the owning validator afterward.

## Explicit waiver

If a producer cannot populate an activated block, it must record the omission:

```json
{
  "block_waivers": [
    {
      "block": "temporal_evidence",
      "reason": "No version-scoped source was available in this legacy captured run.",
      "waived_by": "author"
    }
  ]
}
```

Every waiver must be an object with a non-empty `block`, `reason`, and `waived_by`.
Duplicate waivers for one block fail. A waiver is traceability, not acceptance truth:
it neither creates evidence nor makes the omitted gate pass semantically.

## Failure contract

Every hard failure begins with `COMPLETENESS GATE:` and names the missing block plus
the signal or signals that activated it. The author must either populate the real
block or add an attributable waiver with a concrete reason.

Run the gate directly with:

```text
python scripts/manifest_completeness_gate.py --plan <full-plan.md> --manifest <evidence-manifest.json>
```

The same check runs automatically inside `scripts/run_gates.py`.
