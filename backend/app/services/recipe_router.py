"""
Deterministic recipe routing - (feature, pattern) -> recipe_id.

Pure code; no LLM. Used after mechanism and pattern classification.
Applies routing overrides from feedback when evidence matches learned keywords
or is similar to past corrected evidence.
"""
from app.core.schemas_pipeline import RecipeSelection
from app.services.recipe_scoring_service import ROUTE_TABLE, RECIPE_FAMILY
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _route_from_evidence_similarity(evidence_text: str) -> RecipeSelection | None:
    """If evidence is similar to past corrected evidence, return override RecipeSelection."""
    if not evidence_text:
        return None
    try:
        from app.services.feedback_aggregation_service import load_routing_overrides
        from app.services.feedback_evidence_service import find_similar_feedback_recipe

        overrides = load_routing_overrides()
        pairs = overrides.get("evidence_similarity_pairs") or []
        if not pairs:
            return None
        result = find_similar_feedback_recipe(evidence_text, pairs)
        if not result:
            return None
        expected_recipe, similarity = result
        feature, pattern = None, None
        for (f, p), rid in ROUTE_TABLE.items():
            if rid == expected_recipe:
                feature, pattern = f, p
                break
        if not feature:
            feature = "keyref"
            pattern = "basic_key_resolution"
        logger.info_structured(
            "Recipe override from evidence similarity",
            extra_fields={"expected_recipe": expected_recipe, "similarity": round(similarity, 2)},
        )
        return RecipeSelection(
            selected_feature=feature,
            selected_pattern=pattern or "media_rich",
            selected_recipe=expected_recipe,
            route_reason=f"override:feedback_similarity:{round(similarity, 2)}",
            cross_feature_blocked=False,
        )
    except Exception:
        pass
    return None


def _route_from_override(evidence_text: str) -> RecipeSelection | None:
    """If evidence matches routing override keywords, return override RecipeSelection.
    Skips media_rich_content override when evidence has strong RTE/inline_formatting signal
    (e.g. cursor, arrow keys, <i>/<b>/<u> tags) - avoids misrouting RTE issues that mention
    "customer's video" to media_rich_content.
    """
    if not evidence_text:
        return None
    try:
        from app.services.feedback_aggregation_service import load_routing_overrides
        from app.utils.evidence_context import evidence_has_inline_formatting_rte_signal

        overrides = load_routing_overrides()
        keywords_map = overrides.get("jira_evidence_keywords") or {}
        text_lower = evidence_text.lower()
        for kw, recipe_id in keywords_map.items():
            if kw.lower() in text_lower and recipe_id:
                # Skip media/image_reference override when evidence is primarily about RTE/cursor
                if RECIPE_FAMILY.get(recipe_id) == "image_reference" and evidence_has_inline_formatting_rte_signal(evidence_text):
                    logger.info_structured(
                        "Skipping routing override: inline_formatting has stronger signal",
                        extra_fields={"keyword": kw, "recipe_id": recipe_id},
                    )
                    continue
                feature, pattern = None, None
                for (f, p), rid in ROUTE_TABLE.items():
                    if rid == recipe_id:
                        feature, pattern = f, p
                        break
                if feature:
                    logger.info_structured(
                        "Recipe override from routing feedback",
                        extra_fields={"keyword": kw, "recipe_id": recipe_id},
                    )
                    return RecipeSelection(
                        selected_feature=feature,
                        selected_pattern=pattern or "media_rich",
                        selected_recipe=recipe_id,
                        route_reason=f"override:feedback_keyword:{kw}",
                        cross_feature_blocked=False,
                    )
    except Exception:
        pass
    return None


