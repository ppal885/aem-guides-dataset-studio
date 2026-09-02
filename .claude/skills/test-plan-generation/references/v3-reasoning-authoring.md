# Behavioral v3 authoring

Use the existing `aem-guides-evidence-manifest-v3` record. A legacy v2 fixture is
input for migration, not a template for a new plan. Do not fabricate facts, queries,
Human approvals, or verification results to make a gate pass.

Claude Desktop remains the reasoning author for the target runtime. Python
enumerates candidates and validates the record. This procedure supplies the
canonical runtime; it does not add an alternate planner, LLM, or final renderer.

## 1. Model inspected behavior before writing ACs

Populate `behavior_model.trigger`, `operations`, `inputs`, `outputs`,
`affected_state`, `consumers`, `processors`, `write_paths`, and `read_paths` as lists.
Empty lists are allowed where genuinely inapplicable; explain unavailable paths
in `unknowns`. Never replace missing implementation evidence with a guessed path.

Record at least one `facts` item with `fact`, `evidence_ids`, `authority`, and
numeric `confidence` in [0,1]. Use the source authority, not the model's opinion.
Bind IDs to inspected sources in `evidence_catalog`; local code must carry its
actual source path and SHA-256. Unknown behavior belongs in `unknowns`, not facts.
Record extra model relationships only when supported: configuration branches,
fallbacks, capabilities, artifact shapes, shared processors, execution/publishing
modes, versioned models, side effects, and state-update/remove paths.

## 2. Scaffold, then disposition (do not hand-type the closure matrix)

After modeling the inspected behavior and declaring `evidence_catalog`, run:

```text
python scripts/v3_scaffold.py --manifest manifest.json
python scripts/v3_scaffold.py --manifest manifest.scaffold.json --out manifest.review.json --inspected-file path/to/inspected-file.py
```

The first command creates `manifest.scaffold.json`. The second illustrates adding
an explicitly selected source file while saving to a new destination. Existing
files are never overwritten. Relative inspected-file paths resolve against the
input manifest's directory, not the shell's working directory. No network,
corpus ingestion, provider call, LLM invocation, or source-tree scan is performed.
Exit 0 means **scaffold written**, not gate passed or plan postable.

The command generates or extends four existing blocks:

- `behavior_graph`: model-role nodes and typed candidate edges with catalog IDs.
  Edge hypotheses are appended to `coverage_hypotheses` so there are no dangling
  `hypothesis_ref` values. Roles do not imply a verified method-call graph.
- `semantic_closure`: every material node x every current `CLOSURE_DIMENSIONS`
  value (currently 31). IDs can grow beyond three digits; no rows are truncated.
- `missing_questions`: one contextual stub per unresolved closure, material edge,
  ambiguous material fact, and unresolved verification. Stubs preserve the source,
  dimension, subject and existing OQ; they add source-policy hints and entity-based
  search concepts. They are labelled `PYTHON_SCAFFOLD`, **not Claude questions**.
- `evidence_catalog` and `evidence_lifecycle`: SHA-256 binding of files selected
  through repeated `--inspected-file` flags or manifest `inspected_files` strings.
  File content is not copied. Binding records only RETRIEVED bytes, with blank
  query/authority/subject. Record the real inspection and bindings before USED.

### Entity provenance and materiality

Existing model string lists work unchanged. A node can use evidence from a fact
that explicitly contains its exact entity phrase. When that wording does not
match, provide the explicit binding in `behavior_model.entity_evidence`:

```json
{"processors:value resolver": ["E1"], "consumers:details panel": ["E2"]}
```

The key is `<model-field>:<exact entity label>`. Alternatively, a list item may be
`{"name":"value resolver","evidence_ids":["E1"],"material":true}` with an
optional canonical graph `kind`. Supported fields include processors, consumers,
attributes, configuration dependencies/branches, affected/persisted state,
inputs/outputs/artifacts, read/write paths, producers, roles, versions and
deployment modes; `configuration`, `config` and `state` are optional aliases. Missing or unavailable
IDs produce gaps and empty provenance, not invented evidence or borrowed catalog
hits. The graph gate rejects the incomplete binding.

Generic field/role mappings and per-kind material defaults live in
`scripts/data/v3_scaffold_policy.json`, checked against the canonical graph and
coverage vocabularies when loaded. There are no product construct-pair rules.
An explicit node `kind` uses that kind's default, not the original field's default;
an explicit boolean `material` takes precedence.

Behavior/state/processor/consumer/configuration entities default material. Role,
version and deployment context defaults non-material; inspect these defaults and
change them when relevant. All generated nodes/edges start
`verification_state=INVESTIGATION_CANDIDATE`, `confidence=0`, `currentness=UNKNOWN`
and `applicability=UNRESOLVED`. Edges start with inference authority. Verify and set the correct
subject/source authority; the generator never asserts current implementation.

### Required author edits

Generated graph, closure and file-use rows carry `author_review_required=true`.
Closure defaults are NOT_APPLICABLE / INVESTIGATED_AND_REJECTED with an
`AUTHOR MUST CONFIRM` reason and blank `disposition_ref`. These are **placeholder
enum values, not completed rejection verdicts**. Gates reject them even if an
author fills a disposition ID or flips the review flag without replacing the
placeholder reason. No AC, verification verdict or acceptance promotion is
generated.

For each closure row, inspect the relationship, replace the reason with the real
evidence-based decision, and set `author_review_required=false`:

- Not applicable: keep NOT_APPLICABLE / INVESTIGATED_AND_REJECTED and link a real
  rejection `disposition_ref`.
