# AEM Guides UAC generator — Claude Desktop context

## Purpose

Use this repository to generate evidence-backed AEM Guides UACs and QE test plans. Claude Desktop is the reasoning client; the Python backend is the deterministic controller and gate runtime. The only browser interface is a read-only evaluation dashboard.

## Required runtime roles

- `test-plan-generation` skill — workflow, evidence discipline, plain-language output, and quality gates
- Python backend — canonical Jira intake, evidence routing, hypotheses, verification, disposition, and rendering
- Pattern MCP — Human-backed investigation patterns, never automatic acceptance truth
- GitHub/repository evidence — implementation and blast-radius truth
- DITA/DITA-OT sources — normative and transformation behavior
- Experience League/FluffyJaws — product documentation and supporting discovery

Human/product decisions outrank historical analogy and AI synthesis. Never promote AI review into Human truth.

## Canonical interfaces

- MCP tool: `guides_test_plan_generator`
- REST: `POST /api/v1/test-plans/pipeline`
- MCP bridge: `POST /api/v1/mcp/guides-test-plan-generator`
- CLI: `scripts/run_test_plan_pipeline.py`
- Skill source: `.codex/skills/test-plan-generation/`

For the shared VM, connect MCP to `http://<VM-IP>:4502/mcp`. The backend listens internally on port `8001`.

## How to request a plan

Ask Claude Desktop to use the `test-plan-generation` skill for the Jira key. It should fetch the live issue through the configured Jira integration, inspect relevant product and automation repositories, gather evidence, run the canonical gates, and render plain-English ACs plus regression coverage and open questions.

The browser dashboard at `http://<VM-IP>:4502/` displays saved evaluation results only. It cannot generate, edit, approve, or post a UAC.

## Guardrails

- Do not recreate or depend on the retired React/Vite frontend.
- Do not add Jira-specific or customer-specific production rules.
- Do not invent missing evidence, performance thresholds, API behavior, or product decisions.
- Do not post to Jira unless the user explicitly requests it and has reviewed the content.
- Keep credentials in ignored environment files or approved secret injection.

See `ONBOARDING.md` for skill installation and `MCP_SETUP.md` for local MCP configuration.
