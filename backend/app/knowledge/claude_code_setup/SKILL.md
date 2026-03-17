# Claude Code Setup Skill for Adobe

## Overview

Interactive assistance for setting up Claude Code at Adobe using:
1. **Shared Bedrock Access** - Quick start using AI Foundations shared instance
2. **Project Turnkey** - Team-level dedicated Bedrock instance
3. **Claude Code Enterprise** - Coming soon

## Setup Workflow

### Step 1: Choose Interface
- **Terminal CLI**: `curl -fsSL https://claude.ai/install.sh | bash` then add `~/.local/bin` to PATH
- **VSCode Extension**: Install "Claude Code" from VSCode Marketplace
- **JetBrains IDE Extension**: Install from JetBrains Plugins Marketplace

### Step 2: Choose Access Method
- **Shared**: Join GRP-DL-AIF-AI-DEV-TALKS, wait 2+ hours, get secret from secretshare
- **Turnkey**: CAMP portal → Launch GenAI → OneTrust ID 18170 → wait ~30 min → get API key

### Step 3: Configure Environment
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_BEARER_TOKEN_BEDROCK="<your-token>"
export AWS_REGION=us-west-2
```

### Step 4: Verify
```bash
claude
# Look for "Overrides (via env):" in output
```

## Migrating from Cursor

- Rules: Copy `~/.cursor/rules/*.mdc` to `~/.claude/rules/`
- Skills: Copy `~/.cursor/skills/` to `~/.claude/skills/`
- Both use same `.mdc` format - fully compatible

## Common Issues

- **command not found**: Add `~/.local/bin` to PATH: `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc`
- **No Overrides message**: Env vars not set in same terminal - export again
- **Access denied**: Group membership not propagated - wait 2+ hours
- **Slow performance**: Consider Project Turnkey for dedicated capacity

## OneTrust Compliance

- OneTrust ID 18170 is ONLY for Claude Code
- NOT cleared for customer data without separate approval
- If using customer data, submit separate OneTrust AI Use Case for IDE usage
