"""Frontend-oriented structured UAC contract (cards/tables) — JSON only, documented in OpenAPI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- OpenAPI / docs examples (single source for nested ``example`` + envelope examples) ---

EXAMPLE_UAC_UI_CONTRACT: dict[str, Any] = {
    "version": 1,
    "risk_badge": {
        "level": "high",
        "label": "High risk",
        "risk_score": 3.0,
        "message": None,
    },
    "classification_card": {
        "jira_key": "GUIDES-1234",
        "classification": {
            "domain": "native_pdf",
            "issue_type": "Bug",
            "customer_names": ["Contoso"],
            "affected_outputs": ["native_pdf"],
            "dita_entities": ["keyref"],
        },
    },
    "executive_summary_card": {
        "summary": (
            "GUIDES-1234 UAC snapshot (native_pdf): entities «keyref», outputs «native_pdf»; customers: Contoso."
        ),
        "release_risk": "Risk level high per indexed enrichment + UAC drivers.",
        "decisions_needed_preview": ["Confirm repro on 4.4 baseline"],
        "qa_commitments_preview": ["GUIDES-1234: Validate keyref in PDF [P1, publish]"],
    },
    "similar_jira_learning_cards": [
        {
            "jira_key": "GUIDES-991",
            "title": "Keyref missing in Native PDF",
            "why_relevant": "Overlapping keyref entities and native_pdf output",
            "what_we_learned": "Reuse overlapped entity/output risk only.",
            "confidence_score": 0.82,
            "scores": {"final": 0.9, "vector": 0.7, "metadata": 0.85},
            "chunk_type": "body",
        }
    ],
    "must_test_scenario_table": {
        "rows": [
            {
                "id": "mt-0",
                "scenario": "GUIDES-1234: keyref resolves in published PDF",
                "why": "Regression vector from similar tickets",
                "evidence": "EPV-991; entity overlap keyref",
                "test_layer": "publish",
                "priority": "P1",
            }
        ]
    },
    "missing_clarification_table": {
        "rows": [
            {
                "id": "mc-0",
                "question": "Which DITA-OT / Native PDF preset?",
                "why": "Output path affects repro",
                "evidence": "",
                "related_entity": "native_pdf",
            }
        ]
    },
    "automation_strategy_card": {
        "fit": "Strong",
        "primary_test_layer": "API",
        "framework": "REST + PDF binary compare",
        "suggested_test_name": "guides_1234_uac",
    },
    "dataset_recommendation_card": {
        "items": ["Dataset/fixture: add labelled DITA + map samples"],
        "hints_from_guardrails": [],
        "insufficient_similar_pool": False,
    },
    "confidence_warnings_card": {
        "confidence": {"score": 0.72, "level": "medium", "signals": ["similar_jira_overlap"]},
        "quality_score": 78,
        "answer_quality": {
            "score": 78,
            "generic_phrases_found": [],
            "missing_specificity": [],
            "recommendation": "accept",
        },
        "uac_validation_ok": True,
        "uac_validation_errors": [],
        "insufficient_similar_evidence": False,
        "claim_verification": {
            "dropped_count": 0,
            "downgraded_count": 1,
            "unsupported_count": 0,
        },
        "guardrails_warnings": [],
        "blocked_claims_count": 0,
    },
    "debug_accordion": {
        "debug_mode": True,
        "retrieval_debug": {"scores": [], "extracted": {}},
        "anti_repetition": None,
        "claim_verification_detail": None,
        "uac_guardrails_detail": {"warnings": [], "blocked_claims": []},
        "structured_uac_available": True,
    },
    "qa_handoff_card": {
        "requested": True,
        "generated": True,
        "note": None,
        "regression_breadth": "focused",
        "smoke_checks": ["Open map, verify keyref badge"],
        "deep_regression_focus": ["Publish Native PDF with ditaval filter"],
        "blocking_for_signoff": [{"question": "Which preset?", "owner_role": "dev"}],
        "exit_criteria": ["PDF matches preview for sample map"],
        "exploratory_angles": ["Empty keyref fallback"],
        "jira_test_script": {
            "title": "Native PDF keyref",
            "preconditions": ["Indexed content present"],
            "steps": ["Publish", "Open PDF"],
            "expected_result": "Key resolves",
        },
        "qa_lead_note": "Pair with customer UAT if similar pool is thin.",
    },
}

MINIMAL_UAC_UI_CONTRACT: dict[str, Any] = {
    "version": 1,
    "risk_badge": {"level": "low", "label": "Low risk", "risk_score": 1.0, "message": None},
    "classification_card": {"jira_key": "EPV-1", "classification": {}},
    "executive_summary_card": {
        "summary": "UAC snapshot",
        "release_risk": "",
        "decisions_needed_preview": [],
        "qa_commitments_preview": [],
    },
    "similar_jira_learning_cards": [],
    "must_test_scenario_table": {"rows": []},
    "missing_clarification_table": {"rows": []},
    "automation_strategy_card": {
        "fit": "Partial",
        "primary_test_layer": "",
        "framework": "",
        "suggested_test_name": "epv_1_uac",
    },
    "dataset_recommendation_card": {
        "items": [],
        "hints_from_guardrails": [],
        "insufficient_similar_pool": False,
    },
    "confidence_warnings_card": {
        "confidence": {},
        "quality_score": None,
        "answer_quality": None,
        "uac_validation_ok": True,
        "uac_validation_errors": [],
        "insufficient_similar_evidence": False,
        "claim_verification": {
            "dropped_count": 0,
            "downgraded_count": 0,
            "unsupported_count": 0,
        },
        "guardrails_warnings": [],
        "blocked_claims_count": 0,
    },
    "debug_accordion": {
        "debug_mode": False,
        "retrieval_debug": {"note": "Set debug=true on the request for the full retrieval sink."},
        "structured_uac_available": False,
    },
    "qa_handoff_card": {
        "requested": False,
        "generated": False,
        "note": None,
        "regression_breadth": "",
        "smoke_checks": [],
        "deep_regression_focus": [],
        "blocking_for_signoff": [],
        "exit_criteria": [],
        "exploratory_angles": [],
        "jira_test_script": {"title": "", "preconditions": [], "steps": [], "expected_result": ""},
        "qa_lead_note": "",
    },
}


def uac_analyze_response_openapi_example() -> dict[str, Any]:
    """Single rich envelope example for POST /analyze (OpenAPI)."""
    ui = EXAMPLE_UAC_UI_CONTRACT
    return {
        "jira_key": "GUIDES-1234",
        "uac_ui": ui,
        "uac_answer": "Legacy markdown brief may still be present; clients should prefer uac_ui for UI.",
        "classification": ui["classification_card"]["classification"],
        "similar_jiras": ui["similar_jira_learning_cards"],
        "quality_score": 78,
        "uac_validation_ok": True,
        "uac_decision_record": {
            "summary": ui["executive_summary_card"]["summary"],
            "dataset_needed": ui["dataset_recommendation_card"]["items"],
        },
    }


def uac_analyze_response_openapi_example_minimal() -> dict[str, Any]:
    """Second envelope example — sparse payload."""
    return {
        "jira_key": "EPV-1",
        "uac_ui": MINIMAL_UAC_UI_CONTRACT,
        "uac_answer": None,
    }


# --- Nested section models ---


class UacRiskBadgeUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field(description="high | medium | low | insufficient | unspecified")
    label: str = Field(description="Human-readable badge label for the level")
    risk_score: float | None = Field(None, description="Numeric risk score when available (e.g. 0–3)")
    message: str | None = Field(None, description="Optional short risk message from enrichment")


class UacClassificationCardUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    jira_key: str = ""
    classification: dict[str, Any] = Field(default_factory=dict)


class UacExecutiveSummaryCardUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    release_risk: str = ""
    decisions_needed_preview: list[str] = Field(default_factory=list)
    qa_commitments_preview: list[str] = Field(default_factory=list)


class UacSimilarJiraLearningCardUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_key: str
    title: str = ""
    why_relevant: str = ""
    what_we_learned: str = ""
    confidence_score: float | None = None
    scores: dict[str, Any] | None = None
    chunk_type: str | None = None


class UacMustTestScenarioRowUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    scenario: str
    why: str = ""
    evidence: str = ""
    test_layer: str = ""
    priority: str = ""


class UacMustTestScenarioTableUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[UacMustTestScenarioRowUi] = Field(default_factory=list)


class UacMissingClarificationRowUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    question: str
    why: str = ""
    evidence: str = ""
    related_entity: str | None = None


class UacMissingClarificationTableUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[UacMissingClarificationRowUi] = Field(default_factory=list)


class UacAutomationStrategyCardUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fit: str = "Partial"
    primary_test_layer: str = ""
    framework: str = ""
    suggested_test_name: str = ""


class UacDatasetRecommendationCardUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(default_factory=list)
    hints_from_guardrails: list[str] = Field(default_factory=list)
    insufficient_similar_pool: bool = False


class UacClaimVerificationSummaryUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dropped_count: int = 0
    downgraded_count: int = 0
    unsupported_count: int = 0


class UacGuardrailWarningUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str | None = None
    message: str | None = None
    detail: str | None = None


class UacConfidenceWarningsCardUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    confidence: dict[str, Any] = Field(default_factory=dict)
    quality_score: int | None = None
    answer_quality: dict[str, Any] | None = None
    uac_validation_ok: bool = True
    uac_validation_errors: list[str] = Field(default_factory=list)
    insufficient_similar_evidence: bool = False
    claim_verification: UacClaimVerificationSummaryUi = Field(default_factory=UacClaimVerificationSummaryUi)
    guardrails_warnings: list[UacGuardrailWarningUi] = Field(default_factory=list)
    blocked_claims_count: int = 0


class UacDebugAccordionUi(BaseModel):
    model_config = ConfigDict(extra="allow")

    debug_mode: bool = False
    retrieval_debug: dict[str, Any] | None = None
    anti_repetition: dict[str, Any] | None = None
    claim_verification_detail: dict[str, Any] | None = None
    uac_guardrails_detail: dict[str, Any] | None = None
    dropped_generic_points: list[dict[str, Any]] | None = None
    generic_phrases_removed: list[str] | None = None
    regeneration_used: bool | None = None
    structured_uac_available: bool = False


class UacQaBlockingRowUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = ""
    owner_role: str = "other"


class UacJiraTestScriptOutlineUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""


class UacQaHandoffCardUi(BaseModel):
    """Second-pass LLM QA plan: smoke vs deep, sign-off blockers, Jira test outline."""

    model_config = ConfigDict(extra="forbid")

    requested: bool = False
    generated: bool = False
    note: str | None = None
    regression_breadth: str = Field("", description="smoke | focused | full when generated")
    smoke_checks: list[str] = Field(default_factory=list)
    deep_regression_focus: list[str] = Field(default_factory=list)
    blocking_for_signoff: list[UacQaBlockingRowUi] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    exploratory_angles: list[str] = Field(default_factory=list)
    jira_test_script: UacJiraTestScriptOutlineUi = Field(default_factory=UacJiraTestScriptOutlineUi)
    qa_lead_note: str = ""


class UacUiContract(BaseModel):
    """Structured sections for dashboard-style UAC rendering (no Markdown in this object)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": EXAMPLE_UAC_UI_CONTRACT})

    version: int = Field(1, description="Contract version for clients")
    risk_badge: UacRiskBadgeUi
    classification_card: UacClassificationCardUi
    executive_summary_card: UacExecutiveSummaryCardUi
    similar_jira_learning_cards: list[UacSimilarJiraLearningCardUi] = Field(default_factory=list)
    must_test_scenario_table: UacMustTestScenarioTableUi
    missing_clarification_table: UacMissingClarificationTableUi
    automation_strategy_card: UacAutomationStrategyCardUi
    dataset_recommendation_card: UacDatasetRecommendationCardUi
    confidence_warnings_card: UacConfidenceWarningsCardUi
    debug_accordion: UacDebugAccordionUi
    qa_handoff_card: UacQaHandoffCardUi = Field(
        default_factory=UacQaHandoffCardUi,
        description="Optional extended QA handoff from a second LLM pass when include_qa_handoff=true",
    )


