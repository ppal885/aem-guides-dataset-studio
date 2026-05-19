from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, model_serializer

from app.core.schemas_topic_generation import (
    DiagramGroupItem,
    DiagramInterpretationModel,
    DiagramRelationshipItem,
    GenerationAssumption,
    LinkRecommendation,
    ReferenceAdoptionDecision,
    ReferenceStyleProfile,
    ScreenshotClassificationAlternative,
    ScreenshotClassificationFeatureModel,
    ScreenshotClassificationSignal,
    ScreenshotBoundingBox,
    ScreenshotContentModel,
    ScreenshotDiagramTreeNode,
    ScreenshotEmbeddedGraphic,
    ScreenshotImageCharacterization,
    ScreenshotIntentRouteDecision,
    ScreenshotEmphasisCue,
    ScreenshotFieldValueItem,
    ScreenshotHeadingItem,
    ScreenshotHierarchyNode,
    ScreenshotLayoutRegion,
    ScreenshotNoteItem,
    ScreenshotParagraphItem,
    ScreenshotPassOutput,
    ScreenshotProceduralContentItem,
    ScreenshotProceduralModel,
    ScreenshotProceduralStep,
    ScreenshotProceduralSubstep,
    ScreenshotRegionItem,
    ScreenshotSectionItem,
    ScreenshotSemanticBlock,
    ScreenshotSettingField,
    ScreenshotSettingOption,
    ScreenshotSettingsReferenceModel,
    ScreenshotSettingsSection,
    ScreenshotTypeClassification,
    ScreenshotTextBlock,
    ScreenshotTableItem,
    ScreenshotUnresolvedBlock,
    ScreenshotUnderstandingTrace,
    TopicGenerationDebug,
    TopicGenerationJob,
    ValidationIssue,
)


ChatAttachmentKind = Literal["image", "reference_dita", "generated_dita"]
ChatDitaType = Literal["topic", "task", "concept", "reference", "map"]
ChatStyleStrictness = Literal["low", "medium", "high"]
ChatScreenshotDeliverableMode = Literal["single_topic", "map_hierarchy"]
ChatMapHierarchyNodeType = Literal["map_root", "concept", "task", "reference", "topic"]
ChatAuthoringOutputMode = Literal["xml_only", "xml_explanation", "xml_validation", "xml_style_diff"]
# default: generic task/topic serialization; cisco_task: enterprise task ordering; cisco_reference: CALS tables + refbody habits; auto: infer from reference.
ChatAuthoringPattern = Literal["default", "cisco_task", "cisco_reference", "auto"]


class ChatMapOutlineNode(BaseModel):
    """Vision outline for DITA map hierarchy (diagram → nested topicrefs). ``map_root`` is logical only."""

    model_config = {"extra": "forbid"}

    title: str = Field(default="", max_length=300)
    dita_type: ChatMapHierarchyNodeType = "topic"
    children: list["ChatMapOutlineNode"] = Field(default_factory=list)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class ChatBundleArtifact(BaseModel):
    """One file in a generated map bundle (.ditamap or .dita)."""

    model_config = {"extra": "ignore"}

    role: Literal["map", "topic"]
    dita_type: str
    filename: str
    href: str
    asset_id: str | None = None
    url: str | None = None
    xml_preview: str = ""


class ChatAttachmentRef(BaseModel):
    asset_id: str
    kind: ChatAttachmentKind
    filename: str
    mime_type: str
    size_bytes: int = 0
    url: str
    storage_path: str | None = None
    content_preview: str | None = None


class ChatDitaGenerationOptions(BaseModel):
    dita_type: ChatDitaType | None = None
    save_path: str | None = None
    file_name: str | None = None
    strict_validation: bool = True
    style_strictness: ChatStyleStrictness = "medium"
    preserve_prolog: bool = False
    xref_placeholders: bool = False
    auto_ids: bool = True
    output_mode: ChatAuthoringOutputMode = "xml_validation"
    authoring_pattern: ChatAuthoringPattern = "default"
    #: When True and reference declared a task DOCTYPE, reuse that declaration line on output (Cisco / CCMS alignment).
    preserve_reference_doctype: bool = False
    #: single_topic: existing screenshot→one topic pipeline; map_hierarchy: diagram → .ditamap + stub topics.
    screenshot_deliverable: ChatScreenshotDeliverableMode = "single_topic"


class ChatAuthoringIntentDecision(BaseModel):
    is_authoring_request: bool = False
    confidence: float = 0.0
    reason: str = ""
    dita_type_hint: ChatDitaType | None = None


class ChatImageContext(BaseModel):
    """Vision output: legacy flat fields plus optional structured IR."""

    summary: str = ""
    visible_text: list[str] = Field(default_factory=list)
    ui_elements: list[dict[str, str]] = Field(default_factory=list)
    inferred_workflow: str = ""
    warnings: list[str] = Field(default_factory=list)
    raw_model: str | None = None
    vision_provider: str | None = None
    structured: ScreenshotContentModel = Field(default_factory=ScreenshotContentModel)
    understanding_trace: ScreenshotUnderstandingTrace | None = None


