# Demo — Plain Claude vs Test-Plan Skill (3 tickets)

Three live AEM Guides tickets. For each: what plain Claude (ticket text only, no skill)
produces, what the skill produces (evidence-backed), and a deterministic score of both
against the human-accepted requirements (all three are real, so we have ground truth).

Scoring is by `analysis/eval_harness.py` (deterministic; the semantic match verdicts are the
inputs, the metrics are reproducible).

| Ticket | Component | Summary |
|---|---|---|
| GUIDES-25713 | Authoring | Show warning on Save when there are duplicate IDs in topics |
| GUIDES-26085 | Backend API | API to track output generation status (`/bin/publishlistener`) |
| GUIDES-53707 | Publishing | AEM Sites output generation fails when topicref used as navtitle |

## Scoreboard (headline)

| Metric | 25713 plain → skill | 26085 plain → skill | 53707 plain → skill |
|---|---|---|---|
| Behavioural recall (real requirements covered) | 17% → **83%** | 25% → **88%** | 12% → **88%** |
| Open-question recall (right unknowns surfaced) | 0% → **100%** | 0% → **100%** | 0% → **100%** |
| Available evidence missed | 4/6 → **0/6** | 5/8 → **0/8** | 7/8 → **0/8** |
| Unsupported ACs (no evidence) | 100% → **0%** | 100% → **0%** | 100% → **0%** |
| Wrong/false ACs invented | 3 → **0** | 1 → **0** | 1 → **0** |

The pattern is identical across a UI ticket, an API ticket, and a backend-crash ticket:
plain Claude restates the ask; the skill covers the behaviour, the regressions, the edge
cases, and names the real open question — because it reads the code and the spec first.

---

## 1. GUIDES-25713 — Authoring (duplicate IDs warning on Save)

**Understanding from Jira.** GUIDES-17528 turned the duplicate-ID error into a warning shown
only as a source-view marker, so authors can miss it. The ask: at Save time in author view,
show the duplicate-ID warning as a prompt too — while still allowing the save.

### Plain Claude (no skill)
- AC: When the user saves a topic with duplicate IDs, a warning is shown.
- AC: The system validates that all IDs in the topic are unique.
- AC: The duplicate-ID error should prevent saving until resolved.  ← **wrong** (the ticket
  explicitly keeps save non-blocking; plain Claude invents a blocking rule).
- Scenario: Save a topic with two identical IDs and see the warning.

*Problem:* one right AC, one vague AC, one AC that contradicts the ticket, no evidence, no
edge cases, no regression, no open question.

### With the skill (evidence-backed)
Evidence read: `xmleditor/src/controllers/widgets/duplicate_ids_controller.ts`.
- AC-01 (Confirmed): Saving a topic with duplicate IDs in author view shows a warning prompt.
- AC-02 (Confirmed): The warning does not block the save — the topic still saves (preserves
  GUIDES-17528 behaviour).
- AC-03 (Confirmed): The prompt lists each duplicate occurrence and, on click, navigates to
  that element's xpath (`createNMinusOneEntries` / `handleDuplicateIdClick`).
- AC-04: The existing source-view marker and author-mode popover
  (`showDuplicateIds`) keep working unchanged.
- AC-05 (Proposed): On large files the id cache is not recreated (`recreateIdCache` skips
  `createIdCache` when `EDITOR_IS_LARGE_FILE`), so the save warning must handle stale or
  skipped detection — otherwise a large topic can save with undetected duplicates.
- Open question: Is the save prompt a blocking modal or a non-blocking toast? This is a
  product UX decision and it changes the whole test matrix, so it must be settled first.

**What the skill caught that plain Claude did not:** the non-blocking rule (avoided a wrong
AC), the navigation behaviour, the marker/popover regression, and the large-file stale-cache
edge case — all from the actual controller code.

| Metric | Plain | Skill |
|---|---|---|
| Behavioural recall | 17% | 83% |
| Open-question recall | 0% | 100% |
| Evidence missed | 4/6 | 0/6 |
| Unsupported ACs | 100% | 0% |
| Wrong ACs invented | 3 | 0 |

---

## 2. GUIDES-26085 — Backend API (track output generation status)

**Understanding from Jira.** IBM automates publishing via the Guides APIs. Today
`GENERATEOUTPUT` returns no job id, and `PUBLISHBEACON` returns the whole output-history
array (also used to load the map dashboard). Ask: a public, efficient API to track one
publishing job, plus documentation of the existing APIs.

