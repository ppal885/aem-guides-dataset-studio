# Reasoning Pipeline Phases And Manifest Details

Moved verbatim from SKILL.md on 2026-09-30 when SKILL.md was consolidated. The rules are unchanged.

## Compatibility record and manifest details

- Minimum evidence manifest fields include `"schema_version": "aem-guides-evidence-manifest-v3"`, a canonical Jira issue key, explicit boolean `accepted_uac_present`, stable `open_questions` records (`id`, `question`, `qa_impact`), a versioned `enumerated_requirements` block, a versioned `operational_contract` block, the complete `evidence_preflight` contract, `"rag_tool": "ask_dita_expert"`, three exact `rag_probes`, `"jira_history_tool": "search_jira_history"`, `"indexed_history_run": true`, two scoped `jira_history_queries`, `history_attempts`, an `evidence_graph` record, a complete `performance_assessment`, clone state, and the canonical semantic blocks `contract_facts`, `issue_domains`, `behavior_model`, `behavior_graph`, `semantic_closure`, `coverage_hypotheses`, `missing_questions`, `evidence_lifecycle`, `verifications`, `dispositions`, and `acceptance_promotions`. Each contract fact's literal text must be an exact excerpt of the canonical Jira field, accepted UAC, attested attachment text, or artifact-and-hash-bound `contract_source_records` capture named by its `source_ref`. When `enumerated_requirements.active=true`, also include `source_requirement_ledger` schema `aem-guides-source-requirement-ledger-v1`. When event/async signals exist, also include versioned `concurrency_race_analysis`.
- Record every Jira-history attempt in `history_attempts` using records such as `[{"source":"search_jira_history","query":"exact query","result":"empty","count":0}]`; `OFFLINE_CHROMA` and `Jira JQL` are also valid source descriptions. `source` and `query` are non-empty strings; `count` is a non-negative integer. Use `ok` only with one or more returned results, and use `empty` or `unavailable` with count zero. This attempt ledger is separate from `jira_history_queries`: it records the observable result even when no result can be cited.
- Run the manifest through `feature_class_registry.py`. Declare every applicable class in `feature_classification` and include each required dimension block. For UI constructs, enumerate only the affected construct's grounded render surfaces and disposition every entry in `scripts/data/ui_surface_catalog.json`; when review discovers another reusable surface, add it with `add_catalog_surface()` so that construct cannot silently miss the same surface again. An undeclared detected class is a REVIEW signal for legacy compatibility, not permission to omit the classification from a new plan.
- Run `relationship_traversal.py` for the affected construct. Record grounded one-hop code and corpus edges, all five cross-cutting dimensions, the exact code/corpus searches, searched clones, and the sibling-config, sibling-UI-option, caller, and same-path findings. Every discovered neighbor must be covered by an AC, exposed as an Open Question, or explicitly out of scope. This is the umbrella; role provisioning and UI-surface checks plug into its PRECONDITION and CONSUMER edges.
- Mark a UI consumer edge with `neighbor_kind: UI_SURFACE`. That marker requires `ui_surface_scope`; a list of screen-like names without the marker is not an acceptable substitute for classification.
- When an AC is supported only by a PR, commit, or diff, declare `implementation_scope_authority` with schema `aem-guides-implementation-scope-authority-v1`. Keep the AC Proposed and map it to a real Open Question, or cite an explicit accepted-UAC/product-decision source. Implementation evidence alone is not product authority.
- For a configuration-backed set, declare `configuration_driven_enumeration` and populate `configuration_enumeration_scope` schema `aem-guides-configuration-enumeration-scope-v1`. Disposition authoritative source and overlay precedence, dynamic discovery, mapped and fallback labels, applicability, activation, unrelated-entry preservation, invalid/duplicate/removal behavior, upgrade, and rollback to real ACs, Open Questions, or grounded out-of-scope reasons.
- Before canonical delegation, write the compatibility record to a UTF-8 temporary file and run `python scripts/validate_test_plan.py <draft-file>`. If it reports any error, repair the record and rerun. This check does not replace the canonical runtime gates or renderer.
- After structural validation passes, run `python scripts/verify_evidence.py <draft-file>` to audit that every cited drive-absolute source-file path exists on disk and that every cited line number is in range. Repair or remove any hallucinated path or line before returning the plan; never present unverified file/line citations as current implementation. Proposed new files, runtime paths, and relative test paths are skipped by design and are not failures.
- When the issue has attachments, write an evidence manifest JSON (`{"issue": ..., "attachments": [{"id", "filename", "downloaded_to", "analyzed": true, "note"}]}`) recording the scratchpad path each attachment was downloaded to, and run `python scripts/verify_evidence.py <draft-file> --attachments-manifest <manifest>`. It fails if any declared download is missing on disk or any attachment is not attested analyzed. This proves each attachment was fetched and attested; it does not prove the Jira list is complete, so still confirm the attachment count against `list_attachments`.
- When source-file evidence came from a subagent or a clone, treat a `verify_evidence.py` failure as a real finding: the path or line is wrong or invented, not a tooling glitch.
- If the validator or evidence scripts are edited, run `python scripts/test_skill_scripts.py` and keep it green; it is the regression guard for both scripts.
- Whenever the plan cites existing automation as `Covered` or `Partially covered`, or the user asks for a shareable or linkable artifact, produce a single deliverable Markdown file: the eleven-section plan body followed by an `Appendix A - Automation Evidence` section. In that appendix, for each Covered or Partially covered AC, read the cited file and quote the relevant step/method/fixture verbatim in a fenced code block, with its absolute path and a one-line note on what it proves and the precise gap, plus the reusable helpers a gap test would build on. Keep code fences OUT of the eleven validated sections (they are bullet-only and code fences fail `validate_test_plan.py`); the appendix lives after the validated body. Validate the plan body alone, then run `python scripts/verify_evidence.py <combined-file>` so source paths quoted in the appendix are disk-checked too, and deliver the file to the user (do not only paste it in chat).
- Quote real code, never paraphrased or invented code. If a cited file cannot be read, say so in the appendix rather than reconstructing its contents from memory.