class ChatReferenceDitaSummary(BaseModel):
    root_type: str = ""
    title: str = ""
    shortdesc: str = ""
    section_tags: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    structure_summary: str = ""
    style_profile: ReferenceStyleProfile | None = None


class ChatSemanticPlanSection(BaseModel):
    name: str
    purpose: str
    details: list[str] = Field(default_factory=list)
    # "bullet" → emit <ul><li>, "numbered" → emit <ol><li>, "" / "plain" → emit <p> per item.
    # Set by merge_structured_into_plan when the section originates from a bullet_list or
    # numbered_steps region so the serializer can choose the right DITA list element.
    list_kind: str = Field(default="", description="bullet | numbered | plain (empty = plain)")


class ChatSemanticPlan(BaseModel):
    title: str
    dita_type: ChatDitaType
    shortdesc: str
    audience: str = ""
    purpose: str = ""
    sections: list[ChatSemanticPlanSection] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    reference_adoption: ReferenceAdoptionDecision | None = None


class ChatDitaValidationResult(BaseModel):
    """Flat validation DTO from folder/review checks (internal services)."""

    valid: bool = False
    repaired: bool = False
    quality_score: int | None = None
    validator_errors: list[str] = Field(default_factory=list)
    validator_warnings: list[str] = Field(default_factory=list)
    structural_issues: list[str] = Field(default_factory=list)
    review_issues: list[Any] = Field(default_factory=list)
    aem_guides_validation_errors: list[str] = Field(default_factory=list)
    applied_repairs: list[str] = Field(default_factory=list)


class TopicGenerationValidation(BaseModel):
    """Structured validation outcome for generation APIs (issues are first-class)."""

    model_config = {"extra": "ignore"}

    valid: bool = False
    repaired: bool = False
    quality_score: int | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    applied_repairs: list[str] = Field(default_factory=list)

    @classmethod
    def from_chat_dita_validation(cls, vr: ChatDitaValidationResult) -> TopicGenerationValidation:
        issues: list[ValidationIssue] = []
        for m in vr.validator_errors:
            issues.append(ValidationIssue(category="validator", severity="error", message=str(m)))
        for m in vr.validator_warnings:
            issues.append(ValidationIssue(category="validator", severity="warning", message=str(m)))
        for m in vr.structural_issues:
            issues.append(ValidationIssue(category="structural", severity="error", message=str(m)))
        for m in vr.aem_guides_validation_errors:
            issues.append(ValidationIssue(category="aem_guides", severity="error", message=str(m)))
        for item in vr.review_issues:
            msg = str(item) if not isinstance(item, dict) else str(item.get("message") or item)
            issues.append(ValidationIssue(category="review", severity="warning", message=msg))
        return cls(
            valid=vr.valid,
            repaired=vr.repaired,
            quality_score=vr.quality_score,
            issues=issues,
            applied_repairs=list(vr.applied_repairs or []),
        )

    def to_chat_dita_validation_result(self) -> ChatDitaValidationResult:
        """Rebuild flat buckets for legacy consumers (UI, older tools)."""
        ve: list[str] = []
        vw: list[str] = []
        se: list[str] = []
        ae: list[str] = []
        rv: list[Any] = []
        for i in self.issues:
            if i.category == "validator":
                (ve if i.severity == "error" else vw).append(i.message)
            elif i.category == "structural":
                se.append(i.message)
            elif i.category == "aem_guides":
                ae.append(i.message)
            elif i.category == "review":
                rv.append(i.message)
            else:
                (ve if i.severity == "error" else vw).append(i.message)
        return ChatDitaValidationResult(
            valid=self.valid,
            repaired=self.repaired,
            quality_score=self.quality_score,
            validator_errors=ve,
            validator_warnings=vw,
            structural_issues=se,
            aem_guides_validation_errors=ae,
            review_issues=rv,
            applied_repairs=list(self.applied_repairs),
        )


TopicGenerationRepairMode = Literal["none", "validate_only", "single_pass", "aggressive"]


class TopicGenerationRequest(BaseModel):
    """
    Typed request for screenshot-guided generation (chat, benchmarks, future workers).

    ``reference_attachment_order`` reserves multi-reference ordering by ``asset_id``.
    ``map_generation_hint`` and ``repair_mode`` are forward-compatible hooks (no-op today unless set).
    """

    model_config = {"extra": "forbid"}

    content: str
    attachments: list[ChatAttachmentRef] = Field(default_factory=list)
    generation_options: ChatDitaGenerationOptions = Field(default_factory=ChatDitaGenerationOptions)
    jira_context: str | None = Field(default=None, max_length=32000)
    authoring_trace_id: str | None = None
    reference_attachment_order: list[str] = Field(
        default_factory=list,
        description="Optional asset_id order when multiple reference_dita attachments are used.",
    )
    repair_mode: TopicGenerationRepairMode = "none"
    map_generation_hint: str | None = Field(
        default=None,
        max_length=16_000,
        description="Reserved for map/TOC-aware generation (opaque; not executed by default).",
    )


