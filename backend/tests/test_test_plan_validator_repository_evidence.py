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


def _dalp_plan(*, classification: str = "ticket-confirmed", score: int = 88) -> str:
    return rf"""# Test Plan: GUIDES-1 — Demo

**Jira:** GUIDES-1 · **Type:** Bug · **Scope:** UI
**Routing:** QE_REVIEW_READY
**Score:** {score} · **Review status:** Review-ready
**QE review:** Required; not auto-approved

## 1. Action items (QA — start here)

### Setup (one time)
1. Use Author and test map.

### Must run before release
| Run first | Scenario | Pass if |
| --- | --- | --- |
| P0 | S-01 | UI shows value |

### Test list (priority order)
| Scenario ID | Priority | Title | Links to | How to verify |
| --- | --- | --- | --- | --- |
| S-01 | P0 R0 | Verify baseline column | EB-1, R-01 | visible Version comment |

### Steps for P0 / P1 tests
- **S-01** Open baseline table. **How to check:** Version comment value is visible and matches CRX property.

### Sign-off checks (acceptance from Jira)
- **AC-1** (S-01) Version comment column is visible. Classification: ticket-confirmed.

## 2. Supplementary — context, risks & traceability

### Summary & expected behaviour
- **Bug / feature:** Baseline column enhancement.
- **API or UI entry point:** Baseline table.
- **How to reproduce today:** Open baseline table.
- **Fix area (if known):** `C:\repo\xmleditor\src\BaselineTable.tsx:10`

- **EB-1:** Version comment is visible.
- **EB-2:** Existing columns still render.
- **EB-3:** CSV export includes the column.

### Where we got the facts (evidence)
| Evidence ID | Source | Classification | What it proves | Link / path |
| --- | --- | --- | --- | --- |
| E1 | Jira | {classification} | Customer needs Version comment | GUIDES-1 |
| E2 | repo | implementation-derived | Baseline table component inspected | C:\repo\xmleditor\src\BaselineTable.tsx:10 |
| E3 | test repo | implementation-derived | UI automation area inspected | C:\repo\guides-ui-tests\features\baseline.feature:8 |

### What can break & risks

### Code path (where the fix lives)
User opens baseline -> xmleditor table -> property resolver -> visible column.

| Area | Impact | Why | Test / skip |
| --- | --- | --- | --- |
| Baseline table | Direct | Customer entry point | S-01 |

| Risk ID | Priority | What goes wrong | Test / skip |
| --- | --- | --- | --- |
| R-01 | P0 | Column shows wrong version comment | S-01 |

### Must not break (regression checks)
- S-01 keeps existing baseline table rendering.

### Likely bugs to watch (top 3)
| ID | What we suspect | How you'd notice | Test |
| --- | --- | --- | --- |
| BH-01 | Wrong version metadata binding | Comment mismatch | S-01 |

### Related past Jiras
| Jira | What happened | Why it matters here | Test |
| --- | --- | --- | --- |
| GUIDES-2 | Baseline table changed | Same UI area | S-01 |

### Automation coverage
| Check | Where | Coverage | Gap |
| --- | --- | --- | --- |
| Baseline UI check | C:\repo\guides-ui-tests\features\baseline.feature:8 | Exact and strong | none |

### Confidence breakdown
| Dimension | Score | Evidence / deduction |
| --- | --- | --- |
| Ticket completeness | 90 | Jira has current and expected behavior |
| Retrieval quality | 85 | Jira and docs found |
| Evidence coverage | 90 | Jira plus repo evidence |
| Source consistency | 90 | no conflict |
| Sign-off testability | 85 | visible UI checks |
| Requirement traceability | 90 | EB and risks map to S-01 |

**Routing reason:** score >=85 so QE_REVIEW_READY.

### QE review package
- QE owner: QE / QA owner
- Must review before release: S-01
- Unresolved questions: none
- Required approval evidence: screenshot and automation run

### Evidence & release status
- Jira / code / Swagger / test-data paths: C:\repo\xmleditor\src\BaselineTable.tsx:10
- Not tested yet: none
- Known gaps: none
- **Release confidence:** High
- **Review status:** Review-ready
"""


def test_dalp_plan_requires_valid_classification_and_qe_score():
    validator = _validator_module()
    errors = validator.validate_text(_dalp_plan())
    assert errors == []


def test_dalp_plan_rejects_invalid_evidence_classification():
    validator = _validator_module()
    errors = validator.validate_text(_dalp_plan(classification="jira-ish"))
    assert any("Invalid evidence classification" in error for error in errors)