### Phase 6.5.5 — Behavioral Coverage Expansion (widen discovery, never acceptance)

The sweep above catches the dimensions you thought to look for. This stage catches the
ones the ticket never mentions. A named value is not atomic: before it can be treated as
covered, the plan must also have considered where it comes from, what is shown when it is
absent, whether it can be supplied indirectly through referenced or reused content, what a
move or rename does to it, whether it can go stale, and whether every consumer surface
agrees. Read `references/behavioral-coverage-expansion.md` and record the result in the
manifest `behavioral_coverage_expansion` block, validated by
`scripts/behavioral_coverage_expansion.py`. The canonical runtime enforces the same
contract in its `BehavioralCoverageExpander` stage, which runs between
`BehaviorModelBuilder` and `SemanticBehavioralClosureExplorer`.

- **Derive triggers from requirement shape, never from a feature name.** A trigger fires on
  what the requirement does — display, export, order, filter, persist, resolve a reference,
  move or rename, change state, depend on configuration — so the same reasoning applies to
  any product family. `MULTIPLE_CONSUMER_SURFACES` is derived, not matched: either two or
  more consumer surfaces exist structurally, or the requirement describes both a displayed
  and an exported form of one value.
- **Map triggers to axes and axes to dimensions**, then treat every activated dimension as a
  question you must answer from evidence. Activation is not coverage.
- **Keep distinct contracts distinct.** Moving or renaming an item is not the same behavior
  as an entry changing lifecycle state, and neither is the same as reordering. They get
  separate dimensions, separate questions, and separate dispositions; never collapse them
  to shorten the list.
- **Discovery is not acceptance.** An expansion candidate carries no acceptance authority.
  It lives in its own `covexp:` identifier namespace, can never be cited as the source for
  an AC, and must not block an explicitly accepted Human contract. Promotion rules,
  source authority, evidence roles, and the existing-vs-new behavior classification are
  all unchanged.
- **Nothing discovered may silently disappear.** Disposition every activated dimension
  explicitly — covered, investigated and rejected, exposed as unresolved, routed to
  research, or not applicable with a concrete reason. Omission is not a disposition, and
  `NOT_APPLICABLE` or `INVESTIGATED_AND_REJECTED` without a reason fails the gate. An
  unresolved activated dimension flows into the existing missing-question and mandatory
  research path unchanged; `NOT_FOUND` still never asserts the opposite behavior.
