---
name: aem-guides-test-scenario-generator
description: Generate senior SDET AEM Guides Jira test plans with evidence, RAG, repo analysis, bug discovery, regression risk, UACs, automation mapping, and QE review.
---

# AEM Guides Test Scenario Generator

Primary goal: **find regressions before release**. The Skill itself is the orchestration workflow: Claude Code fetches Jira through Adobe Jira MCP, inspects local cloned repos, queries the existing VM RAG/MCP, applies deterministic validation/scoring, and writes a QE-reviewed test-plan deliverable.

Output is a **short markdown test plan (<=3 pages / ~195 lines)** in **plain English**, plus retained machine-readable evidence/score artifacts when tools expose them. Do not build or ask for a separate pipeline app.

**Works on:** Claude Code, Cursor Agent, and Codex when the same MCP tools and repo paths are configured.

**Canonical skill location:** `aem-guides-dataset-studio/claude-skills/aem-guides-test-scenario-generator/`  
**Claude copy:** `~/.claude/skills/aem-guides-test-scenario-generator/` (sync when skill changes)

## Mandatory workflow (blocking order)

0. **Use this Skill as the orchestrator** — do not create another Jira client, repo scanner, RAG system, vector DB, duplicate pipeline app, or duplicate Skill. Use existing MCP tools and direct repo access already available in Claude Code.
1. **Fetch complete Jira** — use Adobe Jira MCP first. Pull summary, description, labels, components, issue type, priority, comments, attachments metadata, linked issues, acceptance criteria fields, and recent status/change context when available.
2. **Normalize ticket analysis** — produce explicit fields: summary, product, component, issue type, customer context, current behaviour, expected behaviour/requested enhancement, business impact, existing acceptance criteria, and missing information.
3. **Classify workflow** — Bug -> reproduction/regression-first. Feature request -> expected behaviour/UAC feasibility-first. Mixed/unclear -> ask focused clarification before Review-ready.
4. **Read registry first** — `{STARLING}/docs/qa/test-plans/test-plans-registry.json`.
5. **Inspect cloned repos before conclusions**:
   - `STARLING_REPO_PATH` (default `C:/starling`)
   - `XML_EDITOR_REPO_PATH` (default `C:/xmleditor`)
   - `DXML_IT_TESTS_REPO_PATH` (default `C:/api automation/dxml-it-tests`)
   - `GUIDES_UI_TESTS_REPO_PATH` (default `C:/ui_framework/guides-ui-tests`)
   Inspect implementation code, commits/changed files, APIs, validators, feature files, page objects, unit/integration/UI tests, and automation gaps. Classify automation: Exact and strong | Exact but weak check | Partial | Obsolete | Mocked-path only | Missing. Never say **Missing** if a repo exists but only lacks ticket-specific coverage; say **Partial** + exact gap.
6. **Query existing VM RAG/MCP** — use `guides_test_plan_generator`, `find_similar_jira_issues`, `ask_dita_expert`, `lookup_dita_construct`, or equivalent registered tools. Retrieve related previous Jiras, product docs, AEM Guides behaviour, DITA/DITA-OT specs, previous regressions, customer scenarios, and Swagger/API evidence for REST tickets. Do not create a new RAG/vector DB.
7. **Generate evidence-grounded UACs** — every UAC must cite Jira/RAG/spec/repo evidence or be marked assumption/human-clarification-required.
8. **Classify every conclusion** — use exactly one: ticket-confirmed, documentation-confirmed, specification-confirmed, implementation-derived, previous-JIRA-derived, assumption, human-clarification-required.
9. **Score deterministically** — score ticket completeness, retrieval quality, evidence coverage, source consistency, UAC testability, and requirement traceability. Use existing deterministic helpers if registered (`test_plan_pipeline` MCP/HTTP or local scripts); otherwise calculate manually and show the score table.
10. **Route by score**:
    - `>=85`: write plan and mark `QE_REVIEW_READY`.
    - `70-84`: write provisional plan and mark `QE_REVIEW_WITH_FLAGS`.
    - `<70`: pause final plan and ask focused human clarification questions; a Draft may be written only if the user asks.
11. **QE review is always required** — high score never means auto-approved. Include a QE review package and unresolved questions.
12. **Write plan** from `references/output-template.md` — action items first, supplementary below, plain English in the plan body.
13. **Validate** — `python scripts/validate_test_plan.py <plan.md>` — fix all errors before delivery.
14. **Update registry and retained memory** — update `test-plans-registry.json`; if backend memory APIs/tools exist, record or cite retained pipeline/test-plan memory for comparison.

## Plan structure (3 sections — do not expand)

| Section | Required content | Limits |
| --- | --- | --- |
| **1. Summary & expected behaviour** | EB-* bullets, compact Evidence table, classification labels, sign-off checks | 5-7 EB bullets; evidence table <=10 rows |
| **2. What can break & risks** | Code path, impact table, risk table, regression checks, likely bugs, Related past Jiras | <=3 likely bugs; <=5 historical Jiras |
| **3. Test scenarios & release** | Test list, P0/P1 steps, automation, confidence/routing, QE review package, what's left & sign-off | <=10 scenarios; detail P0/P1 only |

## Writing style (mandatory — read `references/plain-english-writing.md`)

