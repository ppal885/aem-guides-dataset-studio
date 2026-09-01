# Upgrade and Migration Coverage Contract

Use this contract when the current ticket or evidence describes an upgrade,
stored-data migration, schema conversion, deployment migration, compatibility
boundary, or a fix-version boundary that changes persisted data or configuration
format. This is a deterministic test-coverage forcing gate.

## Relationship to Temporal Evidence

`scripts/temporal_evidence.py` decides whether an evidence item is current and
applicable to the version under test. It does not prove that an upgrade or migration
operation was tested.

`scripts/upgrade_migration_coverage.py` owns only the operation-level QA contract:
the starting state, execution behavior, resulting state, mixed-state behavior when
possible, and rollback or irreversibility. A `temporal_evidence` record cannot
substitute for this coverage ledger, and this ledger cannot change evidence
authority or currentness.

## Activation

The gate activates when the plan or evidence mentions any of these current-change
signals:

- a product version, release, service-pack, installation, or instance upgrade;
- stored-data, repository, schema, or configuration-format migration;
- conversion from non-UUID identifiers to UUID identifiers;
- migration from on-premise deployment to cloud deployment;
- backward or forward compatibility;
- a fix-version boundary together with a stored-data, schema, or configuration
  format change.

A plan with no such signal passes without an `upgrade_migration_coverage` block.
A coverage ledger belonging to another gate does not activate this one merely by
mentioning migration in a disposition reason.

Mixed-state coverage is required when evidence makes coexistence possible, including
a non-UUID-to-UUID conversion, an explicitly partial or mixed state, a rolling or
staged migration, or an interruptible/resumable migration. A generic version upgrade
does not invent a mixed-state requirement when current evidence does not support it.

## Manifest Block

Once activated, record all four dimensions. Map applicable behavior to existing ACs
or, where allowed below, one decision-shaped Open Question. Record every genuinely
irrelevant dimension as `NOT_APPLICABLE` with a concrete reason.

```json
{
  "upgrade_migration_coverage": {
    "schema_version": "aem-guides-upgrade-migration-coverage-v1",
    "dimensions": [
      {
        "dimension": "PRE_STATE",
        "disposition": "COVERED_BY_AC",
        "reason": "Existing legacy content is the input to the conversion.",
        "ac_refs": ["AC-01"]
      },
      {
        "dimension": "MIGRATION_EXECUTION",
        "disposition": "COVERED_BY_AC",
        "reason": "The migration operation and its terminal outcomes are in scope.",
        "ac_refs": ["AC-02", "AC-03", "AC-04"]
      },
      {
        "dimension": "POST_STATE_AND_MIXED",
        "disposition": "COVERED_BY_AC",
        "reason": "Old and converted records can coexist while conversion is incomplete.",
        "ac_refs": ["AC-05"]
      },
      {
        "dimension": "ROLLBACK_OR_IRREVERSIBILITY",
        "disposition": "OPEN_QUESTION",
        "reason": "The product contract does not define whether rollback is supported.",
        "open_question_ref": "OQ-01"
      }
    ]
  }
}
```

Allowed dispositions are:

- `COVERED_BY_AC`: provide non-empty `ac_refs` that exist in the plan.
- `OPEN_QUESTION`: allowed only for `PRE_STATE` and
  `ROLLBACK_OR_IRREVERSIBILITY`; provide an existing `open_question_ref` containing
  `QA impact:`. Execution and post-state behavior need testable ACs when applicable.
- `NOT_APPLICABLE`: provide a concrete reason. A bare `N/A`, `none`, `unknown`, or
  similar placeholder fails.

## Required Dimensions

### PRE_STATE

Cover content, data, identifiers, or configuration authored or stored in the old
format or source version before the operation. Testing only newly created content
after the upgrade does not prove migration compatibility. An Open Question is valid
when the authoritative source version or old-format fixture is genuinely undecided.

### MIGRATION_EXECUTION

Map one or more ACs that together cover:

- the upgrade or migration operation runs;
- it reaches successful completion;
- it is idempotent/rerunnable/resumable, or is explicitly defined as one-shot; and
- failures produce an observable report, message, status, diagnostic, or reason.

This dimension is AC-only when applicable. Do not use evidence applicability or a
generic operational note as a substitute for executing the operation.

### POST_STATE_AND_MIXED

Cover the migrated result in its new/target state. When current evidence permits an
incomplete conversion, also cover partially migrated content or old and new formats
coexisting. The mixed-state oracle must prove correct handling rather than merely
mentioning that two formats exist.

This dimension is AC-only when applicable. A verified atomic migration can use a
post-state AC without a mixed-state clause when evidence proves that no partial state
can exist. The complete dimension is `NOT_APPLICABLE` only when the changed path has
no persisted migration result at all.

### ROLLBACK_OR_IRREVERSIBILITY

State whether rollback/revert/restore is supported and what observable old-state
result it produces, or state that the migration is irreversible/one-way. Use a
QA-impact Open Question when product evidence has not decided that contract.

## Boundaries

- Current Jira/UAC remains acceptance authority. The gate never turns an
  implementation observation or historical migration into a Confirmed AC.
- This gate does not reclassify temporal evidence, choose source/target versions, or
  decide which release is current. Continue to use `temporal_evidence.py` for those
  decisions.
- It does not duplicate operational retry, performance, security, localization, or
  AC-language checks. It only forces an explicit migration test disposition.
- A signal activates investigation, not automatic applicability. A concrete,
  evidence-based `NOT_APPLICABLE` disposition remains valid.
- Keep ticket identities, customer names, implementation symbols, and one-off version
  literals outside this generic contract.

## Command

```text
python scripts/upgrade_migration_coverage.py --plan <plan.md> --manifest <manifest.json>
```

Exit `0` means the gate is inactive or every dimension has a complete disposition.
Exit `1` prints one or more stable `MIGRATION GATE:` failures.
