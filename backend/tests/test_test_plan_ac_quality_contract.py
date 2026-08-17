from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation" / "SKILL.md"
OUTPUT_TEMPLATE_PATH = SKILL_PATH.parent / "references" / "output-template.md"


def test_skill_requires_live_jira_fetch_and_rejects_placeholders():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "fetch that issue before drafting the plan" in skill
    assert "Do not silently describe the source as pasted text" in skill
    assert "Treat placeholders such as `GUIDES-XXXXX` as missing input" in skill


def test_skill_requires_testable_identified_acceptance_contracts():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "AC-01" in skill
    assert "[Proposed]" in skill
    assert "[Confirmed]" in skill
    assert "do not write acceptance criteria as generic `Verify...` test instructions" in skill
    assert "Never infer defaults for omitted filters" in skill


def test_skill_requires_complete_ac_scenario_traceability():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    template = OUTPUT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "12-20 for broad APIs" in skill
    assert "No confirmed or proposed AC may remain without at least one scenario" in skill
    assert "P0 [AC-01, AC-02]" in template


def test_skill_keeps_raw_rag_scores_internal():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "Never expose numeric retrieval confidence" in skill
