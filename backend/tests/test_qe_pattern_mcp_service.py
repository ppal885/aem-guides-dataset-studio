from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.services.qe_pattern_mcp_service as pattern_service

from app.core.schemas_qe_pattern_mcp import (
    QePatternMateriality,
    QePatternProductionStatus,
    QePatternProvenance,
    QePatternProviderStatus,
    QePatternRecord,
    QePatternSupportGroup,
    QePatternValidationStatus,
    ResolveQePatternsRequest,
)
from app.services.qe_pattern_mcp_service import (
    PatternLibraryUnavailable,
    QePatternResolver,
    TrainV2PatternLibraryProvider,
    _pattern_version,
)


_SOURCE_HASH = "a" * 64


class _StaticProvider:
    provider_name = "TEST"

    def __init__(self, patterns: list[QePatternRecord]) -> None:
        self.patterns = patterns

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        return self.patterns, "fixture-v1", _SOURCE_HASH


class _UnavailableProvider:
    provider_name = "TEST"

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        raise PatternLibraryUnavailable("offline")


def _pattern(
    pattern_id: str,
    *,
    surface: str,
    signal: str,
    relationship: str,
    family: str,
    validation: QePatternValidationStatus = QePatternValidationStatus.APPROVED,
    production: QePatternProductionStatus = QePatternProductionStatus.ACTIVE,
    publishing_modes: list[str] | None = None,
    configuration_states: list[str] | None = None,
    hard_negatives: list[str] | None = None,
    customer_specific: bool = False,
    jira_specific: bool = False,
) -> QePatternRecord:
    approved = validation == QePatternValidationStatus.APPROVED
    supporting = ["case-alpha", "case-alpha-variant", "case-beta"]
    qualifying = supporting if approved else []
    groups = (
        [
            QePatternSupportGroup(
                group_id="incident-alpha",
                case_ids=["case-alpha", "case-alpha-variant"],
            ),
            QePatternSupportGroup(
                group_id="incident-beta",
                case_ids=["case-beta"],
            ),
        ]
        if approved
        else []
    )
    return QePatternRecord(
        pattern_id=pattern_id,
        pattern_version="fixture-v1",
        validation_status=validation,
        production_status=production,
        abstract_change_surface=[surface],
        applicable_domains=["PUBLISHING"],
        applicable_publishing_modes=publishing_modes or [],
        applicable_configuration_states=configuration_states or [],
        abstract_signals=[signal],
        question_families=[family],
        relationship_to_explore=[relationship],
        preferred_evidence_sources=["current contract", "implementation evidence"],
        materiality=QePatternMateriality.P1,
        blocking_default=True,
        human_support_count=len(qualifying),
        independent_case_count=len(groups),
        supporting_case_ids=supporting,
        qualifying_human_support_case_ids=qualifying,
        independent_support_groups=groups,
        counterexamples=[],
        hard_negatives=hard_negatives or [],
        confidence=0.9 if approved else None,
        customer_specific=customer_specific,
        jira_specific=jira_specific,
        provenance=QePatternProvenance(
            source_kind="TEST_FIXTURE",
            source_locator="tests/pattern-fixture.json",
            source_sha256=_SOURCE_HASH,
            source_schema_version="fixture-v1",
            derivation_partition="TEST_ONLY",
            human_backed=True,
            raw_human_uac_included=False,
            approval_overlay_sha256=_SOURCE_HASH if approved else None,
            approval_authority="HUMAN_QE" if approved else "NONE",
            validated_by="qe-reviewer" if approved else None,
            validated_at="2026-09-01T00:00:00Z" if approved else None,
        ),
    )


def _resolve(
    patterns: list[QePatternRecord],
    **request_overrides: object,
):
    payload: dict[str, object] = {
        "domain": "Publishing",
        "change_surfaces": ["output hierarchy"],
        "abstract_signals": ["structure controlling semantic"],
    }
    payload.update(request_overrides)
    request = ResolveQePatternsRequest(**payload)
    return QePatternResolver(_StaticProvider(patterns)).resolve(request)


def test_exact_abstract_match_is_deterministic() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )

    first = _resolve([pattern])
    second = _resolve([pattern])

    assert first == second
    assert first.provider_status == QePatternProviderStatus.SUCCESS
    assert [row.pattern.pattern_id for row in first.matched_patterns] == [
        "OUTPUT_HIERARCHY"
    ]
    assert first.matched_patterns[0].influence_allowed is True
    assert first.matched_patterns[0].blocking_recommendations == ["GOVERNING_STRUCTURE"]


