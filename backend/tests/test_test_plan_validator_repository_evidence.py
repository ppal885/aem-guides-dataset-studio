import importlib.util
from pathlib import Path


def _validator_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "claude-skills"
        / "aem-guides-test-scenario-generator"
        / "scripts"
        / "validate_test_plan.py"
    )
    spec = importlib.util.spec_from_file_location("validate_test_plan", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_review_ready_requires_product_repo_path():
    validator = _validator_module()
    errors: list[str] = []
    validator._validate_repository_evidence(
        errors,
        "Review status: Review-ready",
        [
            "| E1 | repository_evidence | UI component inspected | no exact path |",
        ],
        [],
    )

    assert any("local product repo evidence" in error for error in errors)


def test_non_missing_automation_requires_test_repo_reference():
    validator = _validator_module()
    errors: list[str] = []
    validator._validate_repository_evidence(
        errors,
        "Review status: Review-ready",
        [
            r"| E1 | repository_evidence | UI component inspected | C:\repo\xmleditor\src\Report.tsx:10 |",
        ],
        [
            "| Check broken report | UI | Exact and strong | Existing test covers it | none |",
        ],
    )

    assert any("guides-ui-tests or dxml-it-tests" in error for error in errors)
