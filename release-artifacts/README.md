# Release Artifacts

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
