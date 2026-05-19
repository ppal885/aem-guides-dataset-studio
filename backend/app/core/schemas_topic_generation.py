"""
Typed contracts for screenshot-guided (and future map / multi-reference) DITA topic generation.

Kept separate from chat-specific envelopes so benchmarks and future job workers can import
without chat session types. Chat layers compose these models in ``schemas_chat_authoring``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


ScreenshotRegionType = Literal[
    "title",
    "heading",
    "paragraph",
    "bullet_list",
    "numbered_list",
    "note",
    "warning",
    "code",
    "table",
    "field_value_block",
    "ui_control_text",
    "acceptance_criteria",
    "unknown",
]


class ScreenshotBoundingBox(BaseModel):
    """Normalized region bounds (0..1 where available)."""

    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    width: float | None = Field(default=None, ge=0.0, le=1.0)
    height: float | None = Field(default=None, ge=0.0, le=1.0)


class ScreenshotFieldValueItem(BaseModel):
    """Structured field/value pair reconstructed from forms, dialogs, or settings views."""

    field: str = ""
    value: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotLayoutRegion(BaseModel):
    """Pass 1 output: coarse document block / layout region detection."""

    model_config = {"extra": "ignore"}

    region_id: str = ""
    layout_type: str = ""
    label: str = ""
    bbox: ScreenshotBoundingBox | None = None
    order_hint: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain: bool = False
    uncertainty_reason: str | None = None


class ScreenshotTextBlock(BaseModel):
    """Pass 2 output: text extracted per detected block."""

    model_config = {"extra": "ignore"}

    region_id: str = ""
    layout_type: str = ""
    bbox: ScreenshotBoundingBox | None = None
    raw_text: str = ""
    lines: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain: bool = False
    uncertainty_reason: str | None = None


class ScreenshotParagraphItem(BaseModel):
    """Normalized paragraph-like text block preserved before downstream authoring transforms."""

    model_config = {"extra": "ignore"}

    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotSemanticBlock(BaseModel):
    """Pass 3 output: block-level semantic classification before final normalization."""

    model_config = {"extra": "ignore"}

    region_id: str = ""
    semantic_type: ScreenshotRegionType = "unknown"
    label: str = ""
    text: str = ""
    lines: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    field_values: list[ScreenshotFieldValueItem] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)
    heading_level: int | None = None
    bbox: ScreenshotBoundingBox | None = None
    order_hint: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain: bool = False
    uncertainty_reason: str | None = None


class ScreenshotPassOutput(BaseModel):
    """Inspectable/debuggable output for a single screenshot-understanding pass."""

    model_config = {"extra": "ignore"}

    pass_name: str
    summary: str = ""
    region_count: int | None = None
    warning_count: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ScreenshotProceduralContentItem(BaseModel):
    """Typed paragraph-like content for prerequisite, context, result, or example buckets."""

    model_config = {"extra": "ignore"}

    text: str = ""
    kind: Literal["prerequisite", "context", "result", "example", "command", "code"] = "context"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotProceduralSubstep(BaseModel):
    """One inferred substep under a numbered step."""

    model_config = {"extra": "ignore"}

    marker: str = ""
    command: str = ""
    info_lines: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotProceduralStep(BaseModel):
    """One inferred top-level procedural step."""

    model_config = {"extra": "ignore"}

    marker: str = ""
    command: str = ""
    info_lines: list[str] = Field(default_factory=list)
    substeps: list[ScreenshotProceduralSubstep] = Field(default_factory=list)
    ui_controls: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotProceduralModel(BaseModel):
    """Intermediate task/procedure representation recovered from a screenshot before DITA generation."""

    model_config = {"extra": "ignore"}

    title: str = ""
    prerequisites: list[ScreenshotProceduralContentItem] = Field(default_factory=list)
    context: list[ScreenshotProceduralContentItem] = Field(default_factory=list)
    steps: list[ScreenshotProceduralStep] = Field(default_factory=list)
    notes: list[ScreenshotNoteItem] = Field(default_factory=list)
    result: list[ScreenshotProceduralContentItem] = Field(default_factory=list)
    examples: list[ScreenshotProceduralContentItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_notes: list[str] = Field(default_factory=list)


SettingsControlType = Literal["text", "dropdown", "checkbox", "radio", "toggle", "table", "unknown"]


class ScreenshotSettingOption(BaseModel):
    """One option inside a checkbox/radio/dropdown-like control."""

    model_config = {"extra": "ignore"}

    label: str = ""
    selected: bool | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotSettingField(BaseModel):
    """Structured field/control recovered from settings, form, or properties screenshots."""

    model_config = {"extra": "ignore"}

    label: str = ""
    value: str = ""
    control_type: SettingsControlType = "unknown"
    helper_text: list[str] = Field(default_factory=list)
    options: list[ScreenshotSettingOption] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotSettingsSection(BaseModel):
    """Logical settings/configuration section with grouped fields and parameter tables."""

    model_config = {"extra": "ignore"}

    title: str = ""
    #: When the UI uses tabs, the tab label this section belongs to (if known).
    tab: str | None = None
    description: list[str] = Field(default_factory=list)
    fields: list[ScreenshotSettingField] = Field(default_factory=list)
    parameter_tables: list["ScreenshotTableItem"] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_region_ids: list[str] = Field(default_factory=list)


class ScreenshotSettingsReferenceModel(BaseModel):
    """Intermediate reference/settings representation recovered before DITA reference generation."""

    model_config = {"extra": "ignore"}

    title: str = ""
    tabs: list[str] = Field(default_factory=list)
    active_tab: str | None = None
    sections: list[ScreenshotSettingsSection] = Field(default_factory=list)
    helper_text: list[str] = Field(default_factory=list)
    parameter_tables: list["ScreenshotTableItem"] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_notes: list[str] = Field(default_factory=list)


ScreenshotType = Literal[
    "editor_structure_screenshot",
    "procedural_ui_screenshot",
    "settings_reference_screenshot",
    "conceptual_diagram",
    "mixed_content_screenshot",
    "generic_content_screenshot",
    "low_confidence_unknown",
]

ScreenshotIntentRoute = Literal[
    "structure_reconstruction_mode",
    "procedural_authoring_mode",
    "reference_extraction_mode",
    "conceptual_diagram_mode",
    "mixed_content_mode",
    "safe_fallback_mode",
]


class ScreenshotClassificationFeatureModel(BaseModel):
    """Typed feature set used for screenshot-type classification before semantic generation."""

    model_config = {"extra": "ignore"}

    region_count: int = 0
    heading_count: int = 0
    section_count: int = 0
    paragraph_count: int = 0
    bullet_item_count: int = 0
    numbered_step_count: int = 0
    substep_count: int = 0
    visible_dita_chip_count: int = 0
    ui_control_count: int = 0
    button_count: int = 0
    menu_name_count: int = 0
    field_value_pair_count: int = 0
    settings_section_count: int = 0
    tab_count: int = 0
    table_count: int = 0
    diagram_entity_count: int = 0
    diagram_relationship_count: int = 0
    connector_graphic_count: int = 0
    unresolved_block_count: int = 0
    uncertain_region_count: int = 0
    max_indentation_depth: int = 0
    average_text_block_words: float = Field(default=0.0, ge=0.0)
    min_text_block_words: float = Field(default=0.0, ge=0.0)
    max_text_block_words: float = Field(default=0.0, ge=0.0)
    text_density: float = Field(default=0.0, ge=0.0, le=1.0)
    structure_density: float = Field(default=0.0, ge=0.0, le=1.0)
    bullet_list_density: float = Field(default=0.0, ge=0.0, le=1.0)
    numbered_sequence_density: float = Field(default=0.0, ge=0.0, le=1.0)
    field_value_density: float = Field(default=0.0, ge=0.0, le=1.0)
    tabular_density: float = Field(default=0.0, ge=0.0, le=1.0)
    ui_control_density: float = Field(default=0.0, ge=0.0, le=1.0)
    connector_likelihood: float = Field(default=0.0, ge=0.0, le=1.0)
    screenshot_context_terms: list[str] = Field(default_factory=list)
    dominant_layout_pattern: str = ""
    overall_extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ScreenshotClassificationSignal(BaseModel):
    """One supporting signal used by the screenshot classifier."""

    model_config = {"extra": "ignore"}

    name: str = ""
    value: float = Field(default=0.0)
    description: str = ""


class ScreenshotClassificationAlternative(BaseModel):
    """Runner-up screenshot types when the classification is ambiguous."""

    model_config = {"extra": "ignore"}

    screenshot_type: ScreenshotType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class ScreenshotTypeClassification(BaseModel):
    """Typed screenshot-type decision returned before downstream semantic generation."""

    model_config = {"extra": "ignore"}

    screenshot_type: ScreenshotType = "low_confidence_unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    supporting_signals: list[ScreenshotClassificationSignal] = Field(default_factory=list)
    ambiguous_alternatives: list[ScreenshotClassificationAlternative] = Field(default_factory=list)


class ScreenshotIntentRouteDecision(BaseModel):
    """Route decision immediately after screenshot-type classification."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    chosen_route: ScreenshotIntentRoute = Field(
        default="safe_fallback_mode",
        alias="chosenRoute",
        serialization_alias="chosenRoute",
    )
    route_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        alias="routeConfidence",
        serialization_alias="routeConfidence",
    )
    reasons: list[str] = Field(default_factory=list)
    downstream_constraints: list[str] = Field(
        default_factory=list,
        alias="downstreamConstraints",
        serialization_alias="downstreamConstraints",
    )


