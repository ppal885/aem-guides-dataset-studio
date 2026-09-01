# Final UAC Linter and Testability Gate (UACFIX-07)

A final quality gate after synthesis, before presentation. Internally every AC should
resolve to CONDITION_OR_STATE, EXPECTED_BEHAVIOR, OBSERVABLE_ORACLE, SCOPE, and
EVIDENCE - the labels are not required in the final prose, but the substance must be
present and testable.

## Rules and where each is enforced

- **DUPLICATE_AC** - hard-enforced here on the final plan ACs (exact same outcome).
- **TESTABILITY contract** - hard-enforced here when the `uac_linter` block is present:
  every listed AC must supply condition_or_state, expected_behavior, observable_oracle,
  scope, and evidence.
- **OQ_CONTRADICTS_AC**, **SCOPE_MISMATCH** - hard-enforced here via the
  `uac_linter.oq_ac_contradictions` and `uac_linter.scope_mismatch_acs` lists, which
  must be empty (resolve upstream before rendering).
- **VAGUE_BEHAVIOR / EXCESSIVE_LENGTH / UNNECESSARY_JARGON / IMPLEMENTATION_LEAKAGE** -
  advisory REVIEW findings from `ac_readability.py` (a REVIEW makes the receipt
  non-postable but keeps the gate exit 0 so an existing plan is not silently broken).
- **UNSUPPORTED_ASSERTION** - `source_requirement_fidelity`.
- **NO_OBSERVABLE_ORACLE** - covered by the TESTABILITY contract (observable_oracle).
- **EXAMPLE_TREATED_AS_GENERIC_RULE**, **REFERENCE_OUTPUT_TREATED_AS_TARGET_CONTRACT**,
  **HISTORICAL_PATTERN_TREATED_AS_CURRENT_TRUTH** - the anti-hardcoding audit, UAC/source
  fidelity, and temporal-evidence gates.

## `uac_linter` block (opt-in)

```json
"uac_linter": {
  "testability": [
    {"ac_ref": "AC-01", "condition_or_state": "...", "expected_behavior": "...",
     "observable_oracle": "metadata.xml", "scope": "Native PDF preset", "evidence": ["Jira ..."]}
  ],
  "oq_ac_contradictions": [],
  "scope_mismatch_acs": []
}
```

## Language target

Prefer "Selected File properties must appear in metadata.xml for the correct topic."
over "The metadata semantic propagation pipeline must preserve per-asset association."
Technical precision belongs in the internal trace/debug, not the final UAC.

## Final oracle

Every material AC must have an observable oracle - final PDF, metadata.xml, editor
source, UI state, DB/API state, repository state, or generated JSON. Do not display
oracle internals unnecessarily.

## Auto-fix policy

A linter may safely rewrite grammar, duplication, and verbosity. It must NEVER
auto-change scope, a product decision, a technical expectation, or a candidate
disposition - those route back to the correct upstream stage. This gate flags material
issues; it does not silently rewrite them (MATERIAL_SEMANTIC_CHANGES_BY_LINTER = 0).

## Backward compatibility

No duplicate ACs and no `uac_linter` block -> clean pass.
