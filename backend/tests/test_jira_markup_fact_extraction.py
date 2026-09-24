"""Jira wiki section headings and reproduction steps are not expected behavior.

A heading such as ``*+Expected Behavior:+*`` or a ``#`` step under
``*+Steps to reproduce:+*`` used to become an expected-behavior contract fact.
That printed raw markup as acceptance criteria and, through
``current_product_decisions``, suppressed applicable QE patterns by token overlap.
"""

from __future__ import annotations

from typing import Any

from app.core.schemas_canonical_test_plan_runtime import (
    AbstractSignalKind,
    ChangeSurfaceKind,
    ContractFactType,
    EvidenceSourceType,
    GenerationProfile,
    IssueDomain,
    PatternLookupRuntimeStatus,
    RuntimeEntryPoint,
)
from app.core.schemas_qe_pattern_mcp import (
    QePatternMateriality,
    QePatternProductionStatus,
    QePatternProvenance,
    QePatternRecord,
    QePatternSupportGroup,
    QePatternValidationStatus,
)
from app.services.canonical_evidence_service import normalize_legacy_packet
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.qe_pattern_mcp_service import QePatternResolver

_HASH = "b" * 64
_HEADINGS = ("+*Issue Summary:*+", "+Steps to reproduce:+", "+Expected Behavior:+")
_STEPS = (
    "# Open a long topic in the editor",
    "# Scroll to the last paragraph and type a few characters",
    "# Press Undo",
)
_EXPECTED = "The editor should keep the current scroll position after Undo"
_DESCRIPTION = "\n".join(
    [
        "+*Issue Summary:*+",
        "After Undo the editor jumps from the end of a long topic to the top.",
        "*+Steps to reproduce:+*",
        " # Open a long topic in the editor",
        " # Scroll to the last paragraph and type a few characters",
        " # Press Undo",
        "*+Expected Behavior:+*",
        f"{_EXPECTED}.",
        "*+Environment Details:+*",
    ]
)
_BEHAVIOR_FACTS = {
    ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
    ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
}


def _facts(issue: dict[str, Any]):
    bundle = normalize_legacy_packet(
        {"jira_key": "GUIDES-TEST", "issue": issue}, tenant_id="markup-facts-test"
    )
    return CANONICAL_REASONING_SERVICE.extract_contract_facts(bundle).facts


def test_markup_headings_and_reproduction_steps_are_not_expected_behavior() -> None:
    facts = _facts({"issue_key": "GUIDES-TEST", "description": _DESCRIPTION})
    literals = {row.literal.strip() for row in facts}

    for heading in (*_HEADINGS, "+Environment Details:+"):
        assert heading not in literals
    behavior = {row.literal.strip() for row in facts if row.fact_type in _BEHAVIOR_FACTS}
    for step in _STEPS:
        assert step not in behavior
    assert any(_EXPECTED in literal for literal in behavior)


def test_heading_variants_and_setup_to_reproduce_section() -> None:
    nested = "+*Product Side Expected Behaviour* (As discussed with the team):+"
    requirement = "# Replace all should skip files checked out by other users"
    sentence = "*Note:* the dialog must close *immediately* after Cancel"
    facts = _facts(
        {
            "issue_key": "GUIDES-TEST",
            "description": "\n".join(
                [
                    "*Attachment / Setup to reproduce the issue*",
                    " # Install the sample content package",
                    " # You will notice the issue as described",
                    nested,
                    f" {requirement}",
                    sentence,
                ]
            ),
        }
    )
    literals = {row.literal.strip() for row in facts}
    behavior = {row.literal.strip() for row in facts if row.fact_type in _BEHAVIOR_FACTS}

    assert nested not in literals
    assert "# Install the sample content package" not in behavior
    assert "# You will notice the issue as described" not in behavior
    assert requirement in behavior
    assert any("must close" in literal for literal in behavior)


def test_reproduction_scenarios_with_expected_results_stay_behavior() -> None:
    expected_step = "Edit and save the template, the properties should keep their values"
    facts = _facts(
        {
            "issue_key": "GUIDES-TEST",
            "description": "\n".join(
                [
                    "*Test data and steps to reproduce the scenario*",
                    f" * {expected_step}",
                    " * Add this template to the folder profile",
                ]
            ),
        }
    )
    behavior = {row.literal.strip() for row in facts if row.fact_type in _BEHAVIOR_FACTS}

    assert any("should keep their values" in literal for literal in behavior)
    assert "Add this template to the folder profile" not in behavior


