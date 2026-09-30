---
name: test-plan-generation
description: "Generate evidence-backed, plain-English AEM Guides QA test plans and UACs from Jira, Dynamics/support incidents, customer escalations, PRs, branches, commits, pasted diffs, logs, screenshots, Figma designs, or user-cloned repos. Also use when a reviewer reads a Jira UAC and supplies Human feedback in a fresh Claude/Codex chat: capture the selected correction with exact reviewed-source binding and separate QE approval for shared learning. Use for pre-development UAC planning, implementation review, and post-fix validation; inspect available product and automation clones; apply lifecycle-stage-specific evidence requirements so missing PRs are not blockers before development; and output concise plain-English plans."
---

# Test Plan Generation

## Goal

Produce a concrete AEM Guides QA test plan that reads like a senior manual QA engineer wrote it: practical, evidence-backed, plain-English, and bullet-only. Acceptance criteria must be easy to understand on the first read, including for non-native English speakers. Adapt evidence requirements to the lifecycle stage. Use RAG to learn product behaviour, but do not let RAG replace issue facts, UAC, current implementation evidence, or an available fix diff. Treat Jira UAC, pasted acceptance criteria, or a normalized support-incident acceptance contract as the primary scope and sign-off contract.

## Route reviewer feedback before plan generation

When the user reviews a UAC already on Jira and gives a correction (missed coverage,
unnecessary scope, wrong expectation, or difficult wording), read
`references/shared-human-uac-learning.md` and use its fresh-chat capture path. The
original generation session or draft ID is not required. This is a feedback task, not
a request to generate another UAC: do not run plan-generation gates, require product
clones, or retrieve unrelated RAG before saving the selected Human correction.

- Announce that only the selected correction will be saved for QE review; respect an
  explicit request not to save/share it. Never upload the whole conversation.
- Fetch the live issue through configured Jira MCP, including the raw UAC field,
  actual field-name metadata, and issue update time. Bind the exact field bytes using
  `feedback_capture.py prepare-jira-review`, then capture. Do not hash a paraphrase,
  rendered HTML, or the newly corrected AC as the original. If the reviewer refers to
  an older version, do not silently substitute the current Jira field.
- If that raw source is unavailable, capture without a fabricated draft/run/hash and
  report `PENDING_BINDING`. A changed-source conflict requires reconfirming the reviewed
  version; do not retry with a newly guessed pin. Editing/posting the Jira UAC remains
  a separate request and follows the existing posting gates.
- Check shared-learning readiness with the installed helper/MCP when configured. A
  readiness response describes configuration, not a saved record, reviewer authority,
  successful index, or proof of learning. Missing tools/credentials are reported, never
  concealed by a local success claim. Status-only requests must not flush the queue.
- Report the actual receipt: queued locally, saved pending binding, saved pending QE
  review, approved publication, and indexing are different states. Capture never grants
  approval, even when the person giving feedback is the ticket's QE Assignee. Reusable
  lesson approval requires that person's explicit decision and live server identity check.
- Apply the full generation workflow only if the user also asks for a revised plan.

## Operating Mode

- Treat `CanonicalTestPlanRuntime` as the only production reasoning and final-rendering authority. This skill gathers and verifies evidence, prepares a hash-bound compatibility record, and delegates it; it must not publish its own draft, compact projection, inferred gate status, or legacy packet composition as the final QE plan.
- Never activate a domain, reference pack, retrieval query, acceptance candidate, threshold, or expected result because an issue key matches a historical example. Historical issues may exist only in regression fixtures and evaluation references; production reasoning uses current source facts plus verified subject-specific evidence.
- Work evidence-first: classify lifecycle stage, collect facts, inspect available clones, normalize behaviour, retrieve RAG, inspect an available diff when stage-relevant, then write scenarios.
- Apply conflict priority in this order: Jira/UAC or normalized incident acceptance contract > inspected fix implementation when one exists > accepted RAG documentation > Figma UI intent > verified current product clone > automation clone > team memory. Surface material contradictions instead of silently choosing.
- Derive edge cases from concrete evidence: UAC boundaries, PR diff, code branches, API contracts, configs, old automation failures, and past similar Jira history; do not invent edge cases from generic module names.
- A current implementation proves what the code does; it does not by itself approve a new product requirement. If a fix adds user-visible handling that Jira or accepted UAC did not request, keep it Proposed and expose the scope choice as an Open Question. Do not promote it to sign-off scope merely because it appears in a PR.
- Map integration impact for every plan: identify adjacent workflows, callers, configs, output types, permissions, and automation areas that can break even if not directly changed.
- Use exact evidence probes before broad reasoning: RAG queries, Jira searches, repo searches, and automation searches must include the precise API path, config key, UI label, DITA construct, error text, or release/version boundary whenever one is available.
- Treat setup and test data as part of QA quality: each plan must make required environment, role, config, fixture, file type, output preset, and upgrade/source-target version needs visible inside `Test Scenarios`, `Regression Areas`, or `Open Questions`.
- Start `Test Scenarios` with one or more `Test data to prepare:` bullets, then write every P0/P1/P2 primary scenario in simple English using `Action:` and `Expected:`. Write `Regression Areas` as executable retest-and-risk bullets so the compact renderer can merge them into `Test Scenarios` as senior-QA `P3 [Regression]` checks.
- Keep the final answer short and tester-facing; keep raw evidence, chunk scores, backend traces, and reasoning audits internal.
- Judge readiness against the lifecycle stage: UAC-ready before development, implementation-review-ready while code is changing, or QA-sign-off-ready after a fix is available.
- Ask for a PR, branch, commit, or pasted diff only in implementation-review or post-fix stages, or when the user explicitly requests changed-code claims.
- Inspect every relevant user-provided or discoverable local clone before declaring code or automation evidence unavailable; do not ask teammates to clone dataset-studio, copy RAG JSON, copy ChromaDB, or run old test-plan MCP tools.
- Clone discovery is not limited to the current workspace. Follow the bounded Windows/Mac/Linux discovery protocol in `references/pr-and-repo-evidence.md`, resolve wrapper directories to the nested `.git` repository, and list the paths actually inspected.

## Tool Boundary

- Use `ask_dita_expert` as the only VM RAG path for AEM Guides, Experience League, DITA, DITA-OT, workflow, release-note, and configuration behaviour facts.
- The FluffyJaws connector is optional supporting discovery, off by default (`SKILL_FLUFFYJAWS_MODE`). When a mode enables it, follow `references/fluffyjaws-evidence.md`: re-ground every finding into a first-class source; a FluffyJaws finding is never an authority and never becomes an AC on its own (enforced by `fluffyjaws_evidence`).
- When `SKILL_PATTERN_CHECKS_MODE` is `PATTERN_CHECKS_SUGGEST` (default off), run `python scripts/pattern_check_suggestions.py <ticket-text-file>`. Each returned QE-approved historical check is a `SUPPORTING_DISCOVERY` candidate: research it with current evidence, turn it into a research question, or set it aside as not applicable. A suggestion is never an acceptance criterion by itself. `UNAVAILABLE` means the data file is missing: continue without suggestions and say so.
- Use Jira MCP first for current Jira facts and historical similar-ticket search. If Jira MCP is unavailable, use pasted Jira, Dynamics, support-case, customer-escalation, log, screenshot, and investigation details; state the evidence source without automatically blocking a pre-development UAC.
- Use the Jira MCP `list_attachments` and `download_attachment` tools to pull every attachment to a scratchpad path, then analyse it (Read images/screenshots, open logs and sample content as text). Never describe an attachment's contents from its filename alone.
- When the Dataset Studio app or local repo is available, use its `jira_qa` related-ticket retrieval as the first historical-learning candidate source, then validate mutable Jira facts with Jira MCP. Treat indexed learning as historical QA evidence only, never as current Jira truth or product documentation.
- After direct product RAG and Jira-history retrieval, call `query_test_evidence_graph` to evaluate connected findings and discover same-mechanism regressions. Default to shadow influence unless the packet/deployment explicitly enables augment; shadow output cannot change the plan. Never use the graph instead of the required direct calls, and never treat a path ID as evidence.
- Use GitHub MCP to inspect or discover a PR only when development may have started, a fix is claimed, or changed-code evidence is requested. Do not search for or request a PR when the issue is explicitly pre-development and no implementation exists.
- When live Jira contains a development link, PR URL, branch, commit, or pull-request reference, treat it as mandatory implementation evidence for `Implementation Review` and `Post-Fix Validation`. Use GitHub MCP when connected; do not stop at Jira development metadata or a PR title.
- Use Figma MCP read-only when Jira, PR, comments, attachments, or the user provides design links, frame names, prototype links, or asks to verify against existing UX/design flow.
- Do not use or expect any generated test-plan slash command or test-plan MCP tool.
- Use connected Jira/GitHub MCPs only if available in the current session. If unavailable, rely on user-provided evidence and local clones, then apply only stage-relevant gaps or blockers.
- For automation evidence, inspect synchronized local clones first because they support exact code, fixture, helper, tag, and history searches. Use GitHub MCP to inspect automation repositories when a local clone is unavailable or stale, to inspect automation PRs/branches, and to validate current remote files or default-branch coverage. Combine both sources when available and state which revision was inspected.
- Use connected Figma MCP only if available in the current session. If unavailable, rely on pasted screenshots/design notes and mark the Figma evidence gap.
- Before using a local product or automation clone as current evidence, run the guarded synchronization flow in `references/git-repo-sync.md`. Fetch every relevant clone, preserve dirty tracked and untracked developer work in a uniquely named stash when synchronization is safe, pull only with `--ff-only`, and report the pre-sync SHA, post-sync SHA, upstream state, and retained stash reference. Never reset, merge, rebase, force-checkout, drop a developer stash, or resolve conflicts automatically.

## Required References

- Read `references/evidence-preflight.md` before evidence retrieval. Run an actual availability check for product RAG, indexed Jira history, live Jira, Git, and Figma; connector configuration alone does not prove availability.
- Read `references/authoritative-source-coverage.md` before discovery or coverage
  reasoning when current Jira intake includes a description, comment, or analysed
  attachment fact. Atomize authoritative source facts before hypotheses can widen
  investigation.
- Read `references/rag-query-cookbook.md` before calling or judging `ask_dita_expert` evidence.
- Read `references/output-generation-overview-evidence.md` for publishing scope, Publish Dashboard tasks, LwDITA output or publishing privileges; use the overview to find the relevant detailed evidence, not to assume engine parity or add every publishing feature to an AC set.
- Read `references/map-collection-publishing-evidence.md` for Map Collection publishing, preset selection or bulk metadata; separate membership from enablement, selection from filters, and collection removal from asset deletion. Do not substitute New Map Collection behaviour or turn the reference into mandatory ACs.
- Read `references/native-pdf-publishing-evidence.md` when current scope concerns Native PDF templates, output presets, or environment configuration; use its source/chunk and image ledger to retrieve the applicable behaviour, preserving engine, version, and UI-label boundaries.
- Read `references/bookmap-toc-native-pdf-evidence.md` for Native PDF TOC/list generation or layout ordering; distinguish bookmap structure from ordinary DITA-map template controls and retrieve the exact source before deciding coverage.
- Read `references/custom-dita-ot-setup-evidence.md` for custom toolkit deployment or DITA Profile configuration; distinguish the uploaded ZIP, assigned repository paths and output-preset settings, and verify release/deployment applicability.
- Read `references/output-path-variables-evidence.md` for publishing destination/name substitutions; retrieve field-specific variable restrictions and keep these separate from Native PDF Language Variable behaviour.
- Read `references/html5-publishing-evidence.md` when current scope concerns HTML5 output presets; retrieve the relevant source-backed dependencies and preserve Map console/Map dashboard and DITA-OT/FMPS distinctions. The reference is not an automatic AC checklist.
- Read `references/custom-publishing-evidence.md` for Custom DITA-OT output presets; preserve plugin/transformation dependencies, console/dashboard labels, and source inconsistencies rather than importing another output family's contract.
- Read `references/condition-presets-evidence.md` for condition-preset creation, editing, default actions or output-preset selection; retrieve surface-specific rules and preserve the documented console/dashboard differences and naming ambiguity.
- Read `references/profile-output-presets-evidence.md` for Global/Folder Profile preset management or map Download as PDF defaults; distinguish shared, map-independent profile configuration from map-specific presets and do not infer PDF-engine equivalence.
- Read `references/output-preset-actions-evidence.md` for editing, duplicating, or deleting output presets; preserve Map console versus Map dashboard controls and the documented template-preset administrator restriction without inventing copy or deletion side effects.
- Read `references/fluffyjaws-evidence.md` before calling the FluffyJaws connector or recording a `fluffyjaws` manifest block; it defines the SUPPORTING_DISCOVERY-only, re-grounding, and no-FJ-to-AC invariants the `fluffyjaws_evidence` gate enforces.
- Read `references/pr-and-repo-evidence.md` before searching GitHub MCP, inspecting PRs, or using user-cloned repos.
- Read `references/git-repo-sync.md` and use `scripts/sync_evidence_repo.py` before treating a local clone as current product or automation evidence.
- Read `references/design-evidence-flow.md` before using Figma MCP or design screenshots as evidence.
- Read `references/attachment-visual-reference-coverage.md` when an inspected
  attachment or user-provided visual reference shows a named UI surface, visible
  artifact/control, and state variants, or when current evidence names a control that
  edits a value and a distinct surface that displays or tag-renders it, or when an AC
  would name a selectable UI option/action. Record visible facts separately from desired
  behavior, disposition every observed material state and named write/read consumer pair,
  and require direct surface-specific proof before calling a configured/documented result
  a selectable action.
