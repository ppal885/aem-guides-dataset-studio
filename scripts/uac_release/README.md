# UAC release automation (GitHub Copilot CLI)

Generates draft UACs for every ticket in a release, posts them to Jira for QE review, and
copies each draft into the **Acceptance Criteria** field once QE approves it.

```
nightly (runner)                                   every 30 min (poster)
JQL -> copilot -p per ticket -> checks -> draft     label UAC_Approved -> AC field -> QEVision_UAC_DONE
             (UAC.md + test-plan.md)      comment + attachment + UAC_Draft
```

Copilot CLI only **generates**. It is denied every Jira write tool; all Jira writes are done
by these scripts, after the checks. The Acceptance Criteria field is written only after a QE
adds the `UAC_Approved` label, and a field that already holds other text is never overwritten.

## Ticket flow

| Label on the ticket | Meaning | Who sets it |
|---|---|---|
| `UAC_Draft` | Draft comment + full test plan attached, waiting for QE | runner |
| `UAC_Approved` | QE accepts the draft as written | QE |
| `QEVision_UAC_DONE` | Draft copied into the Acceptance Criteria field | poster |

## Every place the feature appears is covered

Copilot also writes `SURFACE_INVENTORY.json`: every place in the product where the feature
appears or where its items open. It is found in the documentation AND by searching the code for
every reuse of each widget, panel, component, service or API the change touches. Each entry has
the on-screen name, its evidence (a documentation URL or a `<file>:<line>` code reference) and
`AC`, `TBD` or `OUT_OF_SCOPE`. The runner marks the ticket `FAILED` when:
- the file is missing, empty, or not a JSON list;
- an entry has no evidence, or evidence that is neither a URL nor `<file>:<line>`;
- the inventory has no documentation URL at all, or no code reference at all;
- an `AC` entry points at an Acceptance Criterion whose text does not name the surface, a `TBD`
  points at one with no TBD line, or `OUT_OF_SCOPE` has no concrete reason.

A shared widget changes every screen that embeds it, so each of those screens must be named in
an Acceptance Criterion or a TBD.

Each entry also records its `authority`: `TICKET`, `ATTACHMENT`, `PRODUCT_DECISION`,
`DOCUMENTATION` or `CODE_REUSE`. A surface found only in documentation or code may get an AC
only when that AC checks the screen still works as before; asking for new behaviour there needs a
TBD. Every attachment entry in `SOURCE_COVERAGE.json` lists the screens it shows in `surfaces`,
and each of those screens must be in the surface inventory.

## Every Acceptance Criterion is asked for

The runner also adds a review note to the draft (it does not fail the ticket) when an Acceptance
Criterion is not driven by anything: it should be
the target of a ticket sentence or attachment in `SOURCE_COVERAGE.json` (one sentence may list
several criteria, e.g. `"ac": [1, 4, 5]`), name a surface the ticket, an attachment or a product
decision asks for, be a still-works check on an inventoried surface, or carry a TBD for the product
owner. A criterion whose only source is `QE reasoning` gets a note too. These stay notes because good
UACs often carry QE-judgment criteria (a quarter of human UAC requirements in the benchmark
validation split had no explicit ticket source); the reviewer decides.

Rules only run when the runner generates a UAC. After editing a UAC by hand, check the folder again
before posting (it must also contain `jira-source.json`):

```
python3 scripts/uac_release/uac_release_runner.py --check-dir /opt/uac-release/runs/GUIDES-12345 --own-name <jira user>
```

## Every line of the ticket is mapped

Before writing the UAC, Copilot writes `SOURCE_COVERAGE.json`: one entry for every sentence and
bullet of the Jira description, every sentence of every comment, and every attachment, each
marked `AC`, `TBD`, `OUT_OF_SCOPE` or `NOT_MATERIAL` (with the Acceptance Criteria number, or a
reason). The runner reads the live ticket itself (saved as `jira-source.json`), splits it into
sentences, and marks the ticket `FAILED` when:
- `SOURCE_COVERAGE.json` is missing or is not a JSON list;
- any description or comment sentence (4 words or more) is not in the map;
- an attachment is not in the map;
- an entry points at an Acceptance Criterion that does not exist, a `TBD` points at one with no
  TBD line, or `OUT_OF_SCOPE` / `NOT_MATERIAL` has no concrete reason;
