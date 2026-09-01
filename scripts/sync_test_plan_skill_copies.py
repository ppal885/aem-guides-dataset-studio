"""Synchronize the canonical test-plan skill into every supported consumer copy."""

from __future__ import annotations

import argparse
import importlib.util
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
GLOBAL_TARGETS = (
    Path.home() / ".claude" / "skills" / "test-plan-generation",
    Path.home() / ".codex" / "skills" / "test-plan-generation",
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


def _load_fingerprint_module():
    module_path = SOURCE / "scripts" / "skill_bundle_fingerprint.py"
    spec = importlib.util.spec_from_file_location(
        "test_plan_skill_bundle_fingerprint_for_sync", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fingerprint policy from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_enforced_files(target: Path) -> None:
    """Copy common enforced files without deleting client-specific extensions."""
    fingerprint_module = _load_fingerprint_module()
    for relative in fingerprint_module.enforced_relative_paths(SOURCE):
        source_path = SOURCE / Path(relative)
        target_path = target / Path(relative)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def sync(
    *,
    source_only: bool = False,
    packages_only: bool = False,
    include_global: bool = False,
) -> list[Path]:
    if source_only and packages_only:
        raise ValueError("source_only and packages_only are mutually exclusive")
    targets = PACKAGE_TARGETS if packages_only else SOURCE_TARGETS
    if not source_only and not packages_only:
        targets = SOURCE_TARGETS + PACKAGE_TARGETS
    for target in targets:
        _copy_tree(target)
    if include_global:
        for target in GLOBAL_TARGETS:
            _copy_enforced_files(target)
        targets += GLOBAL_TARGETS
    return list(targets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source-only", action="store_true")
    group.add_argument("--packages-only", action="store_true")
    parser.add_argument(
        "--include-global",
        action="store_true",
        help="also sync enforced common files to user-level installed copies",
    )
    args = parser.parse_args()
    targets = sync(
        source_only=args.source_only,
        packages_only=args.packages_only,
        include_global=args.include_global,
    )
    for target in targets:
        print(f"synced: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
