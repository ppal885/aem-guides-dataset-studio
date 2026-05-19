from __future__ import annotations

from app.core.schemas_chat_authoring import (
    ScreenshotClassificationAlternative,
    ScreenshotTypeClassification,
)
from app.services.screenshot_intent_router import ScreenshotIntentRouter


def _classification(
    screenshot_type: str,
    *,
    confidence: float = 0.82,
    reasons: list[str] | None = None,
    alternatives: list[ScreenshotClassificationAlternative] | None = None,
) -> ScreenshotTypeClassification:
    return ScreenshotTypeClassification(
        screenshot_type=screenshot_type,
        confidence=confidence,
        reasons=reasons or [f"classified as {screenshot_type}"],
        ambiguous_alternatives=alternatives or [],
    )


def test_routes_editor_structure_to_structure_reconstruction_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("editor_structure_screenshot"))
    assert decision.chosen_route == "structure_reconstruction_mode"
    assert decision.route_confidence >= 0.75
    assert decision.downstream_constraints


def test_routes_procedural_ui_to_procedural_authoring_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("procedural_ui_screenshot"))
    assert decision.chosen_route == "procedural_authoring_mode"
    assert decision.route_confidence >= 0.75


def test_routes_settings_reference_to_reference_extraction_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("settings_reference_screenshot"))
    assert decision.chosen_route == "reference_extraction_mode"
    assert decision.route_confidence >= 0.75


def test_routes_conceptual_diagram_to_conceptual_diagram_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("conceptual_diagram"))
    assert decision.chosen_route == "conceptual_diagram_mode"
    assert decision.route_confidence >= 0.75


def test_routes_mixed_content_to_mixed_content_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("mixed_content_screenshot", confidence=0.78))
    assert decision.chosen_route == "mixed_content_mode"
    assert decision.route_confidence >= 0.7


def test_routes_low_confidence_unknown_to_safe_fallback_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("low_confidence_unknown", confidence=0.46))
    assert decision.chosen_route == "safe_fallback_mode"
    assert decision.route_confidence >= 0.48
    assert any("conservative" in reason.lower() or "ambiguous" in reason.lower() for reason in decision.reasons)


def test_routes_generic_content_to_safe_fallback_mode():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("generic_content_screenshot", confidence=0.61))
    assert decision.chosen_route == "safe_fallback_mode"
    assert decision.downstream_constraints


def test_route_confidence_is_dampened_by_close_alternative():
    router = ScreenshotIntentRouter()
    decision = router.route(
        _classification(
            "procedural_ui_screenshot",
            confidence=0.68,
            alternatives=[
                ScreenshotClassificationAlternative(
                    screenshot_type="settings_reference_screenshot",
                    confidence=0.64,
                    reasons=["field/value panels are also visible"],
                )
            ],
        )
    )
    assert decision.chosen_route == "procedural_authoring_mode"
    assert decision.route_confidence < 0.68
    assert any("alternative screenshot type" in reason.lower() for reason in decision.reasons)


def test_route_decision_serializes_expected_aliases():
    router = ScreenshotIntentRouter()
    decision = router.route(_classification("editor_structure_screenshot"))
    payload = decision.model_dump(mode="json", by_alias=True)
    assert payload["chosenRoute"] == "structure_reconstruction_mode"
    assert "routeConfidence" in payload
    assert "downstreamConstraints" in payload
