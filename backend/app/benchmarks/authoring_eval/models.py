from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class VisionStructuredFixture(BaseModel):
    """Subset of ScreenshotContentModel fields for YAML-driven stubs."""

    title: str = ""
    numbered_steps: list[str] = Field(default_factory=list)
    bullet_lists: list[list[str]] = Field(default_factory=list)
    ui_labels: list[str] = Field(default_factory=list)
    confidence: float = 0.85
    uncertainty_warnings: list[str] = Field(default_factory=list)


class VisionFixture(BaseModel):
    summary: str = ""
    visible_text: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    vision_provider: str | None = "benchmark_stub"
    structured: VisionStructuredFixture = Field(default_factory=VisionStructuredFixture)


class BenchmarkCase(BaseModel):
    """One row in the benchmark manifest."""

    id: str
    prompt: str
    expected_dita_type: Literal["topic", "task", "concept", "reference"] | None = None
    reference_path: str | None = Field(
        default=None,
        description="Path relative to dataset root, e.g. references/sample_task.dita",
    )
    screenshot_path: str | None = Field(
        default=None,
        description="Optional PNG relative to dataset; if omitted a minimal 1×1 PNG is used.",
    )
    vision: VisionFixture = Field(default_factory=VisionFixture)
    style_strictness: Literal["low", "medium", "high"] = "high"
    strict_validation: bool = True
    output_mode: Literal["xml_only", "xml_explanation", "xml_validation", "xml_style_diff"] = "xml_validation"
    dita_type_override: Literal["topic", "task", "concept", "reference"] | None = Field(
        default=None,
        description="If set, passed as generation_options.dita_type (user override).",
    )
    save_path: str | None = Field(
        default=None,
        description="If set, generation attempts AEM save when valid (mock in tests).",
    )
    expect_saved_to_aem: bool = Field(
        default=False,
        description="When true, case expects status=saved when AEM save is mocked to succeed.",
    )
    notes: str = ""


class BenchmarkDefaults(BaseModel):
    tenant_id: str = "benchmark-tenant"
    session_id: str = "benchmark-session"
    user_id: str = "benchmark-user"


class BenchmarkManifest(BaseModel):
    version: int = 1
    defaults: BenchmarkDefaults = Field(default_factory=BenchmarkDefaults)
    cases: list[BenchmarkCase] = Field(default_factory=list)

    @classmethod
    def load_yaml(cls, path: Path) -> BenchmarkManifest:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)


class DimensionScores(BaseModel):
    """Scalar scores for one generated sample. Use 0–1 where higher is better unless noted."""

    xml_valid: bool
    structural_ok: bool
    topic_type_correct: bool | None = Field(
        default=None,
        description="None when expected_dita_type not specified.",
    )
    style_adherence: float | None = Field(
        default=None,
        description="0–1 vs reference profile when reference present; else None.",
    )
    over_copying_risk: float = Field(
        ...,
        description="0 = no leaked reference @id / xref @href / @conref in output; 1 = any leak detected.",
    )
    unresolved_xref_conref_rate: float = Field(
        ...,
        description="Unresolved same-document xref/conref count / max(1, total xref+conref elements).",
    )
    pipeline_repair_used: bool = Field(
        ...,
        description="True if repair_optional stage ran (proxy for auto-fix pressure).",
    )
    insertion_success: bool | None = Field(
        default=None,
        description="True if status==saved when expect_saved_to_aem; else None if not applicable.",
    )
    regeneration_observed: bool | None = Field(
        default=None,
        description="Reserved: set from product telemetry JSONL merge, not single-shot generation.",
    )
    edit_after_generation_observed: bool | None = Field(
        default=None,
        description="Reserved: product telemetry only.",
    )


class CaseEvalReport(BaseModel):
    case_id: str
    ok: bool
    dimensions: DimensionScores
    result_status: str
    generated_dita_type: str
    assertion_failures: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class SuiteReport(BaseModel):
    manifest_path: str
    case_reports: list[CaseEvalReport] = Field(default_factory=list)
    aggregates: dict[str, Any] = Field(default_factory=dict)
