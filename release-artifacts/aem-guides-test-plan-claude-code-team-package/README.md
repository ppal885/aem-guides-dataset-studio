# AEM Guides Test Plan Generator — Claude Code Team Package

This package is for Adobe team members who want to run the AEM Guides Test Plan Generator from Claude Code without cloning the full Dataset Studio repository.

## What is inside

- `claude-skills/aem-guides-test-scenario-generator/` — Claude skill for senior SDET-style test plans.
- `.claude/commands/guides-test-plan-generator.md` — slash command: `/guides-test-plan-generator DXML-12345`.
- `mcp.remote-vm.example.json` — preferred team setup; connects Claude Code to the VM-hosted MCP/RAG.
- `mcp.local-stdio.example.json` — developer fallback; only for machines that have this repo cloned locally.

## Recommended setup: no repo clone

1. Unzip this package anywhere, for example:

   `%USERPROFILE%\.claude\aem-guides-test-plan-package`

2. Copy the skill folder into Claude Code skills:

   `%USERPROFILE%\.claude\skills\aem-guides-test-scenario-generator`

3. Copy the slash command file into Claude commands:

   `%USERPROFILE%\.claude\commands\guides-test-plan-generator.md`

4. Add the MCP config from `mcp.remote-vm.example.json` to your Claude Code MCP config.

5. Restart Claude Code.

6. Run:

   `/guides-test-plan-generator DXML-12345`

## VM MCP requirement

The VM must expose the Dataset Studio MCP endpoint through the public nginx port:

`http://10.42.46.78:4502/mcp`

If this endpoint is not exposed yet, the remote setup will not work. In that case add the nginx `/mcp` proxy to `http://127.0.0.1:8001/mcp`, or use the local stdio setup on a machine where the repo exists.

## Expected behavior

The generated test plan should include ticket analysis, evidence table, UACs, blast radius, bug hypothesis register, kill-the-fix analysis when a diff exists, regression packs, automation strength, residual risk, confidence, and QE review status.

## Repo evidence behavior

Local repo clones are optional. If repos are unavailable, the plan should not fail. It should mark repo evidence as missing/partial and lower the confidence status to `Draft` or `QE_REVIEW_WITH_FLAGS`.

## Security

Do not put Jira passwords, PATs, AEM passwords, or bearer tokens into Git. If the token changes, update only the local Claude Code MCP config.