class ScreenshotUnderstandingTrace(BaseModel):
    """Typed debug trace across the multi-pass screenshot understanding pipeline."""

    model_config = {"extra": "ignore"}

    provider: str | None = None
    model: str | None = None
    layout_regions: list[ScreenshotLayoutRegion] = Field(default_factory=list)
    text_blocks: list[ScreenshotTextBlock] = Field(default_factory=list)
    semantic_blocks: list[ScreenshotSemanticBlock] = Field(default_factory=list)
    procedural_model: ScreenshotProceduralModel | None = None
    settings_reference_model: ScreenshotSettingsReferenceModel | None = None
    image_characterization: ScreenshotImageCharacterization | None = None
    embedded_graphics: list[ScreenshotEmbeddedGraphic] = Field(default_factory=list)
    diagram_interpretation: DiagramInterpretationModel | None = None
    classification_features: ScreenshotClassificationFeatureModel | None = None
    screenshot_type_classification: ScreenshotTypeClassification | None = None
    screenshot_intent_route_decision: ScreenshotIntentRouteDecision | None = None
    reading_order: list[str] = Field(default_factory=list)
    semantic_hierarchy: list[ScreenshotHierarchyNode] = Field(default_factory=list)
    final_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    stages: list[ScreenshotPassOutput] = Field(default_factory=list)


