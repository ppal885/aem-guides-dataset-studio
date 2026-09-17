"""G1: run-scoped execution identity for host-mediated research.

A logical research question stays identity-stable across repeated UAC runs
(``question_id`` / revision / claim fingerprint), but every top-level
Generate-UAC invocation carries a distinct canonical run id and the host
research ``execution_id`` / pending / fulfilled / consumed state is scoped
to the research episode's run.  A second run of the same Jira creates fresh
executions and delegates fresh research; a duplicate result for an
already-consumed execution within one run still fails closed; one run never
consumes or mutates another run's state; no timestamp-based cleanup exists.
"""

from __future__ import annotations

import json

from app.core.schemas_canonical_test_plan_runtime import (
    AgentResearchRequest,
    AuthorityClass,
    AuthoritySubject,
    EvidenceRecord,
    EvidenceSourceType,
    CanonicalEvidenceBundle,
    MissingQuestion,
    OpenQuestionClass,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    SourceVisibility,
)
from app.services.agent_execution_provider import (
    HostMediatedResearchProvider,
    load_role_contract,
)


def _record() -> EvidenceRecord:
    return EvidenceRecord(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_reference="test:doc",
        tenant_id="tenant_g1",
        visibility=SourceVisibility(tenant_id="tenant_g1"),
        requirement_authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        content={"snippet": "documented baseline behavior"},
    )


