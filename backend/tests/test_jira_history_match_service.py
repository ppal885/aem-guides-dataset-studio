from app.services.jira_history_match_service import build_historical_match_contract


def test_exact_api_route_qualifies_same_mechanism():
    result = build_historical_match_contract(
        "Manage action fails in /bin/guides/v1/map/reports/metadata/tags/common",
        {
            "summary": "Metadata manage API times out",
            "root_cause": "Traversal in /bin/guides/v1/map/reports/metadata/tags/common",
        },
    )

    assert result["qualified"] is True
    assert result["strength"] == "exact"
    assert any("API route" in signal for signal in result["shared_exact_signals"])


def test_verified_root_cause_with_specific_terms_qualifies_structurally():
    result = build_historical_match_contract(
        "xref scope is dropped by the serializer",
        {
            "summary": "Published xref loses scope",
            "root_cause": "Scope omitted by the shared serializer",
            "learning": {"is_verified_fix": True},
        },
    )

    assert result["qualified"] is True
    assert result["strength"] == "structural"
    assert {"scope", "serializer"}.issubset(result["shared_specific_terms"])


def test_component_and_customer_overlap_never_qualify():
    result = build_historical_match_contract(
        "new editor toolbar button is missing for KONE",
        {
            "summary": "Unrelated editor search issue for KONE",
            "matching_components": ["Editor"],
            "matching_customers": ["KONE"],
        },
    )

    assert result["qualified"] is False
    assert result["area_only_rejected"] is True
    assert result["customer_component_are_ranking_only"] is True


def test_dita_output_symptom_combination_qualifies_without_area_filtering():
    result = build_historical_match_contract(
        "MathML outputclass is missing from Native PDF merged HTML",
        {
            "summary": "MathML outputclass dropped from Native PDF merged HTML",
            "matching_entities": ["mathml"],
            "matching_outputs": ["Native PDF"],
        },
    )

    assert result["qualified"] is True
    assert result["shared_dita_entities"] == ["mathml"]
    assert result["shared_outputs"] == ["native-pdf"]


def test_map_preview_scroll_does_not_match_author_canvas_viewport_by_area_alone():
    result = build_historical_match_contract(
        "In Author view, editing a long topic jumps the editor canvas to the document top and loses the active cursor location.",
        {
            "summary": "Map Preview restores its scroll position after returning from Edit",
            "document": (
                "Map Preview must retain the selected topic, condition panel state, and scroll "
                "position when the user returns from Edit."
            ),
            "matching_components": ["Editor"],
        },
    )

    assert result["qualified"] is False
    assert result["strength"] == "unproven"
    assert result["mechanism_score"] == 0.2
    assert result["evidence_types"] == ["cross_surface_scroll_overlap_only"]
    assert "different mechanisms" in result["reason"]


def test_cross_surface_scroll_can_match_only_with_shared_restoration_evidence():
    result = build_historical_match_contract(
        "Author canvas must restore the active editing position after reference insertion.",
        {
            "summary": "Map Preview state restoration",
            "document": (
                "Map Preview must restore the active editing position when returning from the "
                "editor, using the shared editor-scroll state restoration mechanism."
            ),
            "learning": {
                "is_verified_fix": True,
                "root_cause": "The shared editor-scroll state restoration anchor was discarded.",
            },
        },
    )

    assert result["qualified"] is True
    assert result["strength"] == "structural"
