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
| `UAC_Rework` | QE wants changes (leave a comment); remove `QEVision_UAC_DONE`/set `regenerate_existing` to redo | QE |
| `QEVision_UAC_DONE` | Draft copied into the Acceptance Criteria field | poster |

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
     fix version `2701` where you are QE Assignee (`currentUser()` is the owner of `JIRA_PAT`)
     and the Acceptance Criteria field is still empty. Change `2701` for each release. Keep
     `resolution = Unresolved` so closed tickets are skipped. Keep `(labels is EMPTY OR labels != QEVision_UAC_DONE)`:
     plain `labels != X` in JQL also drops tickets that have no labels at all.
   - `tickets`: optional exact list, e.g. `["GUIDES-12345", "GUIDES-23456"]`. When it is not
     empty it is used instead of `jql` (useful before the fix version or QE Assignee is set).
   - `approved_scope_jql`: the same fix version, issue type and QE Assignee scope, without the other filters.
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

Daily use: nothing to run. Review each `UAC_Draft` comment in Jira and add `UAC_Approved` (or
`UAC_Rework` with a comment). Logs: `/opt/uac-release/runs/logs/` and `/opt/uac-release/cron.log`.

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

## Files per ticket (`<output_dir>/<KEY>/`)

`UAC.md`, `test-plan.md`, `field-body.txt` (exact text the poster will write),
`copilot-transcript.md`, `copilot-output.txt`, `status.json`. Logs are in `<output_dir>/logs/`.

## Tests

`python -m unittest scripts/uac_release/test_uac_release.py` (offline: fake Jira, stubbed Copilot).