- **Every material subject decides all nine dependency dimensions.** Dispositioning
  activated dimensions only proves nothing was lost after discovery; it cannot prove
  discovery asked about everything, because a dependency that never triggered is never
  activated and so never has to be answered. Record one `dependency_records` entry per
  material subject deciding `PROVENANCE`, `PRECEDENCE_AND_FALLBACK`,
  `INDIRECTION_AND_RESOLUTION`, `CONTEXT_DEPENDENCY`, `IDENTITY`, `LIFECYCLE_MUTATION`,
  `FRESHNESS_AND_STALENESS`, `CONSUMER_PARITY`, and `UNRESOLVED_OR_NEGATIVE_BRANCH`. A
  record that omits a kind fails; `NOT_APPLICABLE` with `n/a`, `none`, `tbd`, or an
  equivalent empty assertion fails; `RESEARCH_REQUIRED` must name the question or
  candidate carrying that research; and a material subject with no record fails. Records
  are built only for material subjects, so discovery stays bounded rather than becoming a
  Cartesian expansion.
- **Route each dependency by where its answer actually lives.** A question about how the
  product behaves today is an implementation read, not a product decision; a question
  about governing rules or documented fallback is a documentation read. Declare that in
  the dimension's evidence path so mandatory research routes correctly — misrouting a
  code question to documentation silently converts it into a human decision. A dependency
  record carries no acceptance authority and can never be promoted or cited as an AC
  source.

### Phase 6.6 — Question-Based Reasoning (Planner → Research Router → Resolver)

Structured reasoning stages between discovery and authoring. The Question Planner and
Question Resolver are coordinator/reasoning stages, NOT new autonomous agents — the
existing Evidence Agent, Doc Researcher, Writer, and Reviewer roles are unchanged.
Flow: evidence → Question Planner → material questions → Research Router → Doc
Researcher / other authorized evidence routes → Question Resolver → coverage reasoning
input → Writer → Reviewer → final UAC. Record the stages in the manifest `question_plan`
and `question_resolutions` blocks, validated by `scripts/question_planner.py` and
`scripts/question_resolver.py` (see `references/question-based-reasoning.md`).

- **Plan only material questions.** Emit a question only when its answer could materially
  improve acceptance understanding or coverage — never carpet every category. The closed
  category vocabulary: EXPECTED_OUTCOME, STATE_TRANSITION, PERSISTENCE, NEGATIVE_CONTRACT,
  SCOPE, VARIANT, ENTRY_PATH, CONFIGURATION, APPLICABILITY, PRESERVATION, ERROR_RECOVERY,
  SCALE, COMPATIBILITY. Every question carries `question_id`, `category`, `question`,
  `why_material`, `triggering_evidence_ids`, `acceptance_impact`, `applicability`,
  `  research_requirement`, and `status` (plus `research_topics[]` when research is routed).
- **The question budget is bounded** (`question_plan.budget`, default 12). If the
  material-question budget is exceeded, do not silently discard questions: move the excess
  into `question_plan.overflow` with `state: QUESTION_BUDGET_EXCEEDED` and an explicit
  escalation note.
- **Route every question through the Research Router** (`question_research` block) before
  resolving it, reusing the R1 Doc Researcher routing contract (Phase 5.5): a
  documentation-requiring material question requires a terminal `doc_research` routing
  state — R1-required research cannot be skipped, and a `RESEARCH_NOT_REQUIRED` doc
  routing contradicts documentation-requiring questions. Required research cannot be
  skipped; NOT_FOUND is not negative proof.
- **Resolve every planned question exactly once** with a terminal disposition: ANSWERED,
  PARTIALLY_ANSWERED, ACCEPTANCE_TBD, INVESTIGATION_ONLY, NOT_APPLICABLE, DUPLICATE, or
  CONFLICTED. The resolution carries `question_id`, `disposition`, `answer`,
  `source_ids`, `source_authority`, `applicability`, `limitations`, `contradictions`,
  `decision_reason`, and `research_ids` binding the admitted research that produced a
  documentation answer - stale or wrong-bound research cannot answer another question,
  and documentation is never cited without admitted research. Semantic decisions are
  externalized in these artifacts; downstream stages consume them rather than
  reconstructing answers from raw ticket text.
