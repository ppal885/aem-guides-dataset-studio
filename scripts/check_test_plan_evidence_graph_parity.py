"""Fail when Codex and Claude evidence-graph skill contracts drift."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CODEX = ROOT / ".codex" / "skills" / "test-plan-generation"
CLAUDE = ROOT / ".claude" / "skills" / "test-plan-generation"
TEAM_PACKAGES = (
    ROOT / "release-artifacts" / "aem-guides-mcp-client-unix" / ".claude" / "skills" / "test-plan-generation",
    ROOT / "release-artifacts" / "aem-guides-mcp-client-windows" / ".claude" / "skills" / "test-plan-generation",
)
IDENTICAL_FILES = (
    Path("references/evidence-graph-contract.md"),
    Path("references/golden-benchmark.md"),
    Path("references/performance-assessment-contract.md"),
    Path("scripts/ac_contract.py"),
    Path("scripts/extract_acs.py"),
    Path("scripts/performance_contract.py"),
    Path("scripts/render_compact_view.py"),
    Path("scripts/evidence_graph_manifest.py"),
)
TEAM_IDENTICAL_FILES = (
    Path("scripts/ac_contract.py"),
    Path("scripts/extract_acs.py"),
    Path("scripts/performance_contract.py"),
    Path("scripts/render_compact_view.py"),
    Path("references/performance-assessment-contract.md"),
    Path("references/golden-benchmark.md"),
)
REQUIRED_MARKERS = {
    Path("SKILL.md"): (
        "query_test_evidence_graph",
        "### Phase 4.5 — Connect Evidence Graph",
        "path ID is traceability metadata only",
        "graph unavailability alone is not a Draft blocker",
        "default to `shadow`",
        "references/evidence-graph-contract.md",
        "references/golden-benchmark.md",
        "aem-guides-ac-v1",
        "aem-guides-performance-assessment-v1",
        "do not add a Performance Analysis section",
        "render_compact_view.py",
        "`Acceptance Criteria`, `Regression Areas`, `Past Jiras`, and `Open Questions`",
    ),
    Path("scripts/evidence_graph_manifest.py"): (
        "GRAPH_INFLUENCE_MODES",
        "evidence_graph.used_for_plan",
        "duration_ms",
        "cache_hit",
    ),
    Path("scripts/run_gates.py"): (
        '"evidence_graph"',
        '"performance_assessment"',
        "validate_evidence_graph_manifest",
        "validate_performance_assessment",
    ),
    Path("scripts/validate_test_plan.py"): (
        "AC_EXACT_FORMAT",
        "parse_ac_line",
        "QUANTIFIED_WORKLOAD_RE",
        "never only a graph path",
    ),
    Path("scripts/performance_contract.py"): (
        "aem-guides-performance-assessment-v1",
        "SIGNAL_CATEGORIES",
        "validate_performance_assessment",
        "validate_plan_alignment",
        "internal evidence-manifest data",
    ),
    Path("references/golden-benchmark.md"): (
        "18 Jira cases",
        "historical precision@5",
        "performance-decision accuracy",
        "golden_status",
        "Do not run all 18 cases for an ordinary test-plan request",
    ),
}


def _canonical_text(path: Path) -> str:
    """Compare contracts semantically across Windows and Unix packages."""
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").rstrip() + "\n"


def check_parity() -> list[str]:
    failures: list[str] = []
    for relative in IDENTICAL_FILES:
        codex_path = CODEX / relative
        claude_path = CLAUDE / relative
        if not codex_path.is_file() or not claude_path.is_file():
            failures.append(f"missing parity file: {relative.as_posix()}")
            continue
        if _canonical_text(codex_path) != _canonical_text(claude_path):
            failures.append(f"Codex/Claude graph contract drift: {relative.as_posix()}")
        if relative == Path("references/evidence-graph-contract.md") and claude_path.is_file():
            for package in TEAM_PACKAGES:
                package_path = package / relative
                if not package_path.is_file():
                    failures.append(f"missing team-package graph contract: {package_path}")
                elif _canonical_text(package_path) != _canonical_text(claude_path):
                    failures.append(f"team-package graph contract drift: {package_path}")
    for relative in TEAM_IDENTICAL_FILES:
        claude_path = CLAUDE / relative
        for package in TEAM_PACKAGES:
            package_path = package / relative
            if not package_path.is_file():
                failures.append(f"missing team-package AC/presentation contract: {package_path}")
            elif _canonical_text(package_path) != _canonical_text(claude_path):
                failures.append(f"team-package AC/presentation contract drift: {package_path}")
    for relative, markers in REQUIRED_MARKERS.items():
        for root, label in ((CODEX, "Codex"), (CLAUDE, "Claude")):
            path = root / relative
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            for marker in markers:
                if marker not in text:
                    failures.append(f"{label} {relative.as_posix()} missing graph marker: {marker}")
    for package in TEAM_PACKAGES:
        skill_text = (package / "SKILL.md").read_text(encoding="utf-8")
        for marker in (
            "shadow",
            "augment",
            "used_for_plan",
            "aem-guides-ac-v1",
            "aem-guides-performance-assessment-v1",
            "render_compact_view.py",
            "Past Jiras",
            "Open Questions",
            "Performance Analysis",
            "golden-benchmark.md",
        ):
            if marker not in skill_text:
                failures.append(f"team-package SKILL.md missing Phase B marker {marker}: {package}")
    return failures


def main() -> int:
    failures = check_parity()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Evidence-graph skill parity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