- the ticket cannot be read from Jira (the check fails closed).

Comments and attachments posted by the automation's own Jira account are skipped. Text inside
`{code}` and `{noformat}` blocks is not split into sentences.

## UAC Doc Researcher is required

Every ticket must run the UAC Doc Researcher (`uac-doc-researcher` agent). Copilot writes its
JSON result to `DOC_RESEARCH.json` next to `UAC.md`. The runner marks the ticket `FAILED` and
posts nothing when:
- `DOC_RESEARCH.json` is missing, is not valid JSON, or has a status other than
  `ANSWER_FOUND`, `PARTIAL`, `NOT_FOUND`, `SOURCE_UNAVAILABLE` or `CONFLICTED`;
- `ANSWER_FOUND` or `PARTIAL` has no findings, or `NOT_FOUND` / `SOURCE_UNAVAILABLE` has no
  limitations naming what was searched;
- a finding cites a `doc:` source without a provenance locator (the page URL);
- `copilot-transcript.md` never mentions `uac-doc-researcher` apart from the prompt itself.

`ask_dita_expert` answers do not replace this step.

## Decision requests for open TBDs

When a UAC has TBDs, Copilot also writes `DECISIONS.md`. It has three sections:
- **What we found:** verified facts, each with its source.
- **Decision needed:** one question per TBD.
- **Impact on the Acceptance Criteria.**

The runner shows this request at the end of the draft comment, so QE reviews the exact text.

After QE adds `UAC_Approved` and the criteria are posted, the poster sends the request once, as its own comment. It tags the people named in `decision_comment`:
- `mention` is a list of issue roles (`assignee`, `reporter`).
- `cc` is a list of Jira usernames.

The request is not sent in these cases:
- `decision_comment.enabled` is false;
- the UAC has no TBD;
- `DECISIONS.md` is missing a section;
- `DECISIONS.md` changed after the draft.

A missing request is logged as a warning in `status.json` and never blocks the AC post.

## One-time VM setup

1. **Clones** (already done): Dataset Studio plus the product and automation repos listed in
   `copilot.add_dirs`.
2. **Copilot CLI**: `npm install -g @github/copilot`. For unattended runs set
   `COPILOT_GITHUB_TOKEN` to a token of an account with a Copilot seat.
3. **Skill and researcher agents** for Copilot:
   `python .claude/skills/test-plan-generation/scripts/sync_agent_registrations.py`
   (writes `.github/agents/*.agent.md`). Without them research does not run.
4. **MCP servers** in Copilot: add the Jira MCP and the Dataset Studio MCP
   (`copilot mcp add --transport http aem-guides-dataset-studio http://<vm>:4502/mcp`).
   The names you use must match the `deny_tools` entries in the config.
5. **Env file** (e.g. `/opt/uac-release/uac.env`, `chmod 600`):
   ```
   JIRA_BASE_URL=https://jira.corp.adobe.com
   JIRA_PAT=<Jira personal access token>
   COPILOT_GITHUB_TOKEN=<GitHub token with Copilot access>
   ```
   Use a Jira account that can only comment, attach and edit fields on these tickets.
6. **Config**: copy `config.example.json` to e.g. `/opt/uac-release/config.json` and set:
   - `jql`: which tickets need a UAC. The example picks open Customer Request tickets with
     fix version `2701` in the current sprint (`sprint in openSprints()`), whoever the QE is,
     and the Acceptance Criteria field is still empty. Change `2701` for each release. Keep
     `resolution = Unresolved` so closed tickets are skipped. Keep `(labels is EMPTY OR labels != QEVision_UAC_DONE)`:
     plain `labels != X` in JQL also drops tickets that have no labels at all.
   - `tickets`: optional exact list, e.g. `["GUIDES-12345", "GUIDES-23456"]`. When it is not
     empty it is used instead of `jql` (useful before the fix version or sprint is set).
   - `max_tickets`: the most tickets one nightly run takes from `jql` (default 100). Tickets
     left over are picked up the next night.
   - `approved_scope_jql`: the same fix version and issue type, without the sprint or other filters,
     so an approved ticket is still posted after the sprint ends.
   - `output_dir`, `add_dirs`, `mcp_health_url`.