- **Hard rules:** a question is not an AC; an answer is not automatically an AC; Actual
  Result cannot establish Expected Result; never reverse a reported failure to invent
  desired behavior; a suspected root cause does not become acceptance behavior; an
  attachment observation does not establish desired behavior; historical Jira does not
  automatically establish current behavior; PARTIAL research cannot produce a fully
  confirmed answer; an equal-authority conflict remains unresolved (stay CONFLICTED, or
  record the higher-authority basis in `conflict_resolution`); a DUPLICATE preserves all
  triggering evidence IDs on the surviving question; root-cause/diagnostic/mechanics
  uncertainty never becomes ACCEPTANCE_TBD merely because it matters to engineering;
  ACCEPTANCE_TBD is allowed only when different plausible answers materially change
  acceptance behavior/scope/configuration/applicability/compatibility/preservation; root
  cause, diagnostics, and implementation mechanics are normally INVESTIGATION_ONLY. The
  Writer never receives raw unresolved questions, and a question is never rendered
  directly as an AC - ACCEPTANCE_TBD questions reach the final Open Questions contract
  only through the existing approved downstream path.
- **Preserved invariants:** source authority, observation-vs-requirement separation, exact
  Jira intake, attachment evidence handling, Doc Researcher routing, the Writer language
  contract, Reviewer independence, and draft-only behavior all remain exactly as defined
  elsewhere in this skill — these stages only add traceable structure between discovery
  and authoring.

### Phase 6.6.5 — Evidence Sufficiency (before coverage decisions)

"Evidence exists" is not "evidence is sufficient to support this answer or coverage."
Evaluate sufficiency at BOTH the resolved-question level and the coverage-decision
level in the manifest `evidence_sufficiency` block, enforced by
`scripts/evidence_sufficiency.py` (see `references/evidence-sufficiency.md`).

- Every material resolved question carries `sufficiency_status` (SUFFICIENT / PARTIAL /
  INSUFFICIENT / CONFLICTED) with the structured sub-states `authority_status`,
  `research_completion`, `applicability_status`, `currentness_status`,
  `contradiction_status`, plus claim-level `supported_claims[]` /
  `unsupported_claims[]`, `limitations[]`, bound `evidence_ids[]` / `research_ids[]`,
  and `decision_reason`. No numeric confidence as authority.
- One applicable authoritative source may be SUFFICIENT; many related passages are not
  automatically sufficient. Do not require documentation when Jira authority itself is
  sufficient. PARTIAL research caps the answer at the established portion unless the
  remaining limitation is demonstrably immaterial to that specific answer; NOT_FOUND is
  never proof of the opposite behavior; CONFLICTED stays CONFLICTED until an existing
  authority rule settles it.
- Wrong-applicability evidence (wrong version / engine / surface) stays insufficient
  without explicit compatibility evidence; UNCLEAR applicability is never confirmed
  applicability. Sufficiency for one claim never bleeds into a neighboring claim.
- Coverage sufficiency is computed from the underlying questions and evidence; P0/P1
  ACCEPTANCE coverage requires SUFFICIENT unless explicitly represented as
  ACCEPTANCE_TBD; the Writer handoff never carries INSUFFICIENT/CONFLICTED coverage or
  an unnamed PARTIAL portion, and the Writer cannot reinterpret evidence to upgrade
  sufficiency.

### Phase 6.7 — Coverage Reasoning (dedicated Coverage Reasoner)

A dedicated Coverage Reasoner — never the Writer — decides coverage on top of resolved
question evidence, recorded in the manifest `coverage_decisions` block and validated by
`scripts/coverage_reasoner.py` (see `references/coverage-reasoner.md`). Inputs:
authoritative requirements, resolved questions, research findings, applicability,
conflicts, attachment observations, existing behavior, new behavior, and preservation
requirements.

- Emit one decision per candidate behavior with `coverage_id`, `behavior`,
  `question_ids`, `evidence_ids`, `research_ids` (the admitted research behind the
  underlying questions), `priority`, `coverage_class`, `contract_type`
  (`POSITIVE`/`NEGATIVE`/`PRESERVATION`), `surface`, `state_or_transition`,
  `configuration`, `applicability`, `variants` (same-outcome variants each bound by
  their own evidence), `reason`, `acceptance_impact`, and the
  `dimensions_considered` axes reasoned about when applicable (single/bulk,
  refresh/revisit, state transitions, negative contracts, alternate UI paths,
  configuration branches, New/Old Editor, Author/Source, Collections/Explorer/Map
  Console, Cloud/6.5, Native PDF/DITA-OT, preprocessing ON/OFF, scale, preservation).
