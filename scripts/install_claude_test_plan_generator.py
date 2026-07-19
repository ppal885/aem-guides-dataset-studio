#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the AEM Guides test-plan Claude skill and slash command.

By default this installs for the current user:

- Skill:   ~/.claude/skills/aem-guides-test-scenario-generator
- Command: ~/.claude/commands/guides-test-plan-generator.md

Use --dest-skill-dir or --dest-command-dir when your Claude Code setup uses a
custom location.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL_DIR = PROJECT_ROOT / "claude-skills" / "aem-guides-test-scenario-generator"
SOURCE_COMMAND = PROJECT_ROOT / ".claude" / "commands" / "guides-test-plan-generator.md"


def default_claude_home() -> Path:
    return Path.home() / ".claude"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest-skill-dir",
        type=Path,
        default=default_claude_home() / "skills",
        help="Directory that contains Claude skill folders.",
    )
    parser.add_argument(
        "--dest-command-dir",
        type=Path,
        default=default_claude_home() / "commands",
        help="Directory that contains Claude slash command markdown files.",
    )
    parser.add_argument(
        "--skip-command",
        action="store_true",
        help="Install only the skill and do not copy the slash command.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned copy operations without writing files.",
    )
    return parser.parse_args()


def copy_tree(source: Path, target: Path, *, dry_run: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source skill not found: {source}")
    print(f"skill: {source} -> {target}")
    if dry_run:
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def copy_file(source: Path, target: Path, *, dry_run: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source command not found: {source}")
    print(f"command: {source} -> {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    args = parse_args()
    skill_target = args.dest_skill_dir / SOURCE_SKILL_DIR.name
    command_target = args.dest_command_dir / SOURCE_COMMAND.name

    copy_tree(SOURCE_SKILL_DIR, skill_target, dry_run=args.dry_run)
    if not args.skip_command:
        copy_file(SOURCE_COMMAND, command_target, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nInstalled. Restart Claude Code, then run:")
        print("  /guides-test-plan-generator GUIDES-12345")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