7. **Check the Copilot flags on your version** with `copilot --help` (the scripts use `-p`, `-s`,
   `--no-ask-user`, `--share`, `--add-dir`, `--allow-all-tools`, `--allow-tool`, `--deny-tool`),
   and confirm that `--deny-tool` wins over `--allow-all-tools`: run one ticket with `--dry-run`
   and check `copilot-transcript.md` shows no Jira write.

## VM commands (Linux; run once, in this order)

Paths below assume clones under `/opt/repos` and state under `/opt/uac-release`; change them to yours.

```bash
# 1. Copilot CLI (needs Node.js 22 or newer from your approved source)
node --version
npm install -g @github/copilot
copilot --version
copilot --help            # confirm -p, -s, --no-ask-user, --share, --add-dir, --allow-all-tools, --deny-tool

# 2. Code: the automation branch of Dataset Studio
cd /opt/repos/aem-guides-dataset-studio
git fetch origin
git checkout uac-release-automation     # after the PRs merge: git checkout main && git pull

# 3. Researcher agents for Copilot (.github/agents/*.agent.md)
python3 .claude/skills/test-plan-generation/scripts/sync_agent_registrations.py

# 4. MCP servers for Copilot (names must match deny_tools in the config)
#    Jira MCP: the same corp-jira server you use today, built on the VM (node dist/index.js)
copilot mcp add corp-jira --env JIRA_API_BASE_URL=https://jira.corp.adobe.com --env JIRA_PERSONAL_ACCESS_TOKEN=<jira-pat> -- node /opt/repos/adobe-mcp-servers/src/corp-jira/dist/index.js
#    Dataset Studio MCP (ask_dita_expert): must answer before anything else works
curl -sf http://10.42.46.78:4502/mcp/health
copilot mcp add --transport http --header "Authorization: Bearer <studio-token>" aem-guides-dataset-studio http://10.42.46.78:4502/mcp
copilot mcp list

# 5. Secrets and config (keep the env file private)
sudo mkdir -p /opt/uac-release && sudo chown "$USER" /opt/uac-release
printf 'JIRA_BASE_URL=https://jira.corp.adobe.com\nJIRA_PAT=<jira-pat>\nCOPILOT_GITHUB_TOKEN=<github-token-with-copilot>\n' > /opt/uac-release/uac.env
chmod 600 /opt/uac-release/uac.env
cp scripts/uac_release/config.example.json /opt/uac-release/config.json
nano /opt/uac-release/config.json   # set add_dirs, mcp_health_url; optionally "tickets": [...]

# 6. Check everything offline, then one real ticket without writing to Jira
python3 -m unittest scripts/uac_release/test_uac_release.py
python3 scripts/uac_release/uac_release_runner.py --config /opt/uac-release/config.json --env-file /opt/uac-release/uac.env --ticket GUIDES-12345 --dry-run
cat /opt/uac-release/runs/GUIDES-12345/status.json
grep -iE "update_jira_issue|add_jira_comment|upload_attachment" /opt/uac-release/runs/GUIDES-12345/copilot-transcript.md   # must print nothing

# 7. Schedule it
crontab -e        # paste the two lines from scripts/uac_release/uac-release.cron (fix REPO/CONFIG)
crontab -l
```

Windows VM: same steps in PowerShell, then register the tasks once (elevated):
`.\scripts\uac_release\register_windows_tasks.ps1 -Repo C:\repos\aem-guides-dataset-studio -Config C:\uac-release\config.json -EnvFile C:\uac-release\uac.env`

Daily use: nothing to run. Review each `UAC_Draft` comment in Jira and add `UAC_Approved`. To change
the criteria, edit the Acceptance Criteria field after it is posted; no label is needed. The draft
comment lists *Suggested checks (QE decide)* below the criteria: checks found only by our own research
(documentation, code, a similar ticket). They are never copied into the field; add the ones you want to
the field after approving, and the monthly report counts them as promoted. When the root cause is not
confirmed yet, the UAC starts with a note saying so. Logs: `/opt/uac-release/runs/logs/` and `/opt/uac-release/cron.log`.

## Run it

```
# First time: one ticket, nothing written to Jira
python scripts/uac_release/uac_release_runner.py --config /opt/uac-release/config.json --env-file /opt/uac-release/uac.env --ticket GUIDES-12345 --dry-run

# Whole release
python scripts/uac_release/uac_release_runner.py --config /opt/uac-release/config.json --env-file /opt/uac-release/uac.env

# Post approved drafts
python scripts/uac_release/uac_approved_poster.py --config /opt/uac-release/config.json --env-file /opt/uac-release/uac.env
```

