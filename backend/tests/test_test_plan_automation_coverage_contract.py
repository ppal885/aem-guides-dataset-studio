from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation" / "SKILL.md"
OUTPUT_TEMPLATE_PATH = SKILL_PATH.parent / "references" / "output-template.md"
REPO_REFERENCE_PATH = SKILL_PATH.parent / "references" / "pr-and-repo-evidence.md"


def test_output_has_dedicated_automation_coverage_section():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    template = OUTPUT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "Automation Coverage & Gaps" in skill
    assert "Automation Coverage & Gaps" in template
    assert "Covered" in template
    assert "Partially covered" in template
    assert "Not covered" in template


def test_automation_evidence_uses_local_clones_and_github_mcp():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "inspect synchronized local clones first" in skill
    assert "Use GitHub MCP to inspect automation repositories" in skill
    assert "state which revision was inspected" in skill


def test_automation_gaps_map_to_ac_and_actionable_implementation():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    reference = REPO_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "Build an AC-to-automation map internally" in skill
    assert "Do not claim zero automation from one repository" in skill
    assert "correct automation layer" in reference
    assert "reusable helpers/fixtures" in reference
    assert "skipped, flaky, quarantined" in reference
