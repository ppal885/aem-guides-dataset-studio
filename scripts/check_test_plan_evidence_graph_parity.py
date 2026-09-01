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

# Parity proves that copies are identical, but identical copies can still all omit a
# newly required contract or regress to an obsolete schema.  Keep this list limited to
# release-boundary contracts whose absence/version would invalidate every gate run.
REQUIRED_CONTRACT_MARKERS: dict[str, tuple[bytes, ...]] = {
    "scripts/ac_contract.py": (b"aem-guides-ac-v1",),
    "scripts/run_gates.py": (
        b"aem-guides-evidence-manifest-v2",
        b"aem-guides-evidence-manifest-v3",
        b"aem-guides-gate-receipt-v1",
    ),
    "scripts/contract_fact_extractor.py": (b"aem-guides-contract-facts-v1",),
    "scripts/behavior_graph.py": (b"aem-guides-behavior-graph-v1",),
    "scripts/semantic_closure.py": (b"aem-guides-semantic-closure-v1",),
    "scripts/generated_output_contract.py": (
        b"aem-guides-generated-output-contract-v2",
    ),
    "scripts/acceptance_promotion.py": (b"aem-guides-acceptance-promotions-v1",),
    "scripts/data/authority_policy.json": (b"aem-guides-subject-authority-v1",),
    "scripts/data/domain_profiles.json": (b"aem-guides-domain-profiles-v1",),
    "scripts/enumerated_coverage.py": (
        b"aem-guides-enumerated-requirements-v1",
    ),
    "scripts/concurrency_race_explorer.py": (
        b"aem-guides-concurrency-race-v1",
    ),
    "scripts/operational_contract.py": (
        b"aem-guides-operational-contract-v1",
    ),
    "references/operational-incident-contract.md": (
        b"aem-guides-operational-contract-v1",
    ),
}


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


def _check_required_contracts(reference: Path, label: str) -> list[str]:
    """Fail if the source omits a release-boundary contract or schema marker."""
    files = _inventory(reference)
    failures: list[str] = []
    for relative, markers in REQUIRED_CONTRACT_MARKERS.items():
        content = files.get(relative)
        if content is None:
            failures.append(f"{label} missing required contract: {relative}")
            continue
        for marker in markers:
            if marker not in content:
                failures.append(
                    f"{label} required contract marker missing: "
                    f"{relative}: {marker.decode('ascii')}"
                )
    return failures


def check_parity(*, include_packages: bool = True) -> list[str]:
    failures: list[str] = []
    failures.extend(_check_required_contracts(CODEX, "Codex source"))
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
