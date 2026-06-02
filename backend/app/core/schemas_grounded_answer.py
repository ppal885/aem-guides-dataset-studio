from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


GroundedAnswerKind = Literal[
    "dita_attribute",
    "dita_element",
    "dita_content_model",
    "dita_placement",
    "dita_output_behavior",
    "dita_attribute_comparison",
    "dita_element_comparison",
    "dita_element_family_overview",
    "dita_map_construct",
    "aem_guides_guidance",
    "native_pdf_guidance",
    "tenant_grounded_guidance",
    "jira_grounded_summary",
]

SourcePolicyDecision = Literal[
    "dita_spec_first",
    "dita_spec_first_then_processor_docs",
    "dita_spec_first_then_aem_guides",
    "aem_guides_first",
    "native_pdf_first",
    "tenant_first",
    "jira_first",
    "mixed_explicit",
]


@dataclass
class VerifiedExampleSnippet:
    label: str
    snippet: str
    source: str = ""
    deterministic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonRow:
    label: str
    definition: str = ""
    syntax: str = ""
    usage_patterns: list[str] = field(default_factory=list)
    supported_elements: list[str] = field(default_factory=list)
    companion_attributes: list[str] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedGroundedFactSet:
    answer_kind: GroundedAnswerKind
    source_policy: SourcePolicyDecision
    guidance_kind: str = ""
    canonical_definition: str = ""
    syntax: str = ""
    valid_values: list[str] = field(default_factory=list)
    supported_elements: list[str] = field(default_factory=list)
    allowed_children: list[str] = field(default_factory=list)
    parent_elements: list[str] = field(default_factory=list)
    companion_attributes: list[str] = field(default_factory=list)
    usage_patterns: list[str] = field(default_factory=list)
    default_behavior: list[str] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    relevant_settings: list[str] = field(default_factory=list)
    placement_notes: list[str] = field(default_factory=list)
    verified_examples: list[VerifiedExampleSnippet] = field(default_factory=list)
    unsupported_points: list[str] = field(default_factory=list)
    semantic_warnings: list[str] = field(default_factory=list)
    comparison_rows: list[ComparisonRow] = field(default_factory=list)
    example_verified: bool = False
    thin_evidence: bool = False
    cross_source_mixed: bool = False
    coverage_status: str = ""
    example_source: str = ""
    generation_strategy: str = ""
    publishing_source_policy: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verified_examples"] = [item.to_dict() for item in self.verified_examples]
        payload["comparison_rows"] = [item.to_dict() for item in self.comparison_rows]
        return payload
