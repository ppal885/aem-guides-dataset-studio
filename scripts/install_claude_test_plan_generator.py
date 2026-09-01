#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the canonical AEM Guides test-plan skill and compatibility alias.

By default this installs for the current user:

- Canonical skill: ~/.claude/skills/test-plan-generation
- Legacy alias:    ~/.claude/skills/aem-guides-test-scenario-generator
Use --dest-skill-dir when your Claude Code setup uses a custom location.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "test-plan-generation"
ALIAS_SKILL_DIR = PROJECT_ROOT / "claude-skills" / "aem-guides-test-scenario-generator"


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
    shutil.copytree(
        source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )


def copy_declaration_only_alias(source: Path, target: Path, *, dry_run: bool) -> None:
    skill_file = source / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Source alias declaration not found: {skill_file}")
    print(f"alias declaration: {skill_file} -> {target / 'SKILL.md'}")
    if dry_run:
        return
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_file, target / "SKILL.md")


def main() -> int:
    args = parse_args()

    copy_tree(
        CANONICAL_SKILL_DIR,
        args.dest_skill_dir / CANONICAL_SKILL_DIR.name,
        dry_run=args.dry_run,
    )
    copy_declaration_only_alias(
        ALIAS_SKILL_DIR,
        args.dest_skill_dir / ALIAS_SKILL_DIR.name,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        print(
            "\nInstalled. Restart Claude Code, then request the test-plan-generation skill."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
