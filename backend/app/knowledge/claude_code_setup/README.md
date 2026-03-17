# Claude Code Setup for Adobe

This folder contains a comprehensive setup guide for installing and configuring Claude Code at Adobe, with support for both the Terminal CLI and VSCode Extension interfaces.

## What is Claude Code?

Claude Code is Anthropic's agentic coding tool that provides AI-powered assistance for software development. It's available in two forms:
- **Terminal CLI** - Standalone command-line tool
- **VSCode Extension** - Integrated extension for Visual Studio Code

Both interfaces require AWS Bedrock access configuration.

## Access Methods at Adobe

### 1. Shared Bedrock Access (AI Foundations)
- **Best for**: Individual contributors, quick start
- **Setup time**: ~2 hours (for group membership propagation)
- **Cost**: Free
- **Pros**: Fastest to set up
- **Cons**: Shared capacity (may be slower during peak times)

### 2. Project Turnkey (Dedicated Bedrock)
- **Best for**: Teams wanting dedicated capacity
- **Setup time**: ~30 minutes (provisioning)
- **Cost**: Pay-as-you-go AWS billing
- **Pros**: Dedicated capacity, better performance, programmatic API access
- **Cons**: Requires CAMP provisioning, costs money

### 3. Claude Code Enterprise
- **Status**: Coming soon
- **Note**: Cowork feature currently under review

## Key Configuration

### Shared Bedrock Access - Required Environment Variables
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_BEARER_TOKEN_BEDROCK="<shared-secret-from-secretshare>"
export AWS_REGION=us-west-2
```

**How to get the secret**:
1. Join distribution group: `GRP-DL-AIF-AI-DEV-TALKS` (auto-approved)
2. Wait 2+ hours for propagation
3. Access secret: https://secretshare.corp.adobe.com (link in full docs)

### Project Turnkey - Required Environment Variables
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_BEARER_TOKEN_BEDROCK="<your-api-key-from-camp>"
export AWS_REGION=us-west-2  # Must match your provisioned region
```

**How to provision**:
1. Log in to CAMP: https://camp.corp.adobe.com
2. Click "Launch GenAI (Fast Track)"
3. Select Claude model (latest available Sonnet or Opus)
4. Use OneTrust ID: `18170`
5. Wait ~30 minutes for provisioning
6. Retrieve API key from CAMP

## Installation

### Terminal CLI
```bash
curl -fsSL https://claude.ai/install.sh | bash
# Add to PATH: export PATH="$HOME/.local/bin:$PATH"
```

### VSCode Extension
1. Open VSCode → Extensions
2. Search for "Claude Code" (by Anthropic)
3. Click Install

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `claude: command not found` | Add `~/.local/bin` to PATH in shell profile |
| No "Overrides (via env):" message | Environment variables not set in current terminal |
| Access denied to shared secret | Group membership hasn't propagated yet (wait 2+ hours) |
| Authentication errors | Verify VPN, check AWS_REGION matches provisioned region |

## Support Resources

- **Wiki**: https://wiki.corp.adobe.com/pages/viewpage.action?spaceKey=devplats&title=Claude+Code+At+Adobe
- **CAMP Portal**: https://camp.corp.adobe.com
- **Slack**: #camp-help (for Project Turnkey issues)

## Using This Setup for AI Chat (Dataset Studio)

The AI chat in AEM Guides Dataset Studio can use the same Bedrock setup for LLM generation. Add to `backend/.env`:

**Project Turnkey** (recommended – CAMP provides AWS credentials):
```bash
LLM_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=<from CAMP>
AWS_SECRET_ACCESS_KEY=<from CAMP>
AWS_REGION=us-west-2
BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
```

**Or use CLAUDE_CODE_USE_BEDROCK** (if you already have it set for Claude Code):
```bash
CLAUDE_CODE_USE_BEDROCK=1
LLM_PROVIDER=bedrock
AWS_REGION=us-west-2
# Plus AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY from Project Turnkey
# Or AWS_PROFILE if using ~/.aws/credentials
```

Restart the backend after setting these variables. The AI chat will then use Claude via Bedrock.

## Important Notes

- **OneTrust ID 18170** is ONLY for Claude Code. NOT cleared for customer data without separate approval.
- **Shared access** requires 2+ hour wait for group membership propagation
- **Environment variables** must be set in the same terminal where you run `claude`
- **Persist variables** by adding exports to `~/.zshrc` or `~/.bashrc`
