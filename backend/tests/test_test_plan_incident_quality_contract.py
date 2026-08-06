from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPOSITORY_ROOT / ".codex" / "skills" / "test-plan-generation"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
OUTPUT_TEMPLATE_PATH = SKILL_ROOT / "references" / "output-template.md"
QUALITY_GATE_PATH = SKILL_ROOT / "references" / "quality-gate-checklist.md"


def _contract_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SKILL_PATH, OUTPUT_TEMPLATE_PATH, QUALITY_GATE_PATH)
    )


def test_incident_cleanup_is_not_a_product_acceptance_criterion():
    text = _contract_text()

    assert "Do not turn a destructive operational procedure into a product acceptance criterion" in text
    assert "Incident recovery validation" in text
    assert "pre-change inventory/backup" in text
    assert "unrelated-state protection" in text
    assert "rollback" in text


def test_expected_behavior_blocks_root_cause_overclaiming():
    text = _contract_text()

    assert "Do not use exclusive wording" in text
    assert "only cause" in text
    assert "credible alternatives" in text


def test_repo_evidence_requires_exact_paths_and_revision_state():
    text = _contract_text()

    assert "never abbreviate a path with `...`" in text
    assert "commit SHA" in text
    assert "ahead/behind" in text
    assert "dirty/clean state" in text


def test_automation_classification_and_gap_recipe_are_strict():
    text = _contract_text()

    assert "adjacent happy-path coverage is only reusable infrastructure" in text
    assert "deterministic failure or state-injection mechanism" in text
    assert "polling endpoint and terminal oracle" in text
    assert "cleanup/rollback" in text
    assert "suite/tags" in text


def test_performance_history_and_concurrency_oracles_are_safe():
    text = _contract_text()

    assert "controlled benchmark" in text
    assert "actual JQL/search intents" in text
    assert "successful completion after serialization/retry" in text
    assert "no duplicate/partial/orphan state" in text


def test_output_contract_requires_mojibake_scan():
    text = _contract_text()

    assert "scan for mojibake" in text
    assert "valid UTF-8" in text
