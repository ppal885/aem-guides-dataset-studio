"""Automation and UAC generation tools grounded in retrieved Jira evidence."""

from __future__ import annotations

from typing import Any

from app.models.jira_models import AutomationFit, AutomationScenario, CommonPattern, JiraIssueDetails, UacPoint
from app.services.jira_qa_automation_rubric import recommend_layer, score_automation_fit


def _scope_label(customer: str | None, feature: str | None) -> str:
    return " ".join(x for x in (customer, feature) if x).strip() or "requested QA scope"


def _safe_feature_name(customer: str | None, feature: str | None) -> str:
    return f"{_scope_label(customer, feature).title()} Regression Validation"


def _details_blob(details: list[JiraIssueDetails]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                d.issue_key,
                d.summary,
                d.description,
                d.comments_summary,
                d.qa_notes,
                d.automation_notes,
                " ".join(d.regression_patterns),
            ]
        )
        for d in details
    )


async def generate_automation_scenarios(
    issue_details: list[dict[str, Any]] | None = None,
    patterns: list[dict[str, Any]] | None = None,
    customer: str | None = None,
    feature: str | None = None,
) -> dict[str, Any]:
    details = [JiraIssueDetails.model_validate(item) for item in (issue_details or [])]
    parsed_patterns = [CommonPattern.model_validate(item) for item in (patterns or [])]
    if not details:
        return {
            "automation_scenarios": [],
            "automation_fit": AutomationFit(
                automation_recommended=False,
                priority="P3",
                dependencies=[],
                required_test_data=[],
                complexity="Unknown",
                score_0_10=0.0,
                rationale="No retrieved Jira evidence available for grounded automation generation.",
            ).model_dump(),
        }

    feature_name = _safe_feature_name(customer, feature)
    patterns_to_use = parsed_patterns or [
        CommonPattern(
            pattern=p,
            frequency=1,
            supporting_issues=[d.issue_key],
            probable_root_causes=[d.root_cause or "Not stated in retrieved evidence."],
        )
        for d in details
        for p in (d.regression_patterns or [])
    ]
    scenarios: list[AutomationScenario] = []
    scope_label = _scope_label(customer, feature)
    for idx, pattern in enumerate(patterns_to_use[:5], start=1):
        issue_refs = pattern.supporting_issues or [d.issue_key for d in details[:3]]
        tags = ["@jira-grounded", f"@{(feature or 'aem-guides').replace(' ', '-')}"]
        scenario_text = (
            f"Feature: {feature_name}\n\n"
            f"  Scenario: Validate {pattern.pattern} does not regress\n"
            f"    Given an AEM Guides QA fixture covers {scope_label} and the historical pattern {pattern.pattern}\n"
            f"    And historical Jira evidence exists for {', '.join(issue_refs)}\n"
            f"    When the QA automation opens the affected content in AEM Guides\n"
            f"    And performs the evidence-relevant authoring, review, or publishing workflow\n"
            f"    Then the workflow should complete without the historical failure pattern: {pattern.pattern}\n"
            f"    And the affected UI, API, preview, or generated output should match the expected evidence-backed result\n"
            f"    And no historical error signature from {', '.join(issue_refs)} should be reported\n"
        )
        scenarios.append(
            AutomationScenario(
                title=f"TC_{idx:02d} || {pattern.pattern} || QA Copilot",
                priority="P1" if pattern.regression_risk == "High" else "P2",
                feature_name=feature_name,
                scenario_text=scenario_text,
                assertions=[
                    "No historical error signature appears in UI/API/log validation.",
                    "Preview and published output match expected resolved DITA content.",
                    "Save, reopen, and publish validations preserve references and metadata.",
                ],
                test_data=[
                    "Minimal anonymized fixture reproducing the retrieved issue pattern.",
                    "Customer-specific fixture variant only when retrieved metadata requires it.",
                    "Expected baseline for each impacted UI, API, preview, or output surface.",
                ],
                tags=tags,
                negative=False,
                grounded_in=issue_refs,
            )
        )
        scenarios.append(
            AutomationScenario(
                title=f"TC_{idx:02d}N || negative guard for {pattern.pattern} || QA Copilot",
                priority="P2",
                feature_name=feature_name,
                scenario_text=(
                    f"Feature: {feature_name}\n\n"
                    f"  Scenario: Reject or flag invalid data for {pattern.pattern}\n"
                    f"    Given an AEM Guides fixture intentionally contains invalid or stale data related to {scope_label}\n"
                    f"    When the same evidence-relevant workflow is executed\n"
                    f"    Then AEM Guides should report an actionable validation warning\n"
                    f"    And the system should not silently produce incorrect UI state, API state, preview, or output\n"
                ),
                assertions=[
                    "Invalid fixture is detected with an actionable warning.",
                    "No silent incorrect publish output is produced.",
                ],
                test_data=["Negative fixture derived from retrieved historical pattern."],
                tags=tags + ["@negative"],
                negative=True,
                grounded_in=issue_refs,
            )
        )

    blob = _details_blob(details)
    rubric = score_automation_fit(blob)
    layer = recommend_layer(blob, rubric)
    automation_fit = AutomationFit(
        automation_recommended=rubric.fit_label in {"Yes", "Partial"},
        priority="P1" if any(p.regression_risk == "High" for p in parsed_patterns) else "P2",
        framework=f"Python Behave + {layer} automation + AEM Guides",
        dependencies=[
            "Indexed Jira QA chunks with evidence snippets",
            "AEM Guides test tenant with the impacted modules enabled",
            "Stable anonymized fixtures and expected baselines for impacted surfaces",
        ],
        required_test_data=[
            "Fixture set covering the requested QA scope",
            "Positive fixture and negative/error fixture derived from retrieved evidence",
            "Output preset and comparison baseline only when output validation is required",
        ],
        complexity="High" if rubric.score_0_10 < 4 else ("Medium" if rubric.score_0_10 < 7 else "Low"),
        score_0_10=rubric.score_0_10,
        rationale=f"Rubric fit {rubric.fit_label}; recommended layer {layer}; grounded issue count {len(details)}.",
    )
    return {
        "automation_scenarios": [scenario.model_dump() for scenario in scenarios],
        "automation_fit": automation_fit.model_dump(),
    }