def test_partial_abstract_match_is_supported() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="hierarchy relationship",
        family="GOVERNING_STRUCTURE",
    )
    response = _resolve(
        [pattern],
        change_surfaces=["generated output hierarchy relationship"],
        abstract_signals=["structure controlling behavior"],
    )

    assert response.provider_status == QePatternProviderStatus.SUCCESS
    assert response.matched_patterns[0].applicability_score > 0.5


def test_hard_negative_suppresses_positive_match() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
        hard_negatives=["read only tooltip"],
    )
    response = _resolve(
        [pattern],
        change_surfaces=["output hierarchy", "read only tooltip"],
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.matched_patterns == []
    assert response.suppressed_patterns[0].pattern_id == "OUTPUT_HIERARCHY"
    assert any(
        value.startswith("HARD_NEGATIVE:")
        for value in response.suppressed_patterns[0].counterexample_conflicts
    )


def test_counterexample_suppresses_positive_match() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    ).model_copy(update={"counterexamples": ["static tooltip only"]})
    response = _resolve(
        [pattern],
        change_surfaces=["output hierarchy", "static tooltip only"],
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert any(
        value.startswith("COUNTEREXAMPLE:")
        for value in response.suppressed_patterns[0].counterexample_conflicts
    )


def test_current_human_oos_overrides_historical_pattern() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )
    response = _resolve(
        [pattern],
        scope_constraints={
            "explicit_out_of_scope": ["output hierarchy is out of scope"]
        },
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.suppressed_patterns[0].pattern_id == "OUTPUT_HIERARCHY"
    assert any(
        value.startswith("CURRENT_EXPLICIT_OOS:")
        for value in response.suppressed_patterns[0].counterexample_conflicts
    )


def test_affirmative_current_human_decision_suppresses_historical_question() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )
    response = _resolve(
        [pattern],
        scope_constraints={"current_product_decisions": ["Use the output hierarchy"]},
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert any(
        value.startswith("CURRENT_PRODUCT_DECISION:")
        for value in response.suppressed_patterns[0].counterexample_conflicts
    )


def test_same_feature_area_different_change_surface_does_not_match() -> None:
    hierarchy = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )
    metadata = _pattern(
        "OUTPUT_METADATA",
        surface="metadata label fallback",
        signal="display mapping semantic",
        relationship="metadata precedence",
        family="GOVERNING_METADATA",
    )

    response = _resolve([metadata, hierarchy])

    assert [row.pattern.pattern_id for row in response.matched_patterns] == [
        "OUTPUT_HIERARCHY"
    ]