class UacAnalyzeApiResponse(BaseModel):
    """
    Analyze response envelope. Primary UI payload: ``uac_ui`` (structured JSON).

    Additional keys are allowed for backward compatibility (e.g. ``structured_uac``, ``evidence_summary``).
    Successful analyze responses include ``uac_ui`` for card/table rendering; ``uac_answer`` remains a legacy Markdown brief.
    """

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                uac_analyze_response_openapi_example(),
                uac_analyze_response_openapi_example_minimal(),
            ]
        },
    )

    jira_key: str
    uac_ui: UacUiContract | None = Field(
        None,
        description="Structured UI contract (cards/tables). Present on successful analyze responses from this service.",
    )
    uac_answer: str | None = None
    classification: dict[str, Any] | None = None
    risk_summary: dict[str, Any] | None = None
    similar_jiras: list[dict[str, Any]] | None = None
    must_test_scenarios: list[dict[str, Any]] | None = None
    missing_clarifications: list[dict[str, Any]] | None = None
    automation_fit: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None
    retrieval_debug: dict[str, Any] | None = None
    structured_uac: dict[str, Any] | None = None
    quality_score: int | None = None
    uac_validation_ok: bool | None = None
    uac_validation_errors: list[str] | None = None
    uac_decision_record: dict[str, Any] | None = None
    uac_guardrails: dict[str, Any] | None = None
    claim_verification: dict[str, Any] | None = None
    insufficient_similar_evidence: bool | None = None


__all__ = [
    "EXAMPLE_UAC_UI_CONTRACT",
    "MINIMAL_UAC_UI_CONTRACT",
    "UacAnalyzeApiResponse",
    "UacAutomationStrategyCardUi",
    "UacClassificationCardUi",
    "UacConfidenceWarningsCardUi",
    "UacDatasetRecommendationCardUi",
    "UacDebugAccordionUi",
    "UacExecutiveSummaryCardUi",
    "UacJiraTestScriptOutlineUi",
    "UacMissingClarificationRowUi",
    "UacMissingClarificationTableUi",
    "UacMustTestScenarioRowUi",
    "UacMustTestScenarioTableUi",
    "UacQaBlockingRowUi",
    "UacQaHandoffCardUi",
    "UacRiskBadgeUi",
    "UacSimilarJiraLearningCardUi",
    "UacUiContract",
    "uac_analyze_response_openapi_example",
    "uac_analyze_response_openapi_example_minimal",
]
