# Prompt: make the posted UAC a reliable input for the Vision agent

Copy everything below the line into a fresh Claude Code / Codex thread on this repository.

---

Repo: `ppal885/aem-guides-dataset-studio` (AEM Guides UAC/test-plan generator). Read `CLAUDE.md` and `AGENTS.md` first.

## Goal

Make the UAC our nightly agent posts to Jira a reliable, documented input for a separate "Vision" agent. Vision will NOT call our API. It reads the Jira Acceptance Criteria field directly and needs only the AC text. Our job is the producer side: guarantee the field format, document the contract, add parsing tests, and make sure no feedback loop forms between Vision's Jira comments and our UAC generation.

## What Vision looks like in Jira (observed, 2026-10)

Vision posts Jira comments from a **human account** ("via Copilot"), not from a bot account. Each comment:

- Starts with `[Vision] <state> — <repo> · via Copilot`, e.g. `[Vision] Needs review — xmleditor · via Copilot`, `[Vision] Checked PR for feedback — xmleditor #8516 · via Copilot`, `[Vision] PR created — xmleditor · via Copilot`.
- Has bold labelled fields: **Outcome**, **PR** (`xmleditor #8516` + corp Git URL), **Fix**, **Root cause**, **Also checked**.
- Ends with a sign-off line: `— Vision · GUIDES-57258 · <state>` (states seen: `Needs review`, `review feedback`).
- One ticket can carry several Vision comments over days (PR created → review feedback → needs review).

Implication: the author account cannot be used to detect Vision; the `[Vision]` prefix and the sign-off line can.

## Current state (verify, don't assume)

- Nightly runner: `scripts/uac_release/uac_release_runner.py`; cron in `scripts/uac_release/uac-release.cron`; config schema in `scripts/uac_release/config.example.json`; docs in `scripts/uac_release/README.md`.
- Runner writes the UAC into the Jira Acceptance Criteria field (config `acceptance_criteria_field`, e.g. `customfield_13400`), reads it back to confirm it rendered, attaches `test-plan.md`, posts a review-notes comment, and adds label `labels.posted` (`QEVision_UAC_DONE`). A field that already holds text is never overwritten. `regenerate_existing` defaults to `false`.
- UAC field format produced by the skill prompt (see the prompt text in `uac_release_runner.py` around "When finished, write these files"):

  ```
  - Acceptance Criteria NN: <criterion>
      **Source:** <...>
      **TBD:** <...>?        (only when a decision is open)
  ```

  Optional first line when the fix is unmerged: `Note: A fix is proposed in a linked pull request but is not merged...`
  Runner parses ACs with regex `^- Acceptance Criteria (\d+):` in several places in `uac_release_runner.py`.
- Vision comments are already meant to be treated as bot notices: `_BOT_COMMENT = re.compile(r"^(?:h\d )?vision\b")`, matched on `_words()` output, which strips markup, URLs and punctuation (so `[Vision] Needs review` becomes `vision needs review` and matches). Bot comments are excluded from closure detection and requirement mapping. Verify this with a test using the real comment shapes above.
- Staleness watch (`scripts/uac_release/uac_staleness_watch.py`) alerts QE when a root cause/fix/PR arrives after a UAC was posted; it never edits tickets. Vision's "PR created" comments are exactly such a signal; check whether they are detected and whether an alert is wanted when the PR comes from Vision.
- Learning harvester (`scripts/uac_release/uac_learning_harvester.py`) diffs QE edits to posted UACs every 30 minutes.

## Deliverables

1. `docs/vision_uac_contract.md`, the consumer contract for the Vision team:
   - JQL to find consumable tickets: `labels = QEVision_UAC_DONE AND "Acceptance Criteria" is not EMPTY` (confirm label name from config).
   - Exact field grammar with a regex Vision can use, how to extract AC text only (skip `Source:`/`TBD:` lines and the proposed-fix `Note:` line), numbering rules (1–10), and the meaning of `TBD` (decision pending, not a confirmed requirement).
   - States Vision must handle: `UAC_Not_Required` label (no UAC will come); text present but no posted label (`WRITTEN_UNRENDERED` or hand-written); QE edits after posting (always read the latest field, check the updated timestamp); ticket re-run by QE.
   - Loop-prevention rule: Vision comments must keep the `[Vision]` prefix so our runner ignores them; our runner never treats Vision output as acceptance authority. Vision's Root cause / Fix fields may later be used as *observation* evidence only, never as an AC source without human confirmation.
   - What Vision must NOT do: write to the Acceptance Criteria field, add/remove our labels.
2. A small shared parser `scripts/uac_release/uac_field_parser.py` exposing `parse_acceptance_criteria(text) -> list[{number, text, source, tbd}]` and `ac_texts_only(text) -> list[str]`. Refactor `uac_release_runner.py` to use it where it currently repeats the regex (3+ places). Behaviour must not change; keep the existing regex semantics including the lookahead for `Suggested checks` / `Out of scope`.
3. Tests in `scripts/uac_release/test_uac_release.py` (or a new file next to it) covering: normal UAC; UAC with `TBD` lines; UAC with the proposed-fix `Note:` line; QE-edited UAC with an added criterion; Jira wiki-rendered variants (bold label `Acceptance Criteria 1:` vs `01:`); a field with no ACs. Also tests that each of the three observed Vision comment shapes (`[Vision] Needs review — ...`, `[Vision] Checked PR for feedback — ...`, `[Vision] PR created — ...`) is classified as bot by the existing `_BOT_COMMENT` regex after `_words()`, and that a normal human comment is not.
4. Update `scripts/uac_release/README.md` with a short "Downstream consumers (Vision)" section linking to the contract.
5. Optional, only if cheap: when the runner posts a UAC, also attach `UAC.json` (structured ACs from the parser) to the ticket, behind a config flag `attach_uac_json` (default `false`). Posting must not fail if this step fails.

## Constraints

- Do not change the UAC wording rules, the skill (`.codex/skills/test-plan-generation/`), the Jira write policy, or production behaviour. No new Jira writes except the optional flagged attachment.
- Keep Jira/customer-specific rules out of the skill and runtime. No hardcoded ticket keys outside tests/eval fixtures (the GUIDES-57258 example above belongs only in tests or this doc).
- Never log or hardcode Jira credentials or tokens; config stays in `/opt/uac-release/uac.env`.
- Preserve user changes in a dirty worktree; stage only your files, never `git add -A`.
- Run `python scripts/uac_release/test_uac_release.py` and `python .codex/skills/test-plan-generation/scripts/audit_production_hardcoding.py` before finishing.

## Output

Branch + commit with a clear message. Summarise: files changed, the final regex, test results, and any open question for the Vision team (for example whether the `[Vision]` prefix is guaranteed, and whether they want `UAC.json`).