- Applicable and verified: set APPLICABLE / COVERED and link its real disposition.
- Still unknown: set UNRESOLVED / UNRESOLVED_AND_EXPOSED, remove any rejection
  destination and link the real `open_question_ref`.

Review graph entities/edges and replace their `review_note` similarly. For file
use, record the actual query, subject, authority, question/hypothesis bindings and
inspection note; only then mark USED. Hashing alone is not inspection or use.
The command does not fabricate OQ IDs, second-pass queries or retrieval results.
Missing OQ links and unperformed second passes remain gate failures.

Rerun after marking closure/verification rows UNRESOLVED to append their question
stubs. Existing graph decisions, closure rows, questions, evidence usage and IDs
are preserved, not reset. New model entities/dimensions append new IDs. If a
source changes, a new evidence ID is created; old hashes and decisions remain
intact and must be reassessed. Deleted/renamed model entities are not silently
pruned: reconcile stale graph rows yourself. Do not reuse a reviewed graph for
changed behavior without rechecking its evidence and scope.

If a selected absolute file path already has a catalog ID but no hash, the helper
fills that hash in place, preserving model references to the ID. It never replaces
an existing non-empty hash with different bytes or chooses between ambiguous IDs.

Continue with discovery and actual investigation below. Populate the other
required authored blocks (`contract_facts`, `issue_domains`, verifications,
dispositions, promotions) from evidence; the scaffold does not waive them.
Finally run the normal `run_gates.py --plan ... --combined ... --manifest ...
--receipt ...`. The scaffold is not a replacement gate or canonical runtime.

## 3. Execute discovery, do not hand-enumerate dimensions afterward

Run the installed copy's `scripts/dimension_synthesizer.py --manifest <path> --json`.
Its `explorers` trace records all twelve family checks: CONTRACT_BOUNDARY,
CONSUMER, STATE_PARTITION, TYPE_ABSTRACTION, REFERENCE_ARTIFACT,
DITA_SEMANTIC_DEPENDENCY, LIFECYCLE, CONFIGURATION, PUBLISHING_MODE, NFR_RISK,
BACKWARD_COMPATIBILITY, and DOWNSTREAM_REGRESSION. No grounded signal means no
candidate. It also runs code/RAG/history neighborhoods, `miss_probe_library`, and
`feature_map`; source unavailability remains a recorded gap.

Carry returned candidates into `coverage_hypotheses`, retaining their stable ID,
canonical `dimension`, `implied_dimension_axis` when present, `generator`,
`equivalence_key`, `technical_basis`, evidence, and probe/feature/source tags.
Investigate each independent relationship named by the technical basis. Split
distinct consumers where applicability differs; collapse only proven equivalents
and preserve the representative's original generator key. Do not delete candidates
to clear DISCOVERY notes: retain their rejection or unresolved outcome.

Discovery is SUPPORTING only. A matched feature, historical analogy, RAG snippet,
or generated candidate does not establish current applicability or acceptance.
Never paste candidate wording straight into an AC.

## 4. Investigate missing evidence

For each material or blocking gap, author a contextual `missing_questions` record:
`question_id`, `hypothesis_id`, `question`, `why_it_matters`, `preferred_sources`,
`search_concepts`, `blocking`, `material`, `source_ref`, `subject`, and the visible
`open_question_ref`. Follow `missing-question-quality-contract.md` for the
separate hash-bound Claude submission; do not relabel Python candidates as Claude
questions.

Execute a genuinely new query for **each** blocking question. Record actual
`evidence_lifecycle` items with `evidence_id`, `source`, `query`, `pass`, `status`,
`question_id`, `hypothesis_id`, `subject`, and `authority`. A query answered for
another question is not this question's second pass. Do not invent a retrieval
when a provider is absent. Empty/unavailable retrieval leaves the candidate
unresolved, not disproved. If no question remains, an explicit empty
`missing_questions` list is valid; the material-gap validators still run.

## 5. Verify, disposition, then promote

Every candidate needs exactly one `verifications` entry, even when rejected:
CONFIRMED, INFERRED_HIGH_CONFIDENCE, REJECTED, or UNRESOLVED. Use
`hypothesis_verifier.py`'s existing fields and subject-specific authority rules.
Supporting/disproving evidence must be USED evidence bound to that hypothesis.
UNRESOLVED requires a real Open Question; no result does not justify REJECTED.

Populate `dispositions` with the candidate's `source_refs` and destination.
Only product-contract-backed acceptance findings receive `acceptance_promotions`
records. Keep the candidate, subject, authority, disposition, AC ID, and visible
status aligned. Confirmed implementation evidence alone is not acceptance truth.
Retain the existing `contract_facts`, `issue_domains`, `behavior_graph`,
`semantic_closure`, and their exactly-once completeness checks.

Run `run_gates.py` on the complete record before canonical delegation. Hypotheses
count toward probe coverage using `dimension` and `implied_dimension_axis`; do not
duplicate them in clarification solely to satisfy the probe gate. Clarification
still records actual blocking Human decisions and answers when applicable.

## Migration and reviewed exceptions

Ordinary waivers of the three core behavioral blocks hard-fail, including in v2.
Other legacy structural waivers retain their transition behavior. Any reasoning
waiver makes the receipt REVIEW/non-postable. In v3 every reasoning waiver requires
an actual reviewed escape. See `manifest-completeness.md` for the recorded-review
shape. Never self-author a review or downgrade the schema to regain postability.
