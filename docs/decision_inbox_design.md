# Design: Decision Inbox for human intervention, integrated with the Vision agent

Status: proposal, needs explicit product approval (CLAUDE.md: no new browser surface unless the user
explicitly requests a product change). Author: UAC automation team. Date: 2026-10-23.

## Problem

Human intervention in the UAC flow exists today, but only through Jira comments, Jira field edits, a CLI
JSON file and raw API calls:

| Intervention | Channel today | Friction |
|---|---|---|
| Answer an open decision (TBD) | Runner posts a decision-request comment; a person replies in Jira | Free text; the next run has to interpret it |
| Correct a posted UAC | QE edits the Acceptance Criteria field; harvester diffs it every 30 min | QE cannot see whether the correction was captured |
| Approve or reject shared learning | `POST /test-plan-learning/feedback/{id}/bind` and `/review` (live QE Assignee only) | API call; no UI |
| Answer convergence questions (PM / Dev / QE conflicts) | CLI `--clarifications <json>` and re-run | Hand-written JSON |
| Decide a re-run after a fix or PR | Staleness alert comment; QE re-runs manually | Alert without an action |
| See what happened | Read-only dashboard (`:4502/`) and release page (`/uac-release`) | Deliberately write-free |

The retired React/Vite Dataset Studio application is not the answer: it was a general-purpose authoring UI,
and the repository rules forbid recreating it. What is missing is a small, write-constrained **Decision
Inbox** that sits between the UAC agent, the Vision agent and the humans, with Jira staying the system of
record.

## Actors and the loop

```
        UAC agent (nightly runner)                    Vision agent
        writes UAC -> Jira AC field                   reads AC field -> fixes -> PR
        posts TBD decision requests                   posts [Vision] comments (PR, root cause)
                 |                                             |
                 v                                             v
        +----------------------- Jira (system of record) ------------------------+
        |  AC field . labels . [Vision] comments . decision-request comments      |
        +--------------------------------------+---------------------------------+
                                               | read-only poll / webhook
                                               v
                               +------------- Decision Inbox -------------+
                               |  FastAPI routes (new, thin)              |
                               |  + one static HTML page behind Nginx     |
                               +------+-------------+------------+-------+
                                      |             |            |
                      answer TBD -----+   approve/reject --+    request re-run --+
                      -> human_clarifications   -> existing /bind, /review   -> runner --tickets KEY
                        JSON + pipeline re-run    (QE Assignee only)          (fix-driven UAC)
```

Invariant: **the Inbox never writes to Jira.** Every Jira write stays in the nightly runner, after its
checks. Vision never writes the Acceptance Criteria field either (see `docs/vision_uac_contract.md`).

## What the Inbox shows (all from existing data)

| Card | Source | Action offered |
|---|---|---|
| Open decision (TBD) | `DECISIONS.md`, decision-request comment, `uac_field_parser.has_open_decision` | Answer -> `human_clarifications` JSON -> pipeline re-run -> runner updates the UAC |
| Vision fix arrived | `[Vision] PR created` comment after the UAC was posted (staleness watch already detects it) | "Re-run UAC with fix evidence" -> runner `--tickets KEY`; the skill's fix-driven mode reads the PR diff |
| Vision needs review | `[Vision] Needs review` comment | Link to the PR; optional "UAC still valid" acknowledgement |
| QE edited the UAC | harvester diff (`uac_learning_harvester.py`) | Approve as shared learning -> existing `/feedback/{id}/bind` + `/review` |
| UAC not posted | runner `status.json` (`FAILED`, `CLOSURE_ASKED`, `WRITTEN_UNRENDERED`, `FIELD_KEPT`) | Show the reason; "retry tonight" flag |

## Integration with Vision, by direction

1. **UAC -> Vision (done, PR #213).** Vision reads the Acceptance Criteria field of tickets labelled
   `QEVision_UAC_DONE`. Grammar and states: `docs/vision_uac_contract.md`; parser:
   `scripts/uac_release/uac_field_parser.py`.
2. **Vision -> Inbox (new, read-only).** Parse Vision comments: `[Vision] <state> - <repo> . via Copilot`,
   the bold fields **Outcome**, **PR**, **Fix**, **Root cause**, **Also checked**, and the sign-off
   `- Vision . KEY . <state>`. Derived from Jira on read; storage optional. Vision changes nothing; it only
   has to keep the `[Vision]` prefix.
3. **Inbox -> UAC agent (new, the actual loop).** When QE clicks "Re-run with fix":
   1. The Inbox builds a `root_cause_fix` evidence block from Vision's Root cause and PR link with
      `basis: BOT_INVESTIGATION` (observation evidence, never acceptance authority).
   2. The runner generates a fix-driven UAC for that ticket (`references/root-cause-fix-driven.md`) and posts
      it as a **draft comment**, not into the field.
   3. QE approves: QE edits the field, or the runner replaces it under an explicit flag that only the live QE
      Assignee can trigger.
4. **Inbox -> Vision (optional, later).** If Vision needs a "UAC approved, go verify" signal, the runner adds a
   label (`QEVision_UAC_APPROVED`) on approval. Vision re-reads the same field; no second channel.

## Backend: reuse first

| Need | Reuse | New |
|---|---|---|
| Approve / reject learning | `/test-plan-learning/feedback`, `/bind`, `/review` | none |
| Re-run with human answers | `POST /api/v1/test-plans/pipeline` with `human_clarifications` | none |
| Runner state | `status.json`, `records.jsonl`, release dashboard collectors | `GET /inbox/items` (read-only aggregator) |
| Vision events | staleness-watch detection, `VISION_COMMENT` regex | `GET /inbox/vision/{key}` (parser over Jira comments) |
| Re-run request | runner `--tickets` | `POST /inbox/rerun/{key}` writes a queue file the runner reads; no direct Jira access |
| Auth | existing bearer token + live-QE-Assignee check from shared learning | same check on every write route |

UI: one static HTML page in the style of the evaluation dashboard, served by Nginx at `:4502/inbox`, calling
the routes above. No React/Vite, no build step. The evaluation dashboard stays separate and read-only.

## Guardrails (CLAUDE.md compatible)

- The Inbox is a product change and needs explicit approval. On approval, CLAUDE.md and README.md name it as
  a supported surface next to the dashboard.
- Vision output is observation evidence only; it never becomes an Acceptance Criterion without a human decision.
- Approve / reject only by the ticket's live QE Assignee with a personal named identity; roles, admin status
  and draft ownership grant nothing (same rule as shared learning today).
- No customer-specific logic in the Inbox, the skill or the runtime.
- If the Inbox is down, the nightly runner is unaffected; the re-run queue file is an optional input.
- No credentials in the page; the backend keeps Jira access, the page only calls the backend.

## Phasing

| Phase | Scope | Effort | Demo value |
|---|---|---|---|
| 1 | Read-only inbox page + `GET /inbox/items` + Vision event parser | 2-3 days | "Every pending decision and every Vision fix in one place" |
| 2 | Actions: answer TBD -> re-run; approve learning (existing endpoints); request re-run | 3-4 days | Human-in-the-loop without leaving the browser |
| 3 | Fix-driven draft-as-comment + approve-to-field; `QEVision_UAC_APPROVED` label | 2-3 days | Closed loop with Vision |

## Open questions

1. Start with Phase 1 (read-only, safe) or go straight to Phase 2?
2. Does the Vision team want an "approved" signal? If yes, is the label approach acceptable?
3. Who owns the Inbox page operationally (same VM, same Nginx, same deploy script `setup_vm.py`)?
4. Is the `[Vision]` prefix guaranteed on every Vision comment, including failures and retries?
