# Handoff: AEM Guides Dataset Studio — session summary for Codex

## Context
This is a full-stack tool (`aem-guides-dataset-studio`) for generating/validating DITA
datasets and, more relevantly this session, for generating evidence-backed QA test plans
(UACs) for AEM Guides Jira tickets using a Claude Code skill at
`.claude/skills/test-plan-generation/` (two copies: `~/.claude/skills/...` = active/dev,
and this repo's `.claude/skills/...` = team/shared).

Repo: `C:\Users\prashantp\Videos\aem-guides-dataset-studio` (git, `main` branch, remote
`https://github.com/ppal885/aem-guides-dataset-studio.git`, currently public).

## 1. Skill fixes this session (both copies, all self-tested green)

Root-cause fixes to `.claude/skills/test-plan-generation/scripts/`:

- **`affected_surface_explorer.py` (new file)** — when `implementation_grounding` names a
  handler/operation/config artifact, the plan must enumerate every value of its operation
  enum and every co-located config key, each mapped to a covering AC or an explicit
  out-of-scope/open-question disposition. Wired into `run_gates.py` as
  `check_affected_surface`. This is the guard for "shipped a fix for Overwrite but not
  Move" class of omission (caught on GUIDES-46111 originally).
- **`verify_evidence.py`: `verify_config_keys()`** — greps the clone for any config key an
  `implementation_grounding` artifact marks `key_provenance: CODE/OSGI_CONFIG`; fails if
  the exact string isn't found. Catches reporter-supplied config-key typos (e.g. a Jira
  comment said `uuid.duplicate.move.old`, the real key is `duplicate.uuid.move.old.file`).
- **`capability_eligibility_explorer.py` / `implementation_grounding.py`: `key_provenance`
  field** — every config key must be tagged `CODE`/`PRODUCT_DOC`/`OSGI_CONFIG` (verified)
  vs `REPORTER`/`TICKET`/`PARAPHRASE`/`UNKNOWN` (unverified, needs an Open Question ref).
- **`validate_test_plan.py`** (dev copy only — team copy already used a centralized
  `ac_contract.py` parser that didn't have this bug): AC id regex was tagged-format-only
  (`- AC-01 [Proposed]:`), so it silently never enforced the AC→scenario→automation
  mapping for the current clean format (`- AC-01: ...`). Fixed to match both.
- **`backend/scripts/post_acs_to_jira.py`** — now update-aware: reads the current AC
  field first; if unchanged, no-ops (no repeated "posted" comment on re-run); if changed,
  posts an "updated" comment instead of the "first posted" one. QE Assignee
  (`customfield_18512`) is auto-tagged only on the very first post, not every re-run.

Gaps 1-5 below were identified in the prior session pass and have now been **fixed** (see
"Gap fixes applied" further down). Gap 6 needed correction, not a fix — see below.

1. ~~No enforced check that a Jira comment's own claim about current code is still true
   against the actual diff.~~ **Fixed**: `comment_claim_verifier.py` + `comment_claims`
   manifest block.
2. ~~No detection of a superseding PR when a ticket references more than one PR/branch.~~
   **Fixed**: `pr_supersession_check.py` + `pr_references` manifest block.
3. ~~Dependency-delegated implementation has no fallback when both GitHub MCP and a local
   clone are unavailable.~~ **Fixed**: `dependency_resolution` sub-field on
   `implementation_grounding` artifacts.
4. ~~`premise_holds` is boolean only.~~ **Fixed**: tri-state (`true | false | "unresolved"`,
   the third requiring a `premise_note`).
5. ~~No batch/cross-ticket tooling.~~ **Fixed**: `batch_evidence_prep.py`.
6. **Corrected, not fixed**: a real evidence knowledge graph already exists in this repo
   (commit `333cbc308`, "feat: add production evidence knowledge graph", Aug 9 2026) —
   `backend/app/services/evidence_graph_store.py` / `evidence_graph_build_service.py` /
   `evidence_graph_query_service.py` / `evidence_graph_contract.py`, with real node types
   (`jira_issue`, `component`, `domain`, `feature`, `release`, `documentation_page`,
   `dita_element`, `behavior_claim`, `root_cause`, `qa_oracle`, `risk`, `error_signature`,
   `api_route`, `config_key`) and typed relations, trust tiers, blue/green generation
   promotion, integrity hashing. It is wired into the skill as a **mandatory** manifest
   block (`evidence_graph_manifest.py`, validated unconditionally by `run_gates.py`) — but
   **it has no node type for PRs, commits, or diffs**; it links Jira issues to
   customers/components/docs/DITA-spec/historical-defect-pattern data, not to code changes.
   So it does not help with gap 1 (comment-vs-code) or gap 2 (PR supersession) — those
   needed the separate fixes above. It is also **disabled locally**
   (`EVIDENCE_GRAPH_ENABLED` unset in `backend/.env`, defaults to `false`) — every plan this
   session recorded `evidence_graph.status: "disabled"` and moved on. Turning it on would
   need the DB migration applied + `EVIDENCE_GRAPH_ENABLED=true` + a populate/sync job; that
   is a separate, real follow-up, not something done in this pass.

## Gap fixes applied (this pass)

All in `.claude/skills/test-plan-generation/scripts/` (**both** the dev copy
`~/.claude/skills/test-plan-generation/` and this repo's team copy
`<repo>/.claude/skills/test-plan-generation/` — self-tests green in both):

- **`comment_claim_verifier.py`** (new) — `comment_claims` manifest block. A Jira
  comment's claim about current code/behaviour (author RCA, reviewer finding, "Fix Ready"
  note) must carry a `verification_status` (`VERIFIED_TRUE|VERIFIED_FALSE|
  STALE_SUPERSEDED|UNVERIFIABLE`) backed by `evidence_ids`, or an `open_question_ref` if
  genuinely unverifiable. Optional/backward-compatible; a soft heuristic
  (`likely_claims_in_comments`) prints a non-blocking REVIEW note when comment text looks
  like a current-behaviour claim but nothing was recorded.