class TopicGenerationResult(BaseModel):
    """Core generation outcome without chat-specific actions (reusable from jobs/workers)."""

    model_config = {"extra": "ignore"}

    status: Literal["saved", "valid", "repaired", "invalid", "error"]
    title: str = ""
    dita_type: ChatDitaType = "topic"
    xml_preview: str = ""
    validation: TopicGenerationValidation = Field(default_factory=TopicGenerationValidation)
    saved_asset_path: str | None = None
    artifact_url: str | None = None
    semantic_plan: ChatSemanticPlan | None = None
    image_context: ChatImageContext | None = None
    reference_summaries: list[ChatReferenceDitaSummary] = Field(default_factory=list)
    reference_adoption_decision: ReferenceAdoptionDecision | None = None
    assumptions: list[GenerationAssumption] = Field(default_factory=list)
    style_profile_diff_summary: str | None = None
    screenshot_confidence: float | None = None
    link_recommendations: list[LinkRecommendation] = Field(default_factory=list)
    debug: TopicGenerationDebug = Field(default_factory=TopicGenerationDebug)
    bundle_artifacts: list[ChatBundleArtifact] = Field(
        default_factory=list,
        description="When screenshot_deliverable=map_hierarchy, all generated files (map + topics).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reference_summary(self) -> ChatReferenceDitaSummary | None:
        return self.reference_summaries[0] if self.reference_summaries else None


class ChatAction(BaseModel):
    key: str
    label: str
    url: str | None = None
    description: str | None = None


class ChatDitaAuthoringResult(TopicGenerationResult):
    """Chat streaming/persistence envelope: adds human-readable text and UI actions."""

    model_config = {"extra": "ignore"}

    actions: list[ChatAction] = Field(default_factory=list)
    message: str = ""
    explanation: str | None = None

    @property
    def validation_result(self) -> ChatDitaValidationResult:
        """Flat validation buckets for code paths that still expect :class:`ChatDitaValidationResult`."""
        return self.validation.to_chat_dita_validation_result()

    @model_serializer(mode="wrap")
    def _serialize_with_legacy_aliases(self, handler):
        """Emit validation_result, string assumptions, and debug dict for existing clients."""
        data = handler(self)
        # Wire format keeps flat validation_result; omit duplicate typed "validation" blob.
        data.pop("validation", None)
        data["validation_result"] = self.validation.to_chat_dita_validation_result().model_dump(mode="json")
        data["assumptions"] = [a.text for a in self.assumptions]
        dbg = self.debug.model_dump(mode="json")
        if self.debug.pipeline_stages:
            dbg.setdefault("pipeline_trace", self.debug.pipeline_stages)
        data["debug"] = dbg
        if self.reference_summaries:
            data["reference_summary"] = self.reference_summaries[0].model_dump(mode="json")
        else:
            data["reference_summary"] = None
        return data


class ChatAuthoringRequestPayload(TopicGenerationRequest):
    """Chat session wrapper: adds free-form UI context and human-precision flag."""

    model_config = {"extra": "forbid"}

    context: dict[str, Any] | None = None
    human_prompts: bool = True


class ValidationDiffSnapshot(BaseModel):
    """Before/after validation for workspace repair — errors vs warnings split for readability."""

    valid_before: bool = False
    valid_after: bool = False
    structural_errors_before: list[str] = Field(default_factory=list)
    structural_errors_after: list[str] = Field(default_factory=list)
    structural_warnings_before: list[str] = Field(default_factory=list)
    structural_warnings_after: list[str] = Field(default_factory=list)
    validator_errors_before: list[str] = Field(default_factory=list)
    validator_errors_after: list[str] = Field(default_factory=list)
    aem_guides_errors_before: list[str] = Field(default_factory=list)
    aem_guides_errors_after: list[str] = Field(default_factory=list)


class DitaRepairRequest(BaseModel):
    """Repair generated/edited DITA without full regeneration when possible."""

    xml: str = Field(..., max_length=600_000)
    reference_dita: str | None = Field(default=None, max_length=600_000)
    target_dita_type: ChatDitaType | None = None
    fix_unresolved_same_document_links: bool = True
    apply_structural_repairs: bool = True
    reformat_to_reference_style: bool = False
    apply_review_safe_fixes: bool = False
    generation_options: ChatDitaGenerationOptions | None = None


class DitaRepairResult(BaseModel):
    xml: str
    repair_summary: list[str] = Field(default_factory=list)
    validation_diff: ValidationDiffSnapshot
    used_structured_reserialize: bool = False
    parse_warnings: list[str] = Field(default_factory=list)
    semantic_plan_summary: dict[str, Any] = Field(default_factory=dict)


ChatMapOutlineNode.model_rebuild()