- Read `references/output-template.md` before writing the final test plan.
- Read `references/plain-language-ac-writing.md` before writing or rewriting acceptance criteria. Apply its short-clause limits, one-main-idea rule, simple-word substitutions, and split rules without removing required technical identifiers.
- Read `references/component-routing.md`, then run `python scripts/component_reference_router.py <jira-json-or-text-file> --out <reference-routing.json>`. Load only the returned generic component pack. `references/uac-reference-examples.md` is a non-authoritative regression/evaluation catalog: never load it to route or draft a production plan, and never use an example issue key or its exact values as acceptance authority.
- Read `references/component-authoring.md` when the router selects Authoring, especially for asset-browser thumbnails, map-Xref display labels, hierarchy selection counts, or Explorer filename/title sorting.
- Read `references/component-integration.md` when the router selects the asset CRUD API mechanism, especially for caller-supplied content/metadata, independent filename/GUID identity, or UPDATE-as-UPSERT behavior.
- Read `references/component-platform.md` when current evidence involves asset upload, overwrite/re-upload, duplicate detection, same-name/name or path conflict, Create Asset, an upload conflict, or a conflict endpoint. Use its Asset Upload Conflict Evidence Contract before any bulk/session contract; apply the bulk section only when the router selects its terminal-state, authentication, or session mechanism.
- Read `references/authoring-state-uac.md` when current evidence mentions Author-canvas scroll/viewport/caret state, Map Preview restoration, CALS multi-column deletion, or the `largeFileTagCount` configuration.
- For those mechanisms, run `python scripts/authoring_state_contract.py <jira-text-file> --out <candidate-contract.json>` and use only the route activated by current mechanism terms. An issue key alone must never activate a route. The helper produces candidate AC/scenario wording; current Jira/UAC remains the scope authority.
- Read `references/review-workflow-uac.md` when Jira scope mentions review tasks, review comments, review right panel, comment import, side-by-side review diff, task dropdowns, current/closed task state, or author incorporation of review comments.
- Read `references/open-questions-catalog.md` before writing the `Open Questions` section.
- Read `references/clarification-gate.md` after behavior/coverage discovery and before authoring acceptance criteria. Enumerate every material dimension, resolve it from evidence or ask the user, and stop while a blocking question is unanswered.
- Read `references/v3-reasoning-authoring.md` and `references/discovery-disposition.md` before authoring any behavioral plan or revising its coverage. Build the real evidence-grounded model, run `v3_scaffold.py --manifest <manifest.json>` to create editable graph/closure/question/file-binding records, then run `dimension_synthesizer.py --manifest <manifest.scaffold.json> --json`. Replace every author-review placeholder with an inspected decision and carry each exact discovery through directed retrieval, verification, disposition, and promotion. An axis/feature tag or copied candidate without this chain leaves DISCOVERY REVIEW non-postable. Repeat discovery for a reported omission or scope/behavior change; a wording-only edit is not a fresh completeness run. Scaffold success is not gate success. Do not start from a v2 fixture or generate blanket waivers.
- Read `references/behavioral-coverage-expansion.md` before authoring coverage for any plan whose requirement displays, exports, orders, filters, persists, resolves a reference, moves or renames an item, changes state, or depends on configuration. Populate `behavioral_coverage_expansion` so discovery widens past the literal ask to the behaviors that regress with it, and disposition every activated dimension explicitly. Discovery is not acceptance: an expansion candidate carries no acceptance authority and must not block an explicitly accepted Human contract.
- Read `references/manifest-completeness.md` before finalizing the evidence manifest. Behavioral `behavior_model`, `coverage_hypotheses`, and `verifications` cannot use ordinary author waivers. Every reasoning waiver emits REVIEW and makes the receipt non-postable, including a genuinely reviewed escape.
- Read `references/qe-completeness-coverage.md` before finalizing any plan with Open Questions, regression items, or QE/reviewer checks. Checkable reviewer requirements belong in ACs, not a separate QE-checks section; genuine undecided product outcomes remain Open Questions. Map every requested check to its AC or unresolved question before responding. For UAC-only output, omit a separate QE-checks section. Classify retained full-plan checklist items explicitly in `qe_completeness`.
- Read `references/root-cause-fix-driven.md` whenever current evidence supplies a root cause, linked PR/commit/fix branch/diff, or a positive merged/fixed/verified claim. Populate `root_cause_fix` before authoring so the fix contract, preserved invariants, newly introduced risks, added tests, and verification gaps drive the plan instead of appearing only as citations.
- Read `references/execution-outcome-loop.md` when importing Human or trusted-CI execution results. Validate any `execution_outcome` block; convert only Human-confirmed escapes into governed `CANDIDATE` miss-probe inputs, and use repeated defect-finding ACs only to raise a mapped generic dimension's priority. Never let an outcome auto-author an AC or auto-promote a pattern.
- Read `references/shared-human-uac-learning.md` whenever a Human corrects a generated UAC, asks the skill to learn from feedback, or asks to bind, approve, reject, revoke, supersede, or inspect a shared lesson. Any authenticated tenant teammate may capture; only the ticket's current live QE Assignee, using a personal named Human identity, may bind/review. Capture only the selected correction with its draft identifiers; never upload the whole chat, treat queued/pending feedback as saved or approved, or retry review automatically. Roles, admin status, draft ownership, ordinary Jira Assignee and names in prose grant no review authority.
- Read `references/missing-question-quality-contract.md` before Claude Desktop writes Missing Questions. Submit only hash-bound contextual questions; a generic or rejected question cannot satisfy a mandatory family, and authoritative evidence must be tried before Human escalation.
- Read `references/operational-incident-contract.md` and populate the versioned `operational_contract` manifest block for every plan. Mark it inactive with a concrete reason only when no job, queue, retry, restart, listener, batch, migration, repair, or long-running behavior is involved.
- Read `references/native-aemsite-baseline-metadata.md` when Jira scope mentions Native AEM Site, baseline publishing, output preset metadata, metadata propagation, copy-to, or incremental publishing metadata.
- Read `references/quality-gate-checklist.md` before marking a plan review-ready.
- Read `references/evidence-graph-contract.md` before calling `query_test_evidence_graph`, recording graph evidence, or using a graph-connected claim.
- Read `references/performance-assessment-contract.md` before deciding whether the ticket needs a Performance AC.
- Read `references/api-implementation-evidence.md` whenever the ticket names a code artifact (REST path, servlet operation, handler method, service class, or config key). Read the actual handler in the clone/GitHub and verify the ticket's current-behaviour premise against the code before writing any AC that asserts current behaviour; declare an `implementation_grounding` manifest block citing the inspected `file:line`. `run_gates.py` fails an API/operation plan that asserts current behaviour without this grounding — never write API ACs from the ticket text alone.
- Read `references/security-coverage.md` whenever the plan or manifest mentions XML/DITA parsing or ingestion, DITA upload/import, entity or DTD handling, conref/keyref/href/xref resolution, a content-accepting REST/servlet endpoint, publishing/output to a shared location, or an ACL/role/permission-bearing operation. Populate all three `security_coverage` dimensions and map each applicable one to ACs or a QA-impact Open Question; explicitly disposition genuinely inapplicable dimensions. `security_coverage.py` hard-fails silence after a security signal.
- Read `references/localization-regression-coverage.md` whenever the changed area touches content/topic/map body, metadata/properties, conref/keyref/reuse, publishing/output, or explicitly names translation/localization/XLIFF/multilingual behavior. Populate `TRANSLATION_STATE`, `XLIFF_ROUNDTRIP`, and `PROJECT_TYPES` in `localization_coverage`; map applicable dimensions to ACs or a QA-impact Open Question and give every not-applicable dimension a concrete reason. `localization_regression_coverage.py` hard-fails silence after a localization signal.
- Read `references/upgrade-migration-coverage.md` whenever current ticket or evidence mentions a version/release upgrade, stored-data or schema migration, non-UUID-to-UUID conversion, on-premise-to-cloud migration, backward/forward compatibility, or a fix-version boundary that changes stored data or configuration format. Populate `PRE_STATE`, `MIGRATION_EXECUTION`, `POST_STATE_AND_MIXED`, and `ROLLBACK_OR_IRREVERSIBILITY` in `upgrade_migration_coverage`. `temporal_evidence.py` still owns evidence applicability; `upgrade_migration_coverage.py` hard-fails silence about testing the migration operation itself.
- Run `python scripts/config_settings_lookup.py <ticket-text-file>` for every UAC, on the ticket summary, description and comments. It lists the AEM Guides configuration settings (Publish Configuration Manager, PID com.adobe.fmdita.config.ConfigManager, `data/guides_config_settings.json`) whose product area the ticket touches, with Cloud Service and on-premise defaults, the Experience League page when one exists, and known documentation-versus-source differences. Defaults often differ by deployment (for example versioning on upload, overwriting a checked-out file, and blocking deletion of referenced assets), so a behaviour seen on one deployment can be the configured default rather than a defect. For each listed setting decide: the behaviour changes with it (an AC or scenario covers the values that matter, naming the setting's on-screen label), it is unknown (a TBD), or it does not apply (a one-line reason in the test plan). A setting with no Experience League page is still a real configuration branch; cite the product source. A listed setting is never an AC by itself.
- Read `references/configuration-driven-enumerations.md` whenever Jira, a PR, code, or supplied UI evidence shows that supported attributes, elements, options, labels, actions, or other UI entries come from a repository/profile/OSGi/JSON/CSV/XML configuration. Apply its dynamic-entry, mapping/fallback, applicability, reload, preservation, and hardcoded-consumer checks before finalizing ACs or scenarios.
- Read `references/aem-feature-map.md` before using or disposing `FEATURE_MAP` discovery candidates. It defines the curated, Human-approved, Experience-League-only domain checklist, environment qualifications, fail-open behavior, and the invariant that a matched native feature is an investigation candidate rather than an AC.
- Read `references/offline-authoring-rag.md` before using `OFFLINE_CHROMA` discovery candidates. It defines the local `aem_guides`/`jira_qa` fallback, bounded feature-map query expansion, non-authoritative provenance, Human-UAC exclusion, fail-open behavior, and the invariant that offline history never claims `indexed_history_run=true`.
- Read `references/customer-discovery-learning.md` before importing CSV precedents or using mined/customer-profile candidates. It separates historical AC text from theme-only rows, requires versioned provenance, and keeps all mined advice VALIDATING/non-authoritative until separate Human review.
- Read `references/golden-benchmark.md` only when evaluating or releasing a test-plan skill, RAG, Jira retrieval, evidence graph, ranking, or AC-contract change. The 18-case benchmark is not part of an ordinary plan request.
- When changing or releasing this skill, run `python scripts/audit_production_hardcoding.py`. Any historical Jira identity or known fixture threshold in active instructions, scripts, data, or generic references blocks release. Regression/evaluation catalogs are the only allowed location for such examples.
- Run the compatibility preflight `python scripts/run_gates.py --plan <body> --combined <plan+appendix> --manifest <manifest> --receipt <gate-receipt.json>` before delegation. New records use evidence-manifest schema `aem-guides-evidence-manifest-v3`; legacy v2 records remain readable but cannot bypass behavioral reasoning. Populate activated blocks through `references/v3-reasoning-authoring.md`. Reasoning waivers are exceptional, non-postable review records under `manifest_completeness_gate`, not a substitute for executing the pipeline. The preflight validates exact artifact binding, AC grammar, UAC/status fidelity, source-requirement fidelity, enumerated requirements, operational and concurrency contracts, semantic records, and self-tests. Its receipt proves only that the input record is safe to delegate; it is not authority for a final plan. A nonzero result or `postable=false` stops the run.
- Set `UAC_GATE_LOG=<path>` (or pass `--gate-log <path>`) to append which gates fired to a JSON-lines log; `python scripts/gate_firing_log.py report <log>` shows how often each gate and each `coverage_forcing` sub-check fires. Recording never changes a gate result. Merge, demote or remove a gate only from this data and from what it caught, never from one ticket.
- After the preflight exits 0, route the same artifacts through `python scripts/canonical_runtime_adapter.py --jira-key <key> --tenant-id <tenant> --manifest <manifest> --plan <full-plan.md> --receipt <gate-receipt.json> --out <runtime-envelope.json>` when the Dataset Studio backend checkout is available through `--repo-root`, `AEM_STUDIO_REPO`, or an ancestor directory. When Claude has a submission bound to the returned `qe_investigation.preparation_id`, also pass `--claude-question-submission <submission.json>`. The adapter must verify the receipt and every bound hash, invoke the fixed canonical stage order exactly once, and return the canonical gates, structured plan, trace, and `rendered_output`. Caller-supplied prose or gate-status text is never authority.
- In a packaged Claude installation without that backend checkout, call the configured `guides_test_plan_generator` MCP tool instead and accept its result only when `runtime_id=aem-guides-test-plan-runtime`, the trace contains the full canonical stage order, and the three canonical gates are present. This is a transport fallback to the same VM runtime, not a second reasoning path. If neither canonical transport is available, stop safely.

### Host-Mediated Agent Research (Copilot coordinator loop)

For an interactive generation request (`Generate UAC for <JIRA-ID>`) running under the Copilot host, run the canonical pipeline with host research enabled - set `AGENT_RESEARCH_MODE=copilot_host` for the command (the store is `AGENT_RESEARCH_STORE` when set, else `backend/storage/agent_research/`). The user never participates in the agent handoff: this coordinator loop is fully automatic, and the user sees only the final UAC or a genuinely necessary clarification.

When the canonical runtime returns `status=waiting_for_agent_research`, required research was dispatched to bounded worker agents and the run is WAITING for their results - it is NOT blocked on a product decision, and it must not be presented as one. The Copilot host (this coordinator) owns delegation; Python never launches agents and the primary agent never researches on the workers' behalf.

Loop until the run leaves `waiting_for_agent_research` (bounded: at most 3 passes, then report honestly):

1. List pending research: `python scripts/agent_research_bridge.py pending --store <store>`.
2. For each unfulfilled request, delegate to the registered custom agent matching its `worker_role` (`uac-doc-researcher`, `uac-code-researcher`, `uac-attachment-researcher` - registered via `.github/agents/*.agent.md` and the user-level Copilot agent directory): call the `task` tool with `agent_type` set to that agent name and `mode: "background"`, launching the whole batch BEFORE reading any result so the researchers execute in parallel. Delegation is INTERNAL - `task` runs each researcher in its own context window and creates NO user-visible conversation. NEVER use `create_session` (or any `open_*_session` tool) to run research: those create one user-visible sidebar session per leaf and break the one-conversation invariant. The task prompt carries ONLY the bounded request context: `execution_id`, `question_id`, `question_revision`, `worker_role`, `requested_claim`, `research_requirement`, `required_source_types`, `product_context`, `research_terms`, and applicability - plus the FULL `authorized_evidence` rows from the pending request (each `source_ref` with its `source_type` and `excerpt` text; the leaf's bounded toolset cannot resolve bare evidence IDs, so never send IDs without their content) and, for `CODE_RESEARCHER`, the `authorized_repository_roots` paths the leaf may inspect plus each root's current HEAD (compute it yourself with `git -C <root> rev-parse HEAD`; the leaf has no shell and verifies code by reading files, so it cannot resolve HEAD on its own). For `ATTACHMENT_RESEARCHER`, pass the `attachment_files[]` rows verbatim (each `source_ref` with its local `path` or its exact `error`) so the leaf opens real attachment content. For `DOC_RESEARCHER`, pass `documentation_roots[]`, `documentation_queries[]`, `rag_candidates[]`, and `rag_status` verbatim; `product_context` is a source-ownership boundary, so the agent must not use another product's page to answer this question. Close with the instruction to follow its role contract's `Return handoff` section (exactly one reply whose entire body is the strict result JSON). Agent chat prose is not a result.
3. Collect each agent's actual response with `read_agent` - one read per `agent_id` after its completion notification arrives; never poll a running agent. NEVER write, paraphrase, or repair the result yourself - if the reply is not one strict JSON object (`status`, `findings[]`, `source_refs[]`, `applicability`, `limitations[]`, `conflicts[]`), ask that agent once via `write_agent` to resend only the JSON; if it still cannot, record that execution as failed rather than fabricating compliance.
4. Submit each collected result through `python scripts/agent_research_bridge.py fulfill-agent --store <store> --execution-id <id> --result <file.json> --model <model>`, where `<model>` is the model recorded in the delegated agent's actual execution metadata (never an assumption). The bridge takes every identity field from the emitted pending request and stamps `provider=COPILOT_HOST` plus the canonical role-contract version itself. A validation failure is final for that execution - never edit the result to force acceptance.
5. Re-run the same canonical command with the same store. Fulfilled results are consumed exactly once; the trace records `provider=COPILOT_HOST`, `model_execution=true`, and the agent's model.
6. Terminal-event discipline (one user-visible conversation per UAC request): researcher lifecycle events - completion notifications, failures, cleanup acknowledgements - are INTERNAL TERMINAL EVENTS, never new work items. They must not trigger orchestration (no new delegation, no resume pass, no UAC state change) and must never recursively trigger another response cycle; the parent performs at most one internal completion transition per execution, and a finished researcher is never re-entered. Normal research results and error results still arrive exactly once through `read_agent` and are consumed exactly once - that channel is unaffected. Because research runs through the `task` tool, no leaf session is created and there is nothing to archive; emit NO user-visible message for any of these events. If a leaf session from an older run still reports in, treat its message as evidence only, never answer it, and never re-enter orchestration for it.
7. Debug mode is the only exception: when the user explicitly asks for diagnostics/audit, or `AGENT_RESEARCH_DEBUG=1` is set in the environment, the parent may surface leaf execution IDs, agent IDs, receipts, and logs. Normal UAC generation never shows them.

Output hygiene: research results, execution IDs, bridge operations, provider/model receipts, and intermediate runtime states are INTERNAL. Present only the final canonical `rendered_output` (or the one genuinely blocking clarification). Surface receipts/internals only when the user explicitly asks for debug or audit detail. While research runs, post exactly one status line ("Researching relevant Jira evidence, documentation, attachments and implementation..."); never narrate per-leaf progress.

Only after research resolves may clarification/TBD logic surface a question to the user. If the host cannot delegate (agent not registered, no response), the run stays waiting and you say so plainly - never silently substitute deterministic research or self-research when host research was configured, and never substitute a general-purpose agent for the registered role agent.

Convergence and conversational clarification: after mandated research resolves, the runtime evaluates the collected evidence per material question across three perspectives - Product/PM (intended contract), Developer (implementation reality), QE (observable/negative/regression) - recorded in the payload `convergence` block with agreements, conflicts, and acceptance-changing unknowns. The runtime never invents a missing product decision. When the final output lists Open product decisions, each carries its evidence and any conflict: present them conversationally and product-specifically, like a real refinement discussion. When the user answers, feed the answer back as an explicit human clarification (the CLI `--clarifications` file) and re-run the same command to reconverge before generating the UAC.
- Return only canonical `rendered_output` / `plan_markdown` when `status` is `completed` or `needs_human_review`, `validation_status=passed`, and ContractIntegrityGate, BehavioralCompletenessGate, and AcceptancePromotionGate all passed. `needs_human_review` is a valid fresh-Jira result but is never postable or Jira-write authority. Do not run `render_compact_view.py` as a second final renderer. It remains a compatibility preview for old stored records only.
- Before handing acceptance criteria to an AI automation-draft agent, run `python scripts/extract_acs.py <full-plan.md> --out <acceptance-criteria.json>`. A nonzero exit blocks handoff. The automation agent consumes this JSON and must not re-parse chat prose or invent setup, actions, assertions, or evidence outside its fields.
- Jira mutation is a separate, explicit human-authorized step. A compatibility receipt alone is not enough to authorize a write: the posting boundary must also verify the completed canonical runtime envelope and post only canonically promoted acceptance records. Until a posting client supports that binding, stop rather than use the legacy compact or eleven-section draft as authority.
- The compatibility record and evidence manifest have more mandatory detail - minimum manifest fields, `history_attempts`, `feature_class_registry.py`, `relationship_traversal.py`, UI consumer edges, implementation scope authority, configuration enumeration scope, `validate_test_plan.py`, `verify_evidence.py` (source paths and attachment manifests), and the automation-evidence appendix. Read `references/reasoning-pipeline-phases.md` (section "Compatibility record and manifest details") before writing the manifest.

### Deterministic Authoring-State Routing

- **Authoring viewport stability** is the route only when current evidence identifies the Author editing canvas plus an active caret/selection/element, reference insertion, or viewport-jump symptom. Cover only source-named triggers and state, then investigate other actions that share the verified viewport/focus controller. Restore visibility relative to the active element when that relationship is approved; do not import a historical action matrix or exact pixel offset.
- Do not automatically add left map-tree/outline state, save/reopen persistence, old/new editor parity, or numeric performance thresholds to an Authoring viewport plan unless current Jira/UAC evidence names them. Large content is a fixture, not an SLA. Do not claim data loss when the evidence establishes only disruption or wrong-location risk.
- **Map Preview state restoration** is a separate route. Enumerate only the preview state and transitions named by current evidence; treat scroll, selected topic, panel/condition state, refresh, and Edit-return as independent candidates until a shared state owner/consumer is verified. Area overlap such as `scroll` does not make Map Preview a same-mechanism Author-canvas match.
- **CALS multi-column deletion** uses the source-defined row/column counts and selected-column positions with distinct cell values. The result keeps the row count, removes exactly the selected columns, preserves retained content/order, produces no ghost column, and leaves no orphan column/span metadata. Do not import historical counts or add `simpletable`/`reltable` parity unless current evidence names them.
- **Large-file safeguard behavior** is configuration-driven when current evidence names `largeFileTagCount`. Test immediately below and at/above the effective parsed-tag threshold. Never convert an observed UI item, cell, or file count into the configured parsed-tag boundary or an invented performance SLA.
- Exact screenshot-only Jira examples may teach a generic candidate pattern but must not be indexed as an exact historical Jira record. Exact UAC indexing requires a live Jira record or Jira CSV provenance with a verified source hash.

### Component-Scoped Reference Routing

- Canonical Jira component labels select the first reference pack. When the component is missing, infer it from accepted UAC, then summary, then description, and record the inference source. Component routing reduces prompt size; it does not establish product behaviour.
- If the accepted UAC and stale description describe different mechanisms, use accepted UAC for ACs/scenarios and keep the displaced request out of Confirmed scope. Surface it only as an evidence-backed Open Question when QA sign-off depends on its disposition.
- When a later accepted scope conflicts with an older description, use the accepted scope and retain the older request only as context or an Open Question. For example, a thumbnail contract does not inherit an older multi-selection request; generic wording that selection still works does not authorize new selection semantics.
- For map-Xref display labels, separate visible text from destination semantics. Preserve `href`, `format`, `scope`, `type`, and external-link behavior unless current accepted evidence changes them. A duplicate or historical issue without accepted UAC can support retrieval only, not an AC.
- For hierarchy-selection counts, derive the expected selected set and count from the current fixture. Test a cold first interaction and a repeat interaction; later self-recovery cannot hide an initial mismatch. Do not import a historical count, content-type list, or root-cause theory.
- For Explorer sorting, keep display label, sort key, sort direction, persisted preference, and feature-flag state separate. Use only the interaction and defaults shown by current accepted UAC or inspected design/runtime evidence. A static image cannot establish hidden menu behavior, precedence, persistence, collation, or accessibility state; expose those missing decisions instead of copying an historical design.
- For asset CRUD API requests, keep filename, path, product identity, version identity, and response identity independent. Discover the current endpoints, fields, defaults, and existing/missing-target behavior from the target handler and approved contract. Keep CREATE/READ/UPDATE/DELETE controls separate even when names look similar. Never import a legacy endpoint or parameter from a historical example; unresolved payload, collision, atomicity, status, retry, and file-type decisions become Open Questions.

## Lifecycle

### Phase 0 — Run Evidence Preflight And Classify Stage

- Before drafting, check `product_rag`, `jira_history`, `live_jira`, `git`, and `figma` exactly as defined in `references/evidence-preflight.md`; record all five results in `evidence_preflight` with a timezone-aware timestamp.
- Do not label a source available because its MCP, credentials, endpoint, or clone is configured. `available` requires a successful lightweight call or inspected evidence; `not_applicable` requires a lifecycle/input reason.
- Enter `degraded` mode whenever any required check is unavailable. Continue with supported work, but apply the source-specific claim restrictions and lifecycle-aware readiness impact instead of inventing facts or blocking unrelated claims.
- Start `Evidence boundary:` with `Evidence mode: full` or `Evidence mode: degraded`. In degraded mode, name every unavailable source and state what remains unverified.
- Classify the lifecycle stage before applying evidence gates:
  - `Pre-Development UAC`: acceptance criteria are being created or refined and development has not started.
  - `Implementation Review`: a branch, commit, PR, patch, or active implementation exists and code-impact review is required.
  - `Post-Fix Validation`: a candidate fix/build exists and QA sign-off or regression validation is required.
- Classify the input source: Jira, Dynamics/support case, customer escalation, logs, screenshots, investigation notes, PR, branch/commit, pasted diff, Figma, local clones, or a combination.
- Infer `Pre-Development UAC` when the user states that UAC is not final, development has not started, or no code change exists. In this stage, missing PR, changed files, and line counts are `Not applicable`, not Draft blockers.
- Treat operational incidents as valid pre-development inputs when they include customer context, symptoms, logs, investigation findings, recovery actions, similar incidents, and an end goal. Normalize these facts into an acceptance contract and targeted open questions.
- If the stage is unclear, infer it from explicit evidence and state the assumption under `Scope From Git`; ask only when the distinction materially changes the plan.
- Keep a pre-development plan Draft only for missing sign-off-critical UAC decisions, unsupported expected behaviour, missing required product-clone evidence, or unresolved environment/test-data constraints—not merely because implementation does not exist.

### Phase 1 — Collect Issue Facts

- Use connected Jira MCP first for a Jira-backed request whenever available; otherwise use pasted Jira, Dynamics, support-case, customer-escalation, logs, screenshots, and investigation details and identify the source.
- When the user supplies a concrete Jira key, fetch that issue before drafting the plan. Do not silently describe the source as pasted text, and do not continue from historical RAG as though it were the live issue. If Jira MCP cannot fetch the key, state the exact Jira evidence failure; use pasted issue content only when the user supplied it.
- Treat placeholders such as `GUIDES-XXXXX` as missing input, not as a real Jira key. Ask for the actual key instead of producing a Jira-backed plan.
- Extract summary, description, expected/actual behaviour, acceptance criteria/UAC, customer and business impact, environment, product/version, logs, error text, affected assets/workflows, actions already taken, requested engineering help, attachments, linked issues, and development links when present.
- Resolve customer context from explicit Jira customer/account fields first, then customer-identifying labels. Preserve multiple customers separately, surface material field/label conflicts, and never infer a customer from reporter identity, email, IMS Org ID, or incidental description text.
- Do not stop at attachment filenames. List every attachment (Jira MCP `list_attachments`), then download and actually analyse each one that could carry evidence: `download_attachment` to a scratchpad path, then Read images/screenshots visually, open logs/HAR/stack traces as text, and inspect sample DITA/maps/zips. Extract concrete facts a QA plan can assert — exact property values and identifier formats (for example `GUID-<uuid>-en`), how a symptom actually renders in the UI (for example an orphan shown as an empty value between commas), affected columns/fields, enum values, error strings, timestamps, and counts.
- When an inspected attachment or user-provided visual reference names a UI surface,
  visible artifact/control, and state variants, record it in
  `visual_reference_evidence` and use the attachment visual-reference contract. The
  image proves visible facts only; it cannot itself promote an expected behavior. Map
  every observed material state to an AC, Open Question, or evidence-backed
  out-of-scope decision rather than covering only the broad feature.
- When current evidence names a control that edits a value and a distinct surface that
  displays or tag-renders that value, record
  `write_read_consumer_parity_evidence`. Disposition the named writer/reader pair in
  `dimension_inventory`: an AC must verify the edit is reflected in the named reader,
  unless a concrete out-of-scope decision or Open Question applies. Do not infer
  unmentioned consumer surfaces.
- When an AC asserts that a selectable UI option/action already exists, record
  `ui_action_surface_evidence` and its `dimension_inventory` disposition. Cite current
  evidence that names that action on that exact surface. A configured or documented
  outcome alone is not proof that a separate selectable action exists. Preserve the
  source-backed requested outcome independently; an unsupported existing-action claim
  becomes an implementation Open Question, never a reason to remove that outcome.
- Also mine content embedded in the description and comments, not just prose: inline log/stack-trace snippets, code or JSON/XML blocks, tables, `{noformat}`/`{code}` regions, and pasted images. Treat these embedded snippets as first-class evidence alongside attachments.
- Before discovery or hypothesis processing, populate
  `authoritative_source_coverage` schema
  `aem-guides-authoritative-source-coverage-v1`. Atomize the current Jira
  description, each retained comment, and each analysed attachment with retained
  inspected text. Every material atom maps directly to an AC, a concrete
  out-of-scope disposition, or a genuine decision Open Question through
  `contract_facts`; retain non-contract context only with a concrete
  `NOT_MATERIAL` reason. A hypothesis may add investigation, but it must never
  select, narrow, or drop a ticket fact.
- Label each such fact by provenance (for example "verified from the attached screenshot") and prefer it over inference; when the plan would otherwise say "matches the attached screenshot", the screenshot must have been opened, not merely listed. If an attachment cannot be fetched or opened, say so explicitly rather than describing its contents.
- Treat supplied UAC as authoritative. When UAC does not exist, derive a proposed acceptance contract from the problem statement and end goal, label every derived criterion `[Proposed]`, label Jira criteria `[Confirmed]`, and do not pretend proposed criteria are already approved.
- Historical observations, completed cleanup steps, support comments, and previously successful recovery are evidence for `Expected Behaviour` or `Incident recovery validation`; they are not Jira-authored AC and must not receive `[Confirmed]` when the native Jira/UAC acceptance field is empty.
- Do not convert a working-as-designed complaint into Confirmed AC. Preserve the current surface-specific behavior as a non-fix historical decision, and label any requested harmonization or taxonomy change `[Proposed]` until a new enhancement Jira supplies accepted UAC.
- Do not treat a configuration-gated control as removed or deprecated merely because it is hidden by default. Verify the exact configuration key/value and default, distinguish product changes from documentation or automation-only work, and never create `[Confirmed]` AC when Jira says `UAC Not Required`.
- Product-fix chronology without accepted UAC remains candidate regression evidence. Explicit `fixed in develop`, merged/cherry-picked hotfix, and exact build-verification comments may prove that code changed and named builds were exercised, but they do not supply an accepted behavior contract or root cause. Keep all derived ACs `[Proposed]`, preserve the exact release/build boundaries, and do not mark the history as a verified reusable fix until the behavior contract, RCA, and QA oracle are all explicit.
- Preserve contradictory automation labels such as `Automated` and `Won't_Automate` as an evidence conflict. Inspect linked automation or ask which label is current; never guess the coverage verdict from either label alone.
- Respect investigation chronology. Text using `could`, `may`, `seems`, `hypothesis`, `to confirm`, or equivalent language is not a confirmed root cause; a later explicit confirmation or invalidation outranks it. Keep disproved theories as negated context and never reuse them as RCA, expected behaviour, or Confirmed AC.
- Do not equate `Resolution: Fixed` with a verified product-code fix. Inspect final comments and implementation evidence. When a Jira is explicitly closed through a workaround, configuration migration, or documentation follow-up with no product change, classify it as non-product historical risk, never as `implemented_fix`, `[Confirmed]` AC, or current expected behaviour. A later explicit merged or build-verified product fix may override an earlier workaround.
- Never merge a mainline accepted UAC into a hotfix ticket when final Jira evidence explicitly narrows the hotfix. Preserve the release/build boundary, reuse only the stated point-fix behavior for that hotfix, and keep the broader mainline contract as candidate context.
- Collapse repeated identical UAC blocks deterministically before assigning source IDs; duplicate pasted criteria must not create duplicate ACs, scenarios, evidence weight, or coverage credit.
- Treat `Automation` sections and automation-PR notes as execution context, not product acceptance clauses. They can prove coverage or expose gaps, but cannot broaden accepted behavior.
- Incident workload observations are not performance SLAs. A repository size, file count, observed duration, 503, CPU/memory spike, or crash proves performance relevance, but pass/fail thresholds require an approved workload, environment, repetitions, percentile, timeout, and resource ceiling. When accepted UAC says no performance change and supplies no threshold, set `performance_contract_complete=false` and ask for the missing oracle instead of inventing one.
- Do not invent AC, comments, customer impact, linked PRs, or related Jira keys.
- Assign stable IDs (`AC-01`, `AC-02`, ...) to every acceptance criterion. These IDs are internal traceability only: scenario mappings, manifest `ac_refs`, and lineage keep the `AC-##` form. The human-facing label is spelled out as `Acceptance Criteria 01`, `Acceptance Criteria 02`, ... in every delivered chat block and posted Jira Acceptance Criteria field, because `AC-01` matches Jira's issue-key shape `[A-Z]+-\d+` and is auto-linked and struck through. Write each criterion as an independently testable product contract containing input or precondition, behavior, and observable outcome. The human-facing projection states the named item and its observable result directly; do not write acceptance criteria as generic `Verify...` test instructions, and never use `Verify that the system...`.
- Write for first-read understanding. Lead with one concrete outcome in a short sentence, use familiar QE words and the documented product name; in the full record, place required cases in short sub-points (the delivered UAC is flat - see "## Acceptance Scope And The Delivered UAC"). Do not force setup, action and result into one long sentence. Move implementation jargon to a `Note for developer:` without removing source-required identifiers. Follow `references/plain-language-ac-writing.md` for loss-less grouping and terminology. Outcomes over 28 words or two sentences require review; only grossly long outcomes hard-fail.
- Evaluating an existing or AI-supplied AC/UAC set must construct the same evidence manifest and run the full `run_gates.py` pipeline. Never return a conversational-only review as if it were a gated evaluation.
- Preserve human reviewer wording as the semantic baseline. Simplify structure without changing its actor, scope, UI label, timing, fallback, exact path, or outcome. If current code conflicts, keep the requirement Proposed and expose the conflict as an Open Question instead of substituting the implementation behavior.
- Never reference another AC ID inside an AC. Repeat the short observable rule or split the criteria so every AC is independently readable and testable.
- Split compound requirements when their required behavior or outcomes differ. Independent failure of two test cases alone does not require two ACs. Preserve every named enum, mode, project type, provider, state, filter, version boundary, and failure outcome as a distinct contract or an explicit same-outcome matrix within one AC; never hide differing fallback, timing, ordering or permission rules.
- Convert unclear AC into tester-readable product contracts and keep ambiguity visible. Never infer defaults for omitted filters, duplicate handling, reference classification, rollback, response codes, or status semantics; move undecided behavior to `Open Questions`.
- AC decidability is a hard gate. Reject unresolved/conditional markers (`to be agreed`, `pending scope`, `if approved`), vague bounds (`bounded`, `reasonable`, `does not continue forever`) without a numeric/configured/source-backed oracle, implementation-choice menus (`via an index, keyset, or custom index`), and combined terminal outcomes (`failed or aborted`). Define success, failure, cancellation, shutdown, retry exhaustion, and recovery separately when applicable. A number elsewhere in the sentence does not quantify an unrelated bound.
- Transcribe every reporter-numbered or bulleted requirement into `enumerated_requirements` schema `aem-guides-enumerated-requirements-v1`, preserving source order and count. Each `REQ-##` maps to real `ac_refs`, one real `open_question_ref`, or an explicit out-of-scope reason. Independently pass/fail items may share an AC only with a concrete `shared_contract_justification`; list omission and unknown references are hard failures.

#### Source Requirement Fidelity Gate

- Whenever `enumerated_requirements.active=true`, populate `source_requirement_ledger` using schema `aem-guides-source-requirement-ledger-v1`. This requirement applies even when `accepted_uac_present=false`; acceptance authority and semantic fidelity are separate decisions.
- Record each source as a stable `SRC-##` object with `type`, durable `locator`, exact `raw_text`, and the lowercase SHA-256 of that UTF-8 text. Do not normalize, summarize, or reconstruct the raw source before hashing it.
- Record one ordered ledger item for every enumerated `REQ-##`. Its `verbatim_text` must be an exact substring of the cited source; its `text` must exactly equal `verbatim_text` and the corresponding enumerated text. The source index, disposition, and AC/Open Question mapping must also match the enumerated item exactly.
- Give every ledger item an independent `authority` of `Proposed` or `Confirmed` and a non-empty set of semantic atoms. Authority controls status elsewhere; it never disables the fidelity check.
- For every atom, copy `text` as an exact substring of the item's `verbatim_text`, then declare `required_terms_all` and/or `required_terms_any` that must survive in the mapped AC or Open Question. Do not replace user-level, per-user, role, scope, timing, fallback, surface, upgrade, configuration, or other source semantics with an implementation observation.
- Preserve exact paths, URLs, backticked names, code-like identifiers, config keys, and any additional `protected_exact` values from the verbatim source in the mapped AC/Open Question. A shortened label or generic phrase is not equivalent to an exact identifier.
- When implementation evidence conflicts with a source atom, do not silently substitute the implementation behavior. Mark that atom `evidence_conflict=true`, map it to a real `open_question_ref`, and preserve the conflicting atom and protected identifiers in that question. Resolve the source contract before sign-off.

#### Authoritative Ticket Source Coverage Gate

- For a behavioral v3 Jira record, build `authoritative_source_coverage` schema
  `aem-guides-authoritative-source-coverage-v1` before discovery. Include the
  exact description, each retained comment, and every analysed attachment with
  retained inspected text. Each source declares its exact raw text, SHA-256,
  inspection, and completed atomization.
- Atomize every material source clause and bind it to existing `contract_facts`.
  Each atom must map directly to an AC, a concrete out-of-scope reason, or a
  genuine Open Question. Retain non-contract context only as `NOT_MATERIAL` with
  a concrete reason. The gate checks that every source clause is accounted for;
  a selective summary is not a complete atomization.
- Perform this comparison before `coverage_hypotheses`. Hypotheses, historical
  matches, current implementation, and ownership/action evidence may widen
  investigation but cannot select, narrow, or remove a ticket fact.
- When current implementation does not prove a claimed existing UI action, keep
  the source-backed requested outcome mapped and expose the action claim as an
  implementation Open Question. Do not delete or down-scope the outcome merely
  to satisfy action proof.

#### Accepted UAC Fidelity Gate

- When Jira or the user supplies final accepted UAC, normalize it instead of independently redesigning it. Preserve 100% of its semantic contract: scope, prerequisites, trigger, expected outcome, ordering, formatting, defaults, exact config names and values, parity targets, and out-of-scope boundaries.
- Assign internal source IDs (`UAC-01`, `UAC-02`, ...) to every accepted in-scope clause and (`OOS-01`, `OOS-02`, ...) to every out-of-scope clause. Require bidirectional traceability: every accepted in-scope clause maps to at least one `[Confirmed]` AC, and every `[Confirmed]` AC maps back only to accepted clauses.
- Splitting a compound accepted clause into atomic ACs is allowed; weakening it, broadening it, replacing its oracle, or adding a more specific outcome is not. Preserve exact identifiers such as feature flags, preset arguments, fields, enums, output names, and ordering rules.
- Treat the newest accepted UAC as higher authority than earlier draft ACs, linked test tickets, RAG, historical Jira, comments, or an earlier generated plan. Keep useful extra coverage `[Proposed]`; never use it to silently change a `[Confirmed]` outcome.
- When the native acceptance field is empty, a Jira comment may supply Confirmed UAC only when the issue has an accepted-UAC label and the comment explicitly declares a final/accepted `Scope:` or says the ticket scope is limited to named behavior. Use the chronologically latest such comment, record `jira_comment_accepted_scope`, keep earlier scope proposals as chronology context, and never promote arbitrary discussion, a pending-scope comment, or any comment when Jira says `UAC Not Required`.
- When accepted UAC says behaviour must match another surface such as AEM Sites, use that surface as the comparison oracle. Compare the accepted dimensions explicitly: entry presence, visible text, order, formatting, clickability, and destination. Do not invent a more specific result until the reference output has been inspected or Jira states it.
- When behaviour requires independent controls, such as a server feature flag plus an output-preset argument, keep them separate and cover the configuration truth table. Do not substitute one control for the other or claim the feature is enabled when only one prerequisite is present.
- Do not turn out-of-scope outputs or behaviours into sign-off ACs. They may appear only as a clearly non-blocking boundary confirmation when needed; a known intentional difference must never be reported as a failure.
- Record the internal comparison in the evidence manifest under `uac_fidelity` using schema `aem-guides-uac-fidelity-v1`. Set `accepted_uac_present=true`, map every accepted clause, list unresolved clauses, contradictions, and scope expansions, and mark `status=pass` only when all accepted clauses are covered with no unresolved clause, contradiction, or expansion. Keep this audit out of the visible test-plan sections.
- Set `accepted_uac_present=false` explicitly when no accepted UAC exists; then omit `uac_fidelity` and keep every AC `[Proposed]`. `Needs_Human_Review`, implementation evidence, a posted draft, or user interest in a behavior does not convert it to `[Confirmed]`. Actual plan statuses must exactly match the fidelity manifest.

### Phase 2 — Normalize Behaviour

- Before summarization, build `contract_facts` schema `aem-guides-contract-facts-v1`. Preserve literal source wording for direct expected behavior, scope, product/output/preset, DITA-OT state, deployment/version, feature state, exact labels/defaults/values/status/colors/counts/limits, human terminology, compatibility, negative requirements, and human/engineering questions. Every material fact must land in an AC, Open Question, explicit scope/out-of-scope record, or a justified non-contract disposition. `contract_integrity_gate.py` fails when a protected term or outcome disappears from the visible plan.
- Route the issue with `issue_domains` schema `aem-guides-issue-domains-v1`; never select a Jira-specific prompt. Classify only positive, in-scope source clauses: ignore negated, unaffected, not-applicable, and structured out-of-scope values. Recognize normal inflections/plurals and treat an explicit thousand-scale workload as a performance-risk route, not as an invented SLA. Active `PUBLISHING` requires `publishing_scope`; it requires `generated_output_contract` only when source evidence places generated artifact content, structure, or delivery in scope. Publishing configuration alone never implies a download/delivery contract. Active `ASSETS` requires `content_identity_contract`. Resolve exact preset/output ownership, `Enable DITA-OT Processing` as `ON`/`OFF`/`BOTH`/`NOT_APPLICABLE`/`UNRESOLVED`, deployment, in/out of scope, and shared-path outputs. When generated delivery is in scope, record `delivery_in_scope=true`, its real surface, and a covered `DELIVERY_AVAILABLE` product oracle; when it is out of scope or unresolved, disposition that oracle accordingly. Unresolved fields become Open Questions; do not silently test every output type.
- Build `behavior_graph` schema `aem-guides-behavior-graph-v1`. Each node and typed edge cites an ID in the canonical source/evidence registry. Each edge records a subject and an authority allowed by that subject's policy, plus currentness, applicability, confidence, verification state, and materiality. Inferred edges are investigation candidates only. Traverse a bounded code/semantic neighborhood and record readers, writers, callers, consumers, configuration, generated artifacts, shared processors, error paths, persisted state, and downstream decision consumers.
- Complete `semantic_closure` schema `aem-guides-semantic-closure-v1` for every material graph entity. Every canonical dimension must be explicitly `APPLICABLE`, `NOT_APPLICABLE`, or `UNRESOLVED`, then end as `COVERED`, `INVESTIGATED_AND_REJECTED`, or `UNRESOLVED_AND_EXPOSED`. Do not use wildcard entity references: every closure decision must name the evidence-bound material entity it covers. Omission is not equivalent to not applicable.
- Every material unresolved fact, edge, or closure record automatically requires a linked `missing_questions` record with subject-specific preferred sources, an `OQ-##` destination, and a genuinely new linked second-pass query in `evidence_lifecycle`. Every USED/REJECTED evidence record links to a declared question or hypothesis. A verification may cite only USED evidence bound to that same hypothesis and subject; every claimed authority must be carried by that cited evidence. No retrieval result remains unresolved; it is never treated as `REJECTED` by absence.
- Route every accepted material question through mandatory research routing before coverage finalizes it (Question Planner -> Research Requirement Classification -> Doc/Code/Historical research -> Question Resolver -> Coverage Reasoner -> Writer -> Reviewer). Classify `research_requirement` (`NONE`, `DOCUMENTATION`, `IMPLEMENTATION`, `HISTORICAL`, `DOCUMENTATION_AND_IMPLEMENTATION`, `MULTI_SOURCE`) from the question's declared evidence path immediately after question planning, execute the mandated research, and record `research_status` (`NOT_REQUIRED`, `PENDING`, `ANSWER_FOUND`, `PARTIAL`, `NOT_FOUND`, `SOURCE_UNAVAILABLE`, `CONFLICTED`, `NOT_APPLICABLE`) with the request/evidence links in the `question_research` manifest block, enforced by `scripts/question_research.py` (see `references/question-research-routing.md`). Hard gate: a material question whose requirement is not `NONE` and whose status is still `PENDING` fails review, and Coverage must not finalize it from the current Jira/configuration evidence alone; the Writer never compensates for missing research. `NOT_FOUND` means the mandated research executed and found no answer - it never asserts the opposite behavior. An explicit Human Accepted AC classifies `NONE`/`NOT_REQUIRED` and proceeds on Jira authority without unnecessary documentation research. The canonical runtime enforces the same contract in its `ResearchRequirementClassifier` stage.
- Keep "documented today" separate from "required after this fix" (enforced by `scripts/behavior_classification.py`; see `references/behavior-classification.md`). Existing documentation establishes baseline/current behavior; the current ticket establishes desired new behavior. Classify every resolved behavior as `EXISTING_CONFIRMED`, `NEW_REQUIREMENT`, `MODIFIED_EXISTING_BEHAVIOR`, `PRESERVED_EXISTING_BEHAVIOR`, `UNKNOWN`, or `CONFLICTED` in the `behavior_classification` manifest block. Never use existing documentation to claim a new feature is already documented, never describe new implementation/configuration as historical documented behavior, name the existing behavior that must remain compatible (`PRESERVED_EXISTING_BEHAVIOR`), and combine sources in an AC's `Evidence:` line only when each source genuinely supports part of that AC - a source line never credits a documentation source for behavior that documentation does not establish. `UNKNOWN`/`CONFLICTED` behaviors stay open questions until resolved.
- Disposition every material contract fact, graph item, closure record, generated-output oracle, and content-identity lifecycle state exactly once. Run `acceptance_promotion.py` separately from hypothesis verification: code, PR, runtime, tests, history, or inference may establish actual implementation but cannot alone authorize intended product behavior. A candidate and visible AC may each be promoted at most once; candidate, subject, authority, disposition, mapped AC, and visible Confirmed/Proposed status must all agree. Every visible AC must have a subject-authorized promotion record; regression, implementation mechanics, unsupported exact values, and unresolved decisions cannot promote.
- Convert Jira text into current behaviour, expected behaviour, affected workflow, data shape, error contract, version boundary, configuration boundary, roles/permissions, user impact, and open questions.
- Build an integration impact map: direct workflow, upstream callers, downstream outputs, shared components/APIs, configs, roles/permissions, environment matrix, test-data fixtures, and automation suites likely affected.
- Derive edge cases from UAC boundaries, inspected PR branches, API contracts, config permutations, old automation failures, and past similar tickets.
- When a configuration defines a set of supported UI entries, do not test only the entries visible in the supplied environment. Include a newly added valid entry and use `references/configuration-driven-enumerations.md` to separate membership discovery, friendly/display-name mapping, unmapped fallback, active schema/profile applicability, supported reload timing, preservation of existing entries, and invalid or duplicate configuration behavior. Inspect every consumer for hardcoded arrays, enums, switches, and default maps that can silently exclude future entries.
- Complete the internal principal-performance-QA review from `references/performance-assessment-contract.md`: assess all seven scale, concurrency, duration, latency/throughput, resource, dependency/queue, and stale-state categories using Jira, attachments/logs, exact docs, same-mechanism history, and inspected code. Store only the structured decision and provenance in the evidence manifest; do not add a Performance Analysis section or standalone plan bullet.
- Use exactly one performance decision. `required` emits one or more evidence-backed `(Performance)` ACs with a quantified workload and numeric or source-backed comparative metric oracle plus mapped performance scenarios. A retained same-mechanism or inspected shared-execution-path historical contract with a quantified workload/oracle also forces `required`; never leave it only under Regression Areas. `conditional` emits no Performance AC and instead adds one QA-impact Open Question for the missing workload/SLA/baseline. `not_required` emits no Performance AC and no reader-facing filler. Never invent a threshold from an approximate customer observation.
- Cite every retained historical performance Jira in the visible Performance AC `Evidence` field. An unrelated Performance AC or generic load scenario cannot satisfy a retained same-mechanism contract.
- Label inferred ownership, impacted code, or workflow assumptions as inferred unless PR/repo evidence confirms them.
- Build focused search intents before retrieval: exact failure/API/config/UI label, expected workflow, boundary/config/version, and regression/automation coverage.
- In `Known Jira Bugs / Past Similar Tickets`, retain full status/RCA/version provenance only in the durable artifact. The compact UI reduces each validated entry to Jira key, title, and one reason it is worth checking.
- In `Automation Coverage & Gaps`, map every AC to direct inspected evidence and decide whether the main feature is Covered, Partially covered, Not covered, or Unverified. The compact UI exposes only that main-feature verdict and high-level guidance for the relevant UI feature file or backend integration/IT test; never invent an exact test path that was not inspected.

#### Operational Incident And Recovery UAC Rules

- For Dynamics/support incidents, production escalations, stuck jobs, queue blockage, workflow failures, cleanup requests, performance degradation, concurrency failures and customer-restoration plans, read `references/operational-incident-contract.md` (section "Operational Incident And Recovery UAC Rules") and populate `operational_contract`. Do not turn a destructive operational procedure into a product acceptance criterion: it is an `Incident recovery validation` scenario.

#### Component UAC Contracts

- For the Translation Project API or EDS GitHub/GitLab Publishing Profiles, read `references/component-uac-contracts.md`.

### Phase 3 — Retrieve Behaviour RAG

- Call `ask_dita_expert` with focused questions from normalized behaviour, not raw keyword spam.
- Run at least three focused RAG probes when behaviour matters: exact API/config/UI/construct terms, expected workflow, and regression/config/version boundary. This is mandatory and front-loaded - do not write the plan until the three probes have run. A single probe that returns noise or off-topic chunks is NOT "RAG unavailable": reformulate with different exact terms and retry to at least three attempts before concluding the behaviour is undocumented, and never let one weak probe stand in for the set.
- Record product-documentation retrieval separately in the evidence manifest as `"rag_tool": "ask_dita_expert"` and a `rag_probes` list containing the exact questions asked; `verify_evidence.py` fails when fewer than three are recorded unless `behaviour_matters` is false and `behaviour_not_applicable_reason` is supplied. Never put Jira-history queries in `rag_probes`. Fold every grounded finding into `Expected Behaviour` with a `RAG` provenance label; a probe that returns nothing still counts, but state plainly what was and was not found.
- Use RAG to ground expected behaviour, workflow rules, product constraints, release-note behaviour, configuration effects, and regression areas.
- If RAG conflicts with Jira/UAC, PR implementation, or Figma design intent, keep Jira/UAC primary and surface the conflict instead of hiding it.
- Prefer latest matching release docs or current Experience League pages over older release notes when both describe the same behaviour; use older release notes only for version-specific upgrade/history claims.
- Reject chunks that only share broad vocabulary such as `topic`, `map`, `assets`, `metadata`, `cloud`, `report`, `translation`, or `workflow` without proving the actual behaviour.
- Never use attribute-only DITA evidence as proof for an exact element behaviour, or generic DITA docs as proof for AEM Guides UI behaviour.
- If RAG is unavailable, noisy, or unrelated, state that evidence status under `Expected Behaviour` or `Regression Areas`. Add a Draft blocker only when the affected behaviour is not already supported by the acceptance contract, exact logs, verified current implementation, design evidence, or another authoritative source.

### Phase 4 — Find Past Similar Tickets

- Use the app's indexed Jira learning retrieval (`jira_qa`) when available, then use Jira MCP/JQL to validate current status, links, comments, and any facts that may have changed. If indexed retrieval is unavailable, use Jira MCP/JQL; otherwise use only user-provided related tickets or available team memory.
- When Jira identifies a customer, query the matching `customer_jira_profile` with current-issue component, workflow/output, and failure-signature terms. Treat profile frequencies as aggregate regression guidance, not usage telemetry or direct product-behaviour proof.
- Querying the indexed `jira_qa` history of already-fixed tickets is a mandatory Phase-4 step, not optional, and must run before writing Known Jira Bugs. Record `"jira_history_tool": "search_jira_history"`, `"indexed_history_run": true`, and a `jira_history_queries` list with both `same_customer` and `cross_customer` entries containing the exact query, component, and customer where applicable. If the tool is unavailable, record an empty query list, `jira_history_unavailable_reason`, and the fallback reason in `indexed_history_run`. The indexed corpus holds past fixed tickets by area and customer, not test data or a live customer inventory; validate status, resolution, and fix version live before citing.
- Record the outcome of every live, offline, JQL, empty, or unavailable history search in `history_attempts`. A record contains non-empty `source` and `query`, `result` as `ok`, `empty`, or `unavailable`, and a non-negative integer `count`. A thin or empty Known Jira Bugs section is valid only when an attempt explicitly records `empty` or `unavailable`; never leave the search outcome implicit.
- Treat the `component` argument to `search_jira_history` as a strict Chroma filter over normalized scalar `component_primary` metadata. Use exactly one canonical Jira value: `Editor`, `Authoring`, `Publishing`, `Platform`, `Schematron`, or `Integration`; never combine `Platform` and `Integration`. If a broader second pass is needed, intentionally omit the component and label any retained result as cross-component instead of presenting it as a same-component match.
- Prefer `learning_behavior_chunk`, acceptance-criteria, resolution/RCA, and test-evidence hits over summary-only matches when their structural evidence is comparable.
- Preserve each learning hit's confidence, historical outcome, verified-fix flag, behavior contract, root cause, QA oracle, and regression risks. A `caution` or non-fix outcome is a risk signal only and must never define current expected behavior.
- Reuse a historical behavior contract or QA oracle only when the outcome is an implemented fix and confidence is `medium` or `high`; keep current Jira/UAC authoritative.
- Search with multiple narrow JQL passes by exact Jira key links, exact error text, API route, config key, workflow, UI label, data shape, version boundary, and likely code area.
- Keep at most five past tickets. For each, explain why similar and what coverage it adds.
- Rank candidates by shared defect mechanism, never by shared feature area or keyword. Name the one concrete mechanism each ticket shares; a ticket that only shares an area belongs in `Regression Areas` or is dropped. Listing one or two genuine matches, or none, is correct; never pad to five.
- Follow `references/historical-ticket-selection.md` for match strength, exclude-by-default of cross-feature hits, re-auditing the whole list, and where excluded candidates go.
- Include both resolved historical bugs that provide reusable RCA/test oracles and open known bugs that can affect execution, expected results, environment choice, or sign-off. Validate current status with Jira MCP before calling a bug open, closed, fixed, duplicated, deferred, or regressed.
- For each selected Jira bug, capture the key, similarity reason, current status/resolution, affected/fix version when available, historical root cause or behavior contract, reusable test evidence, and the exact scenario or regression area it changes. Do not expose raw retrieval scores.
- Record the actual JQL/search intents used and whether each historical fact came from current Jira fields, comments, linked test evidence, or indexed history. Write `not available in current evidence` for missing fix versions, affected versions, RCA, or test evidence; never silently omit those fields or infer them from ticket status.

### Phase 4.5 — Connect Evidence Graph

- Call `query_test_evidence_graph` only after the three focused `ask_dita_expert` probes and the same-customer and cross-customer `search_jira_history` calls have completed.
- Read the packet's influence mode and default to `shadow` when it is absent. In `shadow`, record graph status, paths, leaves, and runtime only; do not change plan content, ACs, scoring, citations, repository scope, or automation verdicts.
- Query with the normalized failure shape plus the exact Jira key, customer, one canonical component, outputs, and DITA entities when known; keep traversal at two hops and no more than 20 paths unless a narrower result is insufficient.
- Retain only paths with underlying leaf citations. Reject candidate-only claims, generic fallback oracles, caution outcomes, and customer/component/domain/feature-only Jira matches.
- Use graph results to connect direct evidence and find same-mechanism risks, never to override current Jira/UAC, inspected implementation, verified Figma evidence, or direct authoritative documentation.
- Deduplicate graph citations against direct RAG and Jira results by leaf/source identifier so one source is not scored twice.
- Record the graph status, exact query, active generation ID, path IDs, and deduplicated leaf citations in the evidence manifest. A path ID is traceability metadata only.
- If graph access is disabled, unavailable, or degraded, record the reason and continue when authoritative direct evidence covers the behavior; graph unavailability alone is not a Draft blocker.
- Only in explicit `augment` mode, fold retained findings into the existing output sections. Do not add an Evidence Graph heading or expose raw graph JSON.

### FluffyJaws Supporting-Discovery (optional, mode-gated)

- Off by default. When `SKILL_FLUFFYJAWS_MODE` enables it, follow `references/fluffyjaws-evidence.md` and record the manifest `fluffyjaws` block.

### Phase 5 — Inspect Clones And Available Git Changes

- Always inspect every relevant available clone, regardless of lifecycle stage: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- Check user-provided workspace roots, environment variables, common teammate paths, and known paths such as `C:\UI TEST\guides-ui-tests` and `C:\UI TEST\dxml-it-tests` before declaring a clone unavailable.
- Synchronize every relevant clone before code or automation mining. Use `python scripts/sync_evidence_repo.py <absolute-repo-path> --stash-dirty`: it records state, fetches/prunes/tags, stashes dirty tracked and untracked developer work only after safety checks, and pulls only when the branch can fast-forward. Leave the named safety stash intact after a successful update and report its exact OID/ref plus restore command.
- If a repo is detached, diverged, lacks an upstream, has an in-progress Git operation, contains dirty submodules, or fetch/pull fails, do not reset, merge, rebase, switch branches, or force synchronization. Inspect the verified upstream/default remote ref with read-only Git commands when possible and label worktree-dependent claims provisional.
- In `Pre-Development UAC`, inspect product clones to identify the current implementation directly implicated by exact classes, workflow names, API paths, config keys, error strings, logs, or UI labels. Report these as `Current implementation implicated`, never as changed code.
- In `Pre-Development UAC`, inspect automation clones for existing happy-path, negative, concurrency, recovery, role/config, performance, and regression coverage. Missing PR/diff and line counts are `Not applicable — development has not started`.
- In `Implementation Review`, inspect the branch/commit/PR diff and capture changed files, functions/classes/components, added/deleted counts, key hunks, tests, config/migration changes, API/error contracts, and gaps. Also compare changed code with the current implementation and existing automation.
- In `Post-Fix Validation`, inspect the exact candidate-fix diff/build source and map changed branches, guards, retries, persistence, cleanup, errors, and tests to fix-safety and regression scenarios.
- Prefer connected GitHub MCP for a referenced PR. If development is expected but Jira has no PR link, search by Jira key, summary, branch, commit message, and PR body before asking for a PR.
- For every referenced or confidently discovered PR, inspect through GitHub MCP: repository, base/head branches, PR state, commits, changed files, complete diff hunks, added/deleted lines, review comments and unresolved threads when available, checks/test results, and linked Jira context. Read the implementation branches and error paths, not only filenames.
- Map each relevant PR hunk and branch to acceptance criteria, test scenarios, regression areas, logging/error behavior, permissions/configuration, persistence/cleanup, concurrency/retry, backward compatibility, and automation impact. Report unrelated or generated-file changes separately and do not inflate QA scope from them.
- If GitHub MCP is unavailable, inspect the exact PR/branch/commit from an available local clone or user-provided diff. In implementation/post-fix stages, do not claim deep PR analysis when only Jira metadata or a summary was available.
- For `guides-ui-tests` and `dxml-it-tests`, mine existing tests, skipped/flaky history, fixtures, selectors/API clients, reusable scenarios, polling/timeouts, cleanup helpers, and automation gaps.
- Before searching `guides-ui-tests`, `dxml-it-tests`, editor E2E, or any discovered automation repository, run the same guarded `sync_evidence_repo.py --stash-dirty` flow used for product clones. Do not report automation as current until fetch/pull state and the exact inspected revision are recorded; preserve dirty local automation development in a named stash with its restore command.
- Also inspect relevant editor E2E or repository-specific automation suites discovered locally or through GitHub MCP. Search by Jira key, AC terms, endpoint and request fields, UI labels, project types, enum values, config keys, workflow names, failure text, and exact implementation symbols.
- Build an AC-to-automation map internally: `Covered`, `Partially covered`, `Not covered`, or `Not suitable for automation`. For covered items, retain exact repository, file, scenario/test method, helper/fixture, layer, and revision. For gaps, recommend the correct UI/API/integration layer, reusable fixture/helper, data setup, cleanup, assertions, tags/suite, and whether a new test or extension is needed.
- Classify automation by the complete AC contract, not by feature-name similarity. A happy-path publish test does not partially cover post-cleanup recovery, concurrency safety, orphan-state cancellation, queue draining, or cross-dashboard consistency unless it creates that precondition and asserts that outcome. Use `Partially covered` only when an existing test proves a named clause of the same AC; otherwise use `Not covered` and list reusable helpers separately.
- A gap recommendation must name the exact repository and candidate test file/class/method, automation layer, reusable client/helper/fixture, deterministic failure or state-injection mechanism, data setup, polling endpoint and terminal oracle, timeout source, output-integrity assertions, cleanup/rollback, suite/tags, and whether to extend or add a test. If the repository cannot safely create the required state, say which test hook or harness capability is needed instead of prescribing manual production mutation.
- Do not claim zero automation from one repository or broad keyword search. Search every relevant discovered automation clone and GitHub automation repository before declaring a gap; distinguish missing coverage from undiscovered, stale, skipped, flaky, quarantined, or inaccessible coverage.
- Never label files as changed without a real diff. Never infer current implementation from generic Jira keywords; require exact repo matches or label the area inferred.
- If an implementation-stage diff is unavailable, add `Draft blocker: implementation diff not inspected`. Do not emit this blocker in pre-development.

### Phase 5.5 — Doc Research Routing (MANDATORY contract after Evidence)

After evidence collection and before any coverage/writing work, record the doc-research
routing decision in the manifest `doc_research` block, validated by
`scripts/doc_research_routing.py` (see `references/doc-research-routing.md`). This
enforces invocation of the existing UAC Doc Researcher role
(`agents/uac-doc-researcher.md`); it introduces no new agent and changes no source
authority.

- **Route to `DOC_RESEARCH_REQUIRED` when materially relevant**: the ticket changes
  existing documented functionality; existing behavior must be understood or preserved;
  configuration semantics are not sufficiently established by the ticket;
  product/version/surface applicability needs confirmation; backward compatibility
  materially affects acceptance; terminology materially affects behavior; the ticket's
  evidence is insufficient but authorized product documentation may answer the missing
  behavior; or the Evidence Agent explicitly requests documentation research. Declare
  the fired triggers in `doc_research.routing.triggers`. Never invoke the Doc Researcher
  merely because related documentation exists.
- **An explicit authoritative Human Accepted AC may be sufficient without research**
  when documentation would not materially change acceptance reasoning: record
  `RESEARCH_NOT_REQUIRED` with `not_required_reason`.
- **HARD GATE:** when the routing state is `DOC_RESEARCH_REQUIRED` and no terminal Doc
  Researcher result exists (`DOC_RESEARCH_COMPLETED` / `DOC_RESEARCH_PARTIAL` /
  `DOC_RESEARCH_UNAVAILABLE` / `DOC_RESEARCH_CONFLICTED`), Coverage/Writer MUST NOT
  proceed, and the gate fails the plan. The coordinator/main agent must not impersonate
  the missing Researcher — every result names `produced_by: uac-doc-researcher`.
- **Doc Researcher output contract:** `research_id`, `status`, `topics[]`, `findings[]`,
  `source_ids[]`, `applicability`, `limitations[]`, `conflicts[]`; every finding carries
  `claim`, `source_id`, `source_type`, `authority`, `applicability`, currentness/version
  when available, and `evidence_role` (`EXISTING_BEHAVIOR`, `REQUIREMENT_CLARIFICATION`,
  `SUPPORTING_CONTEXT`).
- **The Researcher must NOT** write ACs, decide final acceptance scope, override a Human
  Accepted AC, infer new behavior from old documentation, promote nearby functionality,
  or treat NOT_FOUND as evidence of the opposite behavior.
- **The Writer receives only admitted research** (`admitted_research_ids`) through the
  existing reasoning path — never arbitrary raw search results. The Reviewer fails the
  plan when required research was skipped, an AC cites documentation that was never
  retrieved, PARTIAL research is represented as complete, or documentation is used to
  support behavior it does not establish.

### Phase 6 — Inspect Figma Design Evidence

- Use Figma MCP when a design/prototype/frame is linked or when the Jira is UI-flow heavy and the user says Figma should be used.
- Learn the existing flow before writing scenarios: entry point, primary path, alternate path, empty/error/loading states, dialogs, toasts, permissions, responsive states, and component variants.
- Compare design evidence with Jira UAC, RAG product behaviour, and PR implementation; call out contradictions as Draft blockers in the affected section.
- Do not treat Figma as proof of backend/API behaviour, permissions, versioning, or persistence unless Jira/PR/RAG also supports it.
- If Figma MCP or design access is missing for a design-dependent ticket, write `Draft blocker: Figma design evidence not inspected`.

### Phase 6.5 — Discovery-First Dimension Sweep (MANDATORY before authoring)

Do this BEFORE writing a single acceptance criterion. Most misses are discovery gaps, not
writing gaps: an AC set drafted from the ticket text plus a couple of greps silently drops
a dimension a reviewer then has to add. Run the full sweep first, disposition every
dimension, and only then author.

First run the authoritative source-to-UAC comparison. The Jira description,
comments, and analysed attachment facts define the initial scope; discovery
hypotheses can only widen investigation. They cannot replace, suppress, or
down-scope an atomized material source fact.

Run every applicable probe and trace, then record the result in the manifest
`dimension_inventory` block (each dimension COVERED_BY_AC / OPEN_QUESTION / OUT_OF_SCOPE /
NOT_APPLICABLE with a one-line reason — the gate fails closed if any is missing):

- Miss-probe library: load `data/miss_probes.json` and, for every ACTIVE probe whose
  signal matches this ticket's evidence, treat its implied dimension as a required
  investigation candidate (entry points, consumers/siblings, value provenance, locale
  granularity, and any newer learned probe). These encode real past misses — never skip a
  matched probe.
- Attachment visual-reference states: when an inspected attachment or user-provided
  visual reference shows a named surface, visible artifact/control, and state variants,
  record `visual_reference_evidence` and disposition the named surface plus every
  material observed state in `dimension_inventory.visual_reference_coverage`. Treat
  the image as an observation only. It can establish visible facts and justify an Open
  Question, but Jira, the user, or an accepted product source must establish desired
  behavior. Do not infer facts from filenames or add unrelated UI scope.
- Write/read consumer parity: when current evidence names a control that edits a value
  and a distinct surface that displays or tag-renders it, record
  `write_read_consumer_parity_evidence` and disposition the pair in
  `dimension_inventory.write_read_consumer_parity`. Cover the named edit-to-display
  result in an AC, or use an Open Question or concrete evidence-backed out-of-scope
  decision. This is bounded to the named value and surfaces; do not assume parity for
  other readers.
- UI action/surface proof: when an AC asserts an existing selectable UI
  option/action, record `ui_action_surface_evidence` and disposition it in
  `dimension_inventory.ui_action_surface_coverage`. The proof must name the exact
  surface and show that the option/action is selectable there. A configured or
  documented outcome is not itself a UI action; do not turn it into one without
  surface-specific evidence. If the current action is unproven, preserve the
  source-backed desired outcome and expose the action assertion as an implementation
  Open Question instead of removing or narrowing scope.
- Asset-upload conflict dimensions: only when current evidence mentions asset upload,
  overwrite/re-upload, duplicate detection, a same-name/name or path conflict, Create
  Asset, an upload conflict, or a conflict endpoint, populate the
  `asset_upload_conflict` contract required by the miss-probe gate. Disposition
  content-identity duplicate detection and name/path conflict separately. This is a
  required investigation/disposition, not an automatic AC: use an evidence-backed
  `OUT_OF_SCOPE`, `NOT_APPLICABLE`, or `PRESERVED` disposition when a separate
  duplicate-detection feature is not on the affected path. Name the affected
  deployment, product surface, and exact behavior path, and record unaffected baseline
  actions separately from the changed path. Name native AEM Assets actions as native
  Assets behavior and source the product-surface ownership: use the native Overwrite
  Files flow, not “Replace”; Create Version is also a native Assets action. Do not
  credit either native action to Guides unless evidence proves a Guides-owned surface.
  Treat a configuration/provider/class name as configuration evidence only: assert a
  handler or route only after inspected request-dispatch evidence; otherwise use an
  Open Question/evidence gap. Disposition every named deployment independently; Cloud
  coverage and On-premise preservation are valid different outcomes, but do not infer
  parity. Scope every document to the deployment and product surface it actually
  covers, so Cloud-only or product-specific documentation cannot support another
  deployment or surface.
- Mined precedents and customer profiles: include matching LEARNED/VALIDATING
  probes and the versioned corpus-side customer checklist through
  `dimension_synthesizer.py`. These are advisory candidates, not mandatory scope or
  evidence of a confirmed miss. Record each relevant candidate's exact equivalence
  key and current-evidence disposition. A customer label can widen investigation;
  it cannot approve an AC. Never copy historical acceptance text into a blinded
  target plan or claim that unavailable history was retrieved.
- Consumers / siblings / entry points: trace the touched construct to ALL code consumers,
  sibling code paths, and every entry point that reaches the same path (UI action, API,
  service, scheduler), with file:line — do not stop at two greps. Translate each to plain
  observable behaviour in the ACs; never put the code identifiers in an AC.
- State / config partitions: enumerate both values of every state axis (profile, baseline,
  enum-bound/unbound, feature flag on/off, single- vs multi-language, setting on/off).
- Output scope: which output presets/types are affected, and DITA-OT processing on vs off.
- Output-engine parity benchmark (GENERATE, never reason about it): for any publishing or
  output-rendering ticket, AND for any ticket whose scope names a DITA element or construct
  whose rendering, derived value, or extracted text matters (bookmap `booktitle` /
  `mainbooktitle` / `booktitlealt`, inline elements such as `option` / `uicontrol` / `ph`,
  tables, `xref`, `conref` / `keyref`, `indexterm`, `searchtitle`, and the like), GENERATE
  the affected construct through the dita-ot output-generation capability and diff the
  results across every output family in scope - Native PDF, Direct DITA-OT PDF, and
  HTML5/XHTML. Diff on text content and character-level whitespace, the separator between
  adjacent text and child elements, which sub-element supplies the value, numbering,
  placement, ordering, and label text. Whitespace and separator preservation around and
  between child elements is an explicit required axis: a missing space or a missing
  separator is exactly the defect class that reads as correct in code and in documentation
  and only appears in generated output. A divergence between output families is a defect
  unless an explicit product requirement documents it. This is the one class the sweep
  cannot infer from ticket text, code grep, or spec - it only appears by producing and
  comparing the outputs, so it must be run, not reasoned about. Probe MP-007 surfaces this
  dimension (advisory until promoted). Record the generated artifacts and the diff result
  in the dimension inventory; "not generated" is a recorded evidence gap, never a pass.
- DITA specification and DITA-OT documentation are required sources for a DITA construct,
  not optional ones: whenever a question concerns what a DITA element MEANS, what its
  content model allows, or how a processor is expected to handle it, route that question to
  the DITA 1.3 specification and the DITA-OT documentation through `ask_dita_expert` in
  addition to the AEM Guides product documentation. Product documentation establishes what
  Guides does; the specification establishes what the construct is for and which sub-element
  is the primary value; DITA-OT documentation establishes baseline processor behaviour that
  a Guides engine may or may not match. Do not answer a construct-semantics question from
  AEM Guides documentation alone, and do not treat a specification statement of intent as
  proof of what any engine actually emits - that still requires the generated-output diff
  above. Record each source separately so an AC never credits the specification for
  behaviour only an engine establishes, or a product doc for semantics only the spec
  establishes.
- Error / negative / boundary paths, performance/scale (when any workload signal exists),
  security, localization (regional vs generic locale), and upgrade/migration.
- Reviewer comments: every imperative check a reviewer raised must be dispositioned.
- Evidence: run RAG at least 3× on the feature's real behaviour and the indexed Jira
  history for the component; record both. Thin/absent history is a recorded gap, not silence.

Only when every dimension above is dispositioned may you proceed to Phase 7. If the sweep
surfaces a blocking unknown, resolve it from evidence or raise it as an Open Question FIRST
— do not author around it.

### Phases 6.5.5 to 6.9.7 — Reasoning Pipeline

Each stage below is mandatory when its manifest block applies. The full rules for every stage are in
`references/reasoning-pipeline-phases.md`; read the stage's section there and its own reference before
filling the block.

| Phase | Stage | Manifest block / script | Reference |
| --- | --- | --- | --- |
| 6.5.5 | Behavioral coverage expansion: widen discovery, never acceptance | `behavioral_coverage_expansion` / `behavioral_coverage_expansion.py` | `behavioral-coverage-expansion.md` |
| 6.6 | Question-based reasoning: planner, research router, resolver | `question_planner.py`, `question_resolver.py` | `question-based-reasoning.md` |
| 6.6.5 | Evidence sufficiency before coverage decisions | `evidence_sufficiency.py` | `evidence-sufficiency.md` |
| 6.7 | Coverage reasoning | `coverage_reasoner.py` | `coverage-reasoner.md` |
| 6.8 | Semantic coverage and AC equivalence | `coverage_equivalence.py` | `coverage-equivalence.md` |
| 6.9 | Requirement lineage, end-to-end AC traceability | `requirement_lineage.py` | `requirement-lineage.md` |
| 6.9.5 | Historical Jira evidence safety | `historical_jira_safety.py` | `historical-jira-safety.md` |
| 6.9.6 | Question-level retrieval quality and evidence admission | `retrieval_admission.py`, `retrieval_benchmark.py` | `retrieval-admission.md` |
| 6.9.7 | Canonical replay: read-only parity after runtime generation | `canonical_runtime_adapter.py --project-result`, `run_gates.py --runtime-replay` | `reasoning-pipeline-phases.md` |

The canonical Python runtime is the only production semantic and promotion authority. Never edit or
regenerate its output to force a gate to pass.

### Phase 7 — Write Test Scenarios

- Write the minimum number of scenarios needed to cover every acceptance criterion and material risk. Use 6-10 for narrow changes and 12-20 for broad APIs, multi-provider workflows, large enum matrices, recovery incidents, or cross-version features; coverage takes priority over an arbitrary cap.
- Each P0/P1/P2 scenario must use the literal fields `Action:` and `Expected:` in one plain-English bullet. When an operational manifest references a scenario, add a stable `[TS-##]` token before the AC mapping, for example `- P0 [TS-01] [AC-01]: Action: ... Expected: ...`.
- Prefix every scenario with the acceptance IDs it covers, for example `P0 [AC-01, AC-04]`. No confirmed or proposed AC may remain without at least one scenario, and no expected result may introduce behavior absent from an AC or accepted evidence.
- Cover happy path, negative/boundary, role/permission, configuration, data-shape, environment matrix, setup/test-data fixture, upgrade/version, API contract, and fix-safety checks when relevant.
- Every P0/P1 scenario must trace to Jira AC, accepted RAG, PR diff, Figma flow evidence, a medium/high implemented-fix Jira learning oracle, or an explicit high-risk regression. Cautionary/non-fix Jira history may justify exploration but not a sign-off expectation.
- Include integration-impact scenarios when the ticket touches shared APIs, shared UI components, configs, publishing paths, editor flows, translation flows, upload/status flows, review flows, or automation infrastructure.

### Phase 8 — Capture Open Questions

- Capture only questions that materially affect QA sign-off, expected behaviour, configuration, environment setup, or scenario coverage.
- Give every real question a unique, contiguous `OQ-##` prefix starting at `OQ-01` and the literal `QA impact:` marker; preserve source order and use the same ordered IDs in the manifest. Do not encode an unresolved decision as an AC.
- Ask permission, role, XML Editor config, AEM config, translation config, DITA, and DITA-OT output questions when the Jira domain requires them.
- For on-premise release, service pack, or upgrade tickets, always ask upgrade-impact questions when not answered: source/target versions, config migration, custom UI config retention, changed defaults, manual post-upgrade steps, backward compatibility, and cloud/on-prem parity.
- For publishing/output tickets, include DITA-OT, PDF, HTML5, preset, transformation, and output validation questions when not answered by Jira/RAG/PR.
- Do not ask generic questions already answered by Jira, RAG, Figma, PR, or repo evidence.
- If there are no meaningful unknowns, write `No open questions from current evidence`.

### Phase 9 — Decide Draft vs Review-Ready

- Use `Draft blocker:` bullets inside the affected final section; do not create a separate blocker section.
- For `Pre-Development UAC`, mark UAC-ready when issue facts, proposed acceptance criteria, current product-clone evidence where available, automation evidence where available, expected-behaviour support, regression areas, test-data/environment needs, and sign-off decisions are sufficiently explicit. PRs, changed files, and line counts are not required.
- For `Implementation Review`, mark review-ready only when the implementation diff, changed files, line counts, current-code comparison, expected behaviour, test scenarios, and integration impact are inspected.
- For `Post-Fix Validation`, mark QA-sign-off-ready only when the candidate fix/build, changed code, acceptance coverage, regression evidence, required environment matrix, and sign-off-critical questions are resolved.
- RAG or historical search unavailability is a blocker only when the missing evidence is necessary to establish a disputed or otherwise unsupported behaviour claim. Do not block a well-supported pre-development UAC merely because an optional source is unavailable.
- Dirty or unavailable clones block only claims that depend on those clones. Keep verified evidence and mark dependent findings provisional instead of downgrading every section automatically.

### After delivery — Capture explicit Human corrections

- At the start of a configured generation/capture invocation, make one bounded `feedback_capture.py flush-queue` attempt before capturing new feedback; status/readiness-only requests never flush. Replay capture records only, preserve the exact queued request and identity/service binding, and report how many moved from `QUEUED_LOCAL` to `SAVED_REMOTE`. If the queue is blocked or belongs to a different service/credential, leave it intact and report that state. Never retry binding, review, approval, rejection, revocation, or supersession, and never replace a stale reviewed-source pin silently.
- When shared feedback capture is configured and the Human directly corrects the UAC in the current conversation, use `scripts/feedback_capture.py capture` as the primary capture path whenever the helper is available. It minimizes/redacts the request before the first send and can queue that exact capture DTO after a retryable failure. Send the selected correction with `source_kind=HUMAN_CORRECTION`, a unique idempotency key, and the available `draft_id`, `plan_fingerprint`, `evidence_bundle_id`, `run_id`, and `ac_id`. Use MCP `capture_uac_feedback` only as a non-queueing alternate. If an MCP response is lost, reconcile with list/status or replay the exact same MCP arguments; never switch the same idempotency key to a differently normalized helper payload. Use `AI_PROPOSAL` for machine-authored suggestions and `UNCONFIRMED` when origin is not established; neither may be promoted as Human truth. Do not infer a correction from silence, a question, model critique, or third-party AI output.
- Send only the correction and minimum trace identifiers. Never send the entire Claude/Codex transcript, hidden reasoning, credentials, unrelated attachments, or a locally generated approval decision.
- Report the returned transport and lifecycle states exactly. `QUEUED_LOCAL` means not saved; `SAVED_REMOTE` does not mean approved; only an explicit server `index_status=INDEXED` may be called indexed. A `PENDING_BINDING` record requires an authenticated source binding before review. For a new chat reviewing Jira, follow the exact Jira snapshot path above instead of requiring the original generation draft.
- Do not approve automatically. Any authenticated tenant teammate may capture, but only the ticket's current live QE Assignee, authenticated as a named Human, may bind/review. The server verifies the personal Jira identity and the live `QE Assignee` field; roles, admin status, draft ownership, ordinary Assignee and names in prose grant no authority. That QE must inspect provenance, applicability, counterexamples and the current revision before deliberately calling `review_uac_feedback`. Supporting corrections from another case need their own prior QE approval. Missing identity/field or Jira unavailability leaves review unauthorized; report the unchanged record state and continue normal generation. Binding/review decisions are never queued or automatically retried.
- Future generation may consume only approved, server-published shared learning returned by the authenticated canonical resolver. Default shared mode is `SHADOW`; it cannot change the plan. In `ENABLED`, discovery lessons remain investigation guidance and language lessons remain `RETRIEVED_NOT_APPLIED` authoring guidance until deliberately applied. If the VM is unavailable, retain the existing approved TRAIN baseline and record shared learning as `UNAVAILABLE`; never read pending feedback or a stale local shared snapshot.

## Acceptance Scope And The Delivered UAC

This section is the single source of truth for what becomes an Acceptance Criterion and how a UAC is
shown. Where another rule in this file or in a reference seems to say otherwise, this section wins.

**Discovery is wide; acceptance is narrow.** The discovery rules (dimension sweep, surface inventory,
consumers and sibling entry points, both editors, reviewer requests, similar UACs, miss probes) decide what
to INVESTIGATE. Every material finding is then placed exactly once in one of four places; nothing is
dropped silently:

1. **Acceptance Criterion** - the behaviour rests on the ticket, an attachment, an accepted UAC, a product
   or PM decision, or the confirmed fix; or it is a QE regression check guarding the reporter's own
   scenario. When QE can state a testable outcome for such a behaviour, it is an AC, not an Open Question
   (`qe_completeness_coverage`, `reviewer_request_coverage`).
2. **TBD on the AC it governs** - a product decision is still open. In the full record it is also an
   `OQ-##` entry. Create a standalone AC for a TBD only when no AC governs it.
3. **Suggested check (QE decide)** - found only by our own research: a documentation page, the code, a
   similar or parent ticket's UAC, an investigator's other scenario, or parity nobody asked for. At most
   three, below the criteria, never copied into the Jira field (`uac_completeness_check.py`).
4. **Out of scope or not applicable** - with a concrete reason, in the full record.

A surface found only in documentation or code gets at most a "still works as before" AC or a TBD
(`uac_release_runner.surface_inventory_problems`). A criterion on a scenario the reporter did not hit is a
suggested check. The reporter's own action done another way is not a different scenario - see "Every way
to do the ticket's action" below.

**Size.** Write the fewest ACs that cover the behaviour: at most ten (`ac_contract.validate_ac_count` in
`uac_linter`). In the human UAC corpus the median ticket has 6 criteria of about 15 words each, a quarter
have 2 or fewer and 40% have 4 or fewer; the size does not follow the length of the ticket. Start from one
AC per distinct outcome the ticket asks for. Every entry point, switch state, item type, value form, item
made before the change and reverse action whose expected outcome is the same as an existing AC is a short
sub-point of that AC, not a new AC - the action_variants and pre_existing_items records point at that AC.
Add an AC only when the expected outcome differs. Blind comparisons showed ours at 5 to 9 ACs on every
ticket while the human UAC had 3 to 30 points. Merge same-outcome cases into one AC and list the cases in a
short clause; split only when the required behaviour or outcome differs. Consolidation only reorganizes: every checkable point survives as an AC clause, a TBD, a
suggested check, or in the full-record markdown. Two ACs with content-word overlap of 0.6 or more are merged
(`coverage_forcing._validate_ac_redundancy`, aligned with `scripts/uac_eval/precision.py`). Every AC adds a
distinct product contract; no recap AC.

**Length.** Keep the delivered criteria - with their sub-points, the Scope line and the Out of scope list -
within 350 words (the median human UAC is 122 words and 90% are under 337; blind comparisons against human
UACs showed ours 4 to 15 times longer). Keep each Source line within 30 words: name the ticket, comment,
documentation page or commit, and keep file paths and line numbers in the full test plan record
(`uac_completeness_check.size_problems`).

**Items made before the change.** Always say what happens to content, maps, presets, output, settings or
projects that were created or generated before the change - for example "older files need re-processing to
get the word count", "check with an old preset and a newly created preset", "existing output gets the
property after the next full Generate". Record it in `UAC_EVIDENCE.json` "pre_existing_items" as the AC that
covers it, a TBD, or NOT_APPLICABLE with a reason. 15% of human UACs cover it, and it was missed on tickets
that never say "upgrade" or "migration" (`uac_completeness_check.pre_existing_problems`). Do not guess the
outcome: human UACs usually say existing items stay as they are ("existing presets remain unaffected"; a new
option is off for them). An AC records "outcome": UNCHANGED, or CHANGED only with the basis that decided it
(TICKET, ATTACHMENT, PRODUCT_DECISION or DEVELOPER_COMMENT); otherwise it is a TBD. Blind comparisons
asserted new behaviour for old items twice, and both were wrong.

**Every way to do the ticket's action.** The reporter shows one path; the human UAC covers the action.
Record in `UAC_EVIDENCE.json` "action_variants", and make each an AC (or a TBD), never only a suggested
check - these criteria are scenario VARIANT:
- **entry_points** - every route to the same action: drag and drop, the toolbar, a dialog, the context
  menu, a keyboard shortcut, an API. When the reporter dragged a file in, the toolbar insert is part of the
  ticket too. Merge routes with the same outcome into one AC and list them as sub-points. When the ticket
  generates output (Native PDF, AEM Sites, HTML5, custom DITA-OT or any other type), name each documented
  generation route: the output preset from the map (Map console or Map Dashboard), Map Collection, a
  baseline, and for PDF the Download as PDF / single-topic path. Each gets an AC, a TBD or NOT_APPLICABLE
  with a reason - the routes share one engine and the reporter used only one (miss probe MP-004;
  `uac_completeness_check.output_route_problems`). When the ticket adds or changes a setting in an output
  preset, also name a Global or Folder Profile preset template applied to maps with Apply Preset Changes: the
  setting must survive that path (human UACs checked it on two tickets where ours did not).
- **input_sources** - when the ticket brings content in (paste, import, upload, drag and drop), where that
  content can come from: the reporter's application and the others the same conversion handles (Word,
  Google Docs, Excel, a web page, another topic or view, another file format). At least two, each an AC, a TBD
  or NOT_APPLICABLE with a reason; "the ticket only reports Word" is not a reason. A Word-table paste ticket's
  human UAC covered Google Docs, an HTML page and Excel where ours made them suggested checks
  (`uac_completeness_check.input_source_problems`).
- **config_switches** - every configuration, feature flag or setting that changes what the action stores or
  shows, with the result in each state ("with UUID file names enabled the GUID is inserted; when disabled
  the path is inserted"). An empty list needs a reason.
- **mechanism** - when the ticket asks for general behaviour ("users can move content while others refer to
  it", "same as Baseline and Conditional Presets"), the other item or reference types, and the named feature
  it must match, are ACs; the reporter's own item is one case of it. When the ask is only the reporter's
  case, say why. Always answer two more: **reverse_action** - the action done the other way round (move the
  item back, re-enable, undo) - and **item_origin** - an item with a different history (created in the
  target folder, never translated, made in an older release). On a move ticket the human UAC moved the item
  back and moved an item that was created in the target folder. And **value_shapes** - the forms of the
  value the change reads or shows: an empty value and a missing one (href="" and no href), special
  characters, fragments, query strings, encoded characters, a very long value. An AC answer lists at least
  two forms in "shapes" and names each; usually they are sub-points of the AC they share an outcome with.
  Human UACs tested these on a blank-href ticket and a URL-as-title ticket where ours covered one value.
Each entry records its **basis**: TICKET, ATTACHMENT, PRODUCT_DECISION, DEVELOPER_COMMENT, DOCUMENTATION or
CODE. A route, switch or item type known only from the code is a TBD or a suggested check, never an AC: in
blind comparisons, routes and modes read only from the code were criteria the human UAC did not have, and
they cost QE review time. Blind comparisons with human UACs missed the other variants while covering the
reporter's single path (`uac_completeness_check.action_variant_problems`). NOT_APPLICABLE needs a reason
that says why the route, switch or item cannot do the action; "nobody named it" or "the reporter did not
use it" is why it is a variant, and the checker refuses it (Map Collection was dropped this way on two
tickets whose human UAC made it a criterion).

**Decided boundaries.** When the ticket, a developer or product has decided a limit - a version or type
the change does not cover ("V2 baseline is out of scope", "applies to the old baseline v1"), a path where
the fix does not apply ("external paste from Word or Excel"), or a loss that is expected ("copying part of
a table loses its column widths") - write it: an Out of scope item or a criterion that states the limit.
Record each in `UAC_EVIDENCE.json` "scope_boundaries" with its basis (TICKET, ATTACHMENT, PRODUCT_DECISION
or DEVELOPER_COMMENT) and disposition (OUT_OF_SCOPE or AC); a limit nobody decided is a TBD, not a
boundary. An empty list needs a reason (`uac_completeness_check.scope_boundary_problems`).

**Decided facts are criteria, not TBDs.** Human UACs are written once the scope is agreed: only 5% of the
386 human UACs in the corpus carry a TBD, while 35% state a configuration, feature flag, preset argument or
default. When the ticket, a developer comment or a product decision already settles a fact - a feature flag
that must be on, a DITA-OT argument in the output preset, the default behaviour ("defaults to the current
behaviour, so existing customers are unaffected"), a parity target ("same as AEM Sites"), or what is not
supported ("flagging not supported") - write it as a criterion. A TBD is only for a decision nobody has made.

**Delivered format - chat and the Jira Acceptance Criteria field.** A list of criteria with optional short
case sub-points; no ticket title line, no Open Questions section, and at most one short sentence of
narration. The only lines outside the criteria are the Note, an optional Scope line and an optional Out of
scope list.

```
Note: The root cause and the fix are not confirmed yet. ...   (only when fix_basis is UNCONFIRMED)
Scope: <what this ticket covers, when the ticket or a decision sets it, e.g. Native PDF publishing only>
- Acceptance Criteria 01: <named item> <observable result>.
  - <short case of the same outcome>                 (optional, at most five)
  **Source:** <Jira key | repository, revision, file and lines | documentation page>
  **TBD:** <open product decision>?
Out of scope:                                          (optional, when a decision excludes something)
- <excluded item>
Suggested checks (QE decide):
- Suggested check 01: <check>
  **Source:** <source>
  **Why suggested:** <what it guards and why it is not an Acceptance Criterion>
```

- The label is spelled out as `Acceptance Criteria 01`, never `AC-01`, because Jira auto-links and strikes
  through issue-key shapes. `AC-##` stays internal in the record, mappings and extracted JSON.
- No `[Proposed]`/`[Confirmed]` tags, spheres, Given/When/Then, pipes, or Starting point/Action/Expected
  scaffolding in the delivered UAC; they live in the record only. `Needs_Human_Review` conveys status.
- The AC body is paste-safe plain text: no bold, italics, backticks, code spans, links or `~`; name
  properties, keys and paths as bare tokens. File paths, revisions and line numbers go on the Source line,
  never in the AC body. For Jira, build the field with `scripts/jira_safe_text.py` `jira_field_body`, which
  strips the chat-only `**Source:**`/`**TBD:**` markup (enforced by `validate_test_plan.py` and the shared
  AC projector).
- A Source names an openable artifact, never "review of X". When a criterion rests on QE reasoning, say so
  and state what evidence does not exist (`ac_presentation.validate_ac_source_specificity`). Never cite
  documentation for behaviour it does not establish.
- Sub-points list the cases of one outcome - each construct in a matrix (map title: ph with keyref, keyword
  with conref), each row of a decision table (last modified in AEM newer: update; older or equal: keep) - the
  way 15% of human UACs nest them. A different outcome is a different criterion; at most five sub-points.
- Scope and Out of scope: add the `Scope:` line and the `Out of scope:` list only when the ticket or a
  product decision sets them (about 10% of human UACs have an Out of scope list); never invent a scope.
- Language: at most two lines; very simple English; state the outcome itself - do not write acceptance
  criteria as generic `Verify...` test instructions (83% of human UACs do not use "Verify that", and the
  prefix made ours about 60% longer). A criterion may still start with "Verify that" when it reads better,
  but never `Verify that the system`. No AI words (ensure that, leverage, robust, seamlessly, gracefully, as expected, properly,
  correctly handled, system shall, end-to-end flow). No vague words (appropriate, relevant, respective,
  corresponding, as applicable, the configured folder, both dashboards): name the exact screen, property and
  value. Use AEM Guides terms from `data/guides_vocabulary.json`, RAG-verified, and never a code identifier.
  Name an action by what the user sees with the UI name in brackets, for example "removed from the live site
  (Unpublish)". Enforced by `ac_readability`, `coverage_forcing._validate_underspecified_terms`,
  `_validate_vague_surface_reference` and `_validate_guides_vocabulary`; follow
  `references/plain-language-ac-writing.md`.
- Once the user has stated a format, reuse it verbatim on every revision.
- The full compatibility record keeps its own grammar (Section Rules): `AC-## [Confirmed|Proposed]` with a
  sphere and `Evidence:`, optional short sub-points, and `OQ-##` Open Questions. The delivered UAC is a
  projection of that record (`ac_presentation.project_ac_block_for_people`), never its input.

## Output Contract

- Presentation vs record: retain the eleven-section hash-bound compatibility record and evidence appendix for auditability, but never present either as the canonical result. The default Claude/Codex response is the canonical runtime's `rendered_output`.
- The canonical renderer may emit these non-empty sections, in order: `Issue understanding`, `Publishing / product scope`, `Acceptance contract` or `Proposed acceptance contract`, `Product decisions required`, `Semantic coverage`, `Structural / hierarchy coverage`, `Referenced content coverage`, `Configuration / state coverage`, `Transformation / processing coverage`, `Generated output validation`, `Reference / link integrity`, `Negative / boundary coverage`, `Failure / recovery coverage`, `Lifecycle coverage`, `Cross-mode regression`, `NFR coverage`, `Explicit out of scope`, `Investigated and rejected`, `Evidence gaps`, and `Coverage gate result`. Do not show empty sections or manually compress away a material disposition.
- `render_compact_view.py` and its four-section output are legacy compatibility projections only. They may be generated for an explicitly requested historical record, but they cannot replace, rewrite, authorize, or be posted instead of the canonical runtime result.
- The delivered Acceptance Criteria format (label, Source and TBD lines, suggested checks, plain text, the ten-AC cap) is defined once in "## Acceptance Scope And The Delivered UAC" above.
- Project full-record `Regression Areas` into smart `P3 [Regression]` Action/Expected scenarios under compact `Test Scenarios`; never expose a separate compact Regression heading.
- Performance analysis never adds another compact section. Its internal manifest decision is visible in compact output only through a justified `(Performance)` AC when required; a conditional QA-impact question remains in the hidden full record.
- Keep `Understanding From Jira`, `Expected Behaviour`, `Scope From Git`, `Code Touched`, `Lines Changed`, `Automation Coverage & Gaps`, and `Appendix A` in the full `.md` artifact. `Test Scenarios` remains visible in compact output. Show the complete record or any named hidden section only when the user explicitly requests it.
- `Jira Tickets Worth Checking` contains only each validated same-mechanism Jira key and concise title. Hide similarity explanation, status, resolution, versions, RCA, ownership, search narration, excluded candidates, and aggregate profiles.
- `Automation Coverage` starts with an explicit main-feature verdict (`Covered`, `Partially covered`, `Not covered`, or `Unverified`) and gives only high-level feature-file/UI or integration/API guidance.
- Output Markdown bullets only.
- Posting ACs into the Jira Acceptance Criteria FIELD (MANDATORY): the field is wiki-rendered, so a {noformat} block shows as a raw grey code panel. Build the field body with `scripts/jira_safe_text.py` `jira_field_body(text)` from the delivered UAC block: each criterion becomes a bold `Acceptance Criteria NN:` label with Source/TBD bullets and file names in {{monospace}} (so underscores and dashes in names cannot become italics or strikethrough). Read the field back with rendered fields after posting and confirm it shows bold labels and bullets. Use `jira_comment_body` only for free-form comments.
- Posting ACs into a Jira COMMENT (MANDATORY): a Jira comment body is Jira WIKI markup AND Jira auto-links any issue-key-shaped token. The delivered `Acceptance Criteria ##` label is deliberately not issue-key-shaped, but the plan's other labels (OQ-03, TS-05, ...) still match `[A-Z]+-\d+`, so Jira links them to a non-existent issue and renders them with a STRIKETHROUGH (removing bold/dashes does NOT fix it). Build the comment body with `scripts/jira_safe_text.py` `jira_comment_body(text)`, which strips Markdown and wraps the body in a `{noformat}` block so Jira interprets no markup and auto-links nothing; the AC ids then render literally. To correct a comment already posted with markup, edit it in place via `JiraClient.update_comment(issue_key, comment_id, body)`, do not pile on a duplicate. `jira_safe_text.validate_jira_safe` flags a body that still carries wiki markup or an unwrapped issue-key-shaped label.
- Do not use tables.
- Do not output JSON unless explicitly requested.
- Do not include raw RAG chunks, chunk scores, backend traces, evidence matrices, or long citations.
- Never expose numeric retrieval confidence such as `0.88` in the user-facing plan. Describe evidence as verified, partial, inferred, conflicting, or unavailable and identify the evidence type.
- Emit valid UTF-8 text. Before returning, scan for mojibake markers such as `â€`, `â‰`, `Ã`, `Â`, or the replacement character; repair them or use ASCII punctuation such as `-`, `->`, and `>=` when the client encoding is uncertain.
- In the full record, do not emit a title, lifecycle preamble, authorization warning, tool trace, or quality-audit prose outside the eleven required sections. Put the concise issue interpretation under `Understanding From Jira` and detailed lifecycle/evidence availability under `Scope From Git`.
- The compatibility input record uses exactly these sections, in this order; these are not a second final-output contract:
  1. `Understanding From Jira`
  2. `Acceptance Criteria`
  3. `Expected Behaviour`
  4. `Scope From Git`
  5. `Code Touched`
  6. `Lines Changed`
  7. `Test Scenarios`
  8. `Known Jira Bugs / Past Similar Tickets`
  9. `Regression Areas`
  10. `Automation Coverage & Gaps`
  11. `Open Questions`

## Section Rules

- **Understanding From Jira**: Give the user a concise confidence check before the plan. Use exactly five bullets beginning `Issue understood:`, `Why it matters: Customer context resolved from Jira:`, `Requested outcome:`, `Lifecycle understood as:`, and `Evidence boundary:`. Restate the Jira or supplied issue in plain English without copying raw fields, inventing implementation, or writing test cases. Begin `Evidence boundary:` with the validated `Evidence mode: full` or `Evidence mode: degraded`; identify whether facts came from live Jira, indexed Jira, or supplied incident text, and expose every unavailable source, resulting claim restriction, contradiction, or missing Jira access. Keep this section to the issue's user-visible problem, impact, requested end state, lifecycle interpretation, and evidence limit.
- **Acceptance Criteria**: In the record, write every criterion in the exact grammar `- AC-## [Confirmed|Proposed]: (Basic|Negative|Integration|Performance) <plain-English acceptance criterion>. Evidence: <underlying source>.` with no Given/When/Then labels or pipes. Break a long criterion into short indented sub-points rather than stacking clauses on one line. Use contiguous unique IDs beginning at `AC-01`, and cap the presented set at ten AC points - merge related criteria and use sub-points if synthesis produced more, keeping remaining granularity in the linked full-record markdown without losing accepted meaning. `Confirmed` is only for accepted-UAC behavior and must match `uac_fidelity`; otherwise every criterion remains `Proposed`. Every AC cites an underlying source; a graph path ID alone is invalid. Follow `references/plain-language-ac-writing.md`: keep one main contract, prefer common words, group same-outcome cases as named sub-points, and split only different required behavior or outcomes. Make each criterion independently pass/fail and decided: no pending/conditional markers, qualitative bounds, non-finite negatives, alternative implementation menus, or ambiguous terminal outcome unions. Keep sign-off-critical unknowns in stable `OQ-##` records.
- Every AC must add one distinct product contract, not another phrasing of the same result. Do not add a final recap AC. Preserve any unique, source-backed cases from a merged AC in record sub-points and mapped Test Scenarios; keep an internal old-to-new coverage mapping. Put implementation-only behavior in Expected Behaviour or an Open Question until product scope approves it.
- A readability or implementation-scope REVIEW keeps the gate exit backward-compatible but makes its receipt non-postable. Resolve the wording or authority decision before any Jira write.
- **Acceptance Criteria - performance**: Add `(Performance)` only when the internal assessment is `required`. It must state a numeric workload such as topic, user, job, reference, or iteration count, and either a numeric latency, throughput, error, timeout, resource, queue, growth, or cardinality threshold with units, or a source-backed comparative target such as `at least 2x p95 improvement versus the recorded before-fix baseline`. The manifest's `performance_ac_ids` must exactly match the visible Performance AC IDs, and every Performance AC must map to an explicit performance/load/stress/soak/scalability/concurrency/benchmark scenario. Never emit a Performance AC for `conditional` or `not_required`.
- **Expected Behaviour**: State intended behaviour from Jira plus accepted `ask_dita_expert` and Figma design-flow evidence. Separate observation, supported inference, and confirmed root cause. Do not use exclusive wording such as `purely`, `only cause`, or `proves the root cause` unless the evidence rules out credible alternatives for the relevant time window. If unsupported, write `Unknown from current evidence`.
- **Scope From Git**: Start with lifecycle stage and readiness target. List issue/development-link source, relevant clone discovery and sync state, GitHub MCP/PR status only when stage-relevant, current or changed product area, diff-inspection state, and Figma evidence state when applicable. For every cited clone include absolute repository path, branch, pre-sync SHA, inspected post-sync SHA/ref, upstream/ahead/behind state, pre/post dirty state, fetch/pull result, whether claims use the synchronized worktree or a verified remote ref, and any retained developer-work stash OID/ref with its restore command.
- **Code Touched**: In pre-development, write `No code changes yet — development has not started`, then list exact current files/functions/classes/workflows under `Current implementation implicated` and evidence-backed likely change points under `Potential code impact`; label inference and never present it as changed code. Use complete absolute file paths and exact symbols; never abbreviate a path with `...`. In implementation/post-fix stages, list actual changed files/symbols from the inspected diff, plus adjacent callers, shared services, configs, persistence paths, UI states, and automation code that can be impacted, with a short QA implication for each.
- **Lines Changed**: In pre-development, write `Not applicable — development has not started`; never add a line-level Draft blocker. In implementation/post-fix stages, summarize added/deleted counts and key hunks by file; if unavailable, add `Draft blocker: implementation diff not inspected`.
- **Test Scenarios**: Open this section with one or more concrete bullets beginning exactly `- Test data to prepare:` (not P-prefixed) before the P0/P1/P2 bullets: name exact fixtures, paths, identifiers, properties/fields, config positive/negative values, environment matrix, deterministic failure injection, cleanup, and pass/fail oracles. Every primary scenario uses literal `Action:` and `Expected:` and maps to one or more AC IDs; add `[TS-##]` when the operational manifest references it. Put destructive one-time remediation under a clearly labelled `Incident recovery validation` bullet rather than an AC. Such validation must include target ownership/correlation, approved exact scope, backup/export, dry-run or pre-delete inventory, unrelated-state preservation, audit evidence, rollback, post-cleanup queue/dashboard checks, and safe production boundaries. For concurrency safeguards, separately assert successful completion, output integrity, no duplicate/partial/orphan state, and the exact bounded retry-exhaustion outcome.
- **Known Jira Bugs / Past Similar Tickets**: List up to five validated Jira keys covering relevant open known bugs and resolved historical bugs, ranked by shared defect mechanism and never padded to five with area-only or keyword-only matches. Each entry must begin its rationale with a `Similarity:` clause that names the concrete shared failure shape (not a shared subsystem name or generic word) and states the match strength; a ticket that only shares a feature area or keyword belongs in `Regression Areas`, not here. Include status/resolution, RCA or behavior lesson when available, affected/fix version, reusable test evidence, and concrete impact on scenarios or regression. Include the narrow Jira/JQL and indexed-history search status, and state there which weak/area-only candidates were deliberately dropped. Mark every unavailable field explicitly instead of inferring or omitting it. If no same-defect-class ticket exists, say so plainly rather than listing near-misses.
- **Regression Areas**: Write each item the way a senior manual QA engineer would - a concrete regression bullet that names the specific workflow, API, config, role, data shape, or build/environment to re-test and states the risk (what could break and why the fix endangers it), not a bare area name or keyword fragment. For example, prefer "Re-run adding a topic to a map via topicref and key/keydef and confirm the properties are still written, because the fix touches the shared write/remove service" over "add-to-map write path". Order by likely blast radius, and call out the single highest-priority regression explicitly. Cover nearby workflows, APIs, configs, roles, browsers, data shapes, design states, component variants, upgrade paths, integration impact, and automation coverage gaps likely to break. Each bullet must be a full sentence, not a terse label; the validator rejects fragments below a minimum length.
- **Automation Coverage & Gaps**: Begin with exactly one `- Main feature coverage: Covered|Partially covered|Not covered|Unverified - <reason>.` bullet. For every AC or grouped matrix, state a verdict. `Partially covered` requires an existing test to exercise and assert a named clause of that same AC; adjacent happy-path coverage is reusable infrastructure only. For existing coverage, include exact repository, full path, exact test/scenario symbol, helper/fixture, layer, and revision. For gaps, include exact candidate location, reusable infrastructure, deterministic setup/injection, polling oracle, timeout source, output-integrity assertions, cleanup/rollback, suite/tags, and whether to extend or add. Search every relevant automation repository and exact implementation symbol before declaring `Not covered`.
- **Open Questions**: Prefix every real question `- OQ-##:` with unique, contiguous IDs starting at `OQ-01`, and include literal `QA impact:` describing what each plausible answer changes for scenarios, expected results, environment, or sign-off. Use the same ordered IDs in the manifest. Cover only relevant permission/config/DITA/output/upgrade/operational decisions. If there are no meaningful unknowns, write exactly `- No open questions from current evidence` as the only bullet and use an empty manifest list.

## Non-Negotiable Rules

Each rule is permanent and human-set. The full wording, examples and manifest fields for every rule are in
`references/qe-authoring-rules.md`: read the matching entry there whenever a rule fires. Where a rule
decides what to investigate, "## Acceptance Scope And The Delivered UAC" decides where the result goes.

**Process**

- **Gate while authoring.** Draft, run `coverage_forcing.validate` and `uac_linter` (plus
  `validate_test_plan.py` / `run_gates.py` for the full plan), fix every failure, re-run, and present or post
  only when clean. After any hand edit also run `python scripts/uac_completeness_check.py <folder>`, and for a
  VM folder `python scripts/uac_release/uac_release_runner.py --check-dir <folder>`. An ungated draft is a
  defect.
- **Read the whole ticket first.** Every description data point, every comment (read the newest for current
  status - `coverage_forcing._validate_current_status_recency`), and every attachment opened, never judged
  from its filename. A per-surface matrix in the description is the verification baseline.
- **Evidence leaves a record.** At least three focused `ask_dita_expert` probes, at least two narrow Jira
  history searches with counts, the UAC Doc Researcher for every generation, and every documentation finding
  used or set aside - recorded in `UAC_EVIDENCE.json` and `history_attempts`. A tool missing from the session
  is not an unavailable source: use `scripts/vm_evidence_call.py`, then the offline `jira_qa` corpus. RAG
  drives the AC wording and documented behaviour; never invent a product term.
- **Ask first, then author.** Enumerate the dimension space and resolve it from evidence (`clarification_gate`).
  In an interactive session, ask the residual blocking questions and wait. In an unattended run, record each
  blocking question as a TBD on the AC it governs and continue. Never wait for a root cause.
- **Root cause and fix.** Record `fix_basis`. When a fix is known, build the requirement oracle from the
  ticket, attachments and UI first and validate the diff against it; split the fix contract into what it adds
  and what it must preserve; turn fix-introduced risks into negative ACs; take the automation verdict from
  tests the fix added; scope sign-off to what the developer's verification did not exercise
  (`root_cause_fix_driven`). An unconfirmed implementation choice is a TBD. When no fix is known, lead with the
  not-confirmed Note and make code-only mechanism guesses suggested checks. A later root-cause comment means
  the UAC must be reviewed (`uac_staleness_watch.py`).
- **Working as designed and reproducibility, before fix ACs on incident tickets.** If reproduction is
  unconfirmed, lead with a reproduction strategy and keep fix ACs Proposed. Separate confirmed expected
  behaviour (assert it) from the defect claim (unverified until reproduced), make the intended behaviour a
  blocking decision, and recommend Working-As-Designed or an enhancement where it applies.
- **The reporter's scenario is the contract.** Every AC follows a reporter step (CUSTOMER) or guards it
  (REGRESSION), recorded in `UAC_EVIDENCE.json` "scenario".
- **Hotfix and backport scope.** Every AC rests on a hotfix ticket line or on code the hotfix diff changes;
  a parent ticket's ACs are an oracle only (`hotfix_scope_check.py`).
- **Compare with similar human UACs** (`similar_uac_compare.py`, related tickets first) and answer every
  dimension AC, TBD, SUGGESTED or NOT_APPLICABLE. A similar UAC is a checklist, never authority.
- **No manifest omission bypass.** Populate signal-activated blocks through the v3 workflow; an ordinary
  waiver of `behavior_model`, `coverage_hypotheses` or `verifications` hard-fails
  (`references/manifest-completeness.md`).

**What to investigate when the signal fires**

- **Surfaces.** Inventory every place the feature appears, from documentation and from code reuse, with its
  authority. Every surface the Jira names appears in an AC or TBD by its exact product name
  (`coverage_forcing._validate_named_surface_parity`). The customer's screenshot screen is the primary target;
  an unclear target is a TBD. Check each AC's relevance to the complaining user. Keep an AC to the construct
  the ticket names, never its general category.
- **Shared code.** Other consumers of a shared path are shared-path regression
  (`shared_path_regression_coverage`). A changed shared service forces sibling entry points, the skipped
  branch's other outcomes, and caller-scoped permissions (`changed_service_neighbourhood`). When one value has
  two chains (displayed value and sort key, list and count, two implementations), read both.
- **Data and state.** Value provenance channels, including the repository node in CRX/DE
  (`value_provenance_coverage`); both values of every state or configuration axis; the lifecycle operations
  that write what a read-only feature shows.
- **Publishing.** DITA-OT processing on and off, presets in and out of scope (`publishing_scope_coverage`);
  every output-generation entry point; output-engine parity by generating and diffing the outputs; the DITA
  specification and DITA-OT documentation for construct semantics.
- **Coverage blocks.** Security (`security_coverage`), localization (`localization_regression_coverage`),
  upgrade and migration (`upgrade_migration_coverage`), and performance
  (`references/performance-assessment-contract.md`; never invent an SLA).
- **Defect patterns.** A defect ticket has at least one negative or boundary check; content constructs cover
  topic types; table paste and import cover the variant axes; links cover protocol schemes; a wrong-status fix
  keeps real failures shown as Failed; overlapping runs stay isolated; two colliding operations cover both
  sides and both orders; a destructive step after the main work gets a partial-failure check; a job whose items
  fail says what happens to the failing item, the remaining items, and how the user learns (`failure_path`); a
  user-facing server error needs a UI-behaviour decision. Enforcers are listed in
  `references/qe-authoring-rules.md`.
- **Reviewer and PM comments are requirements.** A reviewer-requested check or a PM direction is an AC, not a
  deferred question (`reviewer_request_coverage`).

## Root-Cause / Fix-Driven Authoring

- Summarized under Non-Negotiable Rules. The five steps (requirement oracle first, lifecycle, fix contract,
  fix-introduced risks, automation verdict, sign-off scope) and the `root_cause_fix` manifest block are in
  `references/qe-authoring-rules.md` and `references/root-cause-fix-driven.md`.

## Working-As-Designed Assessment

- Summarized under Non-Negotiable Rules. The full assessment (reproducibility, intended configuration or
  design, expected versus defect, blocking decision, recommended disposition) is in
  `references/qe-authoring-rules.md`.

## Ask-First Clarification Workflow

- Summarized under Non-Negotiable Rules. The dimension space, materiality, resolve-from-evidence, ask-and-wait
  steps and the `clarification` manifest block are in `references/qe-authoring-rules.md` and
  `references/clarification-gate.md`.

## Hard Rules

- Keep acceptance criteria in the plan.
- Always state the lifecycle stage and apply its evidence requirements consistently.
- Always inspect relevant available product clones for current implementation and automation clones for coverage before declaring code or automation evidence unavailable.
- Never write `no backend/Starling clone available`, `none found`, or `full coverage gap` after searching only the opened automation workspace. Such conclusions require the bounded clone discovery protocol, separate product and automation searches, exact searched terms, and resolved clone paths.
- Never treat missing PR, changed files, or line counts as a blocker in `Pre-Development UAC`.
- Never present current implementation found in a clone as changed code unless a real diff proves the change.
- Never abbreviate cited repository or file paths with `...`, and never describe a clone as current from wall-clock recency such as `last commit today`; report its exact revision and sync state.
- Never hide, discard, or silently restore developer changes. A successful dirty-repo sync must retain a named stash and expose the exact restore command; a blocked sync must leave the worktree unchanged.
- Never promote an approximate incident runtime, dataset size, or resource recommendation into a pass/fail requirement without an approved SLA or controlled benchmark contract.
- Never add a `Performance Analysis`, `Performance Assessment`, or equivalent output section. The analysis is mandatory but internal; only a justified Performance AC or conditional QA-impact Open Question appears in the existing sections.
- Never treat `terminal success/failure` as sufficient for a workflow whose acceptance contract requires successful output; test success, output integrity, and retry-exhaustion failure as distinct outcomes.
- The canonical `aem-guides-ac-v2` record uses exact labels `AC-## [Confirmed]` or `AC-## [Proposed]`, one controlled sphere, a plain-English criterion followed by `Evidence: <source>.` (no Given/When/Then labels or pipes), contiguous IDs, and terminal punctuation; long criteria may carry short indented sub-points. The legacy `aem-guides-ac-v1` Given/When/Then grammar is still parsed for saved plans but is never produced. Reject a human-facing projection supplied as source, plus decorated labels, missing evidence, extra fields, duplicate IDs, and evidence-free ACs.
- Never use the compact renderer's `- Acceptance Criteria ##:` projection as durable plan input, automation input, or Jira-posting input.
- Acceptance criteria describe observable product outcomes, not implementation choices. Keep node deletion, tracker reconciliation, mandatory workflow-step placement, single-source-of-truth architecture, lock type, retry mechanism, serialization strategy, and concrete cleanup commands in scenarios, code-impact analysis, or open questions unless Jira explicitly approves that implementation contract.
- A configuration-backed list is never treated as permanently closed merely because a screenshot, current default file, or implementation branch shows a finite set. When extensibility is in scope, require observable behavior for another valid configured entry; keep replacement of a hardcoded allowlist as code-impact or regression evidence unless accepted UAC explicitly makes it part of the product contract.
- Every non-incident P0/P1/P2 scenario must contain at least one `[AC-##]` mapping. `Incident recovery validation` bullets are the only traceability exemption.
- `Not suitable for automation` applies only to the destructive one-time production operation itself. Repeatable post-recovery product behavior on a production-equivalent environment is `Covered`, `Partially covered`, or `Not covered`.
- When one Jira connector requires authorization but another connected Jira MCP succeeds, omit the failed-connector warning from the final plan and report only the evidence source actually used.
- Never mutate Jira from an unvalidated draft, a failed/non-postable/stale receipt, a compact projection, or a caller-supplied `passed` string. Jira writes require explicit user approval, `--apply`, a current hash-bound receipt, a successful fresh strict extraction/render check, and a successful fail-closed read/recheck of the current Jira AC field.

## Quality-Gate Audit Requests

- When the user asks to audit a previous answer, first read `references/quality-gate-checklist.md` and run `scripts/validate_test_plan.py` against the previous plan when its text is available.
- List every validator failure plus evidence-quality failures that static validation cannot detect. Do not stop after the first few failures.
- Regenerate a complete record only after the failure list. Validate it with the same gate, then return the corrected canonical rendered output and retain the corrected eleven-section artifact for explicit requests.
- Do not retain an obsolete Jira-authorization warning when live Jira evidence was subsequently fetched successfully.
- Do not add extra headings such as `What can break`, `Likely bugs`, `Fix safety`, `Important combinations`, or `Draft blockers` beyond the required output sections.
- Put likely bugs, fix-safety, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Never call a plan `proper RAG-backed` when evidence is generic, unrelated, unavailable, or only keyword-matched.
- Never mark a plan ready when evidence required for its declared lifecycle stage or a sign-off-critical decision is missing. Do not impose implementation-stage PR, diff, or line-count requirements on pre-development UAC work.

## Golden Benchmark Release Qualification

- For test-plan skill or evidence-pipeline releases, run the blinded golden benchmark from `references/golden-benchmark.md` for both Codex and Claude variants after their self-tests pass.
- Treat seeded goldens as development-only. Only an independently reviewed `approved` manifest may establish a production baseline, and no metric may regress from that baseline.
- A benchmark failure blocks release qualification only; it must not bypass, replace, or break the normal single-ticket test-plan workflow.
