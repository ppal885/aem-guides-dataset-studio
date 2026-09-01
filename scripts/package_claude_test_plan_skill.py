#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create the team ZIP for the canonical skill and its legacy Claude alias."""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIRS = (
    PROJECT_ROOT / ".claude" / "skills" / "test-plan-generation",
    PROJECT_ROOT / "claude-skills" / "aem-guides-test-scenario-generator",
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "release-artifacts" / "aem-guides-test-plan-claude-skill.zip"
)
PACKAGE_ROOT = "aem-guides-test-plan-claude-skill"


README_TEXT = """# AEM Guides Test Plan Generator Claude Skill

This ZIP installs the canonical AEM Guides test-plan skill plus a declaration-only
legacy alias. Canonical execution still requires either the Dataset Studio backend
checkout (`--repo-root` / `AEM_STUDIO_REPO`) or the configured VM canonical-runtime
MCP endpoint described below.

## Install

Extract this ZIP, then copy:

- `skills/test-plan-generation/` to `~/.claude/skills/test-plan-generation/`
- `skills/aem-guides-test-scenario-generator/` to `~/.claude/skills/aem-guides-test-scenario-generator/` (legacy alias)

Windows paths:

- `%USERPROFILE%\\.claude\\skills\\test-plan-generation\\`
- `%USERPROFILE%\\.claude\\skills\\aem-guides-test-scenario-generator\\`

macOS/Linux paths:

- `~/.claude/skills/test-plan-generation/`
- `~/.claude/skills/aem-guides-test-scenario-generator/`

Restart Claude Code after copying.

## Use

Ask Claude to use the `test-plan-generation` skill for the Jira or supplied evidence.

## Required MCP/RAG/backend tools

This local skill does not contain the RAG index and does not replace Adobe Jira
MCP. Claude Code must be configured with:

- Adobe Jira MCP for live Jira reads
- local repo access for `xmleditor`, `starling`, `guides-ui-tests`, `dxml-it-tests`
- the existing VM-backed AEM Guides MCP/RAG tools, especially `guides_test_plan_generator`
- optional existing deterministic helper `test_plan_pipeline`

The Dataset Studio or VM backend provides Jira evidence, AEM Guides RAG/enriched behavior chunks,
DITA/DITA-OT evidence, repository analysis, and the canonical stage-owned
reasoning runtime. The canonical skill collects evidence and delegates final
reasoning/rendering to that runtime. The legacy skill is an alias only. Do not
create a second Jira client, RAG index, vector DB, repo scanner, reasoning
pipeline, or renderer.
"""


INSTALL_PS1 = r"""$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$canonicalSource = Join-Path $root "skills\test-plan-generation"
$aliasSource = Join-Path $root "skills\aem-guides-test-scenario-generator"
$canonicalDest = Join-Path $env:USERPROFILE ".claude\skills\test-plan-generation"
$aliasDest = Join-Path $env:USERPROFILE ".claude\skills\aem-guides-test-scenario-generator"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $canonicalDest) | Out-Null
if (Test-Path $canonicalDest) { Remove-Item -Recurse -Force $canonicalDest }
if (Test-Path $aliasDest) { Remove-Item -Recurse -Force $aliasDest }
Copy-Item -Recurse -Force $canonicalSource $canonicalDest
Copy-Item -Recurse -Force $aliasSource $aliasDest
Write-Host "Installed. Restart Claude Code, then request the test-plan-generation skill."
"""


INSTALL_SH = """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_DEST="$HOME/.claude/skills/test-plan-generation"
ALIAS_DEST="$HOME/.claude/skills/aem-guides-test-scenario-generator"
mkdir -p "$(dirname "$CANONICAL_DEST")"
rm -rf "$CANONICAL_DEST" "$ALIAS_DEST"
cp -R "$ROOT/skills/test-plan-generation" "$CANONICAL_DEST"
cp -R "$ROOT/skills/aem-guides-test-scenario-generator" "$ALIAS_DEST"
echo "Installed. Restart Claude Code, then request the test-plan-generation skill."
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


def add_text(
    zf: zipfile.ZipFile, name: str, text: str, *, executable: bool = False
) -> None:
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
    for skill_dir in SKILL_DIRS:
        if not skill_dir.exists():
            raise FileNotFoundError(f"Missing skill directory: {skill_dir}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "aem-guides-test-plan-claude-skill",
        "version": "canonical-runtime-v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "canonical_skill": "test-plan-generation",
        "legacy_alias": "aem-guides-test-scenario-generator",
        "required_mcp_tools": [
            "Adobe Jira MCP",
            "guides_test_plan_generator",
        ],
        "optional_mcp_tools": [
            "test_plan_pipeline",
            "find_similar_jira_issues",
            "show_mcp_rag_corpus_status",
        ],
        "install_canonical_skill_to": "~/.claude/skills/test-plan-generation",
        "install_legacy_alias_to": "~/.claude/skills/aem-guides-test-scenario-generator",
    }

    with zipfile.ZipFile(
        args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        add_text(zf, "README.md", README_TEXT)
        add_text(zf, "install.ps1", INSTALL_PS1)
        add_text(zf, "install.sh", INSTALL_SH, executable=True)
        add_text(
            zf,
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        for skill_dir in SKILL_DIRS:
            sources = (
                [skill_dir / "SKILL.md"]
                if skill_dir.name == "aem-guides-test-scenario-generator"
                else sorted(skill_dir.rglob("*"))
            )
            for source in sources:
                if source.is_file() and should_include(source):
                    rel = source.relative_to(skill_dir).as_posix()
                    add_file(zf, source, f"skills/{skill_dir.name}/{rel}")

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
            f"{PACKAGE_ROOT}/skills/test-plan-generation/SKILL.md",
            f"{PACKAGE_ROOT}/skills/aem-guides-test-scenario-generator/SKILL.md",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"ZIP missing required entries: {missing}")
        alias_prefix = f"{PACKAGE_ROOT}/skills/aem-guides-test-scenario-generator/"
        alias_entries = sorted(name for name in names if name.startswith(alias_prefix))
        if alias_entries != [f"{alias_prefix}SKILL.md"]:
            raise RuntimeError(
                "Legacy alias must contain only SKILL.md; found "
                + ", ".join(alias_entries)
            )

    print(
        json.dumps(
            {"output": str(args.output), "bytes": args.output.stat().st_size}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