- **priority**: `P0` = behavior required to prove the primary ticket contract and prevent
  the direct customer regression (class `ACCEPTANCE`); `P1` = materially related
  regression behavior (class `QE_REGRESSION`); `SUPPORTING` = supporting regression or
  investigation coverage; `EXCLUDED` = explicitly excluded with a reason, never reaching
  the Writer. Do not promote generic test ideas: every decision traces to resolved
  questions and/or evidence.
- A decision may stand only on questions whose resolution and research permit it:
  ANSWERED is eligible; PARTIALLY_ANSWERED grounds only the established portion
  (regression/investigation); ACCEPTANCE_TBD is never converted into confirmed
  behavior; INVESTIGATION_ONLY never becomes acceptance coverage; NOT_APPLICABLE
  produces no coverage; a DUPLICATE contributes linkage through its surviving
  question and never creates duplicate coverage; CONFLICTED never silently produces
  confirmed acceptance coverage. An acceptance decision never rests on actual-result,
  observation, suspected-root-cause, or historical-ticket authority. NOT_FOUND or
  otherwise incomplete required research cannot ground an ACCEPTANCE decision.
  Documented-today (EXISTING_CONFIRMED) behavior must not be repackaged as new
  acceptance coverage, and a NEW_REQUIREMENT is not a preservation contract.
- **The Writer receives an explicit admitted coverage package** (`writer_handoff` is
  mandatory once decisions exist) containing only accepted (non-EXCLUDED) decisions and
  every P0 decision. The Writer must not invent additional acceptance behavior, promote
  QE_REGRESSION to ACCEPTANCE, convert INVESTIGATION into an AC, resolve
  ACCEPTANCE_TBD, add unapproved variants, or independently decide P0/P1 — it may
  simplify wording, combine approved same-outcome variants, and preserve required
  product terminology.
- **The Reviewer verifies** (via the `writer_package` block) that every AC maps to
  admitted ACCEPTANCE coverage ids, all P0 accepted behavior is represented, P1 did not
  expand acceptance scope, QE_REGRESSION/INVESTIGATION never leak into ACs,
  ACCEPTANCE_TBD was not silently resolved, no unapproved variants were introduced, and
  source mapping stays consistent with the evidence/question/research bindings.
  Semantic failures route upstream to the Coverage Reasoner; the Reviewer never
  silently repairs acceptance semantics.

### Phase 6.8 — Semantic Coverage / AC Equivalence

After coverage reasoning, classify pairs of coverage decisions for semantic equivalence
BEFORE the Writer authors ACs, recorded in the manifest `coverage_equivalence` block and
validated by `scripts/coverage_equivalence.py` (see
`references/coverage-equivalence.md`). The primary comparison happens on coverage
decisions, not merely Writer prose: compare `coverage_id`s structurally across coverage
IDs, question IDs, expected outcome, state transition, scope, configuration, and
applicability — never textual similarity alone. Same nouns do not mean the same outcome;
different wording does not mean different outcomes.

- **Classifications:** `SAME_OUTCOME_VARIANT` (same expected outcome through variant
  phrasing/polarity — the Writer should normally create one AC), `DISTINCT_OUTCOME`
  (different expected outcomes), `DEPENDENT_OUTCOME` (one outcome depends on the other;
  record the dependency; never auto-merged), `CONFLICT` (the same outcome asserted
  contradictorily; kept visible, never merged, routed upstream).
- **Decision record:** `decision_id`, the two coverage ids, `classification`, declared
  `shared_dimensions`/`differing_dimensions`, `reason`, and `merge_allowed` (true only
  for SAME_OUTCOME_VARIANT).