def test_accepted_criteria_keep_numbered_items_and_drop_only_bare_headings() -> None:
    facts = _facts(
        {
            "issue_key": "GUIDES-TEST",
            "description": "Undo moves the editor to the top of the topic.",
            "acceptance_criteria": "\n".join(
                [
                    "*+Support matrix:+*",
                    " # Browser: the scroll position is kept in Chrome and Firefox",
                    "h3. Upgrade impact: None",
                ]
            ),
        }
    )
    accepted = {
        row.literal.strip()
        for row in facts
        if row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
    }

    assert "+Support matrix:+" not in {row.literal.strip() for row in facts}
    assert "# Browser: the scroll position is kept in Chrome and Firefox" in accepted
    assert any(literal.endswith("Upgrade impact: None") for literal in accepted)


class _StaticLibraryProvider:
    provider_name = "MARKUP_FACTS_TEST_LIBRARY"

    def __init__(self, patterns: list[QePatternRecord]) -> None:
        self._patterns = patterns

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        return self._patterns, "markup-facts-test-library-v1", _HASH


class _RecordingResolver:
    def __init__(self, delegate: QePatternResolver) -> None:
        self.delegate = delegate
        self.requests: list[Any] = []

    def resolve(self, request: Any) -> Any:
        self.requests.append(request)
        return self.delegate.resolve(request)


def _pattern(pattern_id: str, *, domain: IssueDomain, relationship: str) -> QePatternRecord:
    case_id = f"CASE-{pattern_id}"
    return QePatternRecord(
        pattern_id=pattern_id,
        pattern_version="fixture-v1",
        validation_status=QePatternValidationStatus.APPROVED,
        production_status=QePatternProductionStatus.ACTIVE,
        abstract_change_surface=[ChangeSurfaceKind.CHANGED_BEHAVIOR.value],
        applicable_domains=[domain.value],
        abstract_signals=[AbstractSignalKind.CHANGED_BEHAVIOR.value],
        question_families=["GOVERNING_SEMANTICS"],
        relationship_to_explore=[relationship],
        preferred_evidence_sources=[EvidenceSourceType.JIRA_DESCRIPTION.value],
        materiality=QePatternMateriality.P2,
        blocking_default=False,
        human_support_count=1,
        independent_case_count=1,
        supporting_case_ids=[case_id],
        qualifying_human_support_case_ids=[case_id],
        independent_support_groups=[
            QePatternSupportGroup(group_id="independent-case", case_ids=[case_id])
        ],
        confidence=0.8,
        customer_specific=False,
        jira_specific=False,
        provenance=QePatternProvenance(
            source_kind="TEST_FIXTURE",
            source_locator="tests/markup-facts",
            source_sha256=_HASH,
            source_schema_version="markup-facts-test-v1",
            derivation_partition="TEST_ONLY",
            human_backed=True,
            raw_human_uac_included=False,
            candidate_source_case_ids=[case_id],
            approval_overlay_sha256=_HASH,
            approval_authority="HUMAN_QE",
            validated_by="test reviewer",
            validated_at="2026-09-01T00:00:00Z",
        ),
    )


def test_markup_heading_neither_becomes_an_ac_nor_suppresses_an_applicable_pattern() -> None:
    resolver = _RecordingResolver(
        QePatternResolver(
            _StaticLibraryProvider(
                [
                    _pattern(
                        "EDITOR_BEHAVIOR_STABILITY",
                        domain=IssueDomain.AUTHORING,
                        relationship="editor behavior stability",
                    ),
                    _pattern(
                        "PUBLISHING_ONLY_PATTERN",
                        domain=IssueDomain.PUBLISHING,
                        relationship="output hierarchy",
                    ),
                ]
            )
        )
    )
    runtime = CanonicalTestPlanRuntime(pattern_resolver=resolver)
    request = runtime.build_request(
        jira_key="GUIDES-TEST",
        tenant_id="markup-facts-test",
        entry_point=RuntimeEntryPoint.CLI,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = runtime.generate_backend_compatibility(
        request=request,
        packet={
            "jira_key": "GUIDES-TEST",
            "issue": {
                "issue_key": "GUIDES-TEST",
                "summary": "Undo moves the editor to the top of the topic",
                "description": _DESCRIPTION,
                "components": ["Authoring"],
            },
        },
    )
    payload = result.output_payload

    written = [row["outcome"] for row in payload["written_acceptance_criteria"]]
    for text in written:
        assert not any(heading in text for heading in _HEADINGS)
        assert not any(step in text for step in _STEPS)

    assert resolver.requests
    for lookup in resolver.requests:
        decisions = lookup.scope_constraints.current_product_decisions
        assert not any(heading in decision for heading in _HEADINGS for decision in decisions)

    lookup = payload["qe_investigation"]["pattern_lookup"]
    assert lookup["status"] == PatternLookupRuntimeStatus.AVAILABLE_MATCH.value
    matched = {row["pattern_id"] for row in payload["qe_investigation"]["matched_human_patterns"]}
    assert matched == {"EDITOR_BEHAVIOR_STABILITY"}
