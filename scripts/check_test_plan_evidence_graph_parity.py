"""Fail when any supported test-plan skill copy drifts from the Codex source."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX = ROOT / ".codex" / "skills" / "test-plan-generation"
CLAUDE = ROOT / ".claude" / "skills" / "test-plan-generation"
CANONICAL = ROOT / "skills" / "test-plan-generation"
TEAM_PACKAGES = (
    ROOT / "release-artifacts" / "aem-guides-mcp-client-unix" / ".claude" / "skills" / "test-plan-generation",
    ROOT / "release-artifacts" / "aem-guides-mcp-client-windows" / ".claude" / "skills" / "test-plan-generation",
)
IGNORED_NAMES = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc"}


def _inventory(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        files[relative.as_posix()] = path.read_bytes()
    return files


def _compare(reference: Path, candidate: Path, label: str) -> list[str]:
    failures: list[str] = []
    reference_files = _inventory(reference)
    candidate_files = _inventory(candidate)
    if not candidate.is_dir():
        return [f"missing skill copy: {label}: {candidate}"]
    missing = sorted(reference_files.keys() - candidate_files.keys())
    extra = sorted(candidate_files.keys() - reference_files.keys())
    changed = sorted(
        path
        for path in reference_files.keys() & candidate_files.keys()
        if reference_files[path] != candidate_files[path]
    )
    failures.extend(f"{label} missing file: {path}" for path in missing)
    failures.extend(f"{label} has extra file: {path}" for path in extra)
    failures.extend(f"{label} content drift: {path}" for path in changed)
    return failures


def check_parity(*, include_packages: bool = True) -> list[str]:
    failures: list[str] = []
    failures.extend(_compare(CODEX, CLAUDE, "Claude"))
    failures.extend(_compare(CODEX, CANONICAL, "canonical"))
    if include_packages:
        for package in TEAM_PACKAGES:
            failures.extend(_compare(CODEX, package, f"team package {package}"))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="Compare Codex, Claude, and canonical source copies only.",
    )
    args = parser.parse_args()
    failures = check_parity(include_packages=not args.source_only)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    scope = "source skill copies" if args.source_only else "all skill copies"
    print(f"Test-plan skill parity: PASS ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
