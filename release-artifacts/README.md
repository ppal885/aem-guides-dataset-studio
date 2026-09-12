# Release Artifacts

## AEM Guides MCP client and test-plan skill

Team packages version `2026.08.13`:

- `aem-guides-mcp-client-windows.zip`
- `aem-guides-mcp-client-unix.zip`

Each archive installs the minimal central-VM MCP client and the synchronized
`test-plan-generation` skill. The compact UI shows a Jira Understanding card
and exactly five sections while retaining the complete eleven-section Markdown
artifact. Rebuild both deterministic archives with:

```bash
python scripts/package_mcp_client_bundles.py
```

### Test-plan skill parity

The independent `CI / test-plan-skill-parity` job runs the existing recursive
checker before installing any test dependencies:

```bash
python scripts/check_test_plan_evidence_graph_parity.py
python -m pytest --noconftest backend/tests/test_test_plan_evidence_graph_parity.py -q
```

The focused tests require only pytest; `--noconftest` avoids loading the backend
application, database, and service fixtures. A failure is not suppressed or
dependent on the backend/security or application-lint jobs.

| Location | Contract |
|---|---|
| `.codex/skills/test-plan-generation/` | Source used by the existing sync and parity scripts. |
| `.claude/skills/test-plan-generation/` | Full recursive byte match with the Codex source. |
| `skills/test-plan-generation/` | Full recursive byte match with the Codex source. |
| `release-artifacts/aem-guides-mcp-client-{unix,windows}/.claude/skills/test-plan-generation/` | Both unpacked package skill trees fully match the Codex source. |

At `cb55d104`, each tree contains the same 198 files: `SKILL.md`,
`CONTRIBUTING.md`, `agents/openai.yaml`, two analysis files, four data files,
70 references, and 119 files under `scripts/`. New paths are checked automatically;
missing, extra, and changed files fail. Only `__pycache__`, `.DS_Store`, and
`.pyc` files are ignored by the existing checker. There are **no per-client file
exceptions within these repository skill trees**. The older `CONTRIBUTING.md`
description of four copies, a `skills/` sync source, limited file enforcement,
and `codex_only_extensions` is superseded by the current scripts and this scope.

Client and platform setup files outside the skill roots have separate contracts:
Claude slash commands do not need matching Codex command files; `.codex/config.toml`
is Codex-specific; Unix `.sh` installers and Windows `.cmd`/`.ps1` installers and
their setup instructions differ by platform. The parity check does not compare
these wrappers or user-installed `~/.claude` / `~/.codex` copies.

For a deliberate common rule/reference change, review it in the Codex source,
then run from the repository root:

```bash
python scripts/sync_test_plan_skill_copies.py
python scripts/check_test_plan_evidence_graph_parity.py
python scripts/package_mcp_client_bundles.py
```

The sync script copies files without pruning removed paths. For a deliberate
deletion, remove that same path from each mirror; the checker reports leftover
files. Do not auto-sync inside CI, because that would conceal an incomplete commit.

ZIP archives are a separate packaging boundary: this job checks the unpacked
Windows/Unix package sources, not ZIP payloads or older standalone/dated archives.
Rebuild the two current MCP client ZIPs after changing their source files. At
`cb55d104`, both MCP ZIP skill payloads match source after CRLF/LF normalization;
68 files in each ZIP have line-ending-only byte differences. No skill or archive
payload changes are needed to enable this CI check.

## AEM Guides test-plan Claude skill

Download:

- `aem-guides-test-plan-claude-skill.zip`

Use this ZIP when team members should run `/guides-test-plan-generator GUIDES-12345`
without cloning the full VM repository. The package contains the Claude skill, slash
command, install scripts, and setup README. The actual RAG/Jira/code evidence still comes
from the central VM MCP backend.

## VM Jira RAG repair

If new Jira issues are not appearing in test-plan evidence, run from the VM repo root:

```bash
backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --check
backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --issue GUIDES-12345 --force
backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --recent-days 7 --limit 300 --force
```

The script loads `.env.docker`, uses the backend venv, checks Jira/Chroma/embedding readiness,
and indexes Jira directly without relying on curl auth headers.
