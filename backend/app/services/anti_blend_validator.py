"""
Anti-blending validator - ensures recipe family matches classified mechanism.

Rejects xref recipe for keyref issue, conref/ditaval unless evidence requires.
"""
from typing import Optional

from app.core.structured_logging import get_structured_logger
from app.services.recipe_scoring_service import (
    RECIPE_FAMILY,
    GENERIC_XREF_RECIPES,
    validate_no_cross_feature_blend,
)

logger = get_structured_logger(__name__)


class ValidationResult:
    """Result of anti-blending validation."""

    def __init__(self, valid: bool, reason: str = ""):
        self.valid = valid
        self.reason = reason


def validate_recipe_family_match(
    selected_feature: str,
    selected_recipe: str,
    spec: Optional[object] = None,
) -> ValidationResult:
    """
    Validate that recipe family matches selected feature.
    If selected_feature is keyref and recipe is xref/conref/ditaval: invalid.
    """
    is_valid, cross_feature_blocked = validate_no_cross_feature_blend(selected_feature, selected_recipe)

    if not is_valid:
        return ValidationResult(valid=False, reason="Recipe family mismatch")

    recipe_family = RECIPE_FAMILY.get(selected_recipe, "")
    if recipe_family and recipe_family != selected_feature:
        logger.info_structured(
            "Anti-blend: recipe family mismatch",
            extra_fields={
                "selected_feature": selected_feature,
                "selected_recipe": selected_recipe,
                "recipe_family": recipe_family,
            },
        )
        return ValidationResult(valid=False, reason=f"Recipe {selected_recipe} is {recipe_family}, expected {selected_feature}")

    return ValidationResult(valid=True, reason="OK")