def test_matching_signal_cannot_override_wrong_change_surface() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )

    response = _resolve(
        [pattern],
        change_surfaces=["metadata label fallback"],
        abstract_signals=["structure controlling semantic"],
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.excluded_pattern_counts["CHANGE_SURFACE_MISMATCH"] == 1


def test_publishing_mode_filters_otherwise_equivalent_patterns() -> None:
    native_pdf = _pattern(
        "NATIVE_PDF_PATTERN",
        surface="output rendering",
        signal="publishing configuration",
        relationship="output rendering",
        family="PUBLISHING_CONFIGURATION",
        publishing_modes=["Native PDF"],
    )
    html5 = _pattern(
        "HTML5_PATTERN",
        surface="output rendering",
        signal="publishing configuration",
        relationship="output rendering",
        family="PUBLISHING_CONFIGURATION",
        publishing_modes=["HTML5"],
    )

    response = _resolve(
        [html5, native_pdf],
        change_surfaces=["output rendering"],
        abstract_signals=["publishing configuration"],
        publishing_mode="Native PDF",
    )

    assert [row.pattern.pattern_id for row in response.matched_patterns] == [
        "NATIVE_PDF_PATTERN"
    ]
    assert response.excluded_pattern_counts["PUBLISHING_MODE_MISMATCH"] == 1


def test_exact_mode_match_ranks_above_partial_match_before_result_limit() -> None:
    partial = _pattern(
        "AAA_PARTIAL_MODE",
        surface="output rendering",
        signal="publishing configuration",
        relationship="output rendering",
        family="PUBLISHING_CONFIGURATION",
        publishing_modes=["PDF"],
    )
    exact = _pattern(
        "ZZZ_EXACT_MODE",
        surface="output rendering",
        signal="publishing configuration",
        relationship="output rendering",
        family="PUBLISHING_CONFIGURATION",
        publishing_modes=["Native PDF"],
    )

    response = _resolve(
        [partial, exact],
        change_surfaces=["output rendering"],
        abstract_signals=["publishing configuration"],
        publishing_mode="Native PDF",
        max_results=1,
    )

    assert [row.pattern.pattern_id for row in response.matched_patterns] == [
        "ZZZ_EXACT_MODE"
    ]


def test_configuration_state_filters_otherwise_equivalent_patterns() -> None:
    enabled = _pattern(
        "CONFIG_ENABLED_PATTERN",
        surface="conditional behavior",
        signal="configuration relationship",
        relationship="conditional behavior",
        family="CONFIGURATION_STATE",
        configuration_states=["enabled"],
    )
    disabled = _pattern(
        "CONFIG_DISABLED_PATTERN",
        surface="conditional behavior",
        signal="configuration relationship",
        relationship="conditional behavior",
        family="CONFIGURATION_STATE",
        configuration_states=["disabled"],
    )

    response = _resolve(
        [disabled, enabled],
        change_surfaces=["conditional behavior"],
        abstract_signals=["configuration relationship"],
        configuration_state="enabled",
    )

    assert [row.pattern.pattern_id for row in response.matched_patterns] == [
        "CONFIG_ENABLED_PATTERN"
    ]
    assert response.excluded_pattern_counts["CONFIGURATION_STATE_MISMATCH"] == 1


def test_mode_specific_human_oos_overrides_historical_pattern() -> None:
    pattern = _pattern(
        "NATIVE_PDF_PATTERN",
        surface="output rendering",
        signal="publishing configuration",
        relationship="output rendering",
        family="PUBLISHING_CONFIGURATION",
        publishing_modes=["Native PDF"],
    )

    response = _resolve(
        [pattern],
        change_surfaces=["output rendering"],
        abstract_signals=["publishing configuration"],
        publishing_mode="Native PDF",
        scope_constraints={"explicit_out_of_scope": ["Native PDF is out of scope"]},
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert any(
        value.startswith("CURRENT_EXPLICIT_OOS:Native PDF")
        for value in response.suppressed_patterns[0].counterexample_conflicts
    )


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("customer_specific", "CUSTOMER_SPECIFIC_PATTERN_REJECTED"),
        ("jira_specific", "JIRA_SPECIFIC_PATTERN_REJECTED"),
    ],
)
def test_specific_patterns_are_rejected(field: str, reason: str) -> None:
    kwargs = {field: True}
    pattern = _pattern(
        "SPECIFIC_PATTERN",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
        **kwargs,
    )

    response = _resolve([pattern], include_analysis_candidates=True)

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.excluded_pattern_counts[reason] == 1


def test_unvalidated_pattern_is_analysis_only() -> None:
    pattern = _pattern(
        "ANALYSIS_PATTERN",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
        validation=QePatternValidationStatus.HUMAN_BACKED_CANDIDATE,
        production=QePatternProductionStatus.ANALYSIS_ONLY,
    )

    production_response = _resolve([pattern])
    analysis_response = _resolve([pattern], include_analysis_candidates=True)

    assert production_response.provider_status == QePatternProviderStatus.EMPTY
    assert analysis_response.provider_status == QePatternProviderStatus.SUCCESS
    assert analysis_response.matched_patterns[0].influence_allowed is False
    assert analysis_response.matched_patterns[0].blocking_recommendations == []


def test_duplicate_variants_do_not_inflate_independent_support() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )

    assert pattern.human_support_count == 3
    assert pattern.independent_case_count == 2
    assert pattern.independent_support_groups[0].case_ids == [
        "case-alpha",
        "case-alpha-variant",
    ]


def test_same_case_cannot_inflate_multiple_independent_groups() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )
    payload = pattern.model_dump(mode="json")
    payload["independent_support_groups"] = [
        {"group_id": "incident-alpha", "case_ids": ["case-alpha"]},
        {"group_id": "incident-beta", "case_ids": ["case-alpha", "case-beta"]},
    ]

    with pytest.raises(ValidationError, match="only one independent support group"):
        QePatternRecord.model_validate(payload)