async def generate_uac_points(
    issue_details: list[dict[str, Any]] | None = None,
    patterns: list[dict[str, Any]] | None = None,
    customer: str | None = None,
    feature: str | None = None,
) -> dict[str, Any]:
    details = [JiraIssueDetails.model_validate(item) for item in (issue_details or [])]
    parsed_patterns = [CommonPattern.model_validate(item) for item in (patterns or [])]
    if not details:
        return {"uac_points": []}
    keys = [d.issue_key for d in details if d.issue_key]
    pattern_names = ", ".join(p.pattern for p in parsed_patterns[:4]) or "retrieved issue symptoms"
    target = _scope_label(customer, feature)
    points = [
        UacPoint(
            category="Customer Impact",
            point=f"Confirm whether {target} failures match customer-visible workflows from retrieved Jira evidence: {pattern_names}.",
            risk_level="High" if any(p.regression_risk == "High" for p in parsed_patterns) else "Medium",
            grounded_in=keys,
        ),
        UacPoint(
            category="Backward Compatibility",
            point=f"Validate existing content for {target} continues to behave correctly across the lifecycle operations evidenced by retrieved Jira.",
            risk_level="Medium",
            grounded_in=keys,
        ),
        UacPoint(
            category="Publishing Impact",
            point=f"Agree which impacted surfaces for {target} are release-blocking: editor, API, preview, generated output, or logs.",
            risk_level="Medium",
            grounded_in=keys,
        ),
        UacPoint(
            category="Migration Risk",
            point=f"Clarify whether historical data for {target} needs migration, reindexing, metadata repair, or fixture anonymization before automation.",
            risk_level="Medium",
            grounded_in=keys,
        ),
        UacPoint(
            category="Cloud/On-Prem Differences",
            point=f"Confirm environment coverage for {target} when retrieved metadata does not state Cloud versus On-Prem behavior.",
            risk_level="Medium",
            grounded_in=keys,
        ),
        UacPoint(
            category="Baseline Impact",
            point=f"Check whether baselines, versions, conditions, or output presets change expected behavior for {target}.",
            risk_level="Medium",
            grounded_in=keys,
        ),
    ]
    return {"uac_points": [point.model_dump() for point in points]}