class ScreenshotRegionItem(BaseModel):
    """
    One detected semantic layout region.

    Regions preserve grouping, type, confidence, and uncertainty so downstream stages
    can omit weak content instead of hallucinating missing structure.
    """

    model_config = {"extra": "ignore"}

    region_id: str = ""
    region_type: ScreenshotRegionType = "unknown"
    label: str = ""
    text: str = ""
    lines: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    field_values: list[ScreenshotFieldValueItem] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)
    heading_level: int | None = None
    bbox: ScreenshotBoundingBox | None = None
    order_hint: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain: bool = False
    uncertainty_reason: str | None = None


class ScreenshotHierarchyNode(BaseModel):
    """Semantic hierarchy inferred from reading order plus heading/title regions."""

    model_config = {"extra": "ignore"}

    node_id: str = ""
    title: str = ""
    level: int = 1
    purpose: str = ""
    region_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# --- Screenshot IR (vision → structured plan input) ---


class ScreenshotSectionItem(BaseModel):
    name: str = ""
    purpose: str = ""
    details: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_ids: list[str] = Field(default_factory=list)


class ScreenshotNoteItem(BaseModel):
    kind: str = ""  # note, caution, important, tip, etc.
    text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotTableItem(BaseModel):
    """Rows as parallel lists of cell text (best-effort from vision)."""

    caption: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotHeadingItem(BaseModel):
    """Logical heading from layout (not OCR line dump)."""

    level: int = 1
    text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_id: str | None = None


class ScreenshotUnresolvedBlock(BaseModel):
    """Low-confidence or ambiguous block preserved verbatim instead of being over-structured."""

    model_config = {"extra": "ignore"}

    region_id: str = ""
    candidate_type: ScreenshotRegionType = "unknown"
    raw_text: str = ""
    lines: list[str] = Field(default_factory=list)
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ScreenshotEmphasisCue(BaseModel):
    """Visually emphasized fragment (bold, code-like, etc.)."""

    text: str = ""
    cue: str = ""  # bold, italic, monospace, highlight, underline, unknown
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_id: str | None = None