Write so a **manual QA engineer** can execute without decoding jargon.

| Avoid in plan body | Use instead |
| --- | --- |
| oracle / multi-layer oracle | **how to verify**, **how to check**, **pass if** |
| blast radius | **what can break**, **what else is affected** |
| UAC | **sign-off checks**, **acceptance checks** |
| residual risk | **what's left**, **not tested yet** |
| failure mode | **what goes wrong** |
| bug hypothesis | **likely bug to watch** |

**Pass criteria must be concrete:** HTTP status, exact JSON field, CRX property name, log text, output file, visible UI column/value — never "works correctly".

Keep IDs (`EB-*`, `AC-*`, `S-*`, `R-*`) for traceability.

**AC vs S:** AC bullets = Jira acceptance/sign-off checks. S-* = executable test scenarios in section 3.

### Removed from old template (do not restore)

- Large standalone `## 3. Evidence map` section.
- 15-section long template.
- Auto-approval language.

### Kept (required)

- Compact **Evidence table** in section 1 with classification labels.
- **Related past Jiras** — compact table in section 2.
- Impact + risk tables with plain headers.
- EB-* expected outcomes.
- **How to check** for P0/P1 scenarios.
- Confidence breakdown and routing status.
- QE review package.

## MCP/tools

| Purpose | Tool/source |
| --- | --- |
| Adobe Jira intake | Adobe Jira MCP tools registered in Claude Code — authoritative live Jira source |
| Existing deterministic helper | `test_plan_pipeline(jira_key, write_starling_artifacts=true)` if already registered — use as scoring/evidence helper, not as a separate app to build |
| Jira + VM RAG packet | `guides_test_plan_generator(jira_key)` — full mode for learned behavior |
| RAG corpus status | `show_mcp_rag_corpus_status` |
| Similar past Jiras | `find_similar_jira_issues` |
| DITA construct lookup | `lookup_dita_construct` / `ask_dita_expert` |
| Generate QA DITA data | `generate_dita` / `generate_dita_ot_output` |
| Upload to AEM | `upload_mcp_generated_data_to_aem` only after explicit user request |
| Swagger index | `references/swagger-api-rag-indexing.md` |

## Classification labels

Use these labels exactly in evidence rows, UACs, assumptions, and confidence notes:

- `ticket-confirmed`
- `documentation-confirmed`
- `specification-confirmed`
- `implementation-derived`
- `previous-JIRA-derived`
- `assumption`
- `human-clarification-required`

## Test plan registry (mandatory memory)

Every create or material update **must** update:

**File:** `{STARLING}/docs/qa/test-plans/test-plans-registry.json`

**Record per JIRA:** `jira_key`, `title`, `plan_file`, `template_version`, `review_status`, `scope`, `dam_path`, `test_data_repo`, `p0_scenarios`, `automation`, `related_past_jiras`, `created`, `updated`.

Set `template_version` to `dalp-compact-v2` for new/rewritten plans.

**DITA learning datasets** (no JIRA): add under `dita_learning_datasets`.

## Deliverable paths

| Repo | Path |
| --- | --- |
| **starling (primary)** | `docs/qa/test-plans/{JIRA-KEY}-test-plan.md` |
| Pipeline/result JSON when helper exists | `docs/qa/test-plans/{JIRA-KEY}-pipeline-result.json` |
| Full RAG packet when helper exists | `docs/qa/test-plans/{JIRA-KEY}-full-rag-packet.md` |
| dataset-studio optional copy | `output/test-plans/{JIRA-KEY}-test-plan.md` |

Save in repo; chat-only output is not the deliverable. Tell the user the full file path when done.

## Quality gates

- **Verification wording:** Use **how to verify / pass if** — HTTP status, CRX property, log line, output file, exact UI value.
- **Evidence classification:** every evidence row and UAC must use one of the seven classification labels.
- **Scoring:** include six deterministic dimensions and routing status (`QE_REVIEW_READY`, `QE_REVIEW_WITH_FLAGS`, or human clarification/Draft).
- **Review-ready:** score >=85, product repo `path:line` in section 1, automation classified with real file paths, sign-off checks listed, QE review package included.
- **With flags / Draft:** partial repo evidence, automation gaps, MCP fast mode without Swagger evidence, missing Author sign-off for REST tickets, or score 70-84.
- **Human clarification:** score <70 or current/expected behavior/business impact is materially unclear.
- **QE review:** always required. A high score must never auto-approve.
- **Length:** validator fails at >195 lines.
- **Language:** validator flags vague pass criteria ("works correctly", "no error").

## DO / DON'T

**DO:** Orchestrate Jira MCP + local repo inspection + existing VM RAG; normalize ticket fields; classify evidence; score deterministically; write plain English for QA; index/query Author Swagger for REST tickets; search past Jiras; check actual clone paths; run validator; update registry; point to saved file path.

**DON'T:** Build duplicate Jira/RAG/repo services; skip product context on unfamiliar areas (Baseline, new APIs); use jargon (oracle, blast radius, UAC) in the plan body; add a large standalone Evidence map section; exceed 3 pages; mark Review-ready with vague pass criteria; auto-approve without QE; deliver plan only in chat without saving to starling.
