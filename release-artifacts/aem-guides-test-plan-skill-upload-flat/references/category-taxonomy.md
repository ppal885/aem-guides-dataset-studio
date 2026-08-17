# Scenario Category Taxonomy

Fixed checklist of categories to evaluate for every tag (DITA element or attribute). Not every
category applies to every tag — skip a category only when it's genuinely inapplicable (e.g. "Nested
Structures" doesn't apply to an empty, non-nestable element), and say so rather than silently omitting
it.

For each included category, produce one or more scenarios with: **Scenario ID**, **title**, **test
data** (real XML, using the grounded facts from the tag lookup — not invented syntax), **preconditions**,
**steps**, **expected result**, **validation layers** (Author view / Source view / Save / Reopen /
Repository / XML persistence / Generated output / Publishing logs / Browser console / Network API /
Backend metadata / JCR properties / Output artifacts — mention only the ones relevant to that scenario).

## A. Basic Functional
Insert, edit, delete, save, reopen, undo, redo, copy, paste — for the tag's actual valid contexts
(don't invent a context the content model doesn't support).

## B. XML Persistence
Author/Source view round-trip, DOCTYPE/namespace integrity, unrelated XML untouched by an edit.

## C. Multiple and Duplicate Usage
Multiple instances in one topic, repeated/duplicate values (same topic, same page, across topics,
across referenced maps), ordering, dedup behavior where applicable — many DITA tags (like index
entries) have real merge/dedup semantics; others don't. State which applies, based on the grounded
facts, not assumption.

## D. Nested Structures
Only if the element's content model actually permits self-nesting or meaningful nested children —
check `allowed_children`/`parent_element` from the grounded lookup before writing nesting scenarios.
One-level, two-level, three-level nesting; parent-only; child-only; multiple/duplicate children;
deleting parent vs. child; moving nested content.

## E. Attribute Coverage
For every attribute the tag actually supports (from `supported_attributes`/`attribute_usage` in the
grounded lookup — never attributes it doesn't have): valid value, alternate valid value, empty,
missing, invalid, duplicate, whitespace, case sensitivity, special characters, conflicting/unsupported
combinations.

**Processing Instruction (required per attribute):** alongside the value-coverage scenarios above,
add a short "Processing Instruction" note for every attribute explaining *how the processor actually
handles it at publish time* — not just what values are valid, but what happens to that value when
DITA-OT/Native PDF resolves the topic. For example: is it resolved at preprocessing time (like
`@conref`/`@keyref`) or carried through to final output as a literal (like `@outputclass`)? Does it
affect content inclusion/exclusion (profiling attributes), navigation/linking behavior, or purely
cosmetic output styling? Does Native PDF and DITA-OT process it identically, or is there a documented
difference (flag explicitly if unverified — don't assume parity, same rule as Section N). Ground this
in the attribute's `attribute_usage`/`default_behavior` fields from the registry lookup; if the
registry doesn't say, state that processing behavior is unverified and needs product/DITA-OT
verification rather than guessing.

## F. Negative Scenarios
Empty element, whitespace-only value, malformed XML, invalid nesting, invalid attribute, unsupported
child, missing required value, broken reference, invalid URI, unmatched/duplicate ID, invalid key,
circular reference, missing target — whichever are actually reachable for this tag.

## G. Boundary-Value
Empty, one character, minimum supported value, normal value, long value, extremely long value, large
number of instances, deep nesting, large topic, large map.

## H. Special Characters
`&amp;`, `/`, `+`, `.`, `-`, `,` and similar — validate XML escaping, rendering, sorting/search where
relevant, output generation, no double-escaping on repeated save.

## I. Unicode and Localization
Realistic multi-script values (Devanagari, CJK, German umlauts/accented Latin, Cyrillic, Arabic/RTL).
Validate UTF-8 preservation across Author/Source/save/reopen, searchability, font rendering in PDF
(cross-reference "Embed used fonts"), locale-aware sorting where the tag has sort semantics, no
replacement characters.

## J. Whitespace
Leading/trailing, internal multiple spaces, multi-line — validate normalization/trimming and whether
it affects de-duplication/matching, not just display.

## K. Profiling and Filtering
`@audience`/`@platform`/`@product`/`@props`/`@otherprops`/`@deliveryTarget` + DITAVAL include/exclude —
validate filtered content AND any secondary artifact the tag contributes (e.g. an index entry, a
generated link) is excluded together, not orphaned.

## L. Reuse
`@conref`/`@conkeyref`/`@keyref`/`@keyscope`/`@mapref`/`@topicref` interaction — only for tags that
plausibly appear inside reused content; missing source, circular reuse, reused content under different
filtering contexts in different reuse targets.

## M. Map-Level Coverage
Only if the tag can appear in a map/topicref/topicmeta context — root map, bookmap, child/referenced
map, topicgroup, topichead, nested topicref, same topic/map referenced multiple times.

## N. Publishing
**Gate this category first:** include Native PDF and DITA-OT PDF validation scenarios whenever the
tag/feature can plausibly affect published output — this covers essentially any DITA element,
attribute, metadata field, reference/reuse mechanism (`@conref`/`@keyref`/etc.), or filtering
behavior (DITAVAL/profiling attributes), since all of these flow into generated output one way or
another. **Skip PDF scenarios entirely** when the feature is strictly UI/editor-only with no
publishing-side effect (e.g. a Web Editor toolbar convenience, an authoring-time-only validation
message, a panel/dialog behavior that doesn't change the DITA source or its resolved output). State
explicitly which case applies and why, rather than defaulting to always-include or always-skip.

When PDF scenarios are included: Native PDF, DITA-OT PDF, HTML5/AEM Sites — generation succeeds,
expected content appears, excluded content absent, references resolve, output artifact correctness
(page numbers, links, generated lists). **Explicitly compare Native PDF vs. DITA-OT behavior — never
assume parity.** State clearly when actual behavior needs product verification.

## O. Performance and Scale
Realistic large numbers (100s–1,000s of instances, large topics/maps) — editor load/save/reopen time,
publish time, output completeness, no truncation/duplication/browser or backend timeout.

## P. Concurrent Editing
Only include when the tag's edits are meaningfully affected by standard lock/stale-content mechanics
(usually true for any authored element) — two-user open/edit/save/stale-content/lock-conflict sequence.

## Q. Editor Regression
Multi-tab, dirty marker, validation panel/error count, save-all, focus/cursor/selection retention
across undo/redo involving this tag.

## R. Error Handling
For every negative case above: editor doesn't crash, error is understandable and locates the affected
file, invalid content isn't silently saved, unrelated topics stay usable, publishing failures are
clearly logged.

## S. Automation Feasibility
Classify each scenario group by suitable automation approach (XML/file assertion, UI automation,
API + output validation, PDF/output comparison, performance suite, accessibility automation) and name
concrete, stable checkpoints (XML file content, network response, dirty marker, generated artifact,
publication status, PDF page reference, HTML DOM, backend metadata) — prefer these over relying only on
visual UI text.
