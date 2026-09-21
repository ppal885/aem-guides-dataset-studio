# Attachment and Visual-Reference Coverage

Use this contract when an **inspected** attachment or user-provided visual reference
shows all of the following:

- a named UI surface;
- a visible artifact or control; and
- two or more observable state variants.

This is a discovery and disposition contract. It prevents a broad feature label from
hiding a named surface or visible state shown by a reference. It does not expand scope
to other screens, controls, or states that the reference does not show.

The write/read consumer-parity extension also applies when current evidence names a
control that edits a value and a distinct UI surface that displays or tag-renders that
same value. It is bounded to the named writer, reader, and value; it does not imply
parity for nearby controls or surfaces.

The UI-action extension applies when an AC would name a selectable option or action.
It separates proof that the control exists on the named surface from proof of the
configured or documented result that follows it.

## Evidence boundary

- Download and inspect an attachment before recording a visual fact. Do not infer UI
  facts from an attachment filename, alt-text guess, or attachment type.
- Record screenshots and comparison-product visuals with
  `observation_authority: OBSERVATION_ONLY`. They prove only what is visibly shown:
  a surface name, an artifact/control, and its observed state variants.
- A visual observation cannot establish desired product behavior. Only Jira, a direct
  user decision, or an accepted product source can promote a state to AC coverage or
  scope it out.
- A comparison-product visual is a UI fact/retrieval lead, not a parity requirement.
  Ask an Open Question when its desired behavior has not been accepted.

## Manifest contract

Declare each inspected source at the top level:

```json
{
  "visual_reference_evidence": [
    {
      "source_ref": "ATTACH-VISUAL-01",
      "source_kind": "ATTACHMENT",
      "reference_context": "CURRENT_PRODUCT",
      "inspected": true,
      "observation_authority": "OBSERVATION_ONLY",
      "surface": "Properties panel",
      "visible_artifact": "Value indicator",
      "state_variants": [
        {
          "state_id": "STATE-EMPTY",
          "observation": "The indicator is absent when no value is present.",
          "material": true
        },
        {
          "state_id": "STATE-PRESENT",
          "observation": "The indicator is shown when a value is present.",
          "material": true
        }
      ]
    }
  ]
}
```

Use `source_kind: ATTACHMENT` for a downloaded ticket attachment and
`USER_PROVIDED` for an image or visual supplied directly in the current request.
Use `reference_context: COMPARISON_PRODUCT` when the visual shows another product.

When `visual_reference_evidence` is non-empty, add
`dimension_inventory.visual_reference_coverage` with schema
`aem-guides-visual-reference-coverage-v1`. It must map every source to:

- a separately dispositioned observed surface; and
- every observed `material: true` state variant.

`dimension_inventory_not_applicable` cannot bypass an inspected visual reference.

Each surface/state disposition is one of:

- `COVERED_BY_AC`: include `ac_refs`, plus
  `desired_behavior_authority` (`JIRA`, `USER`, or `ACCEPTED_PRODUCT_SOURCE`) and
  distinct `desired_behavior_evidence_refs`;
- `OPEN_QUESTION`: include `open_question_ref`; or
- `OUT_OF_SCOPE`: include a concrete reason plus a Jira/user/accepted-product scope
  authority and evidence reference.

Never use the visual source itself as the desired-behavior or scope authority. A state
marked `material: false` needs a concrete materiality reason and does not require a
coverage disposition.

## Write/read consumer parity

When current evidence names a value writer and reader, record the pair even when the
source is not a visual reference:

```json
{
  "write_read_consumer_parity_evidence": [
    {
      "pair_id": "VALUE-PAIR-01",
      "value_name": "Display value",
      "write_surface": "Value editor",
      "write_control": "Display field",
      "read_surface": "Summary view",
      "read_artifact": "Display tag",
      "source_refs": ["SRC-CURRENT-UI-PAIR"]
    }
  ]
}
```

The writer and reader must be distinct named surfaces. `source_refs` record the
current evidence that names the value relationship; they do not, by themselves,
approve the expected behavior.

For every declared pair, add
`dimension_inventory.write_read_consumer_parity` with schema
`aem-guides-write-read-consumer-parity-v1` and one matching `pair_id`. Its
disposition is one of:

- `COVERED_BY_AC`: provide `ac_refs`, a Jira/user/accepted-product authority, and
  its evidence references. At least one mapped AC must name the value, write surface
  and control, and read surface and artifact, and state that the edit is reflected
  there.
- `OPEN_QUESTION`: provide `open_question_ref` when the required read-after-write
  result is not yet decided.
- `OUT_OF_SCOPE`: provide a concrete reason plus Jira/user/accepted-product scope
  authority and evidence references.

Do not use `dimension_inventory_not_applicable` to bypass a named write/read pair.