### Plain Claude (no skill)
- AC: An API is provided to track the output generation status.
- AC: The API returns whether publishing succeeded or failed.
- Scenario: Call the API and verify it returns the job status.

*Problem:* restates the ask. No job-id linkage, no efficiency requirement, no dashboard
regression, no auth, no documentation, no open question, no evidence.

### With the skill (evidence-backed)
Evidence read: `starling/core/utils/.../PublishUtils.java` (`generateOutput` → `operation =
GENERATEOUTPUT`), `PublishWorkflowStep.java`, dashboard consumers `outputmanager.js` /
`outputcontroller.js`, `core-api-servlet-paths.csv`.
- AC-01 (Confirmed): The generate-output response returns a jobId that can be passed to the
  status API.
- AC-02 (Confirmed): A status API returns one job's status without the full output-history
  array.
- AC-03 (Confirmed): The `GENERATEOUTPUT` and `PUBLISHBEACON` APIs are documented for
  customers (the ticket's second ask).
- AC-04: The map-dashboard load that consumes `PUBLISHBEACON` keeps working
  unchanged.
- AC-05 (Confirmed): The public status API enforces tenant/permission access control.
- AC-06 (Confirmed): The status API distinguishes in-progress, success, and failure and
  returns an error payload on failure.
- AC-07: Single-job tracking stays efficient under many concurrent jobs,
  instead of returning the whole history array.
- Open question: What is the exact REST contract and versioning of the new API? The ticket
  says "technical design can be discussed" — a design decision to settle before sign-off.

**What the skill caught that plain Claude did not:** the job-id link, the array-bloat
efficiency requirement, the dashboard regression, auth, documentation, and the design open
question.

| Metric | Plain | Skill |
|---|---|---|
| Behavioural recall | 25% | 88% |
| Open-question recall | 0% | 100% |
| Evidence missed | 5/8 | 0/8 |
| Unsupported ACs | 100% | 0% |
| Wrong ACs invented | 1 | 0 |

---

## 3. GUIDES-53707 — Publishing (topicref-as-navtitle crash) — already done

**Understanding from Jira.** Native AEM Sites publishing fails with a `GuidesException` from
`PathUtils.appendUnixSlash` when a topicref is used as navtitle, and it keeps failing until
the generated site nodes are deleted manually (Avaya, Stage). The DITA-semantic trigger is a
**navtitle without an href**: a `<topichead>` (and a `<topicref>` used purely as a navtitle)
carries a navtitle but no `@href`, so path resolution receives a null path and throws.

### Plain Claude (no skill)
- AC: Fix the NullPointerException so output generation does not fail.
- Scenario: Publish the map and confirm no error.

### With the skill (evidence-backed)
- AC-01: A topicref-as-navtitle map generates AEM Sites output without the exception.
- AC-02: Previously failing maps regenerate without manually deleting the generated nodes.
- AC-03: The failed-generation state clears itself so a retry succeeds without manual cleanup.
- AC-04: navtitle resolution honours locktitle; the title source is resolved when href is
  absent (DITA 1.3 semantics).
- AC-05: The same map is verified across all output presets (AEM Sites
  new/legacy, HTML5, Native PDF, DITA-OT PDF), not only the one that crashed.
- AC-06: A malformed/empty topicref href is handled gracefully instead of throwing.
- AC-07: A `<topichead>` / navtitle-only topicref (navtitle, no href) generates its
  navigation entry or is safely skipped, without the null-path exception. ← **the core
  DITA-semantic case the ticket title never spelled out.**
- Open question: Does `locktitle=yes` also avoid the failure, and what is the intended title
  source when there is no href? Needs product/spec confirmation.

| Metric | Plain | Skill |
|---|---|---|
| Behavioural recall | 12% | 88% |
| Open-question recall | 0% | 100% |
| Evidence missed | 7/8 | 0/8 |
| Unsupported ACs | 100% | 0% |
| Wrong ACs invented | 1 | 0 |

---

## Why the skill wins (one line)

Plain Claude writes acceptance criteria from the sentence in the ticket. The skill writes
them from the **code, the spec, and the neighbouring behaviour** — so it covers the
regressions, the edge cases, and the real unknowns a senior QA would, and it stops inventing
requirements the ticket never asked for.