- **Merge groups** carry `equivalence_id`, `coverage_refs`, `canonical_outcome` (an
  internal grouping label — never evidence), `question_refs`, `evidence_refs`,
  `research_refs`, `variant_refs`, `source_lineage`, `priority`, `applicability`, and
  `partial_members`. A merge requires a SAME_OUTCOME_VARIANT basis decision with
  `merge_allowed`, preserves all question/evidence/research IDs, all approved variants,
  and all lineage, keeps the highest member priority, and never crosses applicability,
  surface, configuration, or state (parity is never inferred). INSUFFICIENT or
  CONFLICTED coverage never merges; PARTIAL coverage participates only through its
  bounded established portion; an ACCEPTANCE_TBD question is never absorbed into a
  confirmed merge; EXCLUDED coverage never merges; one decision survives into exactly
  one AC. Do not merge distinct behavior simply to reduce AC count.
- **Writer/Reviewer binding:** the Writer receives equivalence-resolved groups; an AC
  may reference a merge via `equivalence_refs` and must then carry every merged variant;
  two ACs may never cover different members of the same merge. The Reviewer detects
  duplicate ACs for a merged group, collapsed distinct outcomes, lost TBD dimensions,
  omitted or invented variants, and lost source lineage — and routes semantic failures
  upstream instead of repairing them.

### Phase 6.9 — Requirement Lineage (end-to-end AC traceability)

Trace every final AC back to the evidence that justified it, recorded in the manifest
`requirement_lineage` block and validated by `scripts/requirement_lineage.py` (see
`references/requirement-lineage.md`): Original Source -> Evidence -> Question ->
Research (when required) -> Question Resolution -> Sufficiency -> Coverage Decision ->
Equivalence Group (when applicable) -> Written AC -> Reviewer Decision. Existing
production IDs are preserved; `SRC-` (original source) and `REV-` (review decision)
are recorded conceptually and reference the existing IDs without rewriting them.

- `sources[]` records each original admitted source with `source_type`, locator,
  optional version/applicability, status, and `evidence_ids`; `ac_lineage[]` binds each
  final AC to its `coverage_refs`, `equivalence_refs`, `question_refs`,
  `evidence_refs`, `research_refs`, `source_refs`, `writer_revision`,
  `source_versions`, and the human-facing `human_source_line`; `tbd_lineage[]` keeps
  every unresolved ACCEPTANCE_TBD question visible with its research attempt, partial
  or insufficient result, and reason — a TBD row never references a confirmed AC;
  `reviews[]` binds each Reviewer decision to the exact Writer revision.
- **Integrity rules:** every referenced ID exists in the producing block; the Writer
  cannot fabricate lineage; unrelated or unused retrieved evidence never contaminates
  an AC; a QE_REGRESSION member of an equivalence group never becomes acceptance
  authority through the group; `human_source_line` derives only from admitted
  supporting sources and never exposes internal IDs (`Q-`, `COV-`, `SUF-`, `EQ-`,
  `DR-`, `EV-`, `SRC-`, `REV-`, `MERGE-`, `canonical_outcome`); a Writer revision
  change makes the review stale and a source-version change invalidates the dependent
  lineage; unsuccessful research stays visible in `tbd_lineage` instead of being
  erased.
- Lineage proves provenance and structural integrity, not semantic correctness; it
  adds traceability only and introduces no new acceptance semantics.

### Phase 6.9.5 — Historical Jira Evidence Safety

Historical Jira similarity is discovery evidence, not acceptance authority: an old
ticket never automatically becomes an authority for the current ticket. Record every
historical item considered for a material Question in the manifest
`historical_jira_assessment` block, validated by
`scripts/historical_jira_safety.py` (see `references/historical-jira-safety.md`). This
extends the existing temporal/authority/resolver path; it creates no competing
framework and no new authority hierarchy.

- Assess per Question (never globally per ticket): `history_id`, `question_id`,
  `jira_key_or_source_id`, `relationship`, the six match dimensions, `currentness`,
  `superseded_status`, `human_accepted_ac_available`, `applicability`,
  `authority_role`, `allowed_use`, `reason`, `limitations[]`. Never classify from
  vector similarity or lexical overlap alone.
- **Relationships:** `AUTHORITATIVE_HISTORY` (only with an `authority_basis` naming
  the existing permitting rule plus exact applicability — a historical Human Accepted
  AC is not automatically authoritative for a different ticket),
  `SUPPORTING_PRECEDENT` (may contribute; S1 still decides; never overrides current
  Jira), `DISCOVERY_ONLY` (locates terminology/sources/paths; never establishes an
  answer or enters Source lines), `NOT_APPLICABLE` (forced by any material
  surface/version/configuration difference — similarity never overrides it),
  `CONFLICTING_HISTORY` (preserve the disagreement; route through existing Q1/S1
  conflict/TBD behavior).
