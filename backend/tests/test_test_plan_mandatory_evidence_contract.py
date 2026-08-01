from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation" / "SKILL.md"
OUTPUT_TEMPLATE_PATH = SKILL_PATH.parent / "references" / "output-template.md"
REPO_REFERENCE_PATH = SKILL_PATH.parent / "references" / "pr-and-repo-evidence.md"


def test_plan_has_explicit_known_jira_bug_section():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    template = OUTPUT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "Known Jira Bugs / Past Similar Tickets" in skill
    assert "Known Jira Bugs / Past Similar Tickets" in template
    assert "open known bugs" in skill
    assert "historical root cause or behavior contract" in skill


def test_predevelopment_plan_reports_potential_code_impact_without_calling_it_changed():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "under `Potential code impact`" in skill
    assert "never present it as changed code" in skill
    assert "adjacent callers, shared services, configs, persistence paths" in skill


def test_referenced_pr_requires_deep_github_mcp_analysis():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    reference = REPO_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "treat it as mandatory implementation evidence" in skill
    assert "complete diff hunks" in skill
    assert "review comments and unresolved threads" in skill
    assert "checks/test results" in skill
    assert "Map concrete hunks to AC IDs" in reference