## UI action/surface proof

A configured or documented outcome is not proof that a separate selectable UI option
or action exists. A source-backed requested outcome remains in the authoritative
source-to-UAC mapping even when current evidence does not prove a claimed existing
action. Do not delete or narrow that outcome to make an action-proof failure pass.

Use this contract only for an AC claim that an option/action already exists on a
surface. A source that names an outcome, setting, or backend effect without a
surface-specific control is not action proof. If that existing-action assertion is
unproven, retain the desired outcome separately and expose the assertion as an
implementation Open Question.

For every named selectable UI option/action in an AC, declare one current-evidence
record:

```json
{
  "ui_action_surface_evidence": [
    {
      "action_id": "UI-ACTION-01",
      "action_name": "Apply selection",
      "surface": "Settings panel",
      "claim_status": "PROVEN",
      "evidence_surface": "Settings panel",
      "proof_kind": "SELECTABLE_UI_ACTION_ON_SURFACE",
      "evidence_kind": "INSPECTED_UI",
      "evidence_refs": ["SRC-CURRENT-SETTINGS-CONTROL"]
    }
  ]
}
```

`evidence_surface` must match `surface`. The evidence must establish both the named
action and its presence on that surface. Use one of these evidence kinds:

- `INSPECTED_UI` for an inspected current visual/control;
- `INSPECTED_IMPLEMENTATION` for an inspected UI implementation bound to the surface;
- `APPLICABLE_PRODUCT_DOCUMENTATION` for documentation that names both the action and
  applicable surface;
- `INSPECTED_DESIGN` for an inspected design that explicitly places the action there.

Do not use a configuration outcome, a documented result, a class/configuration name,
accepted scope alone, or evidence from another surface as this proof. Accepted scope can
approve the expected result, but it cannot by itself prove an existing selectable action.

For each record, add `dimension_inventory.ui_action_surface_coverage` with schema
`aem-guides-ui-action-surface-coverage-v1` and the matching `action_id`:

```json
{
  "ui_action_surface_coverage": {
    "schema_version": "aem-guides-ui-action-surface-coverage-v1",
    "actions": [
      {
        "action_id": "UI-ACTION-01",
        "disposition": "COVERED_BY_AC",
        "reason": "The accepted scope names the observed selectable control.",
        "ac_refs": ["AC-03"],
        "desired_behavior_authority": "JIRA",
        "desired_behavior_evidence_refs": ["SRC-JIRA-ACTION-SCOPE"]
      }
    ]
  }
}
```

The action disposition is one of:

- `COVERED_BY_AC`: provide `ac_refs`, a Jira/user/accepted-product authority, and
  its evidence references. At least one mapped AC must name both the action and surface.
- `OPEN_QUESTION`: provide `open_question_ref` when the expected outcome remains
  undecided.
- `OUT_OF_SCOPE`: provide a concrete reason plus Jira/user/accepted-product scope
  authority and evidence references.

Action-existence proof and desired-behavior authority are separate. A visible or
implemented control can prove that the action exists, but it cannot independently
approve the product outcome. `dimension_inventory_not_applicable` cannot bypass a
declared UI action/surface record.

For an unproven existing-action assertion, do not supply a guessed proof. Record:

```json
{
  "action_id": "UI-ACTION-02",
  "action_name": "Apply selection",
  "surface": "Settings panel",
  "claim_status": "UNVERIFIED",
  "unverified_reason": "Current evidence names an outcome but does not show this control on the surface.",
  "open_question_ref": "OQ-01",
  "claim_evidence_refs": ["SRC-JIRA-REQUEST"]
}
```

Its matching `ui_action_surface_coverage` record must also use `OPEN_QUESTION`
and the same `open_question_ref`. This records an implementation-evidence gap; it
does not decide the requested outcome's source-to-UAC disposition.

## Authoring consequences

- Name the observed surface and artifact exactly enough for a tester to locate them.
- Preserve every observed material state as an AC, Open Question, or evidence-backed
  out-of-scope decision. Omission is not a scope decision.
- When a named control edits a value that a named surface renders, cover the
  read-after-write result in one AC or leave a concrete Open Question/out-of-scope
  decision. Do not replace this relationship with a broad feature label.
- When an AC asserts an existing selectable UI option/action, name its exact surface
  and bind both to surface-specific action proof. Keep configured or documented
  outcomes as outcomes; do not invent a separate UI control for them. An unsupported
  existing-action assertion becomes an implementation Open Question while the
  source-backed requested outcome stays covered independently.
- Keep an observed visual fact separate from the expected behavior. If the ticket does
  not say which variant is intended, write an Open Question rather than asserting the
  screenshot's outcome.
- Do not add an AC for a nearby surface merely because it looks related. Investigate it
  only when current evidence or a verified shared path makes it material.