- **`pr_supersession_check.py`** (new) — `pr_references` manifest block, activates only
  when a ticket has >1 PR/branch in play. Exactly one entry must be `AUTHORITATIVE` with a
  `comparison_note`, or every entry must be `UNRESOLVED` with an `open_question_ref`. Also
  a CLI (`python pr_supersession_check.py <repo> <base_ref> <pr_a> <pr_b>`) that fetches
  both PR refs and reports their file-level diff automatically — this is what would have
  made the GUIDES-45948 #8098-vs-#8135 comparison one command instead of manual diffing.
- **`implementation_grounding.py`**: `premise_holds` now accepts `true | false |
  "unresolved"` (third state requires `premise_note`); new optional `dependency_resolution`
  sub-field (`RESOLVED_LOCAL_CLONE|RESOLVED_GITHUB_MCP|UNRESOLVED_NO_ACCESS|
  NOT_APPLICABLE`, the `UNRESOLVED_NO_ACCESS` case requires a `note`) for artifacts whose
  real logic is delegated to an external/vendored package (the GUIDES-49507 `@rh/jui-app`
  case).
- **`batch_evidence_prep.py`** (new) — `python batch_evidence_prep.py --batch tickets.json`
  runs the PR-fetch + `diff --stat` step for a whole batch of tickets in one pass instead
  of one at a time.
- All wired into `run_gates.py` (both copies); self-tests added to `test_skill_scripts.py`
  (both copies) — `test_comment_claims`, `test_pr_supersession`, plus new assertions inside
  `test_implementation_grounding`.
- **Also fixed in passing**: the team copy's self-test suite was missing the config-key
  `key_provenance` test coverage entirely, even though the validator (in both copies)
  already enforced it — a live instance of the exact dual-copy-drift problem this list
  describes. Backported those tests from the dev copy.
- Reference docs updated in both copies: `references/api-implementation-evidence.md`
  (`premise_holds` tri-state, `dependency_resolution`, `comment_claims` protocol),
  `references/pr-and-repo-evidence.md` (PR-supersession protocol, batch-prep tool).

