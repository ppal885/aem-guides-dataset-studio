# UAC release automation (GitHub Copilot CLI)

Generates draft UACs for every ticket in a release, posts them to Jira for QE review, and
copies each draft into the **Acceptance Criteria** field once QE approves it.

```
nightly (runner)                                   every 30 min (poster)
JQL -> copilot -p per ticket -> checks -> draft     label UAC_Approved -> AC field -> UAC_Posted
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
| `UAC_Rework` | QE wants changes (leave a comment); remove `UAC_Posted`/set `regenerate_existing` to redo | QE |
| `UAC_Posted` | Draft copied into the Acceptance Criteria field | poster |

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
6. **Config**: copy `config.example.json` to e.g. `/opt/uac-release/config.2701.json` and set:
   - `jql`: which tickets need a UAC. Example for your own release tickets:
     `project = GUIDES AND fixVersion = "2701" AND "QE Assignee" = currentUser() AND "Acceptance Criteria" is EMPTY AND labels != UAC_Posted`
   - `approved_scope_jql`: the same release scope, without the label filters.
   - `output_dir`, `add_dirs`, `mcp_health_url`.
7. **Check the Copilot flags on your version** with `copilot --help` (the scripts use `-p`, `-s`,
   `--no-ask-user`, `--share`, `--add-dir`, `--allow-all-tools`, `--allow-tool`, `--deny-tool`),
   and confirm that `--deny-tool` wins over `--allow-all-tools`: run one ticket with `--dry-run`
   and check `copilot-transcript.md` shows no Jira write.

## Run it

```
# First time: one ticket, nothing written to Jira
python scripts/uac_release/uac_release_runner.py --config /opt/uac-release/config.2701.json --env-file /opt/uac-release/uac.env --ticket GUIDES-12345 --dry-run

# Whole release
python scripts/uac_release/uac_release_runner.py --config /opt/uac-release/config.2701.json --env-file /opt/uac-release/uac.env

# Post approved drafts
python scripts/uac_release/uac_approved_poster.py --config /opt/uac-release/config.2701.json --env-file /opt/uac-release/uac.env
```

Schedule: `uac-release.cron` (Linux) or `register_windows_tasks.ps1` (Windows).

## What the runner checks before posting a draft

- Jira login works, the Dataset Studio MCP health URL answers, and `copilot` is on PATH.
  If any fails the run stops, so a UAC is never written without product documentation.
- Copilot exited 0 and wrote both `UAC.md` and `test-plan.md`.
- `test-plan.md` passes `validate_test_plan.py`.
- `UAC.md` has 1-10 Acceptance Criteria and no blocked vocabulary.

Anything else is marked `FAILED` in `<output_dir>/<KEY>/status.json` and nothing is posted.

## Files per ticket (`<output_dir>/<KEY>/`)

`UAC.md`, `test-plan.md`, `field-body.txt` (exact text the poster will write),
`copilot-transcript.md`, `copilot-output.txt`, `status.json`. Logs are in `<output_dir>/logs/`.

## Tests

`python -m unittest scripts/uac_release/test_uac_release.py` (offline: fake Jira, stubbed Copilot).