def test_jira_key_alone_cannot_create_an_abstract_match() -> None:
    pattern = _pattern(
        "OUTPUT_HIERARCHY",
        surface="output hierarchy",
        signal="structure controlling semantic",
        relationship="output hierarchy",
        family="GOVERNING_STRUCTURE",
    )

    response = _resolve(
        [pattern],
        change_surfaces=["GUIDES-47692"],
        abstract_signals=["GUIDES-47692"],
    )

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.excluded_pattern_counts["CHANGE_SURFACE_MISMATCH"] == 1
    assert response.excluded_pattern_counts["ABSTRACT_SIGNAL_MISMATCH"] == 1


def test_provider_unavailable_is_fail_closed() -> None:
    response = QePatternResolver(_UnavailableProvider()).resolve(
        ResolveQePatternsRequest(
            domain="Publishing",
            change_surfaces=["output hierarchy"],
        )
    )

    assert response.provider_status == QePatternProviderStatus.UNAVAILABLE
    assert response.matched_patterns == []
    assert response.validated_production_pattern_count == 0


def test_blank_domain_is_rejected_during_request_validation() -> None:
    with pytest.raises(ValidationError, match="domain must not be blank"):
        ResolveQePatternsRequest(
            domain="   ",
            change_surfaces=["output hierarchy"],
        )


def test_string_false_cannot_enable_analysis_candidates() -> None:
    with pytest.raises(ValidationError):
        ResolveQePatternsRequest(
            domain="Publishing",
            change_surfaces=["output hierarchy"],
            include_analysis_candidates="false",  # type: ignore[arg-type]
        )


def test_empty_library_is_a_valid_empty_result() -> None:
    response = _resolve([])

    assert response.provider_status == QePatternProviderStatus.EMPTY
    assert response.pattern_count == 0
    assert response.matched_patterns == []


def test_existing_train_library_is_adapted_without_production_promotion() -> None:
    records, version, source_hash = TrainV2PatternLibraryProvider().load()

    assert version == "V2"
    assert len(source_hash) == 64
    assert len(records) == 33
    assert all(
        row.validation_status == QePatternValidationStatus.HUMAN_BACKED_CANDIDATE
        for row in records
    )
    assert all(row.production_influence_allowed is False for row in records)
    assert all(row.human_support_count == 0 for row in records)
    assert all(row.independent_case_count == 0 for row in records)
    assert all(not row.supporting_case_ids for row in records)
    assert all(row.provenance.candidate_source_case_ids for row in records)
    assert all(not row.applicable_domains for row in records)
    assert all(not row.counterexamples for row in records)
    assert all(row.activation_guardrails for row in records)
    assert all(row.provenance.human_backed for row in records)
    assert all(not row.provenance.raw_human_uac_included for row in records)


def test_missing_train_provider_path_reports_unavailable(tmp_path: Path) -> None:
    provider = TrainV2PatternLibraryProvider(
        library_path=tmp_path / "missing.json",
    )
    response = QePatternResolver(provider).resolve(
        ResolveQePatternsRequest(
            domain="Publishing",
            abstract_signals=["structure controlling semantic"],
        )
    )

    assert response.provider_status == QePatternProviderStatus.UNAVAILABLE
    assert response.matched_patterns == []