ScreenshotEmbeddedGraphicKind = Literal[
    "dita_map_hierarchy",
    "flowchart",
    "sequence_diagram",
    "architecture_block",
    "screenshot_within_screenshot",
    "table_or_matrix",
    "unclassified",
]


class ScreenshotDiagramTreeNode(BaseModel):
    """
    Hierarchical node for diagrams embedded in a screenshot (e.g. DITA map trees).

    Aligns with map-hierarchy extraction: ``map_root`` denotes the map container, not a .dita file.
    """

    model_config = {"extra": "ignore"}

    title: str = ""
    dita_type: str = "topic"
    children: list["ScreenshotDiagramTreeNode"] = Field(default_factory=list)
    confidence: float = Field(default=0.72, ge=0.0, le=1.0)


class ScreenshotEmbeddedGraphic(BaseModel):
    """One information graphic or nested figure inside a larger capture (composite screenshots)."""

    model_config = {"extra": "ignore"}

    kind: ScreenshotEmbeddedGraphicKind = "unclassified"
    label: str = ""
    description: str = ""
    diagram_root: ScreenshotDiagramTreeNode | None = None


class ScreenshotImageCharacterization(BaseModel):
    """
    Explicit structured scene analysis (replaces opaque chain-of-thought).

    Populated by vision so planners can reason about primary vs secondary content, like a human
    technical writer examining the capture before writing.
    """

    model_config = {"extra": "ignore"}

    primary_scene: str = ""
    secondary_elements: list[str] = Field(default_factory=list)
    embedded_content_summary: str = ""
    author_intent_hypothesis: str = ""


DiagramKind = Literal["hierarchy", "taxonomy", "relationship", "flow_structure", "unknown"]
DiagramContentOrientation = Literal["conceptual", "procedural", "reference", "mixed", "unknown"]
DiagramRelationshipKind = Literal["parent_child", "association", "flow", "grouping", "unknown"]


class DiagramRelationshipItem(BaseModel):
    """Relationship recovered from a diagram between two named entities."""

    model_config = {"extra": "ignore"}

    source: str = ""
    target: str = ""
    kind: DiagramRelationshipKind = "unknown"
    label: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiagramGroupItem(BaseModel):
    """Logical grouping recovered from a diagram cluster or branch."""

    model_config = {"extra": "ignore"}

    name: str = ""
    members: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiagramInterpretationModel(BaseModel):
    """
    Typed semantic interpretation for diagram-heavy screenshots.

    Keeps the dominant meaning of the image separate from procedural screenshot content.
    """

    model_config = {"extra": "ignore"}

    diagram_kind: DiagramKind = "unknown"
    content_orientation: DiagramContentOrientation = "unknown"
    dominant_meaning: str = ""
    key_entities: list[str] = Field(default_factory=list)
    relationships: list[DiagramRelationshipItem] = Field(default_factory=list)
    groups: list[DiagramGroupItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


ScreenshotDiagramTreeNode.model_rebuild()


class ScreenshotContentModel(BaseModel):
    """
    Intermediate representation (IR) for semantic screenshot understanding.

    Populated by vision models guided to infer document structure; post-processing
    may adjust confidence and merge duplicate UI strings. Downstream DITA generation
    maps: title/headings/sections -> topic titles & sections; numbered_steps -> task
    steps; bullet_lists -> lists; notes -> note/caution; tables -> simpletable;
    code_snippets -> codeblock; ui_labels/menu_names/button_names -> uicontrol hints;
    emphasis_cues -> inline markup hints; acceptance_criteria -> ol/section.
    ``image_characterization`` and ``embedded_graphics`` capture composite captures
    (e.g. authoring UI plus an embedded hierarchy diagram) for IA-aware planning.
    """

    model_config = {"extra": "ignore"}

    title: str = ""
    regions: list[ScreenshotRegionItem] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)
    semantic_hierarchy: list[ScreenshotHierarchyNode] = Field(default_factory=list)
    headings: list[ScreenshotHeadingItem] = Field(default_factory=list)
    paragraphs: list[ScreenshotParagraphItem] = Field(default_factory=list)
    sections: list[ScreenshotSectionItem] = Field(default_factory=list)
    numbered_steps: list[str] = Field(default_factory=list)
    substeps: list[ScreenshotProceduralSubstep] = Field(default_factory=list)
    bullet_lists: list[list[str]] = Field(default_factory=list)
    notes: list[ScreenshotNoteItem] = Field(default_factory=list)
    tables: list[ScreenshotTableItem] = Field(default_factory=list)
    field_value_pairs: list[ScreenshotFieldValueItem] = Field(default_factory=list)
    code_snippets: list[str] = Field(default_factory=list)
    ui_labels: list[str] = Field(default_factory=list)
    menu_names: list[str] = Field(default_factory=list)
    button_names: list[str] = Field(default_factory=list)
    emphasis_cues: list[ScreenshotEmphasisCue] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    procedural_model: ScreenshotProceduralModel | None = None
    settings_reference_model: ScreenshotSettingsReferenceModel | None = None
    image_characterization: ScreenshotImageCharacterization | None = None
    embedded_graphics: list[ScreenshotEmbeddedGraphic] = Field(default_factory=list)
    diagram_interpretation: DiagramInterpretationModel | None = None
    screenshot_type_classification: ScreenshotTypeClassification | None = None
    screenshot_intent_route_decision: ScreenshotIntentRouteDecision | None = None
    uncertain_region_ids: list[str] = Field(default_factory=list)
    unresolved_blocks: list[ScreenshotUnresolvedBlock] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="Overall extraction confidence in [0, 1].")
    field_confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Optional per-field scores from the model (e.g. title, steps, tables).",
    )
    uncertainty_warnings: list[str] = Field(default_factory=list)


