# Ask-First Clarification Gate

Use this contract after behavior and coverage-hypothesis discovery, and before
acceptance criteria are written. Its purpose is to prevent a material product
dimension from being silently decided by assumption.

The gate records investigation state; it does not replace the existing publishing,
value-provenance, or shared-path AC-content gates. It reuses their applicability
signals and checks only that the corresponding dimension was enumerated and resolved.

## Activation

The `clarification` manifest block is mandatory when any of these is true:

- `behaviour_matters` is declared and is not `false`;
- `behavior_model` or `coverage_hypotheses` is present;
- the plan has an existing publishing/preset, value-written-to-output, or shared-code-path signal.

A non-activated legacy record may omit the block and continues to pass.

## Ask-first workflow

1. Enumerate every plausible behavior dimension before drafting ACs. Start with
   value-set channels, shared code consumers, output presets/engines, topic types,
   terminal states, lifecycle stages, configuration branches, roles, and migration
   paths. Keep only candidates that can plausibly change this ticket's behavior.
2. Mark each candidate material or non-material and state why.
3. Resolve material candidates from current evidence first. Cite the exact evidence.
4. If evidence cannot answer a material question and its answer changes scope, the
   oracle, or AC correctness, ask the user and stop authoring until it is answered.
5. Defer a question to `Open Questions` only when it is non-blocking. Record the real
   `OQ-##` identifier rather than a prose-only note.
6. Author ACs only after every material dimension has a supported disposition. Record
   real `AC-##` identifiers for dimensions covered by an AC.
7. Preserve the manifest trace. Never fabricate a user answer to make the gate pass.

## Manifest contract

```json
{
  "clarification": {
    "schema_version": "aem-guides-clarification-v1",
    "dimension_space": [
      {
        "dimension_id": "D-01",
        "axis": "VALUE_SET_CHANNEL",
        "candidate": "repository metadata node via CRX/DE",
        "material": true,
        "materiality_reason": "The output reads a value that can be set outside the authoring UI.",
        "resolution": "COVERED_BY_AC",
        "evidence_refs": ["E-03"],
        "ac_refs": ["AC-04"]
      }
    ],
    "questions_surfaced_to_user": [
      {
        "question_id": "CQ-01",
        "question": "Which configuration branch is the accepted behavior?",
        "blocking": true,
        "answer": "Use the current repository-backed configuration.",
        "answered_by": "user",
        "status": "ANSWERED"
      }
    ],
    "authoring_gated_on_answers": true
  }
}
```

Allowed axes are:

- `VALUE_SET_CHANNEL`
- `CODE_PATH_CONSUMER`
- `OUTPUT_PRESET`
- `TOPIC_TYPE`
- `TERMINAL_STATE`
- `LIFECYCLE`
- `CONFIG_BRANCH`
- `PERMISSION_ROLE`
- `MIGRATION_PATH`

Allowed resolutions are:

- `COVERED_BY_AC`
- `RESOLVED_FROM_EVIDENCE`
- `ASKED_AND_ANSWERED`
- `DEFERRED_OPEN_QUESTION`
- `UNRESOLVED`

`UNRESOLVED` is allowed only for a non-material dimension. A deferred question must
point to a declared Open Question, and AC coverage must point to an AC present in the
plan body.

## Required signal dimensions

- A publishing or preset signal requires `OUTPUT_PRESET`.
- A value-written-to-output signal requires `VALUE_SET_CHANNEL`, including a concrete
  repository-node or CRX/DE candidate.
- A shared-code-path signal requires `CODE_PATH_CONSUMER`.

These checks prove enumeration. The owning coverage gates remain responsible for the
actual AC wording and expected behavior.

## Blocking questions

Every blocking question must have `status: "ANSWERED"`, a non-empty `answer`, and
`answered_by: "user"` or `"evidence"`. If any blocking question exists,
`authoring_gated_on_answers` must be exactly `true`. A `WAITING` blocking question is a
hard stop: do not write or post the governed AC.

## Command

```text
python scripts/clarification_gate.py --plan <plan.md> --manifest <manifest.json>
```

All hard failures begin with `CLARIFICATION GATE:` and exit non-zero.