Schedule: `uac-release.cron` (Linux) or `register_windows_tasks.ps1` (Windows).

## What the runner checks before posting a draft

- Jira login works, the Dataset Studio MCP health URL answers, and `copilot` is on PATH.
  If any fails the run stops, so a UAC is never written without product documentation.
- Copilot exited 0 and wrote both `UAC.md` and `test-plan.md`.
- `test-plan.md` passes `validate_test_plan.py`.
- `UAC.md` has 1-10 Acceptance Criteria and no blocked vocabulary.

Anything else is marked `FAILED` in `<output_dir>/<KEY>/status.json` and nothing is posted.

## Evidence record

Every ticket also needs `UAC_EVIDENCE.json`, checked with the skill script `uac_completeness_check.py`:
the evidence preflight (product RAG, Jira history, live Jira, clones), at least three `ask_dita_expert`
probes, at least two narrow Jira history searches, and one disposition for every documentation finding of
the UAC Doc Researcher (used in the named Acceptance Criteria, whose Source line names the documentation,
or set aside with a reason). A tool missing from the Copilot session is not an unavailable source: the
skill script `vm_evidence_call.py` calls the backend at `$AEM_STUDIO_URL/mcp`, so set `AEM_STUDIO_URL` in
`uac.env`. `--check-dir` runs the same check, so run it again after editing a UAC by hand.

## Learning from QE edits

`uac_learning_harvester.py` (cron 02:30 nightly) reads every ticket this automation posted to the
Acceptance Criteria field (`status.json` state `POSTED`, exact text in `field-body.txt`). It compares
the posted criteria with the current field, one criterion at a time: **accepted** (unchanged),
**removed** (QE deleted it), **added** (QE wrote one we did not have) or **changed** (wording or
expected result edited). A criterion QE struck through in Jira (`-text-` or `{-}text{-}`) counts
as **removed**, and the text QE left unstruck next to it (usually a note in brackets) is kept as the
reason; a partly struck criterion counts as changed with the struck part and reason. Criteria are found
by `Acceptance Criteria NN:` or `AC-NN:` labels (also after a bullet) or by top-level bullets; a plain
note after a blank line belongs to no criterion, and an `Open Questions` heading or an `OQ-NN` line starts
a questions section that is not part of any criterion until the next label. Only a human's edit counts; edits by the automation's
own Jira user are ignored. An untouched field counts as accepted only once the ticket status is in
`learning_accepted_statuses` (default `UAT`, `Closed`, `Resolved`, `Done`). Each new ticket version is
appended once to `<output_dir>/learning/records.jsonl` with the posted text, the new text, who changed
it and when.

`uac_learning_harvester.py --report last` (cron 06:00 on the 1st) writes
`<output_dir>/learning/report-YYYY-MM.md`: an overall line, then per component the counts, what QE
removed (we wrote too much), what QE added (we missed), and the **missed screens**: screens (panel,
console, dashboard, app, view, ...) that a QE-added criterion names and our posted UAC never mentioned,
counted once per ticket. A screen miss that recurs in these counts is the signal to change the surface
rules; one ticket is not. A **Removed by kind** table says why each posted criterion was written - reporter
step, regression check, entry point, switch state, item type, reverse action, item history, value forms,
items made before the change, failure path, read from the run's `UAC_EVIDENCE.json` - and how often QE
removed each kind, plus the median number of criteria we posted against the median QE left. A kind QE
removes often is the signal to change the size or variant rules. The harvester only reads Jira; it never
writes to it.

### Backfill hand-posted UACs

A UAC posted by hand (not by this automation) has no `field-body.txt`, so the nightly harvest skips it.
Backfill it from the Jira history, read-only:

```
python3 scripts/uac_release/uac_learning_harvester.py --config /opt/uac-release/config.json --env-file /opt/uac-release/uac.env --backfill GUIDES-12345 GUIDES-23456 --generator-user <jira user who posted the UAC> --dry-run
```

The last Acceptance Criteria change by a generator user (the automation's Jira user, the users in
`learning_generator_users`, and every `--generator-user`) is the posted version; changes after it by
anyone else are QE's edits. Drop `--dry-run` to append the records. A ticket where the last write is
still the generator's and the status has not reached an accepted status has nothing to learn yet.