def _approval_provider(
    tmp_path: Path,
    **approval_overrides: object,
) -> TrainV2PatternLibraryProvider:
    repository_root = Path(__file__).resolve().parents[2]
    library_path = (
        repository_root
        / "benchmark"
        / "v2"
        / "train_mining"
        / "reasoning_pattern_taxonomy_train_v2.json"
    )
    library_bytes = library_path.read_bytes()
    library = json.loads(library_bytes.decode("utf-8"))
    raw_pattern = library["patterns"][0]
    case_id = raw_pattern["source_jiras"][0]
    approval: dict[str, object] = {
        "pattern_id": raw_pattern["pattern_id"],
        "pattern_version": _pattern_version(raw_pattern),
        "source_sha256": hashlib.sha256(library_bytes).hexdigest(),
        "approval_authority": "HUMAN_QE",
        "validated_by": "qe-reviewer",
        "validated_at": "2026-09-01T00:00:00+00:00",
        "production_status": "ACTIVE",
        "abstract_change_surface": ["output hierarchy"],
        "applicable_domains": ["PUBLISHING"],
        "applicable_publishing_modes": ["Native PDF"],
        "applicable_configuration_states": ["template selected"],
        "abstract_signals": ["structure controlling semantic"],
        "question_families": ["GOVERNING_STRUCTURE"],
        "relationship_to_explore": ["output hierarchy"],
        "preferred_evidence_sources": ["current contract"],
        "materiality": "P1",
        "blocking_default": True,
        "qualifying_human_support_case_ids": [case_id],
        "independent_support_groups": [
            {"group_id": "independent-case-1", "case_ids": [case_id]}
        ],
        "counterexamples": ["static tooltip only"],
        "hard_negatives": ["unrelated display label"],
        "confidence": 0.9,
        "customer_specific": False,
        "jira_specific": False,
    }
    approval.update(approval_overrides)
    approval_path = tmp_path / "approvals.json"
    approval_path.write_text(
        json.dumps(
            {
                "schema_version": "aem-guides-qe-pattern-approvals-v1",
                "approvals": [approval],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return TrainV2PatternLibraryProvider(
        library_path=library_path,
        approval_path=approval_path,
    )


def test_real_approval_overlay_can_activate_one_versioned_generic_pattern(
    tmp_path: Path,
) -> None:
    provider = _approval_provider(tmp_path)
    records, _, _ = provider.load()
    active = [row for row in records if row.production_influence_allowed]

    assert len(active) == 1
    assert "+approval-" in active[0].pattern_version
    assert active[0].provenance.approval_overlay_sha256 is not None
    assert active[0].human_support_count == 1
    assert active[0].independent_case_count == 1

    response = QePatternResolver(provider).resolve(
        ResolveQePatternsRequest(
            domain="Publishing",
            change_surfaces=["output hierarchy"],
            abstract_signals=["structure controlling semantic"],
            publishing_mode="Native PDF",
            configuration_state="template selected",
        )
    )
    assert response.validated_production_pattern_count == 1
    assert [row.pattern.pattern_id for row in response.matched_patterns] == [
        active[0].pattern_id
    ]


def test_train_provider_reuses_only_the_same_versioned_file_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _approval_provider(tmp_path)
    original_reader = pattern_service._read_json_object
    read_paths: list[Path] = []

    def counted_reader(path: Path):
        read_paths.append(path)
        return original_reader(path)

    monkeypatch.setattr(pattern_service, "_read_json_object", counted_reader)
    first = provider.load()
    second = provider.load()

    assert first == second
    assert first is not second
    assert first[0] is not second[0]
    assert len(read_paths) == 2

    first[0].clear()
    third = provider.load()
    assert third[0]
    assert len(read_paths) == 2


def test_deep_json_parser_failure_is_reported_as_invalid_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _approval_provider(tmp_path)

    def fail_for_excessive_depth(_value: str):
        raise RecursionError("synthetic excessive nesting")

    monkeypatch.setattr(pattern_service.json, "loads", fail_for_excessive_depth)
    response = QePatternResolver(provider).resolve(
        ResolveQePatternsRequest(
            domain="Publishing",
            change_surfaces=["output hierarchy"],
            abstract_signals=["structure controlling semantic"],
        )
    )

    assert response.provider_status == QePatternProviderStatus.INVALID_LIBRARY
    assert response.error_code == "QE_PATTERN_LIBRARY_INVALID"


@pytest.mark.parametrize(
    "approval_overrides",
    [
        {"pattern_version": "train-v2-stale00000000"},
        {"source_sha256": "b" * 64},
        {"approval_authority": "AI_REVIEW"},
        {"validated_by": "   "},
        {"validated_at": "2026-09-01T00:00:00"},
    ],
)
def test_invalid_or_stale_real_approval_overlay_fails_closed(
    tmp_path: Path,
    approval_overrides: dict[str, object],
) -> None:
    provider = _approval_provider(tmp_path, **approval_overrides)
    response = QePatternResolver(provider).resolve(
        ResolveQePatternsRequest(
            domain="Publishing",
            change_surfaces=["output hierarchy"],
        )
    )

    assert response.provider_status == QePatternProviderStatus.INVALID_LIBRARY
    assert response.validated_production_pattern_count == 0
    assert response.error_code == "QE_PATTERN_LIBRARY_INVALID"
