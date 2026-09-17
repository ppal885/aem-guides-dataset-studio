# Behavioral Coverage Expansion

## The problem this solves

Evidence authority was already strong: sources were classified, research was
routed, and acceptance promotion was strict. The weakness was one stage earlier,
in **coverage discovery**. The plan captured the explicit ask and stopped there.

A ticket says *"the displayed order must match the exported order"*. The literal
reading produces two things: an ordering contract and a UI/export parity
contract. Both are correct, and both are incomplete, because the same change can
regress behaviors nobody wrote down:

- where the displayed value actually comes from;
- what is shown when the value is missing;
- whether the value can be supplied indirectly through referenced or reused
  content;
- what happens when the underlying item is moved or renamed;
- whether the value can go stale after its source changes;
- whether every consumer surface resolves it the same way.

None of those appear in the ticket text. All of them can break.

## The fix: broad discovery, strict promotion

`BehavioralCoverageExpander` runs between `BehaviorModelBuilder` and
`SemanticBehavioralClosureExplorer`. It reads the requirement's *shape* and
widens the set of dimensions closure must dispose of.

```
BehaviorModelBuilder
  -> BehavioralCoverageExpander      <- derives triggers, activates dimensions
  -> SemanticBehavioralClosureExplorer
  -> MissingQuestionGenerator
  -> ResearchRequirementClassifier
  -> ... unchanged ...
  -> AcceptancePromotionGate
```

Activating a dimension is enough. Closure already emits a row for every
(entity x dimension) pair, unresolved rows already become missing questions, and
missing questions already route into research. So expansion needs no new
plumbing and changes nothing about how a criterion is accepted.

## Triggers are requirement-shaped, never feature-named

A trigger fires on what the requirement *does*, using ordinary English that any
product family uses. It never fires on an AEM feature name.

| Trigger | Fires on requirement language such as |
| --- | --- |
| `DISPLAYED_VALUE` | display, shown, listed, column, label, title, visible |
| `EXPORTED_VALUE` | export, download, report, generated file, csv |
| `ORDERING_RULE` | order, sort, sequence, position, hierarchy |
| `COMPARED_OR_FILTERED_VALUE` | filter, search, compare, match, group |
| `PERSISTED_VALUE` | persist, stored, saved, metadata, property |
| `RESOLVED_REFERENCE` | reference, resolve, reuse, link |
| `IDENTITY_REFERENCE` | move, rename, delete, path |
| `STATE_TRANSITION` | state, status, transition, enable, disable |
| `CONFIGURATION_DEPENDENCY` | configuration, setting, preset, profile, flag |
| `MULTIPLE_CONSUMER_SURFACES` | derived, not matched (see below) |

`MULTIPLE_CONSUMER_SURFACES` is never keyword-matched. It is derived two ways:

- **structurally** - two or more consumer / downstream-decision-consumer change
  surfaces exist; or
- **compositionally** - the requirement describes both a displayed form and an
  exported form of one value, which is two independent readings of the same
  thing whether or not the evidence declared two surfaces.

## Axes and the dimensions they activate

| Axis | Activated dimensions |
| --- | --- |
| `VALUE_PROVENANCE` | `VALUE_PROVENANCE` |
| `FALLBACK_AND_ABSENCE` | `FALLBACK`, `ABSENT_VALUE` |
| `VALUE_RESOLUTION_OR_INDIRECTION` | `VALUE_RESOLUTION_OR_INDIRECTION`, `REFERENCED_CONTENT`, `NESTED_REFERENCED_CONTENT` |
| `IDENTITY_AND_LIFECYCLE` | `LIFECYCLE`, `IDENTITY_CHANGE` |
| `CONTEXT_AND_SCOPE` | `PARENT_CONTEXT`, `CHILD_CONTEXT`, `HIERARCHY` |
| `CONSUMER_SURFACE_PARITY` | `CROSS_SURFACE_SYNC`, `ALTERNATE_REPRESENTATION` |
| `MUTATION_AND_FRESHNESS` | `MUTATION_FRESHNESS`, `PERSISTED_STATE` |
| `NEGATIVE_AND_BROKEN_RESOLUTION` | `BROKEN_RESOLUTION`, `NEGATIVE_STATE` |

