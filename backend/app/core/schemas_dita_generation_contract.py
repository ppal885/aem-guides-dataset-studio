from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ContractStatus = Literal["preview_ready", "clarification_required", "conflict", "unsupported"]
ConstraintScope = Literal["bundle", "artifact"]
ContentMode = Literal["auto_hybrid", "grounded", "synthetic_sample"]
GlossaryUsageMode = Literal["standalone", "with_topics", "with_map_and_topics"]
ComplianceStatus = Literal["satisfied", "issues_found"]
BuildValidationStatus = Literal["not_run", "passed", "failed", "disabled"]
ExampleShape = Literal["minimal_demo", "full_demo", "unspecified"]
ConstructBundleStrategy = Literal["single_topic", "topic_bundle", "glossary_pack", "map_bundle", "mixed_bundle"]


class ElementConstraint(BaseModel):
    name: str
    required: bool = True
    source: str = "prompt"
    scope: ConstraintScope = "artifact"
    implied_family: str | None = None
    allowed_parents: list[str] = Field(default_factory=list)
    supported_attributes: list[str] = Field(default_factory=list)


class AttributeConstraint(BaseModel):
    attribute_name: str
    required: bool = True
    source: str = "prompt"
    scope: ConstraintScope = "bundle"
    required_values: list[str] = Field(default_factory=list)
    supported_elements: list[str] = Field(default_factory=list)
    valid_values: list[str] = Field(default_factory=list)
    implied_family: str | None = None


class PrologMetadataConstraint(BaseModel):
    field_name: str
    required: bool = True
    source: str = "prompt"
    scope: ConstraintScope = "artifact"
    value: str | None = None


class TopicrefAttributeDistributionConstraint(BaseModel):
    attribute_name: str
    attribute_value: str
    count: int = 1
    source: str = "prompt"
    target: str = "topicref"


class StructureRequirement(BaseModel):
    structure_name: str
    count: int | None = None
    rows: int | None = None
    columns: int | None = None
    language: str | None = None
    scope: ConstraintScope = "artifact"
    source: str = "prompt"


class KeyedLinkRequirement(BaseModel):
    key_name: str = "external-docs"
    href: str = "https://example.com/docs"
    format: str = "html"
    scope: str = "external"
    definition_element: str = "keydef"
    consumer_element: str = "xref"
    link_text: str = "External documentation"
    source: str = "prompt"


class FilenameRequirement(BaseModel):
    requested_name: str
    safe_name: str
    strategy: str = "sanitize"
    reason: str = "Physical filenames must be safe for the target filesystem."
    source: str = "prompt"


class ConstraintConflict(BaseModel):
    kind: str
    message: str
    requested: str | None = None
    reason: str = ""
    suggested_families: list[str] = Field(default_factory=list)


class ClarificationRequest(BaseModel):
    missing_field: str
    question: str
    options: list[str] = Field(default_factory=list)


class FamilyDecision(BaseModel):
    requested: str | None = None
    inferred: str | None = None
    resolved: str | None = None
    reason: str = ""
    source: str = ""
    compatible_families: list[str] = Field(default_factory=list)


class ArtifactContract(BaseModel):
    kind: str
    count: int = 1
    label: str = ""
    topic_family: str | None = None


class BundleContract(BaseModel):
    bundle_type: str = "single_topic"
    include_map: bool = False
    artifacts: list[ArtifactContract] = Field(default_factory=list)


class ArtifactDraft(BaseModel):
    kind: str
    topic_family: str | None = None
    title: str = ""
    shortdesc: str | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    required_elements: list[str] = Field(default_factory=list)
    required_attributes: dict[str, list[str]] = Field(default_factory=dict)


class MapDraft(BaseModel):
    title: str = ""
    topicrefs: list[dict[str, Any]] = Field(default_factory=list)
    keydefs: list[dict[str, Any]] = Field(default_factory=list)
    reltables: list[dict[str, Any]] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    kind: str
    message: str
    severity: Literal["warning", "error"] = "error"