- Historical Actual Results, reproduction steps, and suspected root causes remain
  observation/investigation evidence — never converted into current acceptance
  requirements; historical Human UAC is never copied into the current UAC without
  current-question reasoning and Coverage admission.
- S1 never reaches SUFFICIENT on non-establishing history; C1 never lets historical
  evidence create coverage directly (only through its bound Question); E1 never merges
  current and historical outcomes for similar wording; L1 keeps every historical
  contribution visible and keeps unused history out of final Source lines.

### Phase 6.9.6 — Question-Level Retrieval Quality and Evidence Admission

Retrieval is not evidence: evaluate and control retrieval against explicit material
Questions via the manifest `retrieval_requests` / `retrieval_results` blocks,
validated by `scripts/retrieval_admission.py` (see
`references/retrieval-admission.md`). This extends the existing read-only retrieval
path — it builds no new RAG system, replaces no vector store, and never reindexes.

- Every retrieval request binds a `question_id`, `research_id`, the actual `query`,
  `required_source_type`, `product_context`, `applicability`, `requested_claim`, a
  bounded `top_k`, and a `retrieval_mode`; query rewrites never change the Question
  binding; retrieval budgets are tracked and no answer is a valid result.
- Every candidate records rank, score (discovery metadata — never authority), source
  identity/version, applicability (`CONFIRMED`/`UNCLEAR`/`WRONG`/`NOT_ASSESSED`), and
  a `relationship`: `TOPIC_MATCH` (discovery only), `RELEVANT`, `SUPPORTS_CLAIM`
  (S1 decides sufficiency), `DECISIVE` (subject to source authority — never
  automatically authoritative or sufficient).
- A declared relationship never exceeds the structural admission ceiling: fetch exact
  evidence before material use; wrong or unassessed applicability stays TOPIC_MATCH;
  unclear applicability is never DECISIVE; exact configuration/property identity is
  required (a same-looking numeric value on a nearby property is not the same
  property); stale retrieval is rejected; retrieved historical Jira routes through H1.
- TOPIC_MATCH/RELEVANT never make a Question SUFFICIENT; only fetched
  SUPPORTS_CLAIM/DECISIVE evidence reaches AC lineage and final Source lines; unused
  chunks stay auditable outside them.
- Retrieval quality is evaluated offline by `scripts/retrieval_benchmark.py` over
  question-level fixtures (retrieval and admission metrics reported separately; the
  headline metric is DECISIVE_EVIDENCE_MISADMISSION_RATE). A live smoke check reports
  read-only gateway connectivity only — never semantic-quality proof.

### Phase 6.9.7 — Canonical Replay (read-only parity after runtime generation)

The canonical Python runtime is the only production semantic and promotion authority.
After a canonical run (CLI, HTTP, or adapter delegation), Skill gates may replay the
SAME runtime result instead of a hand-authored manifest:

1. Preserve the canonical result unchanged.
2. Project it read-only: `python scripts/canonical_runtime_adapter.py --project-result <runtime-result.json> --out <projection.json>`. The projection preserves runtime IDs, evidence refs, research state, promotions, clarifications, and applicability; fields the runtime does not carry are recorded as `UNAVAILABLE_FROM_RUNTIME` in the projection metadata, never fabricated.
3. Replay gates over the projection: `python scripts/run_gates.py --manifest <projection.json> --runtime-replay --parity-report <parity.json>`. Gate outcomes are PASS / FAIL / NOT_EVALUABLE / DISAGREEMENT; a missing runtime contract is NOT_EVALUABLE, never a pass.
4. Surface every disagreement (gate, runtime artifact ref, replay decision, reason, severity) for human review or the convergence backlog.
5. NEVER edit or regenerate the canonical runtime output to force a gate PASS: runtime output -> replay disagreement -> review/convergence backlog. The canonical AcceptancePromotionGate remains the only production promotion authority; Skill replay reports AGREES / DISAGREES / NOT_EVALUABLE and cannot modify promotion decisions, candidates, the canonical render, or runtime status.