## New, larger finding: `.codex/skills/test-plan-generation/` is a THIRD copy, far behind

There are three copies of this skill, not two:
1. Dev: `C:\Users\prashantp\.claude\skills\test-plan-generation\` (personal, outside repo)
2. Team: `<repo>\.claude\skills\test-plan-generation\` (tracked, Claude Code reads it)
3. **Codex: `<repo>\.codex\skills\test-plan-generation\`** (tracked, presumably what Codex
   CLI reads for this repo)

The `.codex` copy's `run_gates.py` (626 lines) only loads `validate_mod`, `compact_mod`,
`verify_mod`, `graph_manifest_mod`, `performance_mod`. It has **no**
`implementation_grounding.py`, `affected_surface_explorer.py`,
`capability_eligibility_explorer.py`, `behavior_model.py`, `coverage_hypotheses.py`,
`scope_conflict_resolver.py`, `state_compatibility_explorer.py`,
`disposition_classifier.py`, `hypothesis_verifier.py`, `missing_questions.py`,
`cross_surface_resolver.py`, `structural_equivalence_verifier.py`,
`change_impact_explorer.py`, `relevance_prioritizer.py`, `scenario_reducer.py`,
`test_oracle_builder.py`, `uac_integration.py`, `pre_uac_critic.py`,
`evidence_authority_resolver.py`, `anti_hardcoding_audit.py`, or
`semantic_relationship_explorer.py` — the entire reasoning/grounding pipeline that the two
`.claude` copies enforce. It runs structural validation + evidence-citation checks +
evidence-graph/performance-contract manifest checks, but **nothing forces a code artifact
to actually be inspected, nothing catches an unverified config key, nothing enforces full
AC coverage of an operation/config surface, nothing reconciles scope conflicts or state
compatibility.** Whatever Codex has generated through this local skill copy did not have
any of the safeguards that caught this session's real defects (the `create.version.
newly.uploaded.content` config-key typo on GUIDES-46111/7207, the missing Move-vs-Overwrite
AC on GUIDES-46111, GUIDES-47043's comment-inferred-not-diff-verified error).

This commit (`333cbc308`, Aug 9 2026) is what created the 3-way split: it added
`evidence_graph_manifest.py`/`performance_contract.py`/`render_compact_view.py` wiring to
the **team** and **codex** copies (both are inside the git repo, so a single commit reaches
both) but — since the **dev** copy lives outside the repo at `~/.claude/skills/...` — could
never have reached it via that commit; a separate manual sync step was apparently needed
and didn't happen. The 5 fixes in this pass went to dev+team only, for the same structural
reason: the `.codex` copy is missing the very modules (`implementation_grounding.py`) that
2 of the 5 fixes extend.

**Not yet decided**: whether to backport the full ~20-module reasoning pipeline into
`.codex/skills/test-plan-generation/` (a large effort — essentially replicating weeks of
incremental skill development into a third copy), do a lighter partial port of just
today's 3 dependency-free additions (`comment_claim_verifier.py`,
`pr_supersession_check.py`, `batch_evidence_prep.py`, which have no imports from the
missing modules), or leave `.codex` as a deliberately simpler/different-purpose variant.
This needs a decision from whoever owns the Codex-side workflow before more work goes into
that copy.

## 2. GitHub Enterprise access without GitHub MCP / gh CLI

`gh` CLI here is only authenticated to public `github.com`, NOT `git.corp.adobe.com`
(Adobe's internal GitHub Enterprise where Starling/xmleditor/guides-ui-tests live), and no
GitHub MCP connector is available this session. **Workaround that worked reliably**:
Adobe's GHE exposes `refs/pull/<n>/head` over plain git — so PR diffs are fetched directly:

```bash
cd C:\starling   # or C:\xmleditor\xmleditor for xmleditor PRs
git fetch origin +refs/pull/8095/head:pr-8095
git diff --stat origin/develop...pr-8095
git diff origin/develop...pr-8095 -- '*SomeFile.java'
```

This substitutes for GitHub MCP entirely for PR inspection. Also useful: Adobe's Starling/
xmleditor repos have `crosshair/guides-<ticket>` branches (an internal AI-investigation bot
snapshots its analysis there) — these usually equal the current PR head exactly (verified
via empty `git diff crosshair-branch...pr-branch` this session for 5/5 tickets checked).

Local product clones used this session (run `python scripts/sync_evidence_repo.py <path>
--stash-dirty` from the skill dir before trusting any clone as current):
- `C:\starling` (Starling/backend) — HEAD after fresh fetch: `69a98eab3948e98aa78684276be7d37fe30b39ea` (branch `develop`)
- `C:\xmleditor\xmleditor` (XML editor UI) — HEAD after fresh fetch: `85574ec9f6` (branch `develop`)
- `C:\UI TEST\guides-ui-tests` (automation) — HEAD: `234e19acd`

Note: `sync_evidence_repo.py`'s own JSON status field can misreport `"fetch": "failed"` when
the actual git output contains an unrelated stderr warning (SSH post-quantum notice) or a
rejected tag — always check the raw fetch output for `-> origin/develop` movement before
trusting the tool's own verdict.

## 3. UACs generated this session (all in `output/test-plans/<KEY>-test-plan.md` +
   `<KEY>-combined.md`, all `run_gates.py`-passed, all indexed into `jira_qa` via
   `cd backend && python scripts/index_test_plan.py --key <KEY>`)

| Ticket | Stage | Verdict | Posted to Jira? |
|---|---|---|---|
| GUIDES-7207 | Post-Fix | 10 ACs, clean | Yes (Needs_Human_Review) |
| GUIDES-46111 | Pre-Dev | 10 ACs (added AC-09/10 this session) | Yes (Needs_Human_Review) |
| GUIDES-47043 | Impl Review | 5 ACs — **corrected this session**, was wrong in an earlier pass (see below) | Yes (updated + correction comment) |
| GUIDES-53707 | Pre-Dev | 8 ACs | **No** (explicit user instruction: do not post) |
| GUIDES-52690 | UAT | 9 ACs, human-vs-AI compared | **No** (human UAC already finalized on Jira, did not overwrite) |
| GUIDES-44288 | Impl Review | 4 ACs, clean fix | Yes (Needs_Human_Review, no QE Assignee set) |
| GUIDES-50144 | Impl Review | 5 ACs, clean fix | Yes (Needs_Human_Review, no QE Assignee set) |
| GUIDES-48193 | Impl Review | 6 ACs, partial-scope fix (3 reviewer gaps confirmed real) | Yes (Needs_Human_Review, no QE Assignee set) |
| GUIDES-47692 | Impl Review | 4 ACs, partial (cache race/bootstrap gaps confirmed real) | Yes (Needs_Human_Review, QE tag [~prashantp]) |
| GUIDES-45948 | Impl Review | 5 ACs, **PR ambiguity found** (#8098 superseded by #8135) | Yes (Needs_Human_Review, QE tag [~ankitb]) |
| GUIDES-49507 | Impl Review | 5 ACs, dependency-guard risk found | Yes (Needs_Human_Review, no QE Assignee set) |

**GUIDES-47043 correction (important)**: an earlier pass this session inferred the
implicated code from Jira comment text alone (before the diff was reviewable) and got it
wrong — cited `dam-buttons.js`, asserted Preview Map + Share UUID Link visibility gating
that the real code doesn't implement, and included a nonexistent `.ditaval` extension.
Once the actual PR #8095 diff was read (`isditaasset` render condition on `.content.xml`,
extensions `xml`/`dita`/`ditamap` only), the plan was corrected and the live Jira AC field
+ a correction-explaining comment were both updated. Lesson: never grounded solely on
comment text when a diff is fetchable.

**GUIDES-45948 open item**: PR #8098 (linked to this ticket) only fixes the V2 baseline
resolution strategy; a later PR #8135 (found by checking the last Jira comment referencing
a different PR) supersedes it with a full V1+V2 fix. The plan is grounded on #8135 as the
current candidate but this needs engineering confirmation on which PR actually merges
(Open Question OQ-1 in the plan).

## 4. Infrastructure changes this session

- **Shared ChromaDB for the team**: `backend/app/services/vector_store_service.py` now
  supports `CHROMA_HOST`/`CHROMA_PORT`/`CHROMA_SSL`/`CHROMA_AUTH_TOKEN` env vars to connect
  via `HttpClient` to a Chroma server instead of the local embedded `PersistentClient`
  (backward-compatible — no `CHROMA_HOST` = old behavior). A `CHROMA_API_PATH` custom-prefix
  attempt was tried and reverted (the chromadb 1.5.5 client validates its API path as a
  strict enum, `/api/v1`|`/api/v2` only — a sub-path prefix like `/chroma/` is rejected
  client-side). The working setup instead routes the REAL `/api/v2` path through the
  existing Nginx port (4502, already used for the backend/MCP), restricted to the team
  subnet. One-time setup script: `scripts/setup_shared_chroma.sh` (idempotent — installs
  chromadb, runs it as a `chroma` systemd service on `127.0.0.1:8000`, adds a
  `location /api/v2/ { allow <subnet>; deny all; proxy_pass http://127.0.0.1:8000; }` block
  to the live Nginx conf with a timestamped backup, reloads Nginx, verifies the proxy
  heartbeat). Teammate connection doc: `docs/connect-shared-vector-db.md` (no repo needed,
  just `pip install chromadb sentence-transformers` + `chromadb.HttpClient(host, port=4502,
  ssl=False)` with NO custom settings).
