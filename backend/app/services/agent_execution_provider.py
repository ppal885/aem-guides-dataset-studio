"""A5: agent execution providers - the boundary between the canonical
runtime's research orchestration and the execution substrate.

The canonical runtime remains the only authority for state, validation,
sufficiency, coverage, promotion, and rendering.  Providers perform bounded
research interpretation and return the shared R2 ResearchWorkerResult
envelope; the runtime validates and admits it.  Agent output is proposed
research evidence, never acceptance authority.

Execution modes (AGENT_RESEARCH_MODE):

- ``deterministic`` (default): the existing R2 deterministic workers.
- ``agent``: real model execution per worker via the backend's configured
  LLM substrate (``llm_service``).  When no model is available the worker
  records WORKER_UNAVAILABLE - never a silent deterministic stand-in that
  claims agent execution.
- ``shadow``: deterministic result remains authoritative; the model worker
  also executes read-only and the comparison is recorded.  Never two
  production authorities.

Truthful receipts: every ResearchWorkerExecution records ``provider`` and
``model_execution`` - a deterministic service is never called an agent.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from app.core.schemas_canonical_test_plan_runtime import (
    AgentResearchRequest,
    CanonicalEvidenceBundle,
    ResearchFinding,
    ResearchFindingEvidenceRole,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
)

_PROVIDER_DETERMINISTIC = "DETERMINISTIC"
_PROVIDER_MODEL_AGENT = "MODEL_AGENT"

_ROLE_CONTRACT_FILES = {
    ResearchWorkerRole.DOC_RESEARCHER: "uac-doc-researcher.md",
    ResearchWorkerRole.CODE_RESEARCHER: "uac-code-researcher.md",
    ResearchWorkerRole.ATTACHMENT_RESEARCHER: "uac-attachment-researcher.md",
}

_MAX_EVIDENCE_EXCERPT = 400
_MAX_EVIDENCE_ITEMS = 25


def agent_research_mode() -> str:
    """The configured execution mode: agent | deterministic | shadow."""

    mode = os.environ.get("AGENT_RESEARCH_MODE", "").strip().casefold()
    return mode if mode in {"agent", "deterministic", "shadow"} else "deterministic"


def load_role_contract(role: ResearchWorkerRole) -> tuple[str, str, str]:
    """Load the canonical Skill role contract for a worker role.

    Returns (contract_name, version_sha256, text).  The canonical source is
    the Skill agents directory; Copilot registrations are generated wrappers
    kept in parity by scripts/sync_agent_registrations.py --check.
    """

    filename = _ROLE_CONTRACT_FILES[role]
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = (
            ancestor / "skills" / "test-plan-generation" / "agents" / filename
        )
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            return filename.removesuffix(".md"), version, text
    raise FileNotFoundError(f"canonical role contract not found: {filename}")


def _excerpt(value: object) -> str:
    text = str(value or "").strip()
    return text[:_MAX_EVIDENCE_EXCERPT]


class DeterministicResearchProvider:
    """The existing R2 deterministic workers behind the provider boundary."""

    provider_id = _PROVIDER_DETERMINISTIC
    model_execution = False

    def __init__(self, workers: dict[ResearchWorkerRole, object]) -> None:
        self._workers = workers

    def execute(
        self,
        request: AgentResearchRequest,
        *,
        bundle: CanonicalEvidenceBundle,
        question,
        requirement,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        worker = self._workers[request.worker_role]
        if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER:
            return worker.research(
                question, requirement, bundle, repository_roots=repository_roots
            )
        return worker.research(question, requirement, bundle)


class ModelAgentExecutionProvider:
    """Real model-backed research workers via the backend's configured LLM
    substrate.  The model receives only the bounded authorized context and
    the canonical role contract; it has NO tools - it can only interpret the
    supplied evidence, so it cannot write, mutate, or fetch anything.  The
    runtime validates the structured result before admission."""

    provider_id = _PROVIDER_MODEL_AGENT

    def __init__(self) -> None:
        # Truthful receipts: True only when an actual model invocation ran
        # during the last execute() call - never for WORKER_UNAVAILABLE.
        self.last_model_execution = False

    def execute(
        self,
        request: AgentResearchRequest,
        *,
        bundle: CanonicalEvidenceBundle,
        question,
        requirement,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        self.last_model_execution = False
        try:
            name, version, contract = load_role_contract(request.worker_role)
        except FileNotFoundError:
            return self._terminal(
                request,
                ResearchWorkerStatus.WORKER_UNAVAILABLE,
                ["canonical role contract unavailable for this role"],
            )
        try:
            from app.services import llm_service

            if not llm_service.is_llm_available():
                return self._terminal(
                    request,
                    ResearchWorkerStatus.WORKER_UNAVAILABLE,
                    ["no model provider is configured (LLM credentials absent)"],
                )
            system_prompt = (
                contract
                + "\n\nYou MUST answer with a single JSON object matching the "
                "requested schema. Never write acceptance criteria. Cite only "
                "supplied source_refs.\n"
            )
            user_prompt = self._user_prompt(request, bundle, question)
            # The model invocation actually happens here.
            self.last_model_execution = True
            raw = asyncio.run(
                llm_service.generate_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=1500,
                    step_name=f"agent_research_{request.worker_role.value}",
                )
            )
        except Exception as exc:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                [f"model execution failed: {exc.__class__.__name__}"],
            )
        return self._validate_and_build(
            request, raw, bundle, role_contract=f"{name}@{version}"
        )

    # ------------------------------------------------------------------

    def _user_prompt(
        self,
        request: AgentResearchRequest,
        bundle: CanonicalEvidenceBundle,
        question,
    ) -> str:
        evidence_lines = []
        authorized = set(request.authorized_source_refs) | set(
            request.context_refs
        )
        for record in bundle.records:
            if record.evidence_id not in authorized:
                continue
            evidence_lines.append(
                f"- source_ref: {record.evidence_id}\n"
                f"  source_type: {record.source_type.value}\n"
                f"  excerpt: {_excerpt(record.content)}"
            )
            if len(evidence_lines) >= _MAX_EVIDENCE_ITEMS:
                break
        return (
            f"question_id: {request.question_id}\n"
            f"question_revision: {request.question_revision}\n"
            f"question: {question.question}\n"
            f"requested_claim: {request.requested_claim}\n"
            f"applicability: {request.applicability or 'current ticket'}\n"
            f"currentness: {request.currentness or 'current'}\n\n"
            "Authorized evidence (cite only these source_refs):\n"
            + ("\n".join(evidence_lines) or "(none supplied)")
            + "\n\nReturn JSON: {\"status\": one of ANSWER_FOUND, PARTIAL, "
            "NOT_FOUND, SOURCE_UNAVAILABLE, CONFLICTED; "
            '"applicability": string; "currentness": string; '
            '"limitations": [string]; "conflicts": [string]; '
            '"findings": [{"claim": string, "source_refs": [string], '
            '"evidence_role": EXISTING_BEHAVIOR | REQUIREMENT_CLARIFICATION '
            "| SUPPORTING_CONTEXT | IMPLEMENTATION_EVIDENCE | "
            'OBSERVED_BEHAVIOR | DESIRED_BEHAVIOR}]}.  NOT_FOUND means the '
            "authorized evidence did not answer the question; never claim "
            "the opposite behavior."
        )

    def _validate_and_build(
        self,
        request: AgentResearchRequest,
        raw: object,
        bundle: CanonicalEvidenceBundle,
        *,
        role_contract: str,
    ) -> ResearchWorkerResult:
        """Canonical admission validation (A5 section 14): never trust agent
        JSON merely because it parses."""

        if not isinstance(raw, dict):
            return self._terminal(
                request, ResearchWorkerStatus.FAILED, ["result is not a JSON object"]
            )
        try:
            status = ResearchWorkerStatus(str(raw.get("status") or ""))
        except ValueError:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                ["result status is outside the R2 vocabulary"],
            )
        bundle_ids = {record.evidence_id for record in bundle.records}
        allowed_refs = (
            set(request.authorized_source_refs)
            | set(request.context_refs)
            | bundle_ids
        )
        findings = []
        for index, item in enumerate(raw.get("findings") or []):
            if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
                return self._terminal(
                    request,
                    ResearchWorkerStatus.FAILED,
                    [f"findings[{index}] lacks a claim"],
                )
            refs = [str(ref) for ref in (item.get("source_refs") or [])]
            unknown = [ref for ref in refs if ref not in allowed_refs]
            if unknown:
                # Fabricated/unknown source reference: reject the result.
                return self._terminal(
                    request,
                    ResearchWorkerStatus.FAILED,
                    ["finding cites sources outside the authorized set"],
                )
            try:
                role = ResearchFindingEvidenceRole(
                    str(item.get("evidence_role") or "SUPPORTING_CONTEXT")
                )
            except ValueError:
                role = ResearchFindingEvidenceRole.SUPPORTING_CONTEXT
            findings.append(
                ResearchFinding(
                    claim=str(item["claim"]).strip()[:2000],
                    source_refs=refs,
                    evidence_role=role,
                    applicability=str(item.get("applicability") or "")[:500],
                )
            )
        if status == ResearchWorkerStatus.ANSWER_FOUND and not findings:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                ["ANSWER_FOUND without findings is not a valid agent result"],
            )
        if status in {
            ResearchWorkerStatus.SOURCE_UNAVAILABLE,
            ResearchWorkerStatus.WORKER_UNAVAILABLE,
            ResearchWorkerStatus.FAILED,
        } and findings:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                ["unavailable/failed status cannot carry findings"],
            )
        try:
            result = ResearchWorkerResult(
                worker_role=request.worker_role,
                question_id=request.question_id,
                status=status,
                findings=findings,
                source_refs=sorted(
                    {ref for finding in findings for ref in finding.source_refs}
                ),
                applicability=str(raw.get("applicability") or "")[:500],
                currentness=str(raw.get("currentness") or "")[:200],
                limitations=[
                    str(item)[:500] for item in (raw.get("limitations") or [])
                ],
                conflicts=[
                    str(item)[:500] for item in (raw.get("conflicts") or [])
                ],
            )
        except Exception as exc:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                [f"result failed envelope validation: {exc.__class__.__name__}"],
            )
        return result

    def _terminal(
        self, request: AgentResearchRequest, status: ResearchWorkerStatus, notes
    ) -> ResearchWorkerResult:
        return ResearchWorkerResult(
            worker_role=request.worker_role,
            question_id=request.question_id,
            status=status,
            limitations=[str(note)[:500] for note in notes],
        )


class RoutedResearchProvider:
    """Mode-aware provider: deterministic | agent | shadow.  Shadow runs both
    read-only and keeps the deterministic result authoritative; the model
    comparison is returned for tracing, never for promotion."""

    def __init__(
        self,
        deterministic: DeterministicResearchProvider,
        agent: ModelAgentExecutionProvider | None = None,
        mode: str | None = None,
    ) -> None:
        self._deterministic = deterministic
        self._agent = agent or ModelAgentExecutionProvider()
        self._mode = mode or agent_research_mode()

    @property
    def mode(self) -> str:
        return self._mode

    def execute(self, request, **kwargs):
        """Return (authoritative_result, executions) where executions carries
        (provider_id, model_execution, result) per actual execution."""

        if self._mode == "agent":
            result = self._agent.execute(request, **kwargs)
            return result, [
                (
                    self._agent.provider_id,
                    bool(getattr(self._agent, "last_model_execution", True)),
                    result,
                )
            ]
        primary = self._deterministic.execute(request, **kwargs)
        executions = [(self._deterministic.provider_id, False, primary)]
        if self._mode == "shadow":
            shadow = self._agent.execute(request, **kwargs)
            executions.append(
                (
                    self._agent.provider_id,
                    bool(getattr(self._agent, "last_model_execution", True)),
                    shadow,
                )
            )
        return primary, executions
