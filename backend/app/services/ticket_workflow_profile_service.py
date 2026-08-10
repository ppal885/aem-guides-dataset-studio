"""Classify Jira tickets (Bug vs Feature Request) and drive pipeline orchestration."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas_test_plan_pipeline import TicketBrief

TicketCategory = Literal["bug", "feature_request", "other"]

_BUG_ISSUE_TYPES = frozenset(
    {"bug", "defect", "incident", "problem", "regression", "production bug", "hotfix"}
)
_FEATURE_ISSUE_TYPES = frozenset(
    {
        "feature request",
        "new feature",
        "customer request",
        "story",
        "improvement",
        "enhancement",
        "feature enhancement",
        "wish",
        "request",
        "epic",
    }
)
_BUG_TEXT_RE = re.compile(
    r"\b(bug|defect|regression|steps to reproduce|str(?:\s+)?to repro|actual result|"
    r"not working|do(?:es)? not work|no longer works?|worked earlier|worked before|"
    r"stopped working|fails?|failed|error|broken|incorrect behavior)\b",
    re.I,
)
_FEATURE_TEXT_RE = re.compile(
    r"\b(feature request|feature enhancement|requested enhancement|new capability|"
    r"business need|problem / business need|request type|enhancement request|"
    r"add ootb|provide option|customer requests)\b",
    re.I,
)


class DefaultScenarioRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    priority: str
    title: str
    links_to: str
    verify_hint: str


class TicketWorkflowProfile(BaseModel):
    """Workflow tuning based on Bug vs Feature Request classification."""

    model_config = ConfigDict(extra="forbid")

    ticket_category: TicketCategory = "other"
    jira_issue_type: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    detection_signals: list[str] = Field(default_factory=list)
    pre_uac_focus: str = ""
    must_run_gate_text: str = ""
    primary_scenario_title: str = "Primary scenario"
    default_scenarios: list[DefaultScenarioRow] = Field(default_factory=list)
    workflow_clarifications: list[str] = Field(default_factory=list)
    score_bonus: int = 0
    score_penalty: int = 0
    human_review_reasons: list[str] = Field(default_factory=list)


def _normalize_issue_type(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def _issue_blob(packet: dict[str, Any], brief: TicketBrief) -> str:
    issue = packet.get("issue") or {}
    parts = [
        brief.summary,
        brief.current_behavior,
        brief.expected_behavior,
        str(issue.get("description") or issue.get("snippet") or ""),
    ]
    return "\n".join(p for p in parts if p)


def classify_ticket_workflow(
    packet: dict[str, Any],
    brief: TicketBrief,
    uac_intel: dict[str, Any] | None = None,
) -> TicketWorkflowProfile:
    """Detect Bug vs Feature Request and return orchestration profile."""
    issue = packet.get("issue") or {}
    signals: list[str] = []
    score = {"bug": 0, "feature_request": 0, "other": 0}

    jira_type = _normalize_issue_type(
        brief.issue_type or str(issue.get("issue_type") or issue.get("type") or "")
    )
    if jira_type:
        signals.append(f"jira_issue_type={jira_type}")
        if jira_type in _BUG_ISSUE_TYPES:
            score["bug"] += 4
        elif jira_type in _FEATURE_ISSUE_TYPES:
            score["feature_request"] += 4
        elif "bug" in jira_type:
            score["bug"] += 3
        elif "feature" in jira_type or "request" in jira_type or "story" in jira_type:
            score["feature_request"] += 3

    uac = uac_intel or {}
    cls = uac.get("classification") if isinstance(uac.get("classification"), dict) else {}
    uac_type = _normalize_issue_type(str(cls.get("issue_type") or ""))
    if uac_type and uac_type != jira_type:
        signals.append(f"uac_issue_type={uac_type}")
        if uac_type in _BUG_ISSUE_TYPES:
            score["bug"] += 2
        elif uac_type in _FEATURE_ISSUE_TYPES:
            score["feature_request"] += 2

    blob = _issue_blob(packet, brief)
    if _BUG_TEXT_RE.search(blob):
        score["bug"] += 2
        signals.append("text=bug/repro/failure language")
    if _looks_like_regression_despite_request_type(blob):
        score["bug"] += 3
        signals.append("text=regression-overrides-request-type")
    if _FEATURE_TEXT_RE.search(blob):
        score["feature_request"] += 2
        signals.append("text=feature/enhancement language")

    if brief.current_behavior.strip() and not brief.expected_behavior.strip():
        score["feature_request"] += 2
        signals.append("actual_present_expected_empty")
    if brief.expected_behavior.strip() and brief.current_behavior.strip():
        score["bug"] += 2
        signals.append("actual_and_expected_present")

    if brief.expected_behavior.strip() and not brief.current_behavior.strip():
        score["bug"] += 1
        signals.append("expected_without_actual")

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if top_score == 0:
        category: TicketCategory = "other"
        confidence: Literal["high", "medium", "low"] = "low"
    elif top_score >= second_score + 2:
        category = top_cat  # type: ignore[assignment]
        confidence = "high" if top_score >= 4 else "medium"
    else:
        category = top_cat if top_score > 0 else "other"  # type: ignore[assignment]
        confidence = "low"
        signals.append("classification_tie_or_weak")

    return _build_profile(category, jira_type or uac_type, confidence, signals, brief)


def _looks_like_regression_despite_request_type(text: str) -> bool:
    lowered = str(text or "").lower()
    has_regression_language = bool(
        re.search(
            r"\b(worked earlier|worked before|do(?:es)? not work anymore|no longer works|"
            r"stopped working|regression|used to work)\b",
            lowered,
        )
    )
    has_comparative_examples = bool(
        re.search(r"(?im)^\s*(does not work|not working|fails)\s*:?\s*$", text or "")
        and re.search(r"(?im)^\s*(works|working|control)\s*:?\s*$", text or "")
    )
    return has_regression_language or has_comparative_examples


def _build_profile(
    category: TicketCategory,
    jira_issue_type: str,
    confidence: Literal["high", "medium", "low"],
    signals: list[str],
    brief: TicketBrief,
) -> TicketWorkflowProfile:
    if category == "bug":
        return TicketWorkflowProfile(
            ticket_category="bug",
            jira_issue_type=jira_issue_type,
            confidence=confidence,
            detection_signals=signals[:8],
            pre_uac_focus=(
                "Explain the product area, then anchor on customer repro: Actual vs Expected, "
                "regression checks, and log/error signals."
            ),
            must_run_gate_text=(
                "Customer repro (S-01) and all P0 regression checks must pass on Author before release."
            ),
            primary_scenario_title="Primary repro",
            default_scenarios=[
                DefaultScenarioRow(
                    scenario_id="S-01",
                    priority="P0",
                    title="Primary repro",
                    links_to="EB-1",
                    verify_hint="Actual matches Expected; customer error/log signal absent.",
                ),
                DefaultScenarioRow(
                    scenario_id="S-02",
                    priority="P0 R0",
                    title="R0 control — unchanged valid path",
                    links_to="EB-2",
                    verify_hint="Known-good data/flow still passes (no regression).",
                ),
                DefaultScenarioRow(
                    scenario_id="S-03",
                    priority="P1",
                    title="Negative / edge inputs",
                    links_to="EB-3",
                    verify_hint="Invalid, empty, or mixed inputs fail safely with clear errors.",
                ),
            ],
            workflow_clarifications=[
                "Confirm exact repro environment (Author URL, content path, user role).",
                "Capture Splunk/log line from ticket — use as pass/fail oracle for S-01.",
                "List adjacent flows that must not regress (shared API/UI paths).",
            ],
            score_bonus=5 if brief.current_behavior.strip() and brief.expected_behavior.strip() else 0,
            score_penalty=8 if not brief.current_behavior.strip() else 0,
            human_review_reasons=(
                ["Bug ticket missing Actual Result / repro steps — confirm before test design."]
                if not brief.current_behavior.strip()
                else []
            ),
        )

    if category == "feature_request":
        return TicketWorkflowProfile(
            ticket_category="feature_request",
            jira_issue_type=jira_issue_type,
            confidence=confidence,
            detection_signals=signals[:8],
            pre_uac_focus=(
                "Explain the product area first, then the enhancement ask. "
                "PM must agree expected behavior before sign-off checks."
            ),
            must_run_gate_text=(
                "PM-agreed expected behavior is documented; all P0 capability scenarios pass on Author."
            ),
            primary_scenario_title="New capability happy path",
            default_scenarios=[
                DefaultScenarioRow(
                    scenario_id="S-01",
                    priority="P0",
                    title="New capability — happy path",
                    links_to="EB-1",
                    verify_hint="Delivered behavior matches PM-agreed expected outcome.",
                ),
                DefaultScenarioRow(
                    scenario_id="S-02",
                    priority="P0",
                    title="Regression — unchanged behavior",
                    links_to="EB-2",
                    verify_hint="Existing baseline/product behavior still works without the new option.",
                ),
                DefaultScenarioRow(
                    scenario_id="S-03",
                    priority="P1",
                    title="Edge / negative / permissions",
                    links_to="TA-3",
                    verify_hint="Empty data, missing property, wrong role handled safely.",
                ),
            ],
            workflow_clarifications=[
                "Agree minimum shippable scope — what is explicitly out of scope?",
                "Confirm which UI/API surfaces are in scope (e.g. Web Editor vs legacy console).",
                "Define pass criteria for filter/sort/export if new columns or properties are added.",
            ],
            score_penalty=10 if not brief.expected_behavior.strip() else 0,
            human_review_reasons=(
                ["Feature request without agreed Expected Result — PM alignment required before UAC."]
                if not brief.expected_behavior.strip()
                else []
            ),
        )

    return TicketWorkflowProfile(
        ticket_category="other",
        jira_issue_type=jira_issue_type,
        confidence=confidence,
        detection_signals=signals[:8],
        pre_uac_focus="Review Jira summary and classify as Bug or Feature Request before finalizing AC.",
        must_run_gate_text="All P0 scenarios and sign-off checks must pass on Author.",
        primary_scenario_title="Primary scenario",
        default_scenarios=[
            DefaultScenarioRow(
                scenario_id="S-01",
                priority="P0",
                title="Primary scenario",
                links_to="EB-1",
                verify_hint="Matches Jira expected behavior.",
            ),
        ],
        workflow_clarifications=[
            "Confirm ticket category (Bug vs Feature Request) with PM before locking test scope.",
        ],
        human_review_reasons=["Ticket category unclear — confirm Bug vs Feature Request with PM."],
    )


def category_display_label(category: TicketCategory) -> str:
    return {
        "bug": "Bug",
        "feature_request": "Feature request",
        "other": "Unclassified",
    }.get(category, "Unclassified")


def render_workflow_markdown(profile: TicketWorkflowProfile) -> str:
    label = category_display_label(profile.ticket_category)
    lines = [
        f"**Ticket type:** {label} "
        f"(Jira: {profile.jira_issue_type or 'n/a'} · confidence: {profile.confidence})",
        "",
        f"**Workflow focus:** {profile.pre_uac_focus}",
        "",
    ]
    if profile.workflow_clarifications:
        lines.append("**Type-specific checks:**")
        for idx, item in enumerate(profile.workflow_clarifications, start=1):
            lines.append(f"- **TW-{idx}:** {item}")
        lines.append("")
    return "\n".join(lines)
