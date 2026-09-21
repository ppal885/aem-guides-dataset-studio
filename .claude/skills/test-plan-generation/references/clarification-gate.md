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
   paths. When current evidence names a value-writing control and a distinct
   value-reading surface, enumerate that exact writer/reader pair. Keep only
   candidates that can plausibly change this ticket's behavior.
   When an AC would name a selectable UI option/action, enumerate the action and its
   exact surface separately from any configured or documented outcome. Do not infer an
   action from an outcome.
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
- `ASSET_UPLOAD_CONFLICT`

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
- A named value-writing control and distinct value-reading surface requires
  `CODE_PATH_CONSUMER` and the dimension inventory's write/read consumer-parity
  disposition. The writer/reader relationship must be covered by an AC, exposed as
  an Open Question, or bounded out with a concrete evidence-backed reason.
- A named selectable UI option/action requires the dimension inventory's
  `ui_action_surface_coverage` disposition and surface-specific proof that the action
  exists there. A configured or documented outcome cannot satisfy that proof.
  This validation checks an existing-action assertion only. The authoritative
  source-to-UAC comparison runs first: preserve a requested outcome as AC, explicit
  out-of-scope decision, or genuine Open Question even if the claimed existing action
  is unsupported. Record that unsupported implementation claim as an Open Question;
  do not let it choose ticket scope.
- An asset-upload conflict signal requires `ASSET_UPLOAD_CONFLICT` plus the
  miss-probe gate's structured `asset_upload_conflict` disposition. Keep
  content-identity duplicate detection, name/path conflict, request dispatch,
  named deployments, affected behavior path, baseline actions, and documentation scope
  independently resolved or exposed. This proves investigation and disposition only:
  an evidence-backed out-of-scope, not-applicable, or preserved dimension does not need
  an AC merely because the signal matched. Name native AEM Assets controls as native
  Assets behavior; Create Version and Overwrite Files are native Assets flows. Do not
  call Overwrite Files “Replace” or credit either native action to Guides without
  evidence of a Guides-owned surface.

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

## Component dimension priors (data-backed, advisory)

When you enumerate the dimension space (Ask-First Workflow step 1), also consult
`scripts/data/component_dimension_priors.json`. It records, per Jira component, the
coverage dimensions that recur in real human UACs (measured over 310 human
`UAC_Done` tickets), so you consider the ones a senior QA usually includes for
that area instead of only the dimensions the one ticket names.

For the ticket's component, treat each `usually_expected` dimension as a
candidate you must actively decide on: cover it in an AC, expose it as an Open
Question, or record why it is out of scope for this specific ticket. High-signal
examples from the corpus:

- Authoring -> all consumer UI surfaces (every panel/view/dropdown that shows the value), 63%.
- Publishing -> the output-preset matrix, 62%.
- Native PDF -> output presets 73%, negative/fallback 45%, state partitions 41%, CSS/rendition 36%.
- Asset Management -> negative/fallback, state partitions, all surfaces, provenance channels.
- Review / Editor -> all consumer UI surfaces (~50-65%), state partitions.
- Translation -> localization impact 91%, state partitions 73%.
- UUID Migration / Platform -> value-provenance channels and regression/parity.

The two dominant, most-missed dimensions across every component are **state
partitions** (both/with-and-without, profile, baseline, enumdef-bound vs not) and
**all consumer UI surfaces** (do not stop at the one panel the ticket names).

**Bind every prior to evidence - this is not optional.** A prior means
*investigate that dimension*, NOT *write an AC for it*. For each prior dimension:
verify it against the ticket, the attachments, the code consumers, or RAG, then
either (a) cover it in an AC that cites that evidence, (b) expose it as an Open
Question when a product decision is needed, or (c) record it out of scope with a
reason. **Never add an AC for a prior dimension just to "cover" it.** A held-out,
LLM-judged evaluation showed that injecting these priors as blanket "cover these
dimensions" guidance did NOT improve real coverage and *tripled hallucinations* -
the model padded acceptance criteria the ticket does not support. An unsupported
AC is a hallucination, and the judge (like a human reviewer and UAT) penalizes it
harder than an honest miss. The priors widen discovery; evidence, not the prior,
authorizes the AC. This is why `contract_facts` and `acceptance_promotions`
require a cited source: an AC with no evidence anchor must not ship.
