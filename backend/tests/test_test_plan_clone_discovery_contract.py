from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation" / "SKILL.md"
REPO_REFERENCE_PATH = SKILL_PATH.parent / "references" / "pr-and-repo-evidence.md"


def test_skill_does_not_limit_clone_discovery_to_workspace():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "Clone discovery is not limited to the current workspace" in skill
    assert "Never write `no backend/Starling clone available`" in skill


def test_windows_clone_discovery_includes_real_team_roots():
    reference = REPO_REFERENCE_PATH.read_text(encoding="utf-8")

    for path in (
        "C:\\starling",
        "C:\\xmleditor\\xmleditor",
        "C:\\ui_framework\\new_editor",
        "C:\\UI TEST\\guides-ui-tests",
        "C:\\ui_framework\\guides-ui-tests",
        "C:\\api automation\\dxml-it-tests",
    ):
        assert path in reference


def test_none_found_requires_product_and_automation_search_evidence():
    reference = REPO_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "Finding only `guides-ui-tests` never justifies" in reference
    assert "Before writing `none found`" in reference
    assert "Never infer `Current implementation implicated: none found`" in reference
    assert "newTranslationProject" in reference
    assert "versionAsOfDate" in reference