- **UI Behavior Harvester** (`ui_harvester/` package, new) — a deterministic Playwright
  state-crawler for AEM Guides that captures UI topology/state/transitions into new
  `ui_state`/`ui_transition` Chroma collections (same embedding model as the rest of the
  RAG). 13 modules (`taxonomy.py`, `state.py`, `dom_extract.py`, `actions.py`,
  `transitions.py`, `harvester.py`, `indexer.py`, `reports.py`, `auth.py`, `config.py`,
  `currentness.py`, `screenshot.py`, `rag_records.py`), 28 unit tests green, config at
  `config/ui_crawler.yaml`. Stopped (per spec) before any live crawl — needs a human to run
  `python -m ui_harvester auth` locally (opens a headed browser for the human to complete
  Adobe SSO/MFA) to produce `ui_evidence/auth/storage_state.json` before a smoke crawl can
  run. Seeding is via `config/ui_crawler.yaml`'s `seed_surfaces` (default: Assets UI) plus
  an optional `fixtures.dita_topic` path + `fixtures.editor_url_template` (host-agnostic,
  no hardcoded environment URL committed) to also seed the web editor with a real topic
  open.
- Ingested ~16 AEM Guides / Experience League doc pages into the `aem_guides` RAG
  collection this session (version-management, editor-configs ×10, topic-map-template ×3,
  JCR/architecture underlying-technology ×2) — collection now ~5,098 chunks locally. VM
  needs the same ingestion re-run (commands were given earlier in-session; re-derivable
  from `backend/app/services/experience_league_index_service.py`'s
  `crawl_experience_league_rag()` with the URL list).

## 5. What's NOT done / pending

- All 11 tickets' ACs are now posted to Jira (`Needs_Human_Review` label on each) — none
  remain draft-only. Every post is still AI-generated and explicitly flagged for human
  QA/reviewer sign-off before it's treated as final.
- GUIDES-45948's PR ambiguity (#8098 vs #8135) needs an answer from Starling engineering
  before this plan's AC-02/AC-03 (which depend on #8135's V1 fix) can be trusted as the
  actual shipping behavior.
- The shared-Chroma VM setup is live and verified (`curl http://<vm>:4502/api/v2/heartbeat`
  returns a heartbeat) but teammates haven't yet been given the connection doc/tested it
  themselves.
- UI Harvester has not run any live crawl (by design — waiting on a human `auth` step).
