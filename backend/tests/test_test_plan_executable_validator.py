from __future__ import annotations

import importlib.util
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = (
    REPOSITORY_ROOT
    / ".codex"
    / "skills"
    / "test-plan-generation"
    / "scripts"
    / "validate_test_plan.py"
)
SPEC = importlib.util.spec_from_file_location("test_plan_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def _valid_plan() -> str:
    return """**Understanding From Jira**
- Issue understood: Concurrent publishing can leave an output job non-terminal.
- Why it matters: Customer context resolved from Jira: JPMC from labels; a blocked publishing queue prevents documentation delivery.
- Requested outcome: Every accepted publish reaches a defined outcome without corrupting output.
- Lifecycle understood as: Pre-Development UAC because implementation has not started.
- Evidence boundary: Supplied Jira evidence supports the problem; implementation and retry policy remain unverified.

**Acceptance Criteria**
- AC-01 [Proposed]: A concurrent publish completes successfully without leaving a job in a non-terminal state. | Evidence: JIRA:GUIDES-1

**Expected Behaviour**
- Jira and current remote code support the proposed outcome; implementation choice remains open.

**Scope From Git**
- Lifecycle stage: Pre-Development UAC.
- C:\\starling clone: branch `develop`; SHA `abc1234`; fetch succeeded; ahead 0; behind 0; clean state.

**Code Touched**
- No code changes yet - development has not started.
- Current implementation implicated: `C:\\starling\\core\\Example.java`, method `publish`.

**Lines Changed**
- Not applicable - development has not started.

**Test Scenarios**
- Test data to prepare: Two valid maps, one shared AEM Sites target, a successful output snapshot, and cleanup access.
- P0 [AC-01]: Action: Run two overlapping publishes. Expected: Both finish and output integrity is preserved.
- Incident recovery validation: Use an approved production-equivalent recovery checklist and preserve audit evidence.

**Known Jira Bugs / Past Similar Tickets**
- GUIDES-1 - Similarity: strongest match with the same concurrent publishing failure shape; Status: Closed; Resolution: Fixed; Affected version: unavailable; Fix version: unavailable; RCA: commit conflict; Test evidence: unavailable; Impact: adds concurrency regression coverage.
- Search method: JQL by exact error `OakState0002`; JQL by workflow `Publish DITAMAP`; indexed history unavailable.

**Regression Areas**
- Re-run unrelated publishing queues and output types that share job-state handling to confirm concurrent execution does not leave jobs non-terminal or corrupt generated output.

**Automation Coverage & Gaps**
- AC-01 - Not covered: add `concurrentPublish` in `C:\\api-tests\\PublishIT.java`; API layer; setup fixture; poll status endpoint; timeout from suite configuration; assert terminal success and output integrity; cleanup fixture; tag `publishing-concurrency`.

**Open Questions**
- Confirm the approved retry budget and SLA; QA impact: the answer defines polling duration, terminal-failure timing, and sign-off thresholds.
"""


def test_validator_accepts_complete_plan():
    assert VALIDATOR.validate(_valid_plan()) == []


def test_validator_rejects_response_quality_failures():
    bad = _valid_plan().replace(
        "- AC-01 [Proposed]: A concurrent publish completes successfully without leaving a job in a non-terminal state. | Evidence: JIRA:GUIDES-1",
        "- AC-01 [Confirmed - historical]: Engineering must delete the tracker node.",
    )
    bad = "Jira requires authorization. Live Jira fetched successfully.\n" + bad
    bad = bad.replace(
        "- P0 [AC-01]: Action: Run two overlapping publishes. Expected: Both finish and output integrity is preserved.",
        "- P0: Run two overlapping publishes.",
    )
    bad = bad.replace(
        "- AC-01 - Not covered: add `concurrentPublish` in `C:\\api-tests\\PublishIT.java`; API layer; setup fixture; poll status endpoint; timeout from suite configuration; assert terminal success and output integrity; cleanup fixture; tag `publishing-concurrency`.",
        "- AC-01 - Not covered: add a test under C:\\api-tests\\...",
    )

    errors = VALIDATOR.validate(bad)

    assert any("outside the required sections" in error for error in errors)
    assert any("authorization warning contradicts" in error for error in errors)
    assert any("exact AC-##" in error for error in errors)
    assert any("missing an AC mapping" in error for error in errors)
    assert any("ellipsis" in error for error in errors)
    assert any("automation recipe is missing" in error for error in errors)


def test_validator_rejects_confirmed_ac_when_native_jira_ac_is_empty():
    plan = _valid_plan().replace(
        "- AC-01 [Proposed]:",
        "- AC-01 [Confirmed]:",
    ).replace(
        "- Jira and current remote code support the proposed outcome; implementation choice remains open.",
        "- Jira native Acceptance Criteria field is empty; no Jira-authored AC exists.",
    )

    assert any("cannot be Confirmed" in error for error in VALIDATOR.validate(plan))


def test_validator_rejects_incomplete_historical_ticket_fields():
    plan = _valid_plan().replace(
        "- GUIDES-1 - Similarity: strongest match with the same concurrent publishing failure shape; Status: Closed; Resolution: Fixed; Affected version: unavailable; Fix version: unavailable; RCA: commit conflict; Test evidence: unavailable; Impact: adds concurrency regression coverage.",
        "- GUIDES-1 - Status: Closed; Resolution: Fixed.",
    )

    assert any("historical Jira entry is missing" in error for error in VALIDATOR.validate(plan))


def test_validator_rejects_missing_jira_understanding_confidence_bullet():
    plan = _valid_plan().replace(
        "- Evidence boundary: Supplied Jira evidence supports the problem; implementation and retry policy remain unverified.\n",
        "",
    )

    errors = VALIDATOR.validate(plan)

    assert any("exactly five confidence-check bullets" in error for error in errors)
    assert any("Evidence boundary" in error for error in errors)


def test_validator_requires_customer_context_resolution_in_jira_understanding():
    plan = _valid_plan().replace(
        "- Why it matters: Customer context resolved from Jira: JPMC from labels; a blocked publishing queue prevents documentation delivery.",
        "- Why it matters: A blocked publishing queue prevents documentation delivery.",
    )

    assert any("Customer context resolved from Jira" in error for error in VALIDATOR.validate(plan))


def test_validator_requires_named_and_sourced_customer_profile():
    plan = _valid_plan().replace(
        "**Known Jira Bugs / Past Similar Tickets**\n",
        "**Known Jira Bugs / Past Similar Tickets**\n"
        "- Observed Customer Jira Profile: JPMC - resolved from Jira label; profile customer-profile-v6; approval draft; 84 Jira keys including 50 Bug/Defect keys and 70 problem-report keys; test-data recommendations available; representative keys GUIDES-1; Aggregate context only.\n",
    )
    assert VALIDATOR.validate(plan) == []

    invalid = plan.replace(
        "- Observed Customer Jira Profile: JPMC - resolved from Jira label; profile customer-profile-v6; approval draft; 84 Jira keys including 50 Bug/Defect keys and 70 problem-report keys; test-data recommendations available; representative keys GUIDES-1; Aggregate context only.",
        "- Observed Customer Jira Profile: customer signals found.",
    )
    assert any("must name the resolved customer" in error for error in VALIDATOR.validate(invalid))


def test_validator_accepts_backticked_absolute_windows_path_with_spaces():
    plan = _valid_plan().replace(
        "`C:\\api-tests\\PublishIT.java`",
        "`C:\\UI TEST\\guides-ui-tests\\PublishIT.java`",
    )

    assert VALIDATOR.validate(plan) == []
