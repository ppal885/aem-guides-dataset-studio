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
    Path("scripts/evidence_graph_manifest.py"),
)
REQUIRED_MARKERS = {
    Path("SKILL.md"): (
        "query_test_evidence_graph",
        "### Phase 4.5 — Connect Evidence Graph",
        "path ID is traceability metadata only",
        "graph unavailability alone is not a Draft blocker",
        "default to `shadow`",
        "references/evidence-graph-contract.md",
    ),
    Path("scripts/evidence_graph_manifest.py"): (
        "GRAPH_INFLUENCE_MODES",
        "evidence_graph.used_for_plan",
        "duration_ms",
        "cache_hit",
    ),
    Path("scripts/run_gates.py"): (
        '"evidence_graph"',
        "validate_evidence_graph_manifest",
    ),
    Path("scripts/validate_test_plan.py"): (
        "AC_EVIDENCE_RE",
        "never only a graph path",
    ),
}


def check_parity() -> list[str]:
    failures: list[str] = []
    for relative in IDENTICAL_FILES:
        codex_path = CODEX / relative
        claude_path = CLAUDE / relative
        if not codex_path.is_file() or not claude_path.is_file():
            failures.append(f"missing parity file: {relative.as_posix()}")
            continue
        if codex_path.read_bytes() != claude_path.read_bytes():
            failures.append(f"Codex/Claude graph contract drift: {relative.as_posix()}")
        if relative == Path("references/evidence-graph-contract.md") and claude_path.is_file():
            for package in TEAM_PACKAGES:
                package_path = package / relative
                if not package_path.is_file():
                    failures.append(f"missing team-package graph contract: {package_path}")
                elif package_path.read_bytes() != claude_path.read_bytes():
                    failures.append(f"team-package graph contract drift: {package_path}")
    for relative, markers in REQUIRED_MARKERS.items():
        for root, label in ((CODEX, "Codex"), (CLAUDE, "Claude")):
            path = root / relative
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            for marker in markers:
                if marker not in text:
                    failures.append(f"{label} {relative.as_posix()} missing graph marker: {marker}")
    for package in TEAM_PACKAGES:
        skill_text = (package / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("shadow", "augment", "used_for_plan"):
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
