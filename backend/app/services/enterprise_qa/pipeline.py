"""Run all enterprise modules; normalize inbound JSON and return a merged intelligence object."""

from __future__ import annotations

import copy
from typing import Any

from app.services.enterprise_qa.allure_analysis_service import AllureAnalysisService
from app.services.enterprise_qa.automation_coverage_engine import AutomationCoverageEngine
from app.services.enterprise_qa.behave_and_api import APIFlowReasoningEngine, BehaveScenarioGenerator
from app.services.enterprise_qa.customer_intelligence_engine import CustomerIntelligenceEngine
from app.services.enterprise_qa.failure_intelligence_engine import FailureIntelligenceEngine
from app.services.enterprise_qa.observability import EnterpriseQaTrace
from app.services.enterprise_qa.qa_learning_engine import recent_hints
from app.services.enterprise_qa.release_readiness_engine import ReleaseReadinessEngine
from app.services.enterprise_qa.response_builder import build_executive_summary
from app.services.enterprise_qa.test_impact_analysis_engine import TestImpactAnalysisEngine

_MAX_CTX_DEPTH = 12_000


def normalize_enterprise_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw or not isinstance(raw, dict):
        return {}
    data = copy.deepcopy(raw)
    for key in ("allure", "jenkins", "automation"):
        sub = data.get(key)
        if isinstance(sub, dict):
            for k, v in list(sub.items()):
                if isinstance(v, str) and len(v) > _MAX_CTX_DEPTH:
                    sub[k] = v[:_MAX_CTX_DEPTH] + "…"
    for k in ("ci_log_excerpt", "notes"):
        if isinstance(data.get(k), str) and len(data[k]) > _MAX_CTX_DEPTH:
            data[k] = data[k][: _MAX_CTX_DEPTH] + "…"
    rtk = data.get("release_ticket_keys")
    if isinstance(rtk, list):
        data["release_ticket_keys"] = [str(x).strip()[:32] for x in rtk[:50] if x]
    return data


async def run_enterprise_pipeline(
    *,
    trace: EnterpriseQaTrace,
    jira_blob: str,
    jira_key: str | None,
    customer: str | None,
    intent: str,
    enterprise_context: dict[str, Any],
    risk_out: dict[str, Any],
    strat_out: dict[str, Any],
    labels: list[str],
    components: list[str],
    reasoning_understanding: str,
    confidence: float,
    related_titles: list[str],
) -> dict[str, Any]:
    ctx = normalize_enterprise_context(enterprise_context)

    trace.step("enterprise_normalize_done")

    fail_eng = FailureIntelligenceEngine()
    failure_intel = fail_eng.analyze(jira_blob, ctx)
    trace.step("failure_intelligence")

    allure_svc = AllureAnalysisService()
    allure_out = allure_svc.analyze(ctx)
    trace.step("allure_analysis")

    impact = TestImpactAnalysisEngine().analyze(
        jira_blob=jira_blob,
        labels=labels,
        components=components,
        failure_intel=failure_intel,
        test_strategy=strat_out,
    )
    trace.step("test_impact")

    coverage = AutomationCoverageEngine().analyze(jira_blob, ctx)
    trace.step("automation_coverage")

    behave = BehaveScenarioGenerator()
    behave_text = await behave.generate(jira_blob=jira_blob, jira_key=jira_key, intent=intent)
    trace.step("behave_scenario")

    api_flow = APIFlowReasoningEngine().analyze(jira_blob)
    trace.step("api_flow")

    cust = CustomerIntelligenceEngine().analyze(
        customer=customer, jira_blob=jira_blob, related_titles=related_titles
    )
    trace.step("customer_intel")

    release = ReleaseReadinessEngine().analyze(
        release_ticket_keys=list(ctx.get("release_ticket_keys") or []),
        coverage=coverage,
        risk_level=str(risk_out.get("risk_level") or "medium"),
        failure_intel=failure_intel,
    )
    trace.step("release_readiness")

    learning_hints = recent_hints()
    trace.step("learning_hints")

    fc = int(allure_out.get("failure_summary", {}).get("failed_test_count") or 0)
    if isinstance(ctx.get("jenkins"), dict):
        fc += len(ctx["jenkins"].get("failed_tests") or [])

    exec_summary = build_executive_summary(
        jira_key=jira_key,
        intent=intent,
        risk_level=str(risk_out.get("risk_level") or "unknown"),
        confidence=confidence,
        reasoning_understanding=reasoning_understanding,
        failure_count=fc,
        coverage_score=int(coverage.get("coverage_score") or 0),
    )

    return {
        "executive_summary": exec_summary,
        "failure_intelligence": failure_intel,
        "allure": allure_out,
        "test_impact": impact,
        "automation_coverage": coverage,
        "behave_scenario_draft": behave_text,
        "api_flow": api_flow,
        "customer_intel": cust,
        "release_readiness": release,
        "learning_hints": learning_hints,
    }
