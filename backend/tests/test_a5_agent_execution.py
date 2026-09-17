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
        # Load the real canonical role contract so the trace receipt is the
        # same shape as production.
        name, version, _text = load_role_contract(request.worker_role)
        self.last_role_contract = f"{name}@{version}"
        if isinstance(self._payload, Exception):
            return self._terminal(
                request, ResearchWorkerStatus.FAILED, ["scripted failure"]
            )
        return self._validate_and_build(
            request, self._payload, bundle, role_contract=self.last_role_contract
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
        mode="backend_model",
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
            mode="backend_model",
        )
    )
    results, executions = orchestrator.execute(
        [question], [requirement], bundle, repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.ANSWER_FOUND
    assert results[0].findings[0].source_refs == [doc.evidence_id]
    assert executions[0].provider == "MODEL_AGENT"
    assert executions[0].model_execution is True
    assert executions[0].role_contract.startswith("uac-doc-researcher@")


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "ANSWERED_KIND_OF"},  # outside the R2 vocabulary
        {
            "status": "DOC_RESEARCH_COMPLETED",
            "findings": [
                {"claim": "x", "source_refs": [], "evidence_role": "EXISTING_BEHAVIOR"}
            ],
        },  # R1 manifest vocabulary is not the worker handoff vocabulary
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
            mode="backend_model",
        )
    )
    results, _executions = orchestrator.execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    # Never a clean answer from a bad result; fail closed.
    assert results[0].status == ResearchWorkerStatus.FAILED
    assert not results[0].findings


@pytest.mark.parametrize(
    "finding",
    [
        {  # path carries a line-range suffix
            "claim": "x",
            "source_refs": [],
            "repository": "repo",
            "revision": "f" * 40,
            "path": "src/app.java:16-29",
        },
        {  # multiple paths packed into one field
            "claim": "x",
            "source_refs": [],
            "repository": "repo",
            "revision": "f" * 40,
            "path": "src/a.java; src/b.java",
        },
        {  # missing revision
            "claim": "x",
            "source_refs": [],
            "repository": "repo",
            "path": "src/app.java",
        },
        {  # missing repository root
            "claim": "x",
            "source_refs": [],
            "revision": "f" * 40,
            "path": "src/app.java",
        },
    ],
)
def test_code_result_path_grammar_fails_closed(finding) -> None:
    from app.services.agent_execution_provider import validate_agent_result_shape

    payload = {"status": "ANSWER_FOUND", "findings": [finding]}
    rejection = validate_agent_result_shape(payload, ResearchWorkerRole.CODE_RESEARCHER)
    assert rejection is not None


# ---------------------------------------------------------------------------
# Researcher capability: discovered documentation provenance + attachment
# content materialization + NO_RELEVANT_EVIDENCE semantics.
# ---------------------------------------------------------------------------


def _doc_orchestrator(payload):
    return _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider({}),
            _FakeModelProvider(payload),
            mode="backend_model",
        )
    )


def _doc_question_setup():
    doc = _record(
        "doc-scope",
        "The configured period governs the retention of entries.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    return doc, question, requirement


def test_doc_discovered_source_with_provenance_is_admitted() -> None:
    doc, question, requirement = _doc_question_setup()
    payload = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": "Experience League documents the retention behavior.",
                "source_refs": ["doc:1a2b3c4d5e6f"],
                "evidence_role": "EXISTING_BEHAVIOR",
                "provenance": {
                    "locator": "https://experienceleague.adobe.com/some/page",
                    "title": "Some page",
                    "query": "output history retention",
                    "accessed_at": "2026-09-17",
                },
            }
        ],
    }
    results, _ = _doc_orchestrator(payload).execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.ANSWER_FOUND
    assert results[0].findings[0].provenance["locator"].startswith("https://")


def test_doc_discovered_source_without_provenance_fails_closed() -> None:
    doc, question, requirement = _doc_question_setup()
    payload = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": "x",
                "source_refs": ["doc:1a2b3c4d5e6f"],
                "evidence_role": "EXISTING_BEHAVIOR",
            }
        ],
    }
    results, _ = _doc_orchestrator(payload).execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.FAILED


