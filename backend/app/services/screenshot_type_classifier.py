from __future__ import annotations

import re
from statistics import mean

from app.core.schemas_topic_generation import (
    ScreenshotClassificationAlternative,
    ScreenshotClassificationFeatureModel,
    ScreenshotClassificationSignal,
    ScreenshotContentModel,
    ScreenshotType,
    ScreenshotTypeClassification,
)

_TAG_RE = re.compile(r"<\s*[A-Za-z][\w:-]*\s*>")
_DITA_TERMS = {
    "dita",
    "topic",
    "task",
    "concept",
    "reference",
    "map",
    "mapref",
    "topicref",
    "keyref",
    "conref",
    "conkeyref",
    "shortdesc",
    "prolog",
    "taskbody",
    "refbody",
    "conbody",
}
_EDITOR_CONTEXT_TERMS = {"editor", "author", "authoring", "dita", "map", "topic", "oxygen", "aem", "guides"}
_PROCEDURAL_CONTEXT_TERMS = {"steps", "step", "procedure", "workflow", "how to", "configure", "create", "task"}
_SETTINGS_CONTEXT_TERMS = {"settings", "preferences", "properties", "configuration", "dialog", "form", "panel"}
_DIAGRAM_CONTEXT_TERMS = {"diagram", "hierarchy", "taxonomy", "relationship", "flow", "structure", "tree"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalized_density(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp(count / float(denominator))


def _region_texts(model: ScreenshotContentModel) -> list[str]:
    texts: list[str] = []
    for region in model.regions:
        if region.text.strip():
            texts.append(region.text.strip())
        for line in region.lines:
            line = " ".join(str(line or "").split()).strip()
            if line:
                texts.append(line)
        for item in region.items:
            item = " ".join(str(item or "").split()).strip()
            if item:
                texts.append(item)
    texts.extend(item.text.strip() for item in model.paragraphs if item.text.strip())
    return texts


def _indent_depth_for_line(text: str) -> int:
    if not text:
        return 0
    indent = len(text) - len(text.lstrip(" "))
    if indent <= 0:
        return 0
    return max(1, indent // 2)


def _context_terms(context: str) -> list[str]:
    lowered = (context or "").lower()
    found: list[str] = []
    for term_group in (_EDITOR_CONTEXT_TERMS | _PROCEDURAL_CONTEXT_TERMS | _SETTINGS_CONTEXT_TERMS | _DIAGRAM_CONTEXT_TERMS,):
        for term in sorted(term_group, key=len, reverse=True):
            if term in lowered and term not in found:
                found.append(term)
    return found


def extract_screenshot_classification_features(
    model: ScreenshotContentModel,
    *,
    screenshot_context: str | None = None,
) -> ScreenshotClassificationFeatureModel:
    region_count = len(model.regions)
    text_samples = _region_texts(model)
    word_counts = [len(sample.split()) for sample in text_samples if sample.strip()]
    average_words = round(mean(word_counts), 3) if word_counts else 0.0
    min_words = float(min(word_counts)) if word_counts else 0.0
    max_words = float(max(word_counts)) if word_counts else 0.0

    visible_dita_chip_count = 0
    for sample in text_samples + list(model.ui_labels) + list(model.menu_names) + list(model.button_names):
        normalized = " ".join(str(sample or "").split()).strip()
        if not normalized:
            continue
        if _TAG_RE.search(normalized):
            visible_dita_chip_count += 1
            continue
        tokens = {token.strip(" <>:/").lower() for token in normalized.split()}
        if tokens & _DITA_TERMS:
            visible_dita_chip_count += 1

    max_indentation_depth = 0
    for region in model.regions:
        for raw in region.lines:
            max_indentation_depth = max(max_indentation_depth, _indent_depth_for_line(str(raw or "")))

    bullet_item_count = sum(len(items) for items in model.bullet_lists)
    numbered_step_count = len(model.numbered_steps)
    substep_count = len(model.substeps)
    field_value_pair_count = len(model.field_value_pairs)
    settings_section_count = len(model.settings_reference_model.sections) if model.settings_reference_model else 0
    tab_count = len(model.settings_reference_model.tabs) if model.settings_reference_model else 0
    table_count = len(model.tables)
    diagram_entity_count = len(model.diagram_interpretation.key_entities) if model.diagram_interpretation else 0
    diagram_relationship_count = len(model.diagram_interpretation.relationships) if model.diagram_interpretation else 0
    connector_graphic_count = sum(
        1
        for graphic in model.embedded_graphics
        if graphic.kind in {"dita_map_hierarchy", "flowchart", "sequence_diagram", "architecture_block"}
    )
    ui_control_count = len(set(model.ui_labels + model.button_names + model.menu_names))
    text_block_count = max(region_count, len(text_samples), 1)
    structural_units = (
        len(model.headings)
        + len(model.sections)
        + bullet_item_count
        + numbered_step_count
        + substep_count
        + field_value_pair_count
        + table_count
        + len(model.semantic_hierarchy)
    )
    text_units = len(model.paragraphs) + len(model.notes) + len(model.code_snippets)

    if model.diagram_interpretation and model.diagram_interpretation.diagram_kind != "unknown":
        dominant_layout_pattern = "diagram"
    elif model.settings_reference_model and (settings_section_count or field_value_pair_count):
        dominant_layout_pattern = "settings_panel"
    elif numbered_step_count or substep_count:
        dominant_layout_pattern = "procedural_steps"
    elif visible_dita_chip_count >= 2:
        dominant_layout_pattern = "editor_structure"
    else:
        dominant_layout_pattern = "generic_text"

    return ScreenshotClassificationFeatureModel(
        region_count=region_count,
        heading_count=len(model.headings),
        section_count=len(model.sections),
        paragraph_count=len(model.paragraphs),
        bullet_item_count=bullet_item_count,
        numbered_step_count=numbered_step_count,
        substep_count=substep_count,
        visible_dita_chip_count=visible_dita_chip_count,
        ui_control_count=ui_control_count,
        button_count=len(model.button_names),
        menu_name_count=len(model.menu_names),
        field_value_pair_count=field_value_pair_count,
        settings_section_count=settings_section_count,
        tab_count=tab_count,
        table_count=table_count,
        diagram_entity_count=diagram_entity_count,
        diagram_relationship_count=diagram_relationship_count,
        connector_graphic_count=connector_graphic_count,
        unresolved_block_count=len(model.unresolved_blocks),
        uncertain_region_count=len(model.uncertain_region_ids),
        max_indentation_depth=max_indentation_depth,
        average_text_block_words=average_words,
        min_text_block_words=min_words,
        max_text_block_words=max_words,
        text_density=_normalized_density(text_units + len(text_samples), text_block_count * 2),
        structure_density=_normalized_density(structural_units, max(region_count, 1) * 2),
        bullet_list_density=_normalized_density(bullet_item_count, max(region_count, 1)),
        numbered_sequence_density=_normalized_density(numbered_step_count + substep_count, max(region_count, 1)),
        field_value_density=_normalized_density(field_value_pair_count + settings_section_count, max(region_count, 1)),
        tabular_density=_normalized_density(table_count + tab_count, max(region_count, 1)),
        ui_control_density=_normalized_density(ui_control_count, max(region_count, 1)),
        connector_likelihood=_clamp(
            (connector_graphic_count * 0.35)
            + (0.08 * diagram_entity_count)
            + (0.06 * diagram_relationship_count)
        ),
        screenshot_context_terms=_context_terms(screenshot_context or ""),
        dominant_layout_pattern=dominant_layout_pattern,
        overall_extraction_confidence=_clamp(model.confidence),
    )


class ScreenshotTypeClassifier:
    """Confidence-aware classifier for coarse screenshot categories before DITA generation."""

    def extract_features(
        self,
        model: ScreenshotContentModel,
        *,
        screenshot_context: str | None = None,
    ) -> ScreenshotClassificationFeatureModel:
        return extract_screenshot_classification_features(model, screenshot_context=screenshot_context)

    def classify(
        self,
        model: ScreenshotContentModel,
        *,
        screenshot_context: str | None = None,
    ) -> tuple[ScreenshotClassificationFeatureModel, ScreenshotTypeClassification]:
        features = self.extract_features(model, screenshot_context=screenshot_context)
        scores, explanations = self._score_classes(features, model=model)
        classification = self._build_result(scores=scores, explanations=explanations, features=features)
        return features, classification

    def _score_classes(
        self,
        features: ScreenshotClassificationFeatureModel,
        *,
        model: ScreenshotContentModel,
    ) -> tuple[dict[ScreenshotType, float], dict[ScreenshotType, list[str]]]:
        scores: dict[ScreenshotType, float] = {
            "editor_structure_screenshot": 0.0,
            "procedural_ui_screenshot": 0.0,
            "settings_reference_screenshot": 0.0,
            "conceptual_diagram": 0.0,
            "mixed_content_screenshot": 0.0,
            "generic_content_screenshot": 0.0,
            "low_confidence_unknown": 0.0,
        }
        reasons: dict[ScreenshotType, list[str]] = {key: [] for key in scores}

        def add(kind: ScreenshotType, amount: float, reason: str) -> None:
            if amount <= 0:
                return
            scores[kind] += amount
            reasons[kind].append(reason)

        ctx_terms = set(features.screenshot_context_terms)
        diagram = model.diagram_interpretation

        if features.visible_dita_chip_count >= 2:
            add("editor_structure_screenshot", 0.42, f"Detected {features.visible_dita_chip_count} visible DITA/editor tag-like chips.")
        if features.ui_control_density >= 0.2:
            add("editor_structure_screenshot", 0.1, "UI-control density is high enough to suggest an editor capture.")
        if {"editor", "dita", "map", "topic", "guides"} & ctx_terms:
            add("editor_structure_screenshot", 0.14, "Prompt context mentions editor or DITA authoring terms.")
        if features.heading_count + features.section_count >= 3:
            add("editor_structure_screenshot", 0.08, "Structured headings and sections are visible in the capture.")

        if model.procedural_model and model.procedural_model.steps:
            add("procedural_ui_screenshot", 0.36, f"Recovered {len(model.procedural_model.steps)} procedural step(s).")
        if features.numbered_sequence_density >= 0.2:
            add("procedural_ui_screenshot", 0.22, "Numbered-sequence density is high.")
        if features.substep_count > 0 or features.max_indentation_depth >= 1:
            add("procedural_ui_screenshot", 0.12, "Indented content suggests nested substeps.")
        if {"procedure", "workflow", "steps", "step", "how to"} & ctx_terms:
            add("procedural_ui_screenshot", 0.12, "Prompt context suggests procedural intent.")
        if model.notes:
            add("procedural_ui_screenshot", 0.05, "Notes or warnings appear alongside procedural content.")

        if features.field_value_density >= 0.25:
            add("settings_reference_screenshot", 0.34, "Field/value density is high.")
        if features.settings_section_count > 0:
            add("settings_reference_screenshot", 0.24, f"Recovered {features.settings_section_count} grouped settings section(s).")
        if features.tab_count > 0:
            add("settings_reference_screenshot", 0.1, f"Detected {features.tab_count} tab label(s).")
        if features.tabular_density >= 0.18:
            add("settings_reference_screenshot", 0.1, "Tabular density suggests reference-style parameter content.")
        if {"settings", "preferences", "properties", "configuration", "dialog", "panel"} & ctx_terms:
            add("settings_reference_screenshot", 0.14, "Prompt context suggests settings or configuration UI.")

        if diagram and diagram.diagram_kind != "unknown":
            add("conceptual_diagram", 0.34, f"Diagram interpretation is {diagram.diagram_kind}.")
        if diagram and diagram.content_orientation == "conceptual":
            add("conceptual_diagram", 0.28, "Diagram orientation is conceptual.")
        if features.connector_likelihood >= 0.3:
            add("conceptual_diagram", 0.18, "Connectors and labeled nodes are likely present.")
        if features.diagram_entity_count >= 3:
            add("conceptual_diagram", 0.1, f"Recovered {features.diagram_entity_count} diagram entities.")
        if {"diagram", "hierarchy", "taxonomy", "relationship", "structure", "tree"} & ctx_terms:
            add("conceptual_diagram", 0.1, "Prompt context suggests diagram interpretation.")

        if features.text_density >= 0.24 and max(
            scores["editor_structure_screenshot"],
            scores["procedural_ui_screenshot"],
            scores["settings_reference_screenshot"],
            scores["conceptual_diagram"],
        ) < 0.55:
            add("generic_content_screenshot", 0.36, "Text dominates without a stronger structural pattern.")
        if features.heading_count or features.paragraph_count:
            add("generic_content_screenshot", 0.1, "General headings or paragraphs are present.")
        if features.structure_density < 0.22 and features.overall_extraction_confidence >= 0.45:
            add("generic_content_screenshot", 0.08, "Structure density is modest but the extraction is readable.")

        strong_specialists = sum(
            1
            for kind in (
                "editor_structure_screenshot",
                "procedural_ui_screenshot",
                "settings_reference_screenshot",
                "conceptual_diagram",
            )
            if scores[kind] >= 0.34
        )
        if strong_specialists >= 2:
            add("mixed_content_screenshot", 0.62, "Multiple specialized screenshot patterns are present.")
        if (
            scores["conceptual_diagram"] >= 0.28
            and (scores["editor_structure_screenshot"] >= 0.24 or scores["settings_reference_screenshot"] >= 0.24)
        ):
            add("mixed_content_screenshot", 0.26, "Diagram signals coexist with editor or settings signals.")
        if (
            scores["procedural_ui_screenshot"] >= 0.28
            and scores["settings_reference_screenshot"] >= 0.28
        ):
            add("mixed_content_screenshot", 0.26, "Procedural content and settings-style fields both appear strong.")

        if features.overall_extraction_confidence < 0.42:
            add("low_confidence_unknown", 0.44, "Overall extraction confidence is low.")
        unresolved_ratio = _normalized_density(features.unresolved_block_count + features.uncertain_region_count, max(features.region_count, 1))
        if unresolved_ratio >= 0.34:
            add("low_confidence_unknown", 0.28, "A large share of regions remain unresolved or uncertain.")
        if features.region_count == 0:
            add("low_confidence_unknown", 0.5, "No reliable regions were recovered from the screenshot.")

        for kind in ("procedural_ui_screenshot", "settings_reference_screenshot"):
            if scores[kind] and scores["conceptual_diagram"] >= 0.42:
                scores[kind] = max(0.0, scores[kind] - 0.12)
                reasons[kind].append("Diagram evidence outweighs forcing this screenshot into a non-diagram class.")

        return scores, reasons

    def _build_result(
        self,
        *,
        scores: dict[ScreenshotType, float],
        explanations: dict[ScreenshotType, list[str]],
        features: ScreenshotClassificationFeatureModel,
    ) -> ScreenshotTypeClassification:
        specialist_scores = [
            scores["editor_structure_screenshot"],
            scores["procedural_ui_screenshot"],
            scores["settings_reference_screenshot"],
            scores["conceptual_diagram"],
        ]
        strong_specialists = [score for score in specialist_scores if score >= 0.55]
        if len(strong_specialists) >= 2 and scores["mixed_content_screenshot"] >= max(0.72, max(strong_specialists) - 0.08):
            scores["mixed_content_screenshot"] = max(scores["mixed_content_screenshot"], max(strong_specialists) + 0.02)
            explanations["mixed_content_screenshot"].append(
                "Hybrid tie-break applied because multiple specialized screenshot patterns remained strong after scoring."
            )
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_type, top_score = ranked[0]
        second_type, second_score = ranked[1]

        low_confidence = (
            features.overall_extraction_confidence < 0.42
            or top_score < 0.38
            or (top_score - second_score) < 0.08 and top_score < 0.62
        )
        if low_confidence and top_type != "low_confidence_unknown":
            scores["low_confidence_unknown"] = max(scores["low_confidence_unknown"], min(0.92, 0.42 + (1.0 - features.overall_extraction_confidence) * 0.3))
            explanations["low_confidence_unknown"].append("Evidence was too weak or ambiguous to select a stronger screenshot class confidently.")
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            top_type, top_score = ranked[0]
            second_type, second_score = ranked[1]

        confidence = _clamp(top_score * (0.65 + 0.35 * features.overall_extraction_confidence))
        if top_type == "low_confidence_unknown":
            confidence = _clamp(max(confidence, 0.45))

        ambiguous_alternatives: list[ScreenshotClassificationAlternative] = []
        for alt_type, alt_score in ranked[1:4]:
            if alt_score < 0.2:
                continue
            if (top_score - alt_score) > 0.18:
                continue
            ambiguous_alternatives.append(
                ScreenshotClassificationAlternative(
                    screenshot_type=alt_type,
                    confidence=_clamp(alt_score * (0.6 + 0.4 * features.overall_extraction_confidence)),
                    reasons=explanations.get(alt_type, [])[:3],
                )
            )

        supporting_signals = self._supporting_signals(top_type=top_type, features=features, scores=scores)
        reasons = explanations.get(top_type, [])[:5]
        if not reasons:
            reasons = ["No strong screenshot-type signal dominated, so the safest fallback classification was used."]

        return ScreenshotTypeClassification(
            screenshot_type=top_type,
            confidence=round(confidence, 3),
            reasons=reasons,
            supporting_signals=supporting_signals,
            ambiguous_alternatives=ambiguous_alternatives,
        )

    def _supporting_signals(
        self,
        *,
        top_type: ScreenshotType,
        features: ScreenshotClassificationFeatureModel,
        scores: dict[ScreenshotType, float],
    ) -> list[ScreenshotClassificationSignal]:
        signals: list[ScreenshotClassificationSignal] = [
            ScreenshotClassificationSignal(
                name="overall_extraction_confidence",
                value=round(features.overall_extraction_confidence, 3),
                description="Overall screenshot-extraction confidence.",
            ),
            ScreenshotClassificationSignal(
                name="visible_dita_chip_count",
                value=float(features.visible_dita_chip_count),
                description="Visible DITA/editor tag-like chips or labels.",
            ),
            ScreenshotClassificationSignal(
                name="numbered_sequence_density",
                value=round(features.numbered_sequence_density, 3),
                description="Density of ordered steps and substeps.",
            ),
            ScreenshotClassificationSignal(
                name="field_value_density",
                value=round(features.field_value_density, 3),
                description="Density of field/value and settings signals.",
            ),
            ScreenshotClassificationSignal(
                name="connector_likelihood",
                value=round(features.connector_likelihood, 3),
                description="Likelihood that the image contains connectors and labeled nodes.",
            ),
            ScreenshotClassificationSignal(
                name="ui_control_density",
                value=round(features.ui_control_density, 3),
                description="Density of UI control labels, buttons, and menus.",
            ),
            ScreenshotClassificationSignal(
                name="structure_density",
                value=round(features.structure_density, 3),
                description="Relative amount of structured content compared with total regions.",
            ),
            ScreenshotClassificationSignal(
                name="score_for_" + top_type,
                value=round(scores.get(top_type, 0.0), 3),
                description="Final raw score for the selected screenshot class.",
            ),
        ]
        return [signal for signal in signals if signal.value > 0][:6]
