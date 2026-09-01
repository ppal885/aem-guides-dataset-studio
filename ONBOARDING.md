# AEM Guides Test-Plan Skill — Team Onboarding & Update

Updated: the `test-plan-generation` Claude skill has new UAC quality gates and
presentation rules. Please re-install from the latest zip.

## Get the zip

Committed to `main` (commit `67515288f`):

- Skill only: `release-artifacts/aem-guides-test-plan-claude-skill.zip`
  - size: 553,384 bytes
  - SHA-256: `710e8b4dbab4bf1aef4e46fd946762283b81b162ba8c8d28519e83cc99eba42b`
- MCP client bundles (skill embedded), also refreshed:
  - `release-artifacts/aem-guides-mcp-client-unix.zip` (macOS / Linux)
  - `release-artifacts/aem-guides-mcp-client-windows.zip` (Windows)

Verify the download (optional):

- macOS/Linux: `shasum -a 256 aem-guides-test-plan-claude-skill.zip`
- Windows (PowerShell): `Get-FileHash .\aem-guides-test-plan-claude-skill.zip -Algorithm SHA256`

## Install

Extract the zip, then copy the skill folder into your Claude Code skills directory and
restart Claude Code.

### macOS / Linux

```bash
unzip aem-guides-test-plan-claude-skill.zip -d aem-skill
mkdir -p ~/.claude/skills
rm -rf ~/.claude/skills/test-plan-generation
cp -R aem-skill/skills/test-plan-generation ~/.claude/skills/test-plan-generation
# legacy alias (optional)
cp -R aem-skill/skills/aem-guides-test-scenario-generator ~/.claude/skills/aem-guides-test-scenario-generator 2>/dev/null || true
```

Sanity check:

```bash
python3 ~/.claude/skills/test-plan-generation/scripts/test_skill_scripts.py
# expect: ALL SELF-TESTS PASSED
```

### Windows (PowerShell)

```powershell
Expand-Archive .\aem-guides-test-plan-claude-skill.zip -DestinationPath .\aem-skill -Force
$dst = "$env:USERPROFILE\.claude\skills\test-plan-generation"
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item .\aem-skill\skills\test-plan-generation $dst -Recurse
```

Sanity check:

```powershell
python "$env:USERPROFILE\.claude\skills\test-plan-generation\scripts\test_skill_scripts.py"
# expect: ALL SELF-TESTS PASSED
```

Restart Claude Code after copying. Then ask Claude to use the `test-plan-generation`
skill for a Jira key or supplied evidence.

## What's new (enforced, non-negotiable)

- ACs are one plain-English line, with no `[Proposed]`/`[Confirmed]` tag in chat or the
  Jira Acceptance Criteria field. The `Needs_Human_Review` label conveys not-yet-accepted
  status.
- Publishing tickets must cover DITA-OT processing on/off and preset in/out-of-scope.
- Value/metadata tickets must cover value provenance beyond the authoring UI, including
  the repository node via CRX/DE (`jcr:content/metadata`), source file, API/import, migration.
- Shared implementation path => other consumers are shared-path regression, not out of scope.
- Performance stays conditional (an Open Question) when a workload is cited but no
  approved SLA exists; no invented thresholds.
- New reasoning gates: temporal/version-aware evidence, evidence-conflict resolver,
  scope applicability, entry-point equivalence, reproduction-dimension matrix,
  acceptance-contract synthesizer, UAC linter, human-feedback delta learner, and a
  FluffyJaws supporting-discovery gate.

## Prerequisites (unchanged)

The zip is the skill only. You still need your Adobe Jira MCP, local clones (`starling`,
`xmleditor`, `guides-ui-tests`, `dxml-it-tests`), and the VM / Dataset-Studio backend for
full evidence and the canonical reasoning runtime. The skill's authoring, gates, and
self-tests run standalone; deep evidence sources are configured separately.

## Verified

Clean-room install (fresh `~/.claude`, no repo checkout): self-tests pass and
`run_gates.py` passes a real plan end-to-end.

Questions: ping the maintainer.
