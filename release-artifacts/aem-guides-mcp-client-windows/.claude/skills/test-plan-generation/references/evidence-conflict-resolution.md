# Evidence Conflict Resolution (UACFIX-02)

When normative semantics, current Human requirement, documented product behaviour,
current implementation, historical Human patterns, and AI hypotheses conflict, do
**not** silently choose one. Record the conflict and resolve it deterministically.
Extends `evidence_authority_resolver.py` — not a parallel final-truth pipeline.

## Conflict record (`conflict_resolution.conflicts[]`)

Each conflict: `claim_id`, `normalized_claim`, `supporting_evidence_ids`,
`conflicting_evidence_ids` (both non-empty — **preserve competing evidence**),
`conflict_type`, `question_type`, `winning_authority` (when resolved),
`resolution` (output state), `resolution_reason`, `remaining_uncertainty`, and
optional `supports_ac` / `disposition`.

## Conflict types

`PRODUCT_DOC_VS_CODE`, `HUMAN_DECISION_VS_DOC`, `CURRENT_VS_HISTORICAL`,
`NORMATIVE_VS_IMPLEMENTATION`, `CUSTOMER_EXPECTATION_VS_DOCUMENTED_BEHAVIOR`,
`VERSION_CONFLICT`, `SCOPE_CONFLICT`, `CONFIGURATION_CONFLICT`, `UNKNOWN_CONFLICT`.

## Output states

`RESOLVED_BY_HIGHER_AUTHORITY`, `RESOLVED_BY_CURRENT_VERSION`,
`IMPLEMENTATION_DEVIATES_FROM_CONTRACT`, `PRODUCT_DECISION_REQUIRED`,
`CURRENT_APPLICABILITY_REQUIRED`, `REFERENCE_ONLY`, `UNRESOLVED`.

## Authority is question-specific (not one global order)

General ordering — current Human product/UAC decision > normative semantic (for a
normative question) > current documented product behaviour > verified current
implementation applicability > historical Human analogy > AI inference — but the
**winner depends on the question**:

- "What does `@rowsep` mean?" → `NORMATIVE_SEMANTIC` (DITA), `question_type: NORMATIVE_SEMANTIC`.
- "What behaviour does AEM Guides promise?" → `CURRENT_HUMAN_DECISION` / `CURRENT_PRODUCT_DOC`, `question_type: PRODUCT_PROMISE`.
- "What does current code do?" → `VERIFIED_CURRENT_IMPLEMENTATION`, `question_type: IMPLEMENTATION_BEHAVIOR`.

The gate rejects a `winning_authority` that isn't legitimate for the `question_type`.

## Hard rules the gate enforces (`scripts/evidence_conflict_resolver.py`)

- **Implementation deviation ≠ rewrite the contract.** If doc/spec/Human say A and
  current code produces B, that is a **defect**: resolution must be
  `IMPLEMENTATION_DEVIATES_FROM_CONTRACT` (with reason), never
  "implementation wins". Do not normalize the contract to the bug.
- **FluffyJaws never wins.** `SUPPORTING_DISCOVERY` (FluffyJaws et al.) can never be
  the `winning_authority` over a current Human decision, normative DITA meaning, or
  a verified current Jira product decision. Route: candidate → applicability →
  evidence → disposition. No FluffyJaws → AC.
- **Non-settling states can't silently support an AC.** `PRODUCT_DECISION_REQUIRED`,
  `CURRENT_APPLICABILITY_REQUIRED`, `REFERENCE_ONLY`, `UNRESOLVED` supporting an AC
  must be dispositioned `OPEN_QUESTION` / `NEEDS_CURRENT_VERIFICATION` / `PRODUCT_DECISION`.

## Trace

Extend `debug_qe_miss` / candidate trace with `CONFLICTS_FOUND`,
`CONFLICT_RESOLUTION`, `WINNING_AUTHORITY`, `LOSING_EVIDENCE`, `WHY`.

## Backward compatibility

Absent `conflict_resolution` is a clean pass. See also
`references/temporal-version-evidence.md` (version applicability) and
`references/fluffyjaws-evidence.md` (discovery authority).