def route_recipe(selected_feature: str, selected_pattern: str, evidence_text: str | None = None) -> RecipeSelection:
    """
    Deterministic routing: (feature, pattern) -> recipe_id.
    Returns RecipeSelection with selected_recipe, route_reason, cross_feature_blocked.
    When evidence_text is provided and matches routing override keywords, returns override recipe.
    """
    if evidence_text:
        override = _route_from_evidence_similarity(evidence_text)
        if override:
            return override
        override = _route_from_override(evidence_text)
        if override:
            return override
    key = (selected_feature, selected_pattern)
    if key in ROUTE_TABLE:
        recipe_id = ROUTE_TABLE[key]
        reason = f"routed:{selected_feature}+{selected_pattern}"
        cross_blocked = selected_feature == "keyref"
        extra = {"feature": selected_feature, "pattern": selected_pattern, "recipe_id": recipe_id}
        if recipe_id == "keyref_nested_keydef_chain_map_to_map_to_topic":
            extra["selection_reason"] = "nested keydef chain resolution across outer map -> intermediate keymap -> keyword/topic source; DITA-OT resolves correctly but Web Editor author/preview does not"
            extra["primary_feature"] = "keyref"
            extra["blocked_drift"] = "xref, conref, ditaval"
        logger.info_structured("Recipe routed", extra_fields=extra)
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe=recipe_id,
            route_reason=reason,
            cross_feature_blocked=cross_blocked,
        )

    for (f, p), rid in ROUTE_TABLE.items():
        if f == selected_feature:
            reason = f"fallback:{selected_feature} (pattern {selected_pattern} not in table)"
            logger.info_structured(
                "Recipe fallback",
                extra_fields={"feature": selected_feature, "pattern": selected_pattern, "recipe_id": rid},
            )
            return RecipeSelection(
                selected_feature=selected_feature,
                selected_pattern=selected_pattern,
                selected_recipe=rid,
                route_reason=reason,
                cross_feature_blocked=selected_feature == "keyref",
            )

    if selected_feature == "image_reference":
        logger.info_structured(
            "Recipe fallback: image_reference",
            extra_fields={"pattern": selected_pattern, "recipe_id": "media_rich_content"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="media_rich_content",
            route_reason="fallback:image_reference",
            cross_feature_blocked=False,
        )

    if selected_feature == "table_content":
        logger.info_structured(
            "Recipe fallback: table_content",
            extra_fields={"pattern": selected_pattern, "recipe_id": "heavy_topics_tables_codeblocks"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="heavy_topics_tables_codeblocks",
            route_reason="fallback:table_content",
            cross_feature_blocked=False,
        )

    if selected_feature == "glossary":
        logger.info_structured(
            "Recipe fallback: glossary",
            extra_fields={"pattern": selected_pattern, "recipe_id": "glossary.glossentry_basic"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="glossary.glossentry_basic",
            route_reason="fallback:glossary",
            cross_feature_blocked=False,
        )

    if selected_feature == "experience_league":
        logger.info_structured(
            "Recipe fallback: experience_league",
            extra_fields={"pattern": selected_pattern, "recipe_id": "experience_league_to_dita"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="experience_league_to_dita",
            route_reason="fallback:experience_league",
            cross_feature_blocked=False,
        )

    if selected_feature == "metadata":
        logger.info_structured(
            "Recipe fallback: metadata",
            extra_fields={"pattern": selected_pattern, "recipe_id": "dita_subject_scheme_dataset_recipe"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="dita_subject_scheme_dataset_recipe",
            route_reason="fallback:metadata",
            cross_feature_blocked=False,
        )

    if selected_feature == "task_content":
        logger.info_structured(
            "Recipe fallback: task_content",
            extra_fields={"pattern": selected_pattern, "recipe_id": "task_topics"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="task_topics",
            route_reason="fallback:task_content",
            cross_feature_blocked=False,
        )

    if selected_feature == "reference_content":
        logger.info_structured(
            "Recipe fallback: reference_content",
            extra_fields={"pattern": selected_pattern, "recipe_id": "reference_topics"},
        )
        return RecipeSelection(
            selected_feature=selected_feature,
            selected_pattern=selected_pattern,
            selected_recipe="reference_topics",
            route_reason="fallback:reference_content",
            cross_feature_blocked=False,
        )

    return RecipeSelection(
        selected_feature=selected_feature,
        selected_pattern=selected_pattern,
        selected_recipe="keys.keydef_basic",
        route_reason="default:keyref basic",
        cross_feature_blocked=True,
    )
