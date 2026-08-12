"""Synchronize the canonical test-plan skill into every supported consumer copy."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".codex" / "skills" / "test-plan-generation"
SOURCE_TARGETS = (
    ROOT / ".claude" / "skills" / "test-plan-generation",
    ROOT / "skills" / "test-plan-generation",
)
PACKAGE_TARGETS = (
    ROOT
    / "release-artifacts"
    / "aem-guides-mcp-client-windows"
    / ".claude"
    / "skills"
    / "test-plan-generation",
    ROOT
    / "release-artifacts"
    / "aem-guides-mcp-client-unix"
    / ".claude"
    / "skills"
    / "test-plan-generation",
)
IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def _copy_tree(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SOURCE,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def sync(*, source_only: bool = False, packages_only: bool = False) -> list[Path]:
    if source_only and packages_only:
        raise ValueError("source_only and packages_only are mutually exclusive")
    targets = PACKAGE_TARGETS if packages_only else SOURCE_TARGETS
    if not source_only and not packages_only:
        targets = SOURCE_TARGETS + PACKAGE_TARGETS
    for target in targets:
        _copy_tree(target)
    return list(targets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source-only", action="store_true")
    group.add_argument("--packages-only", action="store_true")
    args = parser.parse_args()
    targets = sync(source_only=args.source_only, packages_only=args.packages_only)
    for target in targets:
        print(f"synced: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
