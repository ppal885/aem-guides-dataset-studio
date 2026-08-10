from app.services.jira_version_applicability_service import (
    canonical_version,
    classify_version_applicability,
)


def test_version_normalization_is_format_only():
    assert canonical_version("AEM Guides 5.0 SP3") == "5.0-sp3"
    assert canonical_version("2606") == "2606"


def test_same_release_is_a_soft_positive_signal():
    result = classify_version_applicability(
        current_affected_versions=["5.0 SP3"],
        historical_fix_versions=["AEM Guides 5.0 SP3"],
    )

    assert result["classification"] == "same_release"
    assert result["shared_versions"] == ["5.0-sp3"]
    assert result["hard_filter_allowed"] is False
    assert result["usable_as_current_expected_behavior"] is False


def test_different_release_is_retained_with_revalidation_warning():
    result = classify_version_applicability(
        current_affected_versions=["2609"],
        historical_fix_versions=["2502"],
    )

    assert result["classification"] == "different_release"
    assert result["relative_age"] == "historical_older"
    assert result["ranking_multiplier"] < 1
    assert result["requires_current_ticket_validation"] is True


def test_missing_release_data_is_unknown_not_filtered():
    result = classify_version_applicability(
        current_affected_versions=[],
        historical_fix_versions=["2502"],
    )

    assert result["classification"] == "unknown"
    assert result["hard_filter_allowed"] is False