## Stale UAC alert

`uac_staleness_watch.py` (cron 07:30 Mon-Fri) checks tickets that carry the posted label and were updated
in the last `staleness_days` days (default 7; or set `staleness_jql`). When a human comment reporting a
root cause, a fix, a pull request or a merge was added after the Acceptance Criteria field last changed,
it sends one alert on `alerts.ticket` listing the ticket. Each comment is alerted once
(`<output_dir>/staleness-state.json`). It never comments on or edits the ticket or its UAC; QE decides
whether to re-run the UAC. `--dry-run` only logs.

## Hotfix and backport scope

When the ticket summary or description says it is a hotfix or a backport (for example `HOTFIX`,
`backport`, `release-hotfix-5.2.2`), Copilot must also write `HOTFIX_SCOPE.json`, and the runner checks
it with the skill script `hotfix_scope_check.py`. Every Acceptance Criterion must rest on a line of the
hotfix ticket itself, or on lines the hotfix diff actually adds or changes (read with
`git diff -U0 <base>...<hotfix>` in the clone named in the file). A generic "No regression should be
introduced" line scopes nothing by itself, and a criterion that rests only on the parent (mainline)
ticket or on behaviour the hotfix does not change fails unless it carries a TBD. The clones named in
the file must exist on the VM.

## Files per ticket (`<output_dir>/<KEY>/`)

`UAC.md`, `test-plan.md`, `field-body.txt` (exact text the poster will write),
`copilot-transcript.md`, `copilot-output.txt`, `status.json`. Logs are in `<output_dir>/logs/`.

A re-run first moves the previous `copilot-transcript.md` and `copilot-output.txt`, and a copy of
`status.json`, into `attempts/<time>/`. The newest `keep_attempts` (default 5) are kept.

## Logs, run history and alerts

- `<output_dir>/logs/uac-runner-YYYYMMDD.log` and `uac-poster-YYYYMMDD.log`: one file per day,
  including the traceback of any error. Files older than `log_retention_days` (default 30; 0 keeps
  everything) are deleted at the start of each run.
- `<output_dir>/runs.jsonl`: one JSON line per run with `run_id`, `tool`, `started`, `seconds`,
  `exit_code`, the result of every ticket, errors, health problems and the alert lines.
  `tail -n 5 /opt/uac-release/runs/runs.jsonl` shows the last runs.
- One ticket failing with an unexpected error (for example Jira returning 500) never stops the
  other tickets. That ticket gets result `ERROR`, and `status.json` gets `last_error`. A ticket
  whose draft was already posted keeps its state, so the poster retries it on its next run.
- Exit codes: 0 all good, 1 a ticket failed, 2 health check failed (runner), 3 the run stopped.
- `<output_dir>/logs/gate-firing.jsonl`: one JSON line per ticket the runner checked, with the number
  of problems each check found (`outputs`, `doc_research`, `surface_inventory`, `evidence.<check>`,
  `source_coverage`, `attachment_surfaces`, `hotfix_scope`, and the advisory review notes). It is
  never pruned. The monthly learning report adds a "Runner checks this month" table from it; for any
  period run `python .claude/skills/test-plan-generation/scripts/gate_firing_log.py report
  /opt/uac-release/runs/logs/gate-firing.jsonl --since 2026-10-01`. A check that fires on nearly
  every ticket, or never, is a candidate to review - read what it caught before changing it.

Alerts: when something needs attention, the script posts one Jira comment on `alerts.ticket`,
mentioning the users in `alerts.mention` (Jira user names). It is sent for a failed health check,
a run that stopped, a ticket with `ERROR`, a runner ticket that was not drafted (`FAILED`), and an
approved ticket the poster could not post. The same alert is not repeated within
`alerts.repeat_hours` (default 24), so the 30-minute poster does not flood the ticket; once a run
is clean, the next problem alerts again at once. `--dry-run` never sends an alert; it only logs it.
With no `alerts.ticket`, the alert is only logged. If Jira itself is down, the alert cannot be
posted; that failure is in the daily log.

`cron.log` only receives what the scripts print. Rotate it with logrotate:

```
# /etc/logrotate.d/uac-release
/opt/uac-release/cron.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

## Tests

`python -m unittest scripts/uac_release/test_uac_release.py` (offline: fake Jira, stubbed Copilot).