def test_doc_discovered_source_slug_ref_and_pairing_rule() -> None:
    doc, question, requirement = _doc_question_setup()

    def run(finding):
        results, _ = (
            _doc_orchestrator({"status": "ANSWER_FOUND", "findings": [finding]})
            .execute([question], [requirement], _bundle(doc), repository_roots=[])
        )
        return results[0]

    prov = {
        "locator": "https://experienceleague.adobe.com/en/docs/x",
        "title": "X",
        "query": "q",
    }
    # Slug-style ref (no hash capability needed) with provenance: admitted.
    ok = run(
        {
            "claim": "Documented behavior.",
            "source_refs": ["doc:manage-digital-assets"],
            "evidence_role": "EXISTING_BEHAVIOR",
            "provenance": prov,
        }
    )
    assert ok.status == ResearchWorkerStatus.ANSWER_FOUND
    # Provenance block without the doc: ref is malformed.
    bad = run(
        {
            "claim": "Documented behavior.",
            "source_refs": [],
            "evidence_role": "SUPPORTING_CONTEXT",
            "provenance": prov,
        }
    )
    assert bad.status == ResearchWorkerStatus.FAILED
    assert "together" in bad.limitations[0]


def test_doc_refs_are_not_valid_for_attachment_research() -> None:
    attachment = _record(
        "att1", "metadata only", EvidenceSourceType.JIRA_ATTACHMENT
    )
    question = _question("What does the screenshot show?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.JIRA_ATTACHMENT]
    )
    payload = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": "x",
                "source_refs": ["doc:1a2b3c4d5e6f"],
                "evidence_role": "OBSERVED_BEHAVIOR",
                "provenance": {"locator": "p", "title": "t", "query": "q"},
            }
        ],
    }
    results, _ = _doc_orchestrator(payload).execute(
        [question], [requirement], _bundle(attachment), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.FAILED


def test_no_relevant_evidence_requires_searched_scopes() -> None:
    doc, question, requirement = _doc_question_setup()
    payload = {"status": "NO_RELEVANT_EVIDENCE", "findings": [], "limitations": []}
    results, _ = _doc_orchestrator(payload).execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    # Schema rule: NO_RELEVANT_EVIDENCE must name what was actually searched.
    assert results[0].status == ResearchWorkerStatus.FAILED
    payload["limitations"] = ["searched references pack and Experience League: nothing relevant"]
    results, _ = _doc_orchestrator(payload).execute(
        [question], [requirement], _bundle(doc), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.NO_RELEVANT_EVIDENCE


def test_attachment_files_materialize_content_or_exact_error(tmp_path) -> None:
    import json

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    attachment = EvidenceRecord(
        source_type=EvidenceSourceType.JIRA_ATTACHMENT,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_reference="test:att-content",
        tenant_id="tenant_a5",
        visibility=SourceVisibility(tenant_id="tenant_a5"),
        requirement_authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        # Attachment metadata WITHOUT a content URL: the exact reason must be
        # recorded, never a fabricated path.
        content={"id": "1", "filename": "shot.png", "mime_type": "image/png"},
    )
    bundle = _bundle(attachment)
    question = _question("What does the screenshot show?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.JIRA_ATTACHMENT]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.ATTACHMENT_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the screenshot show?",
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[attachment.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(request, bundle=bundle, question=question, requirement=requirement)
    pending = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    payload = json.loads(pending.read_text(encoding="utf-8"))
    files = payload["attachment_files"]
    assert len(files) == 1
    assert files[0]["source_ref"] == attachment.evidence_id
    # No content URL -> exact reason recorded, no fabricated path.
    assert files[0]["path"] == ""
    assert "no content URL" in files[0]["error"]


def _fake_retrieve_factory(monkeypatch, rows_by_substring):
    """A plan-aware fake of the pipeline doc retriever: returns the mapped
    rows only when the query contains the mapped substring."""

    import app.services.doc_retriever_service as docs_mod

    def fake(query, k=5, max_snippet_chars=400, allowed_host_suffixes=None):
        for substring, rows in rows_by_substring.items():
            if substring in query.lower():
                return {"query": query, "retrieval_mode": "semantic", "results": rows}
        return {"query": query, "retrieval_mode": "semantic", "results": []}

    monkeypatch.setattr(
        docs_mod, "retrieve_relevant_docs_with_diagnostics", fake
    )
    return docs_mod


def _doc_pending_payload(tmp_path, monkeypatch, claim, rows_by_substring):
    import json

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    _fake_retrieve_factory(monkeypatch, rows_by_substring)
    record = _record("doc-rag", "baseline", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION)
    question = _question(claim)
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim=claim,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[record.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(request, bundle=_bundle(record), question=question, requirement=requirement)
    pending = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    return json.loads(pending.read_text(encoding="utf-8"))


# The regression fixture family: an output-history / publishing-warning
# question whose indexed documentation uses output-generation / map
# dashboard terminology.  Production logic stays ticket-agnostic; only this
# fixture uses these terms.
_OUTPUT_CLAIM = (
    "Does the Output History on the outputs panel show publishing "
    "warnings from the publish log?"
)
_OUTPUT_DOC_ROW = {
    "url": "https://docs.example.test/output-generation",
    "title": "Output generation troubleshooting",
    "snippet": "The Map dashboard Generated Outputs list shows each run's status and its log.",
    "corpus": "aem_guides",
    "chunk_id": "chunk-out-1",
}


def test_query_plan_always_retains_the_original_query_first(tmp_path, monkeypatch) -> None:
    payload = _doc_pending_payload(tmp_path, monkeypatch, _OUTPUT_CLAIM, {})
    assert payload["documentation_queries"][0] == _OUTPUT_CLAIM
    assert len(payload["documentation_queries"]) <= 4


def test_vocabulary_expansion_improves_recall_across_terminology(tmp_path, monkeypatch) -> None:
    # The doc only surfaces when the query carries documentation-side
    # terminology ("generated outputs" / "map dashboard"), which the claim's
    # own words ("output history") never contain.
    payload = _doc_pending_payload(
        tmp_path, monkeypatch, _OUTPUT_CLAIM, {"generated outputs": [_OUTPUT_DOC_ROW]}
    )
    candidates = payload["rag_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["url"] == _OUTPUT_DOC_ROW["url"]
    assert any(
        "generated outputs" in query.lower()
        for query in candidates[0]["matched_queries"]
    )
    assert "generated outputs" in payload["rag_expansion_terms"]


def test_duplicate_candidates_across_expansions_collapse(tmp_path, monkeypatch) -> None:
    # Same URL surfaced by both the original claim and the expansion: one
    # candidate, both queries recorded as provenance.
    payload = _doc_pending_payload(
        tmp_path,
        monkeypatch,
        _OUTPUT_CLAIM,
        {"output history": [_OUTPUT_DOC_ROW], "generated outputs": [_OUTPUT_DOC_ROW]},
    )
    candidates = payload["rag_candidates"]
    assert len(candidates) == 1
    assert set(candidates[0]["matched_queries"]) == set(
        payload["documentation_queries"]
    )
    assert len(candidates[0]["matched_queries"]) >= 2


def test_expansion_terms_never_become_evidence(tmp_path, monkeypatch) -> None:
    payload = _doc_pending_payload(
        tmp_path, monkeypatch, _OUTPUT_CLAIM, {"generated outputs": [_OUTPUT_DOC_ROW]}
    )
    assert payload["rag_expansion_terms"]
    # Expansion terms are retrieval hints: candidates are marked as discovery
    # leads and carry no evidence authority of their own.
    assert all(
        candidate.get("discovery_lead") is True
        for candidate in payload["rag_candidates"]
    )


def test_irrelevant_expansion_cannot_override_original_query(tmp_path, monkeypatch) -> None:
    strong_original = {
        "url": "https://docs.example.test/original-strong",
        "title": "Output History warnings",
        "snippet": "Output History shows publishing warnings from the publish log.",
        "corpus": "aem_guides",
        "chunk_id": "chunk-orig",
    }
    weak_expansion = {
        "url": "https://docs.example.test/expansion-weak",
        "title": "Unrelated page",
        "snippet": "Completely unrelated content.",
        "corpus": "aem_guides",
        "chunk_id": "chunk-weak",
    }
    payload = _doc_pending_payload(
        tmp_path,
        monkeypatch,
        _OUTPUT_CLAIM,
        {
            "output history": [strong_original],
            "generated outputs": [weak_expansion],
        },
    )
    candidates = payload["rag_candidates"]
    assert candidates[0]["url"] == strong_original["url"]
    assert candidates[0]["score"] > candidates[1]["score"]


def test_doc_request_receives_rag_candidates_before_live_verification(
    tmp_path, monkeypatch
) -> None:
    """An output-history / publishing-warning claim reaches the DOC
    researcher WITH merged, provenance-carrying retrieval candidates -
    before any live document verification the leaf performs."""

    payload = _doc_pending_payload(
        tmp_path, monkeypatch, _OUTPUT_CLAIM, {"output history": [_OUTPUT_DOC_ROW]}
    )
    assert payload["rag_status"].startswith("ok:")
    candidates = payload["rag_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["title"] == _OUTPUT_DOC_ROW["title"]
    assert _OUTPUT_CLAIM in candidates[0]["matched_queries"]
    assert "semantic" in candidates[0]["retrieval_modes"]
    assert candidates[0]["score"] is not None
    assert "generated outputs" in candidates[0]["snippet"].lower()
    # Vocabulary routing stays away from generic overview queries.
    queries = [q.lower() for q in payload["documentation_queries"]]
    assert queries[0] == _OUTPUT_CLAIM.lower()
    assert all("overview" not in q for q in queries)


def test_lifecycle_language_requires_documented_existing_behavior() -> None:
    """A fix comment / code finding must never be labeled delivered/shipped/
    current product behavior unless documentation establishes that state."""

    from app.services.agent_execution_provider import validate_agent_result_shape

    impl_claim = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": "The fix was delivered and adds the indicator.",
                "source_refs": [],
                "repository": "repo",
                "revision": "f" * 40,
                "path": "src/app.java",
                "evidence_role": "IMPLEMENTATION_EVIDENCE",
            }
        ],
    }
    rejection = validate_agent_result_shape(
        impl_claim, ResearchWorkerRole.CODE_RESEARCHER
    )
    assert rejection is not None and "release/current-behavior" in rejection

    # A negated, disciplined use of the phrase is not a lifecycle claim.
    negated = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": "The linked fix is In Progress; this is not established as current product behavior.",
                "source_refs": [],
                "evidence_role": "REQUIREMENT_CLARIFICATION",
            }
        ],
    }
    assert (
        validate_agent_result_shape(negated, ResearchWorkerRole.DOC_RESEARCHER)
        is None
    )
    # Sentence-scoped: the negation may sit far before the phrase.
    negated_long = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": (
                    "No consulted product documentation establishes this as "
                    "delivered or current product behavior."
                ),
                "source_refs": [],
                "evidence_role": "REQUIREMENT_CLARIFICATION",
            }
        ],
    }
    assert (
        validate_agent_result_shape(
            negated_long, ResearchWorkerRole.DOC_RESEARCHER
        )
        is None
    )
    # A later affirmative sentence still trips even after a negated one.
    mixed = {
        "status": "ANSWER_FOUND",
        "findings": [
            {
                "claim": (
                    "No comment establishes release state. The indicator is "
                    "delivered in the current build."
                ),
                "source_refs": [],
                "evidence_role": "REQUIREMENT_CLARIFICATION",
            }
        ],
    }
    assert (
        validate_agent_result_shape(mixed, ResearchWorkerRole.DOC_RESEARCHER)
        is not None
    )

    # EXISTING_BEHAVIOR role but only a Jira comment behind it: provider
    # rejects (no documentation basis for current-behavior language).
    comment = _record(
        "fix-comment", "Fixed by: added the indicator.", EvidenceSourceType.JIRA_COMMENT
    )
    doc = _record(
        "doc-lc",
        "The documented behavior today.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    question = _question("What is the current documented behavior?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )

    def payload_with(ref_id):
        return {
            "status": "ANSWER_FOUND",
            "findings": [
                {
                    "claim": "This is the current product behavior.",
                    "source_refs": [ref_id],
                    "evidence_role": "EXISTING_BEHAVIOR",
                }
            ],
        }

    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider({}),
            _FakeModelProvider(payload_with(comment.evidence_id)),
            mode="backend_model",
        )
    )
    results, _ = orchestrator.execute(
        [question], [requirement], _bundle(doc, comment), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.FAILED
    assert "documentation source" in results[0].limitations[0]

    orchestrator = _orchestrator_with(
        RoutedResearchProvider(
            DeterministicResearchProvider({}),
            _FakeModelProvider(payload_with(doc.evidence_id)),
            mode="backend_model",
        )
    )
    results, _ = orchestrator.execute(
        [question], [requirement], _bundle(doc, comment), repository_roots=[]
    )
    assert results[0].status == ResearchWorkerStatus.ANSWER_FOUND


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
# COPILOT_HOST pending payload: the delegated leaf has a bounded read-only
# toolset and cannot resolve evidence IDs, so the pending request must carry
# the authorized CONTENT (bounded excerpts) plus authorized repository roots.
# ---------------------------------------------------------------------------


def test_copilot_host_pending_carries_bounded_evidence(tmp_path) -> None:
    import json
    import os

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    authorized = _record(
        "authorized", "documented behavior excerpt", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
    )
    intruder = _record(
        "intruder", "unrelated record", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION
    )
    bundle = _bundle(authorized, intruder)
    question = _question("What does the documentation establish?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the documentation establish?",
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[authorized.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    root = str(tmp_path / "repo")
    result = provider.execute(
        request,
        bundle=bundle,
        question=question,
        requirement=requirement,
        repository_roots=[root],
    )
    assert result.status == ResearchWorkerStatus.AWAITING_HOST

    pending = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    payload = json.loads(pending.read_text(encoding="utf-8"))
    rows = payload["authorized_evidence"]
    # Only the authorized record, with its actual content excerpted.
    assert [row["source_ref"] for row in rows] == [authorized.evidence_id]
    assert rows[0]["source_type"] == EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION.value
    assert "documented behavior excerpt" in rows[0]["excerpt"]
    assert all(len(row["excerpt"]) <= 400 for row in rows)
    assert payload["authorized_repository_roots"] == [os.path.abspath(root)]
    # Identity fields stay exactly as emitted.
    assert payload["execution_id"] == request.execution_id
    assert payload["question_revision"] == "rev-test"
    # The role-contract version is bound at emission.
    from app.services.agent_execution_provider import load_role_contract

    name, version, _text = load_role_contract(ResearchWorkerRole.DOC_RESEARCHER)
    assert payload["role_contract_version"] == f"{name}@{version}"


def test_copilot_host_resume_binds_envelope_to_emitted_contract(tmp_path) -> None:
    """fulfill accepted -> provider accepted -> consumed exactly once, with
    the contract version bound to the emitted request (not wall-clock
    contract state), and a wrong version rejected."""

    import json

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    record = _record("authorized", "excerpt", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION)
    bundle = _bundle(record)
    question = _question("What does the documentation establish?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the documentation establish?",
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[record.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(request, bundle=bundle, question=question, requirement=requirement)
    pending_file = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    bound_version = json.loads(pending_file.read_text(encoding="utf-8"))[
        "role_contract_version"
    ]

    def _envelope(version: str) -> dict:
        return {
            "execution_id": request.execution_id,
            "question_id": request.question_id,
            "question_revision": "rev-test",
            "worker_role": "DOC_RESEARCHER",
            "provider": "COPILOT_HOST",
            "model": "test-model",
            "role_contract_version": version,
            "result": {
                "status": "NOT_FOUND",
                "findings": [],
                "source_refs": [],
                "applicability": "",
                "limitations": ["authorized evidence has no answer"],
                "conflicts": [],
            },
        }

    # Wrong contract version (schema-valid shape, not the bound version):
    # rejected, not consumed.
    fulfilled = tmp_path / "fulfilled" / pending_file.name
    fulfilled.parent.mkdir(parents=True, exist_ok=True)
    fulfilled.write_text(
        json.dumps(_envelope("uac-doc-researcher@" + "0" * 12)), encoding="utf-8"
    )
    rejected = provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    assert rejected.status == ResearchWorkerStatus.FAILED
    assert "drifted" in rejected.limitations[0]
    assert not fulfilled.with_suffix(".consumed").exists()

    # The version bound into the emitted request: accepted and consumed once.
    fulfilled.write_text(
        json.dumps(_envelope(bound_version)), encoding="utf-8"
    )
    accepted = provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    assert accepted.status == ResearchWorkerStatus.NOT_FOUND
    assert provider.last_model_execution is True
    assert provider.last_model == "test-model"
    assert provider.last_role_contract == bound_version
    assert fulfilled.with_suffix(".consumed").exists()

    # Third pass: duplicate consumption is rejected.
    duplicate = provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    assert duplicate.status == ResearchWorkerStatus.FAILED
    assert "already consumed" in duplicate.limitations[0]


def test_copilot_host_envelope_rejects_smuggled_fields(tmp_path) -> None:
    """The envelope boundary: a leaf cannot smuggle receipt claims (extra
    top-level fields) past the canonical schema."""

    import json

    from app.services.agent_execution_provider import (
        HostMediatedResearchProvider,
        load_role_contract,
    )

    record = _record("authorized", "excerpt", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION)
    bundle = _bundle(record)
    question = _question("What does the documentation establish?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the documentation establish?",
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[record.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(request, bundle=bundle, question=question, requirement=requirement)
    pending_file = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    bound_version = json.loads(pending_file.read_text(encoding="utf-8"))[
        "role_contract_version"
    ]
    name, _v, _t = load_role_contract(ResearchWorkerRole.DOC_RESEARCHER)
    assert bound_version.startswith(f"{name}@")

    smuggled = {
        "execution_id": request.execution_id,
        "question_id": request.question_id,
        "question_revision": "rev-test",
        "worker_role": "DOC_RESEARCHER",
        "provider": "COPILOT_HOST",
        "model": "test-model",
        "role_contract_version": bound_version,
        # Smuggled receipt claim: only the host may assert model execution.
        "model_execution": True,
        "result": {
            "status": "NOT_FOUND",
            "findings": [],
            "source_refs": [],
            "applicability": "",
            "limitations": ["none"],
            "conflicts": [],
        },
    }
    fulfilled = tmp_path / "fulfilled" / pending_file.name
    fulfilled.parent.mkdir(parents=True, exist_ok=True)
    fulfilled.write_text(json.dumps(smuggled), encoding="utf-8")
    rejected = provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    assert rejected.status == ResearchWorkerStatus.FAILED
    assert "canonical schema" in rejected.limitations[0]
    assert provider.last_model_execution is False
    assert not fulfilled.with_suffix(".consumed").exists()


def test_copilot_host_pending_falls_back_to_env_repository_roots(
    tmp_path, monkeypatch
) -> None:
    """When the caller passes no roots, the pending payload resolves the same
    configured env vars the deterministic code worker uses."""

    import json
    import os

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    monkeypatch.setenv("STARLING_REPO_PATH", str(tmp_path / "starling"))
    monkeypatch.delenv("XML_EDITOR_REPO_PATH", raising=False)
    monkeypatch.delenv("GUIDES_UI_TESTS_REPO_PATH", raising=False)
    monkeypatch.delenv("AEM_STUDIO_REPO", raising=False)

    record = _record("authorized", "excerpt", EvidenceSourceType.CURRENT_CODE)
    bundle = _bundle(record)
    question = _question("What does the implementation do today?")
    requirement = _requirement(
        question, ResearchRequirement.IMPLEMENTATION, [EvidenceSourceType.CURRENT_CODE]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.CODE_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the implementation do today?",
        research_requirement=ResearchRequirement.IMPLEMENTATION,
        authorized_source_refs=[record.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    pending = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    payload = json.loads(pending.read_text(encoding="utf-8"))
    assert payload["authorized_repository_roots"] == [
        os.path.abspath(str(tmp_path / "starling"))
    ]


def test_copilot_host_pending_is_not_rewritten_on_repeat(tmp_path) -> None:
    import json

    from app.services.agent_execution_provider import HostMediatedResearchProvider

    record = _record("authorized", "excerpt", EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION)
    bundle = _bundle(record)
    question = _question("What does the documentation establish?")
    requirement = _requirement(
        question, ResearchRequirement.DOCUMENTATION, [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION]
    )
    from app.core.schemas_canonical_test_plan_runtime import AgentResearchRequest

    request = AgentResearchRequest(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim="What does the documentation establish?",
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[record.evidence_id],
    )
    provider = HostMediatedResearchProvider(store=tmp_path)
    provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    pending = tmp_path / "pending" / f"{request.execution_id.replace(':', '_')}.json"
    first = pending.read_text(encoding="utf-8")
    # A second pass (e.g. resume poll) must not mutate the emitted request.
    provider.execute(
        request, bundle=bundle, question=question, requirement=requirement
    )
    assert pending.read_text(encoding="utf-8") == first
    assert json.loads(first)["authorized_evidence"]


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