# --- Reference style (sanitized; never stores id/href/conref targets) ---


class ReferenceStyleProfile(BaseModel):
    """
    Sanitized style profile from a reference DITA topic.

    Does not store element ``id`` values or ``conref``/``keyref`` targets. Optionally records
    **xref href basenames** (filename only) from the attachment so authors can reuse the same
    link targets when ``xref_placeholders`` / allowlist mode is enabled in chat options.
    """

    model_config = {"extra": "ignore"}

    declared_doctype_line: str | None = None
    root_local_name: str = ""
    xml_indent_style: Literal["space_2", "space_4", "tab"] | None = Field(
        default=None,
        description="Preferred XML indentation when serializing generated topics (e.g. from reference analysis).",
    )
    root_attributes_sample: dict[str, str] = Field(default_factory=dict)
    child_order_top_level: list[str] = Field(default_factory=list)
    inline_element_usage: dict[str, int] = Field(default_factory=dict)
    structural_habits: list[str] = Field(default_factory=list)
    tone_hint: str = ""  # terse | verbose | neutral
    uses_prolog: bool = False
    prolog_child_tags: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    #: Basenames only (e.g. ``t_Foo.xml``) from ``xref href`` in the reference; no path or ``#`` fragments.
    reference_xref_basenames: list[str] = Field(default_factory=list)
    #: Ordered ``taskbody`` child element names (e.g. prereq, context, steps) when root is ``task``.
    taskbody_top_level_sequence: list[str] = Field(default_factory=list)
    #: Top-level section titles recovered from the body/refbody/conbody when safe to reuse as structural titles.
    body_section_titles: list[str] = Field(default_factory=list)
    #: Short human hints for planners/LLM (structure only, no copied prose).
    structural_outline_hints: list[str] = Field(default_factory=list)
    #: True if reference uses ``ui-type`` (or namespaced equivalent) on any element.
    reference_uses_ui_type_attributes: bool = False


ReferenceAdoptionMode = Literal[
    "compatible_adoption",
    "partial_adoption",
    "conflict_preserve_content",
]


class ReferenceSerializerPolicy(BaseModel):
    """Concrete serializer/draft hints derived from a compatible reference profile."""

    model_config = {"extra": "ignore"}

    target_root_type: Literal["topic", "task", "concept", "reference"] | str = "topic"
    preferred_top_level_order: list[str] = Field(default_factory=list)
    preferred_taskbody_sequence: list[str] = Field(default_factory=list)
    preferred_section_names: list[str] = Field(default_factory=list)
    preferred_section_name_map: dict[str, str] = Field(default_factory=dict)
    preferred_structural_habits: list[str] = Field(default_factory=list)
    prefer_prolog: bool = False
    prefer_properties_layout: bool = False
    prefer_cals_tables: bool = False
    prefer_task_examples_before_result: bool = False
    prefer_uicontrol: bool = False
    prefer_menucascade: bool = False
    prefer_ui_type_attributes: bool = False
    tone_hint: str = ""