def _question() -> MissingQuestion:
    return MissingQuestion(
        question="What does the documentation establish?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _requirement(question: MissingQuestion) -> ResearchRequirementRecord:
    return ResearchRequirementRecord(
        question_id=question.question_id,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        material=True,
        rationale="test",
        required_source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )


def _bundle(record: EvidenceRecord) -> CanonicalEvidenceBundle:
    return CanonicalEvidenceBundle(
        tenant_id="tenant_g1",
        records=[record],
    )


def _request(question, record, run_scope: str) -> AgentResearchRequest:
    return AgentResearchRequest(
        run_scope=run_scope,
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        question_revision="rev-test",
        requested_claim=question.question,
        research_requirement=ResearchRequirement.DOCUMENTATION,
        authorized_source_refs=[record.evidence_id],
    )


def _fulfill(store, execution_id: str, question, marker: str) -> None:
    """Write a host result envelope the way the bridge does (identity taken
    from the pending request, contract version bound at emission)."""

    name, version, _text = load_role_contract(ResearchWorkerRole.DOC_RESEARCHER)
    fulfilled = store / "fulfilled" / f"{execution_id.replace(':', '_')}.json"
    fulfilled.parent.mkdir(parents=True, exist_ok=True)
    fulfilled.write_text(
        json.dumps(
            {
                "execution_id": execution_id,
                "question_id": question.question_id,
                "question_revision": "rev-test",
                "worker_role": "DOC_RESEARCHER",
                "provider": "COPILOT_HOST",
                "model": "test-model",
                "role_contract_version": f"{name}@{version}",
                "result": {
                    "status": "NOT_FOUND",
                    "findings": [],
                    "source_refs": [],
                    "applicability": "",
                    "limitations": [marker],
                    "conflicts": [],
                },
            }
        ),
        encoding="utf-8",
    )


def _pending_ids(store) -> list[str]:
    pending = store / "pending"
    if not pending.is_dir():
        return []
    return sorted(path.stem for path in pending.glob("*.json"))


def test_run_scope_changes_execution_identity_not_question_identity(tmp_path) -> None:
    record = _record()
    question = _question()
    first = _request(question, record, "run:AAAA")
    second = _request(question, record, "run:BBBB")
    legacy = _request(question, record, "")
    # Same logical question: stable question identity across runs...
    assert first.question_id == second.question_id == legacy.question_id
    # ...but run-scoped executions are distinct per run.
    assert first.execution_id != second.execution_id
    assert first.execution_id != legacy.execution_id
    # The run-independent logical key matches across runs (traceability).
    provider = HostMediatedResearchProvider(store=tmp_path)
    assert provider._logical_execution_key(first) == provider._logical_execution_key(
        second
    )


def test_resume_pass_consumes_in_flight_episode_across_invocations(tmp_path) -> None:
    """Pass 1 (run A) emits; pass 2 is a new top-level invocation (run B)
    and must resume episode A's fulfilled result, not emit a duplicate."""
    record = _record()
    bundle = _bundle(record)
    question = _question()
    requirement = _requirement(question)
    provider = HostMediatedResearchProvider(store=tmp_path)

    # Pass 1, run A: emits the pending, awaits the host.
    req_a = _request(question, record, "run:AAAA")
    waiting = provider.execute(
        req_a, bundle=bundle, question=question, requirement=requirement
    )
    assert waiting.status == ResearchWorkerStatus.AWAITING_HOST
    assert _pending_ids(tmp_path) == [
        f"agent-request_{req_a.execution_id.split(':')[1]}"
    ]

    # Pass 1b (a polling invocation, run B) before fulfillment: resolves to
    # episode A - no duplicate pending.
    req_b = _request(question, record, "run:BBBB")
    still_waiting = provider.execute(
        req_b, bundle=bundle, question=question, requirement=requirement
    )
    assert still_waiting.status == ResearchWorkerStatus.AWAITING_HOST
    assert len(_pending_ids(tmp_path)) == 1

    # The host fulfills episode A; pass 2 (run C) consumes it.
    _fulfill(tmp_path, req_a.execution_id, question, "episode A result")
    req_c = _request(question, record, "run:CCCC")
    resumed = provider.execute(
        req_c, bundle=bundle, question=question, requirement=requirement
    )
    assert resumed.status == ResearchWorkerStatus.NOT_FOUND
    assert resumed.limitations == ["episode A result"]
    fulfilled_file = (
        tmp_path / "fulfilled" / f"{req_a.execution_id.replace(':', '_')}.json"
    )
    assert fulfilled_file.with_suffix(".consumed").exists()


def test_second_run_after_completion_gets_fresh_executions(tmp_path) -> None:
    """A repeated Generate-UAC run after the episode completed must delegate
    fresh research, not die on the consumed marker."""
    record = _record()
    bundle = _bundle(record)
    question = _question()
    requirement = _requirement(question)
    provider = HostMediatedResearchProvider(store=tmp_path)

    req_a = _request(question, record, "run:AAAA")
    provider.execute(req_a, bundle=bundle, question=question, requirement=requirement)
    _fulfill(tmp_path, req_a.execution_id, question, "episode A result")
    consumed = provider.execute(
        req_a, bundle=bundle, question=question, requirement=requirement
    )
    assert consumed.status == ResearchWorkerStatus.NOT_FOUND

    # Second top-level run (run Z): fresh execution, fresh pending, waiting.
    req_z = _request(question, record, "run:ZZZZ")
    fresh = provider.execute(
        req_z, bundle=bundle, question=question, requirement=requirement
    )
    assert fresh.status == ResearchWorkerStatus.AWAITING_HOST
    resolved = provider._resolve_run_scope(req_z)
    assert resolved.execution_id != req_a.execution_id
    assert resolved.run_scope == "run:ZZZZ"
    assert len(_pending_ids(tmp_path)) == 2
    # Run A's state is untouched: still fulfilled, still consumed.
    fulfilled_a = (
        tmp_path / "fulfilled" / f"{req_a.execution_id.replace(':', '_')}.json"
    )
    assert fulfilled_a.exists()
    assert fulfilled_a.with_suffix(".consumed").exists()


def test_duplicate_fulfill_within_one_run_fails_closed(tmp_path) -> None:
    """Within one run, a second result for the same execution is rejected;
    nothing silently re-executes a consumed execution id."""
    record = _record()
    bundle = _bundle(record)
    question = _question()
    requirement = _requirement(question)
    provider = HostMediatedResearchProvider(store=tmp_path)

    req = _request(question, record, "run:AAAA")
    provider.execute(req, bundle=bundle, question=question, requirement=requirement)
    _fulfill(tmp_path, req.execution_id, question, "first")
    first = provider.execute(
        req, bundle=bundle, question=question, requirement=requirement
    )
    assert first.status == ResearchWorkerStatus.NOT_FOUND

    # Duplicate resume of the same episode scope in the same run: fail closed.
    duplicate = provider.execute(
        req, bundle=bundle, question=question, requirement=requirement
    )
    assert duplicate.status == ResearchWorkerStatus.FAILED
    assert "already consumed" in duplicate.limitations[0]


def test_one_run_cannot_consume_another_runs_state(tmp_path) -> None:
    """A different logical question in run B never touches run A's episode;
    and a fulfilled episode waits for its own run's consumption."""
    record = _record()
    bundle = _bundle(record)
    question = _question()
    requirement = _requirement(question)
    provider = HostMediatedResearchProvider(store=tmp_path)

    req_a = _request(question, record, "run:AAAA")
    provider.execute(req_a, bundle=bundle, question=question, requirement=requirement)
    _fulfill(tmp_path, req_a.execution_id, question, "run A only")

    # An unrelated logical request in run B: no consumption of A's result.
    other_question = MissingQuestion(
        question="What does a different claim establish?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )
    req_b = _request(other_question, record, "run:BBBB")
    waiting_b = provider.execute(
        req_b, bundle=bundle, question=other_question, requirement=requirement
    )
    assert waiting_b.status == ResearchWorkerStatus.AWAITING_HOST
    fulfilled_a = (
        tmp_path / "fulfilled" / f"{req_a.execution_id.replace(':', '_')}.json"
    )
    assert fulfilled_a.exists()
    assert not fulfilled_a.with_suffix(".consumed").exists()


def test_no_timestamp_cleanup_and_legacy_state_left_intact(tmp_path) -> None:
    """Old pendings are never deleted or refreshed by a new run; legacy
    pre-G1 pendings (no run_scope) simply never match a scoped episode."""
    legacy_dir = tmp_path / "pending"
    legacy_dir.mkdir(parents=True)
    legacy = legacy_dir / "agent-request_deadbeef.json"
    legacy.write_text(json.dumps({"execution_id": "agent-request:deadbeef"}))

    record = _record()
    bundle = _bundle(record)
    question = _question()
    requirement = _requirement(question)
    provider = HostMediatedResearchProvider(store=tmp_path)
    req = _request(question, record, "run:AAAA")
    provider.execute(req, bundle=bundle, question=question, requirement=requirement)

    assert legacy.exists()
    assert len(_pending_ids(tmp_path)) == 2
