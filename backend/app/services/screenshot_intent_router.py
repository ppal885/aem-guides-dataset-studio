from __future__ import annotations

from app.core.schemas_topic_generation import (
    ScreenshotClassificationAlternative,
    ScreenshotIntentRoute,
    ScreenshotIntentRouteDecision,
    ScreenshotType,
    ScreenshotTypeClassification,
)

_TYPE_TO_ROUTE: dict[ScreenshotType, ScreenshotIntentRoute] = {
    "editor_structure_screenshot": "structure_reconstruction_mode",
    "procedural_ui_screenshot": "procedural_authoring_mode",
    "settings_reference_screenshot": "reference_extraction_mode",
    "conceptual_diagram": "conceptual_diagram_mode",
    "mixed_content_screenshot": "mixed_content_mode",
    "generic_content_screenshot": "safe_fallback_mode",
    "low_confidence_unknown": "safe_fallback_mode",
}

_ROUTE_CONSTRAINTS: dict[ScreenshotIntentRoute, list[str]] = {
    "structure_reconstruction_mode": [
        "Prioritize structural reconstruction over authored explanatory prose.",
        "Preserve visible editor hierarchy, chips, and UI structure before inferring content semantics.",
        "Do not convert editor layout into procedural steps unless explicit numbered evidence exists.",
    ],
    "procedural_authoring_mode": [
        "Preserve ordered steps, substeps, step notes, and UI controls as procedural evidence.",
        "Prefer task-oriented downstream planning and avoid flattening step information into paragraphs.",
        "Do not infer missing steps when the screenshot evidence is incomplete.",
    ],
    "reference_extraction_mode": [
        "Preserve field/value associations, settings sections, tabs, and parameter tables exactly.",
        "Prefer reference-style downstream planning over conceptual or procedural reshaping.",
        "Do not collapse configuration panels into generic descriptive paragraphs.",
    ],
    "conceptual_diagram_mode": [
        "Preserve entities, relationships, hierarchy, and grouping as conceptual structure.",
        "Prefer conceptual downstream planning; do not force procedural steps from labeled nodes alone.",
        "Retain ambiguous diagram semantics in warnings rather than inventing workflow actions.",
    ],
    "mixed_content_mode": [
        "Preserve multiple coexisting content modes instead of forcing one dominant topic shape too early.",
        "Keep procedural, reference, and conceptual evidence separated for downstream planning.",
        "Surface ambiguities explicitly when specialized screenshot signals compete.",
    ],
    "safe_fallback_mode": [
        "Preserve ambiguity and unresolved blocks instead of over-structuring weak evidence.",
        "Avoid forcing a specialized topic route until stronger evidence is available.",
        "Carry low-confidence warnings forward for downstream planning and UI review.",
    ],
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


class ScreenshotIntentRouter:
    """Deterministic post-classification router for screenshot authoring intent."""

    def route(self, classification: ScreenshotTypeClassification) -> ScreenshotIntentRouteDecision:
        chosen_route = _TYPE_TO_ROUTE.get(classification.screenshot_type, "safe_fallback_mode")
        route_confidence = self._route_confidence(classification, chosen_route=chosen_route)
        reasons = self._reasons(classification=classification, chosen_route=chosen_route, route_confidence=route_confidence)
        constraints = list(_ROUTE_CONSTRAINTS[chosen_route])
        if route_confidence < 0.55 and chosen_route != "safe_fallback_mode":
            constraints.append("Treat this route as provisional because the routing evidence is still ambiguous.")
        return ScreenshotIntentRouteDecision(
            chosen_route=chosen_route,
            route_confidence=route_confidence,
            reasons=reasons,
            downstream_constraints=constraints,
        )

    def _route_confidence(
        self,
        classification: ScreenshotTypeClassification,
        *,
        chosen_route: ScreenshotIntentRoute,
    ) -> float:
        confidence = classification.confidence
        if chosen_route == "safe_fallback_mode":
            confidence = max(confidence, 0.52)

        top_alt = classification.ambiguous_alternatives[0] if classification.ambiguous_alternatives else None
        if top_alt is not None:
            gap = max(0.0, classification.confidence - top_alt.confidence)
            if gap < 0.08:
                confidence -= 0.12
            elif gap < 0.14:
                confidence -= 0.08
            elif gap < 0.2:
                confidence -= 0.04

        if classification.screenshot_type == "low_confidence_unknown":
            confidence = max(0.48, min(confidence, 0.7))
        return _clamp(confidence)

    def _reasons(
        self,
        *,
        classification: ScreenshotTypeClassification,
        chosen_route: ScreenshotIntentRoute,
        route_confidence: float,
    ) -> list[str]:
        reasons = list(classification.reasons[:4])
        reasons.append(
            f"Mapped screenshot type {classification.screenshot_type} to route {chosen_route}."
        )
        top_alt = classification.ambiguous_alternatives[0] if classification.ambiguous_alternatives else None
        if top_alt is not None and self._routes_differ(top_alt, chosen_route):
            reasons.append(
                f"Alternative screenshot type {top_alt.screenshot_type} remained plausible at {top_alt.confidence:.2f} confidence."
            )
        if route_confidence < 0.55:
            reasons.append("Route confidence is intentionally conservative because the screenshot evidence remains ambiguous.")
        return reasons

    def _routes_differ(
        self,
        alternative: ScreenshotClassificationAlternative,
        chosen_route: ScreenshotIntentRoute,
    ) -> bool:
        return _TYPE_TO_ROUTE.get(alternative.screenshot_type, "safe_fallback_mode") != chosen_route