**Identity change and lifecycle stay separate.** Moving or renaming an asset is
not the same product behavior as an entry changing state, so they are separate
dimensions that get separate closure rows, separate questions, and separate
dispositions. They are never collapsed to shorten the list.

`CONSUMER_SURFACE_PARITY` is the first deterministic path that activates
`ALTERNATE_REPRESENTATION` at all; before this stage that dimension was only
reachable through a mandatory family.

## The four invariants

1. **Triggers are requirement-shaped.** Every candidate records the generic
   trigger that activated it. A candidate that cannot name one is invalid.
2. **Discovery is bounded and deterministic.** One candidate per
   (axis, subject); subjects come from the behavior model's primary entities
   and the change surfaces, capped so a broad ticket cannot explode the plan.
   The same input always produces the same `covexp:` candidate ids.
3. **Discovery is not acceptance.** A candidate carries no acceptance
   authority. Its id lives in the `covexp:` namespace and can never appear as a
   promoted acceptance candidate. The promotion path is untouched, so an
   explicitly accepted Human contract still completes without being blocked by
   newly discovered questions.
4. **No silent loss.** Every dimension a material candidate activates must be
   explicitly dispositioned. `BehavioralCompletenessGate` fails the plan when an
   activated dimension comes back not-applicable for every entity - that is the
   signature of a dimension being discovered and then quietly dropped.

## What expansion does *not* do

- It does not answer anything. An activated dimension with no evidence becomes a
  missing question and routes through the existing mandatory research contract;
  `NOT_FOUND` still never asserts the opposite behavior.
- It does not promote. No candidate becomes an acceptance criterion.
- It does not change source authority, evidence roles, existing-vs-new behavior
  classification, or the Writer and Reviewer contracts.
- It does not add a gate. The stage name deliberately does not end in `Gate`,
  because the posting boundary derives its required gate set from stage names
  ending in `Gate` and the three canonical gates must stay exactly three.

## Manifest block

Optional and backward-compatible: absent means a clean pass. Validated by
`scripts/behavioral_coverage_expansion.py`.

```json
{
  "behavioral_coverage_expansion": {
    "schema_version": "aem-guides-behavioral-coverage-expansion-v1",
    "triggers": ["DISPLAYED_VALUE", "EXPORTED_VALUE", "MULTIPLE_CONSUMER_SURFACES"],
    "candidates": [
      {
        "candidate_id": "covexp:...",
        "axis": "VALUE_PROVENANCE",
        "subject": "the displayed topic title",
        "trigger": "DISPLAYED_VALUE",
        "dimensions": ["VALUE_PROVENANCE"],
        "question": "Where does the value shown for the displayed topic title come from?",
        "rationale": "A displayed value can be set through more than one channel; the stated ask does not say which one governs.",
        "material": true
      }
    ],
    "dispositions": [
      {
        "dimension": "VALUE_PROVENANCE",
        "disposition": "RESEARCH_REQUIRED",
        "reason": ""
      }
    ]
  }
}
```

`NOT_APPLICABLE` and `INVESTIGATED_AND_REJECTED` require a concrete `reason`: a
dimension may not be closed without testing it and without saying why.

## Authoring checklist

- Run the expander before authoring, not after a reviewer finds the gap.
- Read every activated dimension as a question you must answer from evidence, not
  as coverage you already have.
- Disposition each one explicitly. "Not mentioned in the ticket" is not a reason;
  say what in the evidence makes it inapplicable.
- Keep identity change, lifecycle state, and ordering as separate contracts.
- Do not convert a discovered candidate into an acceptance criterion because it
  sounds reasonable. It needs the same authority as anything else.
