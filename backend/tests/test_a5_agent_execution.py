"""A5: real agent execution bridge - offline contract tests.

These tests use fakes/mocks for the model substrate; they prove contracts,
routing, validation, and trace truthfulness.  They never claim real agent
execution - the opt-in smoke test is separate and reports honestly when no
model provider is configured.
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    ContractFact,
    ContractFactType,
    ContractMode,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationProfile,
    MissingQuestion,
    OpenQuestionClass,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    RuntimeEntryPoint,
    SourceVisibility,
)
from app.services.agent_execution_provider import (
    DeterministicResearchProvider,
    ModelAgentExecutionProvider,
    RoutedResearchProvider,
    agent_research_mode,
    load_role_contract,
)
from app.services.research_workers import (
    AttachmentResearchWorker,
    CodeResearchWorker,
    DocResearchWorker,
    ResearchOrchestrator,
)


def _record(reference: str, text: str, source_type: EvidenceSourceType):
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_reference=f"test:{reference}",
        tenant_id="tenant_a5",
        visibility=SourceVisibility(tenant_id="tenant_a5"),
        requirement_authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        content={"description": text},
    )


def _bundle(*records) -> CanonicalEvidenceBundle:
    return CanonicalEvidenceBundle(tenant_id="tenant_a5", records=list(records))


def _question(text: str) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _requirement(
    question: MissingQuestion,
    research_requirement: ResearchRequirement,
    source_types,
) -> ResearchRequirementRecord:
    return ResearchRequirementRecord(
        question_id=question.question_id,
        research_requirement=research_requirement,
        material=True,
        required_source_types=list(source_types),
        rationale="test requirement",
    )


class _FakeModelProvider(ModelAgentExecutionProvider):
    """Scripted model substrate: returns canned JSON through the real
    validation path (no network).  model_execution stays True only because
    the scripted call stands in for an actual model invocation in these
    contract tests."""

    def __init__(self, payload: dict | Exception):
        self._payload = payload
        # Scripted stand-in for an actual model invocation in contract tests.
        self.last_model_execution = True

    def execute(self, request, *, bundle, question, requirement, **kwargs):
        if isinstance(self._payload, Exception):
            return self._terminal(
                request, ResearchWorkerStatus.FAILED, ["scripted failure"]
            )
        return self._validate_and_build(
            request, self._payload, bundle, role_contract="test@contract"
        )


def _orchestrator_with(provider) -> ResearchOrchestrator:
    workers = [DocResearchWorker(), CodeResearchWorker(), AttachmentResearchWorker()]
    return ResearchOrchestrator(workers=workers, provider=provider)


# ---------------------------------------------------------------------------
# Role contracts and registration parity (spec sections 1, 5-7, 24)
# ---------------------------------------------------------------------------


def test_role_contracts_load_for_all_three_roles() -> None:
    for role in ResearchWorkerRole:
        name, version, text = load_role_contract(role)
        assert name and version and "must NOT" in text


def test_copilot_registration_parity() -> None:
    import subprocess
    import sys
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "test-plan-generation"
        / "scripts"
        / "sync_agent_registrations.py"
    )
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Provider modes (spec sections 10-12)
# ---------------------------------------------------------------------------


def test_default_mode_is_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_RESEARCH_MODE", raising=False)
    assert agent_research_mode() == "deterministic"


def test_deterministic_mode_never_claims_model_execution() -> None:
    doc = _record(
        "doc1",
        "The retention window is controlled by the configured period.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider(
                {role: worker for role, worker in [
                    (ResearchWorkerRole.DOC_RESEARCHER, DocResearchWorker()),
                    (ResearchWorkerRole.CODE_RESEARCHER, CodeResearchWorker()),
                    (ResearchWorkerRole.ATTACHMENT_RESEARCHER, AttachmentResearchWorker()),
                ]}
            ),
            mode="deterministic",
        )
    )
    results, executions = orchestrator.execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    assert results and results[0].status == ResearchWorkerStatus.ANSWER_FOUND
    assert all(
        execution.provider == "DETERMINISTIC" for execution in executions
    )
    assert all(not execution.model_execution for execution in executions)


def test_agent_mode_unavailable_model_is_honest_worker_unavailable() -> None:
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    # Real ModelAgentExecutionProvider, no LLM configured in this env.
    provider = RoutedResearchProvider(
        DeterministicResearchProvider({}),
        ModelAgentExecutionProvider(),
        mode="agent",
    )
    orchestrator = _orchestrator_with(provider)
    results, executions = orchestrator.execute(
        [question], [requirement], _bundle(), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.WORKER_UNAVAILABLE
    assert executions[0].provider == "MODEL_AGENT"
    # No model actually executed - the receipt never claims one did.
    assert executions[0].model_execution is False


def test_agent_mode_valid_result_is_admitted_and_traced() -> None:
    doc = _record(
        "doc2",
        "The configured period governs the retention of entries.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    bundle = _bundle(doc)
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    payload = {
        "status": "ANSWER_FOUND",
        "applicability": "current",
        "currentness": "current",
        "limitations": [],
        "conflicts": [],
        "findings": [
            {
                "claim": "The configured period governs entry retention.",
                "source_refs": [doc.evidence_id],
                "evidence_role": "EXISTING_BEHAVIOR",
            }
        ],
    }
    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider({}),
            _FakeModelProvider(payload),
            mode="agent",
        )
    )
    results, executions = orchestrator.execute(
        [question], [requirement], bundle, repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.ANSWER_FOUND
    assert results[0].findings[0].source_refs == [doc.evidence_id]
    assert executions[0].provider == "MODEL_AGENT"
    assert executions[0].model_execution is True
    assert executions[0].role_contract == "uac-doc-researcher@" + executions[
        0
    ].role_contract.split("@")[1]


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "ANSWERED_KIND_OF"},  # outside the R2 vocabulary
        {"status": "ANSWER_FOUND", "findings": []},  # answer without findings
        {
            "status": "ANSWER_FOUND",
            "findings": [
                {"claim": "x", "source_refs": ["ev:fabricated"], "evidence_role": "EXISTING_BEHAVIOR"}
            ],
        },  # fabricated source reference
        {
            "status": "SOURCE_UNAVAILABLE",
            "findings": [
                {"claim": "x", "source_refs": [], "evidence_role": "SUPPORTING_CONTEXT"}
            ],
        },  # unavailable cannot carry findings
        "not-a-dict",  # not a JSON object
    ],
)
def test_agent_result_validation_fails_closed(payload) -> None:
    doc = _record(
        "doc3",
        "The configured period governs the retention of entries.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider({}),
            _FakeModelProvider(payload),
            mode="agent",
        )
    )
    results, _executions = orchestrator.execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    # Never a clean answer from a bad result; fail closed.
    assert results[0].status == ResearchWorkerStatus.FAILED
    assert not results[0].findings


def test_shadow_mode_keeps_deterministic_authoritative() -> None:
    doc = _record(
        "doc4",
        "The configured period governs the retention of entries.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    bundle = _bundle(doc)
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    model_payload = {
        "status": "NOT_FOUND",
        "applicability": "",
        "currentness": "",
        "limitations": ["model found nothing"],
        "conflicts": [],
        "findings": [],
    }
    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider(
                {ResearchWorkerRole.DOC_RESEARCHER: DocResearchWorker()}
            ),
            _FakeModelProvider(model_payload),
            mode="shadow",
        )
    )
    results, executions = orchestrator.execute(
        [question], [requirement], bundle, repository_roots=[]
    )
    # Deterministic answer remains the authoritative result consumed by the
    # runtime even though the shadow model disagreed (NOT_FOUND).
    assert results[0].status == ResearchWorkerStatus.ANSWER_FOUND
    providers = {(execution.provider, execution.model_execution) for execution in executions}
    assert ("DETERMINISTIC", False) in providers
    assert ("MODEL_AGENT", True) in providers
    by_provider = {e.provider: e.status for e in executions}
    assert by_provider["DETERMINISTIC"] != by_provider["MODEL_AGENT"]


# ---------------------------------------------------------------------------
# Production entry point: mode + truthful receipts (spec sections 17, 27)
# ---------------------------------------------------------------------------


def test_production_run_records_provider_truth() -> None:
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99321",
        tenant_id="tenant_a5",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99321",
        "issue": {
            "issue_key": "GUIDES-99321",
            "summary": "Archive retention needs a bounded option.",
            "description": (
                "There is no easy way to bound retained archives; the "
                "listing grows without limit."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )
    executions = result.output_payload["research_worker_executions"]
    assert executions
    for execution in executions:
        # Truthful receipts: provider + model_execution are always present.
        assert execution["provider"] in {"DETERMINISTIC", "MODEL_AGENT"}
        assert execution["model_execution"] is False
        assert execution["result_ref"]


# ---------------------------------------------------------------------------
# Opt-in REAL agent smoke (spec section 28): never claims execution from a
# mock - it skips with an explicit reason when no model provider exists.
# ---------------------------------------------------------------------------


def test_real_agent_smoke_opt_in() -> None:
    import os

    if os.environ.get("A5_REAL_AGENT_SMOKE") != "1":
        pytest.skip("opt-in: set A5_REAL_AGENT_SMOKE=1 with LLM credentials")
        return
    from app.services import llm_service

    if not llm_service.is_llm_available():
        pytest.skip("no model provider configured (LLM credentials absent)")
        return
    doc = _record(
        "smoke-doc",
        "The configured retention period governs how long entries remain.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    bundle = _bundle(doc)
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    provider = ModelAgentExecutionProvider()
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    agent_request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision=question.question_revision,
        requested_claim=question.question,
        research_requirement=requirement.research_requirement,
        authorized_source_refs=[doc.evidence_id],
    )
    result = provider.execute(
        agent_request, bundle=bundle, question=question, requirement=requirement
    )
    # Real model execution occurred and the runtime validated the result.
    assert provider.last_model_execution is True
    assert result.status in {
        ResearchWorkerStatus.ANSWER_FOUND,
        ResearchWorkerStatus.PARTIAL,
        ResearchWorkerStatus.NOT_FOUND,
    }
    for finding in result.findings:
        assert set(finding.source_refs) <= {doc.evidence_id}
