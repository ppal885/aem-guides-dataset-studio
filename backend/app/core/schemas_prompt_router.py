from typing import Any, Literal

from pydantic import BaseModel, Field


PromptIntent = Literal[
    "dita_question",
    "dita_generation",
    "dita_answer_then_generation",
    "dita_review",
    "screenshot_authoring",
    "reference_guided_generation",
    "dataset_job",
    "aem_guides_question",
    "native_pdf_guidance",
    "dita_ot_build",
    "artifact_request",
    "unsupported",
    "unknown",
]

ExecutionAction = Literal[
    "answer_directly",
    "answer_then_preview",
    "preview_first",
    "clarify_first",
    "run_directly",
    "reject_as_unsupported",
]


class PromptRouteDecision(BaseModel):
    intent: PromptIntent = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supported: bool = True
    needs_clarification: bool = False
    execution_hint: str = ""
    legacy_answer_mode: str = "default"
    reasoning_notes: list[str] = Field(default_factory=list)
    candidate_contract: dict[str, Any] = Field(default_factory=dict)


class ExecutionPolicyDecision(BaseModel):
    action: ExecutionAction = "answer_directly"
    reason: str = ""
    review_required: bool = False
    clarification_question: str | None = None
    candidate_contract: dict[str, Any] = Field(default_factory=dict)