class ReferenceAdoptionDecision(BaseModel):
    """Reference-style adoption decision after content-first route/type resolution."""

    model_config = {"extra": "ignore"}

    mode: ReferenceAdoptionMode = "partial_adoption"
    target_root_type: Literal["topic", "task", "concept", "reference"] | str = "topic"
    adopted_constraints: list[str] = Field(default_factory=list)
    rejected_constraints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    effective_serializer_habits: list[str] = Field(default_factory=list)
    serializer_policy: ReferenceSerializerPolicy | None = None


# --- Validation & assumptions (first-class, extensible) ---


ValidationIssueCategory = Literal["validator", "structural", "aem_guides", "review", "parse", "link", "unknown"]
ValidationIssueSeverity = Literal["error", "warning", "info"]


class ValidationIssue(BaseModel):
    """Single validation or review finding (replaces unstructured string buckets over time)."""

    model_config = {"extra": "ignore"}

    category: ValidationIssueCategory = "unknown"
    severity: ValidationIssueSeverity = "error"
    message: str
    code: str | None = Field(default=None, description="Stable machine code when available.")
    location: str | None = Field(default=None, description="Optional XPath, element id, or line hint.")


GenerationAssumptionSource = Literal[
    "semantic_plan",
    "vision",
    "reference_style",
    "pipeline",
    "repair",
    "user_context",
    "unknown",
]


class GenerationAssumption(BaseModel):
    """Explicit assumption surfaced to authors (audit / quality)."""

    model_config = {"extra": "ignore"}

    text: str
    source: GenerationAssumptionSource = "unknown"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


LinkRecommendationKind = Literal["xref", "conref", "keyref", "parse", "unknown"]


class LinkRecommendation(BaseModel):
    """Safe link/reuse guidance without fabricated repository paths."""

    model_config = {"extra": "ignore"}

    kind: LinkRecommendationKind = "unknown"
    severity: Literal["error", "warning", "info"] = "info"
    summary: str
    action: str = ""


# --- Debug / telemetry (structured; small extension map only) ---


class TopicGenerationDebug(BaseModel):
    """Structured debug payload for traces and benchmarks (avoid large opaque dicts)."""

    model_config = {"extra": "ignore"}

    authoring_trace_id: str | None = None
    pipeline_run_id: str | None = None
    pipeline_version: str | None = None
    serialization_mode: str | None = None
    review_quality_score: int | None = None
    strict_validation: bool | None = None
    style_strictness: str | None = None
    output_mode: str | None = None
    reference_guided_enabled: bool | None = None
    had_jira_context: bool | None = None
    link_recommendation_count: int | None = None
    resolved_authoring_pattern: str | None = None
    screenshot_type: str | None = None
    screenshot_type_confidence: float | None = None
    screenshot_intent_route: str | None = None
    reference_adoption_mode: str | None = None
    reference_adoption_warnings: list[str] = Field(default_factory=list)
    #: Ordered pipeline stages (serializable records); prefer over ad-hoc dicts.
    pipeline_stages: list[dict[str, Any]] = Field(default_factory=list)
    #: Escape hatch for experimental flags (keep values small / JSON-safe).
    extensions: dict[str, str] = Field(default_factory=dict)


# --- Async / job (future worker queue; optional today) ---


TopicGenerationJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class TopicGenerationJob(BaseModel):
    """
    Durable job record for async generation (map assembly, multi-reference, long repair).

    Not yet backed by a queue; included so APIs can evolve without breaking types.
    """

    model_config = {"extra": "ignore"}

    job_id: str
    status: TopicGenerationJobStatus = "queued"
    request_fingerprint: str | None = Field(
        default=None,
        description="Hash of request inputs for idempotency (future).",
    )
    pipeline_run_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    #: Reserved: target map asset id, repair mode, multi-ref order, etc.
    flags: dict[str, bool] = Field(default_factory=dict)
