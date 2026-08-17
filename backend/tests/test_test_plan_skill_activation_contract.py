from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_test_plan_workflow_is_skill_only():
    skill_path = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation" / "SKILL.md"
    command_path = REPOSITORY_ROOT / ".claude" / "commands" / "guides-test-plan-generator.md"

    assert skill_path.exists()
    assert not command_path.exists()

    skill = skill_path.read_text(encoding="utf-8")
    assert "Do not use or expect any generated test-plan slash command or test-plan MCP tool." in skill
    assert "Use `ask_dita_expert` as the only VM RAG path" in skill


def test_remote_mcp_has_no_test_plan_handler_or_registration():
    route_path = REPOSITORY_ROOT / "backend" / "app" / "api" / "routes" / "remote_mcp.py"
    route = route_path.read_text(encoding="utf-8")

    assert '"guides_test_plan_generator"' not in route
    assert "def _guides_test_plan_generator" not in route