class ContractComplianceReport(BaseModel):
    status: ComplianceStatus = "satisfied"
    required_elements: list[str] = Field(default_factory=list)
    required_attributes: list[str] = Field(default_factory=list)
    required_metadata: list[str] = Field(default_factory=list)
    glossary_usage_mode: GlossaryUsageMode | None = None
    issues: list[str] = Field(default_factory=list)


class BuildValidationOutcome(BaseModel):
    enabled: bool = False
    status: BuildValidationStatus = "not_run"
    message: str | None = None
    validator: str | None = None
    issues: list[str] = Field(default_factory=list)


class ConstructSemantic(BaseModel):
    name: str
    category: str = ""
    construct_group: str = ""
    construct_scope: ConstraintScope | None = None
    source: str = "prompt"
    source_url: str | None = None
    family_hint: str | None = None
    bundle_strategy: ConstructBundleStrategy | None = None
    include_map: bool = False
    requires_contract_path: bool = False
    required_elements: list[str] = Field(default_factory=list)
    required_attributes: list[str] = Field(default_factory=list)
    required_companion_artifacts: list[str] = Field(default_factory=list)
    valid_root_types: list[str] = Field(default_factory=list)
    valid_artifact_types: list[str] = Field(default_factory=list)
    compatible_topic_families: list[str] = Field(default_factory=list)
    preferred_structures: list[str] = Field(default_factory=list)
    example_counts: dict[str, int] = Field(default_factory=dict)
    invalid_single_topic_reason: str | None = None
    canonical_demo_shape: str = ""
    validation_rules: list[str] = Field(default_factory=list)
    deterministic_recipe_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class DomainDecomposition(BaseModel):
    source: str = "heuristic"
    focus: str | None = None
    subtopics: list[str] = Field(default_factory=list)
    reason: str = ""


class DitaGenerationContract(BaseModel):
    contract_version: str = "v2"
    status: ContractStatus = "preview_ready"
    summary: str = ""
    clarification_needed: bool = False
    clarification_question: str | None = None
    clarification_request: ClarificationRequest | None = None
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    conflicts: list[ConstraintConflict] = Field(default_factory=list)
    content_mode: ContentMode = "auto_hybrid"
    bundle_type: str = "single_topic"
    topic_family: str = "auto"
    consuming_topic_family: str | None = None
    subject: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    artifacts: list[ArtifactContract] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    include_map: bool = False
    glossary_usage_mode: GlossaryUsageMode = "standalone"
    example_request: bool = False
    example_construct: str | None = None
    construct_scope: ConstraintScope | None = None
    example_shape: ExampleShape = "unspecified"
    example_shape_clarification_required: bool = False
    construct_semantics: list[ConstructSemantic] = Field(default_factory=list)
    domain_decomposition: DomainDecomposition | None = None
    required_elements: list[ElementConstraint] = Field(default_factory=list)
    required_attributes: list[AttributeConstraint] = Field(default_factory=list)
    topicref_attribute_distributions: list[TopicrefAttributeDistributionConstraint] = Field(default_factory=list)
    required_metadata: list[PrologMetadataConstraint] = Field(default_factory=list)
    preferred_structures: list[str] = Field(default_factory=list)
    structure_requirements: list[StructureRequirement] = Field(default_factory=list)
    keyed_link_requirements: list[KeyedLinkRequirement] = Field(default_factory=list)
    filename_requirements: list[FilenameRequirement] = Field(default_factory=list)
    forbidden_structures: list[str] = Field(default_factory=list)
    influence_inputs: list[str] = Field(default_factory=list)
    family_decision: FamilyDecision = Field(default_factory=FamilyDecision)
    artifact_drafts: list[ArtifactDraft] = Field(default_factory=list)
    map_draft: MapDraft | None = None
    build_validation: BuildValidationOutcome = Field(default_factory=BuildValidationOutcome)
    execution_text: str | None = None
    execution_instructions: str | None = None
