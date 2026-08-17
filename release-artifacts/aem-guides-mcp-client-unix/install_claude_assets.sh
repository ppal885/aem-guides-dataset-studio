#!/usr/bin/env bash
set -euo pipefail

CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$CLIENT_DIR"

mkdir -p "$HOME/.claude/commands"
mkdir -p "$HOME/.claude/skills"

rm -f \
  "$HOME/.claude/commands/ask-dita-expert.md" \
  "$HOME/.claude/commands/generate-dita-ot-output.md" \
  "$HOME/.claude/commands/guides-test-plan-generator.md" \
  "$HOME/.claude/commands/aem-ask-dita-expert.md" \
  "$HOME/.claude/commands/aem-data-upload-workflow.md" \
  "$HOME/.claude/commands/aem-generate-dita.md" \
  "$HOME/.claude/commands/aem-generate-dita-ot-output.md" \
  "$HOME/.claude/commands/aem-guides-test-plan.md" \
  "$HOME/.claude/commands/aem-guides-test-scenario-generator.md" \
  "$HOME/.claude/commands/aem-rag-status.md" \
  "$HOME/.claude/commands/aem-upload-generated-to-aem.md"

rm -rf "$HOME/.claude/skills/test-plan-generation"
rm -rf "$HOME/.claude/skills/aem-data-upload-workflow"
rm -rf "$HOME/.claude/skills/aem-guides-dita-qa-pipeline"
rm -rf "$HOME/.claude/skills/aem-guides-test-scenario-generator"

cp -R .claude/skills/test-plan-generation "$HOME/.claude/skills/"

echo "Installed Claude skill to:    $HOME/.claude/skills/test-plan-generation"
echo "Removed old AEM slash commands and deprecated AEM skills."
echo
echo "Recommended MCP registration:"
echo "  claude mcp add-json aem-guides-dataset-studio \"\$(cat \"$CLIENT_DIR/claude-mcp-server.json\")\""
echo
echo "No AEM upload slash command is installed. Use MCP tool: upload_dataset_to_aem"
