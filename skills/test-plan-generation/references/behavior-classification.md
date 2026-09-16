# Existing-vs-New Behavior Classification

Documentation may establish current product behavior while the current ticket
proposes new behavior. "Documented today" must never be confused with "required
after this fix." Every resolved behavior is classified so coverage, promotion,
and the Writer keep evidence roles honest. Enforced by
`scripts/behavior_classification.py`; pairs with the mandatory research routing
in `references/question-research-routing.md`.

## Classification record (`behavior_classification.items[]`)

One item per resolved behavior: `target_ref` (the disposition/AC it classifies),
`behavior_class`, `existing_evidence_ids[]` (documentation / current
implementation), `requested_evidence_ids[]` (current ticket),
`change_evidence_ids[]` (change-set evidence), and optional `source_line`,
`coverage_disposition`, `open_question_ref`.

## Behavior classes

- `EXISTING_CONFIRMED` — established by existing documentation/current
  implementation evidence only (the documented baseline).
- `NEW_REQUIREMENT` — established by the current ticket or its change set only.
- `MODIFIED_EXISTING_BEHAVIOR` — documented behavior the ticket explicitly
  changes; requires both the documented baseline and the ticket's change
  evidence.
- `PRESERVED_EXISTING_BEHAVIOR` — documented behavior that must remain
  compatible after the change; coverage names it explicitly.
- `UNKNOWN` — insufficient evidence to classify; stays open until resolved.
- `CONFLICTED` — sources disagree; stays open until a Human settles it.

## Rules

1. Existing documentation can establish baseline/current behavior.
2. The current ticket can establish desired new behavior.
3. Existing documentation must not be used to claim that a new feature is
   already documented — `NEW_REQUIREMENT` cites no existing-behavior evidence.
4. New implementation/configuration must not be retroactively described as
   historical documented behavior — a change-set-only behavior is
   `NEW_REQUIREMENT`, never `EXISTING_CONFIRMED`.
5. Coverage explicitly identifies which existing behavior must remain
   compatible — `PRESERVED_EXISTING_BEHAVIOR` carries its existing-behavior
   evidence.
6. The Writer may combine sources in an AC's `Evidence:` line only when each
   source genuinely supports part of the final AC — a documentation source label
   requires existing-behavior evidence on the record.
7. The source line must not credit a documentation source for behavior that
   documentation does not establish.

## Worked shape (purge-style enhancement)

A documented retention parameter ("entries are purged after a configured
period") is `EXISTING_CONFIRMED`. A ticket-requested new retention mode is
`NEW_REQUIREMENT` — even if a documentation page about the general feature
matched during retrieval, that page does not establish the new mode, so it is
not cited. "Existing entries of other kinds must remain intact" is
`PRESERVED_EXISTING_BEHAVIOR`. A mode-combination semantic nobody has
established is `UNKNOWN` and stays an open question until resolved.

## Backward compatibility

Absent `behavior_classification` block: clean pass.
