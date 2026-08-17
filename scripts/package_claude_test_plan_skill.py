#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create the team-download ZIP for the AEM Guides test-plan Claude skill."""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / "claude-skills" / "aem-guides-test-scenario-generator"
COMMAND_FILE = PROJECT_ROOT / ".claude" / "commands" / "guides-test-plan-generator.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "release-artifacts" / "aem-guides-test-plan-claude-skill.zip"
PACKAGE_ROOT = "aem-guides-test-plan-claude-skill"


README_TEXT = """# AEM Guides Test Plan Generator Claude Skill

This ZIP is for team members who should use the AEM Guides test-plan generator
without cloning the full VM repository.

## Install

Extract this ZIP, then copy:

- `skills/aem-guides-test-scenario-generator/` to `~/.claude/skills/aem-guides-test-scenario-generator/`
- `commands/guides-test-plan-generator.md` to `~/.claude/commands/guides-test-plan-generator.md`

Windows paths:

- `%USERPROFILE%\\.claude\\skills\\aem-guides-test-scenario-generator\\`
- `%USERPROFILE%\\.claude\\commands\\guides-test-plan-generator.md`

macOS/Linux paths:

- `~/.claude/skills/aem-guides-test-scenario-generator/`
- `~/.claude/commands/guides-test-plan-generator.md`

Restart Claude Code after copying.

## Use

```text
/guides-test-plan-generator GUIDES-12345
```

## Required MCP/RAG/backend tools

This local skill does not contain the RAG index and does not replace Adobe Jira
MCP. Claude Code must be configured with:

- Adobe Jira MCP for live Jira reads
- local repo access for `xmleditor`, `starling`, `guides-ui-tests`, `dxml-it-tests`
- the existing VM-backed AEM Guides MCP/RAG tools, especially `guides_test_plan_generator`
- optional existing deterministic helper `test_plan_pipeline`

The VM backend provides Jira evidence, AEM Guides RAG/enriched behavior chunks,
DITA/DITA-OT evidence, and repository analysis. The skill only defines the
workflow, output structure, quality gates, and validation rules. Do not create a
second Jira client, RAG index, vector DB, repo scanner service, pipeline app, or
duplicate skill.
"""


INSTALL_PS1 = r"""$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillSource = Join-Path $root "skills\aem-guides-test-scenario-generator"
$commandSource = Join-Path $root "commands\guides-test-plan-generator.md"
$skillDest = Join-Path $env:USERPROFILE ".claude\skills\aem-guides-test-scenario-generator"
$commandDestDir = Join-Path $env:USERPROFILE ".claude\commands"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillDest) | Out-Null
New-Item -ItemType Directory -Force -Path $commandDestDir | Out-Null
if (Test-Path $skillDest) { Remove-Item -Recurse -Force $skillDest }
Copy-Item -Recurse -Force $skillSource $skillDest
Copy-Item -Force $commandSource (Join-Path $commandDestDir "guides-test-plan-generator.md")
Write-Host "Installed. Restart Claude Code, then run: /guides-test-plan-generator GUIDES-12345"
"""


INSTALL_SH = """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DEST="$HOME/.claude/skills/aem-guides-test-scenario-generator"
COMMAND_DEST="$HOME/.claude/commands/guides-test-plan-generator.md"
mkdir -p "$(dirname "$SKILL_DEST")" "$(dirname "$COMMAND_DEST")"
rm -rf "$SKILL_DEST"
cp -R "$ROOT/skills/aem-guides-test-scenario-generator" "$SKILL_DEST"
cp "$ROOT/commands/guides-test-plan-generator.md" "$COMMAND_DEST"
echo "Installed. Restart Claude Code, then run: /guides-test-plan-generator GUIDES-12345"
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def should_include(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    if "evals" in parts:
        return False
    return True


def add_text(zf: zipfile.ZipFile, name: str, text: str, *, executable: bool = False) -> None:
    info = zipfile.ZipInfo(f"{PACKAGE_ROOT}/{name}")
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    if executable:
        info.external_attr = 0o755 << 16
    zf.writestr(info, text)


def add_file(zf: zipfile.ZipFile, source: Path, archive_name: str) -> None:
    info = zipfile.ZipInfo(f"{PACKAGE_ROOT}/{archive_name}")
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, source.read_bytes())


def main() -> int:
    args = parse_args()
    if not SKILL_DIR.exists():
        raise FileNotFoundError(f"Missing skill directory: {SKILL_DIR}")
    if not COMMAND_FILE.exists():
        raise FileNotFoundError(f"Missing slash command: {COMMAND_FILE}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "aem-guides-test-plan-claude-skill",
        "version": "dalp-compact-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "skill": "aem-guides-test-scenario-generator",
        "slash_command": "guides-test-plan-generator",
        "required_mcp_tools": [
            "Adobe Jira MCP",
            "guides_test_plan_generator",
        ],
        "optional_mcp_tools": [
            "test_plan_pipeline",
            "find_similar_jira_issues",
            "show_mcp_rag_corpus_status",
        ],
        "install_skill_to": "~/.claude/skills/aem-guides-test-scenario-generator",
        "install_command_to": "~/.claude/commands/guides-test-plan-generator.md",
    }

    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        add_text(zf, "README.md", README_TEXT)
        add_text(zf, "install.ps1", INSTALL_PS1)
        add_text(zf, "install.sh", INSTALL_SH, executable=True)
        add_text(zf, "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        for source in sorted(SKILL_DIR.rglob("*")):
            if source.is_file() and should_include(source):
                rel = source.relative_to(SKILL_DIR).as_posix()
                add_file(zf, source, f"skills/aem-guides-test-scenario-generator/{rel}")
        add_file(zf, COMMAND_FILE, "commands/guides-test-plan-generator.md")

    with zipfile.ZipFile(args.output) as zf:
        bad_file = zf.testzip()
        if bad_file:
            raise RuntimeError(f"ZIP integrity failed at {bad_file}")
        names = set(zf.namelist())
        required = {
            f"{PACKAGE_ROOT}/README.md",
            f"{PACKAGE_ROOT}/install.ps1",
            f"{PACKAGE_ROOT}/install.sh",
            f"{PACKAGE_ROOT}/manifest.json",
            f"{PACKAGE_ROOT}/skills/aem-guides-test-scenario-generator/SKILL.md",
            f"{PACKAGE_ROOT}/commands/guides-test-plan-generator.md",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"ZIP missing required entries: {missing}")

    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
