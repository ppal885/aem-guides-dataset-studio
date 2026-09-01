# Localization Regression Coverage Contract

Use this contract when a current plan or evidence manifest shows that the changed
area can affect source content, metadata, reusable references, publishing, or a
localization workflow. This is a deterministic regression-coverage forcing gate.
It does not make localization part of accepted product scope automatically.

## Product Enumeration Source

The canonical product values come from the
[Translation Project API UAC Reference](../SKILL.md#translation-project-api-uac-reference):

- translation states: `Out of Date`, `In Progress`, `In Sync`, `Out of Sync`, and
  `Missing copy`;
- project types: `newTranslationProject`, `xliffTranslationProject`,
  `newMultiLingualTranslationProject`, `addToExistingProject`, and
  `newScopingTranslationProject`.

These values are documented AEM Guides enumerations, not ticket-specific examples.
The gate keeps each enumeration as a complete validated set. A familiar single
project type cannot stand in for the supported set.

## Activation

`scripts/localization_regression_coverage.py` examines the plan and manifest.
Coverage metadata such as `localization_coverage` and `security_coverage` does not
activate another gate by mentioning a product term in its reason.

Any of these current-change signals activates the localization ledger and the
`TRANSLATION_STATE` decision:

- source content, topic body, or map body;
- metadata or properties;
- conref, conkeyref, keyref, keydef, or reusable content;
- publishing or generated output;
- translation, localization, XLIFF, or multilingual scope in the ticket/component.

The narrower dimensions activate as follows:

- `XLIFF_ROUNDTRIP`: the change touches markup/content structure, or XLIFF is named.
- `PROJECT_TYPES`: translation-project creation, addition, type, or scope is touched,
  or a documented project-type value is named.

A plan with none of these signals remains backward-compatible and passes without a
`localization_coverage` block.

## Manifest Block

Once any signal is active, record all three dimensions. Map applicable dimensions
to ACs or one decision-shaped Open Question. Record every genuinely irrelevant
dimension as `NOT_APPLICABLE` with a concrete reason.

```json
{
  "localization_coverage": {
    "schema_version": "aem-guides-localization-coverage-v1",
    "dimensions": [
      {
        "dimension": "TRANSLATION_STATE",
        "disposition": "COVERED_BY_AC",
        "reason": "The changed metadata is read by content already in a translation project.",
        "ac_refs": ["AC-04"]
      },
      {
        "dimension": "XLIFF_ROUNDTRIP",
        "disposition": "NOT_APPLICABLE",
        "reason": "The change does not modify source markup or XLIFF conversion.",
        "ac_refs": []
      },
      {
        "dimension": "PROJECT_TYPES",
        "disposition": "OPEN_QUESTION",
        "reason": "The accepted project-creation scope is not defined.",
        "open_question_ref": "OQ-02"
      }
    ]
  }
}
```

Allowed dispositions are:

- `COVERED_BY_AC`: provide non-empty `ac_refs` that exist in the plan. The mapped
  ACs must represent the applicable localization dimension.
- `OPEN_QUESTION`: provide one `open_question_ref` that exists in the plan, contains
  `QA impact:`, and represents the unresolved localization decision.
- `NOT_APPLICABLE`: provide a concrete reason explaining why the signalled change
  does not exercise the dimension. A bare `N/A`, `none`, `unknown`, or similar
  placeholder fails.

## Required Dimensions

### TRANSLATION_STATE

For content already in a translation project, the mapped ACs or Open Question must
cover the effect of the change on translation status. At minimum, cover:

- transition or detection as `Out of Sync`; and
- `Missing copy` detection.

Other documented states remain available for the ticket-specific matrix, but this
gate does not force every state onto every content or publishing change.

### XLIFF_ROUNDTRIP

When source content or markup structure changes, the mapped ACs or Open Question
must cover XLIFF export and import as one round trip and preserve the affected
construct without markup, structure, or content loss. Name the affected construct
in the plan. The gate checks the dimension, not a specific sentence template.

### PROJECT_TYPES

When translation-project creation or scope changes, the mapped ACs or Open Question
must enumerate the complete supported project-type set:

- `newTranslationProject`
- `xliffTranslationProject`
- `newMultiLingualTranslationProject`
- `addToExistingProject`
- `newScopingTranslationProject`

The set may be covered in one matrix-backed AC or distributed across several mapped
ACs. Do not make one project type the only supported case.

## Boundaries

- Current Jira/UAC remains acceptance authority. Use `OPEN_QUESTION` when the
  expected localization effect is undecided; do not fabricate a Confirmed AC.
- This gate does not duplicate publishing, reference, metadata, configuration, or
  AC-language checks. It only forces a localization disposition and verifies its
  mapped dimension.
- A signal activates investigation, not automatic applicability. An explicit,
  concrete `NOT_APPLICABLE` disposition is valid when evidence proves the changed
  path does not participate in localization.
- Keep ticket-specific fixtures and implementation symbols outside this generic
  contract.

## Command

```text
python scripts/localization_regression_coverage.py --plan <plan.md> --manifest <manifest.json>
```

Exit `0` means the gate is inactive or every dimension has a complete disposition.
Exit `1` prints one or more stable `LOCALIZATION GATE:` failures.
