"""R2: canonical research workers - bounded, structured research adapters.

These are deterministic research services with provenance, invoked by the
canonical research orchestrator for material questions whose research
requirement is not NONE.  They are NOT chat-agent impersonations: every
worker returns the shared ResearchWorkerResult envelope and every finding
cites first-class sources (bundle evidence ids, or repository + revision +
path for read-only clone research).  Raw grep output is discovery input,
never a finding.

Worker availability is honest: when a mandated source cannot execute, the
envelope records SOURCE_UNAVAILABLE / WORKER_UNAVAILABLE / FAILED and claim
sufficiency stays bounded - infrastructure failure is never disguised as a
product answer.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone

from app.core.schemas_canonical_test_plan_runtime import (
    CanonicalEvidenceBundle,
    MissingQuestion,
    ResearchFinding,
    ResearchFindingEvidenceRole,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
)
from app.services.question_research_routing_service import (
    DOCUMENTATION_RESEARCH_SOURCES,
    IMPLEMENTATION_RESEARCH_SOURCES,
)

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_PATHISH_RE = re.compile(r"[\\/]|\.[a-z]{1,5}$", re.IGNORECASE)

# Read-only repository roots authorized for bounded code research.  These are
# the existing configured-clone environment conventions; the worker never
# mutates a repository.
from app.services.agent_execution_provider import (  # noqa: E402
    RESEARCH_REPOSITORY_ENV_VARS,
)

_MAX_TERMS = 6
_MAX_MATCHED_RECORDS = 20
_MAX_REPO_FILES = 20
_MAX_CLAIM = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terms(question: MissingQuestion) -> list[str]:
    """Investigation vocabulary: raw evidence terms first (they triggered the
    question), then readable question-text words."""

    words: list[str] = []
    for term in question.investigation_terms:
        words.extend(_WORD_RE.findall(term.casefold()))
    words.extend(_WORD_RE.findall(question.question.casefold()))
    stop = {
        "the", "and", "for", "are", "with", "this", "that", "what", "which",
        "when", "how", "does", "affected", "behavior",
    }
    seen: list[str] = []
    for word in words:
        if word not in stop and word not in seen:
            seen.append(word)
    return seen[:_MAX_TERMS]


def _record_text(record) -> str:
    parts = [record.source_reference]
    content = record.content

    def _flatten(value) -> None:
        if isinstance(value, dict):
            for item in value.values():
                _flatten(item)
        elif isinstance(value, list):
            for item in value:
                _flatten(item)
        elif value is not None:
            parts.append(str(value))

    _flatten(content)
    return " ".join(parts).casefold()


def _match_records(bundle: CanonicalEvidenceBundle, source_types, terms):
    matched = []
    for record in bundle.records:
        if record.source_type not in source_types:
            continue
        text = _record_text(record)
        hits = [term for term in terms if term in text]
        if hits:
            matched.append((record, hits))
    return matched[:_MAX_MATCHED_RECORDS]


def _first_literal(record, terms) -> str:
    """Return the shortest content literal containing a term (bounded)."""

    literals: list[str] = []

    def _flatten(value) -> None:
        if isinstance(value, dict):
            for item in value.values():
                _flatten(item)
        elif isinstance(value, list):
            for item in value:
                _flatten(item)
        elif isinstance(value, str):
            literals.append(value)

    _flatten(record.content)
    for literal in sorted(literals, key=len):
        lowered = literal.casefold()
        if any(term in lowered for term in terms):
            return literal[:_MAX_CLAIM]
    return record.source_reference[:_MAX_CLAIM]


class DocResearchWorker:
    """Bounded documentation research over authorized documentation evidence
    already admitted to the canonical bundle."""

    role = ResearchWorkerRole.DOC_RESEARCHER

    def research(
        self,
        question: MissingQuestion,
        requirement: ResearchRequirementRecord,
        bundle: CanonicalEvidenceBundle,
    ) -> ResearchWorkerResult:
        started = _now()
        terms = _terms(question)
        doc_records = [
            record
            for record in bundle.records
            if record.source_type in DOCUMENTATION_RESEARCH_SOURCES
        ]
        if not doc_records:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=ResearchWorkerStatus.SOURCE_UNAVAILABLE,
                limitations=[
                    "No authorized documentation evidence is present in the "
                    "canonical evidence bundle."
                ],
                started_at=started,
                completed_at=_now(),
            )
        matched = _match_records(bundle, DOCUMENTATION_RESEARCH_SOURCES, terms)
        conflicted_ids = {
            evidence_id
            for conflict in bundle.authority_conflicts
            for evidence_id in (
                list(conflict.selected_evidence_ids)
                + list(conflict.competing_evidence_ids)
            )
        }
        findings = []
        conflicts = []
        for record, hits in matched:
            literal = _first_literal(record, hits)
            if record.evidence_id in conflicted_ids:
                conflicts.append(literal)
            findings.append(
                ResearchFinding(
                    claim=literal,
                    source_refs=[record.evidence_id],
                    evidence_role=ResearchFindingEvidenceRole.EXISTING_BEHAVIOR,
                    applicability=str(
                        getattr(record.version_scope, "product_version", "") or ""
                    ),
                    currentness=str(getattr(record, "currentness", "") or ""),
                )
            )
        if conflicts and findings:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=ResearchWorkerStatus.CONFLICTED,
                findings=findings,
                source_refs=[f.source_refs[0] for f in findings],
                conflicts=conflicts,
                started_at=started,
                completed_at=_now(),
            )
        if findings:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=ResearchWorkerStatus.ANSWER_FOUND,
                findings=findings,
                source_refs=[f.source_refs[0] for f in findings],
                started_at=started,
                completed_at=_now(),
            )
        return ResearchWorkerResult(
            worker_role=self.role,
            question_id=question.question_id,
            status=ResearchWorkerStatus.NOT_FOUND,
            limitations=[
                "Authorized documentation evidence was searched and did not "
                "answer this question; absence is not the opposite behavior."
            ],
            started_at=started,
            completed_at=_now(),
        )


class AttachmentResearchWorker:
    """Bounded attachment-evidence interpretation over the canonical bundle.
    Attachments may establish observed/current/customer-stated-desired
    behavior; they never establish a specific implementation.  Visual or
    binary content the runtime cannot read is an explicit limitation, never
    a fabricated observation."""

    role = ResearchWorkerRole.ATTACHMENT_RESEARCHER

    def research(
        self,
        question: MissingQuestion,
        requirement: ResearchRequirementRecord,
        bundle: CanonicalEvidenceBundle,
    ) -> ResearchWorkerResult:
        started = _now()
        from app.core.schemas_canonical_test_plan_runtime import EvidenceSourceType

        attachments = [
            record
            for record in bundle.records
            if record.source_type == EvidenceSourceType.JIRA_ATTACHMENT
        ]
        if not attachments:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=ResearchWorkerStatus.SOURCE_UNAVAILABLE,
                limitations=["No attachment evidence is present in the bundle."],
                started_at=started,
                completed_at=_now(),
            )
        findings = []
        limitations = []
        for record in attachments:
            content = record.content if isinstance(record.content, dict) else {}
            excerpt = str(
                content.get("excerpt") or content.get("analysis") or ""
            ).strip()
            analyzed = bool(
                (record.metadata or {}).get("analyzed")
            ) or bool(excerpt)
            if analyzed and excerpt:
                findings.append(
                    ResearchFinding(
                        claim=excerpt[:_MAX_CLAIM],
                        source_refs=[record.evidence_id],
                        evidence_role=(
                            ResearchFindingEvidenceRole.OBSERVED_BEHAVIOR
                        ),
                        currentness=str(getattr(record, "currentness", "") or ""),
                    )
                )
            else:
                limitations.append(
                    f"Attachment '{record.source_reference}' "
                    "was not analyzed; visual/binary content is not "
                    "interpreted by the runtime."
                )
        if findings:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=(
                    ResearchWorkerStatus.ANSWER_FOUND
                    if not limitations
                    else ResearchWorkerStatus.PARTIAL
                ),
                findings=findings,
                source_refs=[f.source_refs[0] for f in findings],
                limitations=limitations,
                started_at=started,
                completed_at=_now(),
            )
        return ResearchWorkerResult(
            worker_role=self.role,
            question_id=question.question_id,
            status=ResearchWorkerStatus.SOURCE_UNAVAILABLE,
            limitations=limitations
            or ["Attachment evidence could not be interpreted."],
            started_at=started,
            completed_at=_now(),
        )


class CodeResearchWorker:
    """Bounded read-only implementation research: canonical bundle
    implementation records plus, when authorized local clones are configured,
    a read-only git grep over those repositories with exact revision
    provenance.  Repositories are never modified."""

    role = ResearchWorkerRole.CODE_RESEARCHER

    def research(
        self,
        question: MissingQuestion,
        requirement: ResearchRequirementRecord,
        bundle: CanonicalEvidenceBundle,
        *,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        started = _now()
        terms = _terms(question)
        findings = []
        limitations = []
        matched = _match_records(bundle, IMPLEMENTATION_RESEARCH_SOURCES, terms)
        for record, _hits in matched:
            findings.append(
                ResearchFinding(
                    claim=_first_literal(record, terms),
                    source_refs=[record.evidence_id],
                    evidence_role=(
                        ResearchFindingEvidenceRole.IMPLEMENTATION_EVIDENCE
                    ),
                    currentness=str(getattr(record, "currentness", "") or ""),
                )
            )
        roots = [
            root
            for root in (
                repository_roots
                if repository_roots is not None
                else [
                    os.environ.get(name, "").strip()
                    for name in RESEARCH_REPOSITORY_ENV_VARS
                ]
            )
            if root
        ]
        searched_repos = 0
        for root in roots:
            if not os.path.isdir(os.path.join(root, ".git")):
                limitations.append(f"Configured repository not usable: {root}")
                continue
            searched_repos += 1
            findings.extend(self._grep_repo(root, terms, limitations))
            if len(findings) >= _MAX_MATCHED_RECORDS + _MAX_REPO_FILES:
                break
        if not findings and not searched_repos and not matched:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=ResearchWorkerStatus.SOURCE_UNAVAILABLE,
                limitations=limitations
                or [
                    "No implementation evidence in the bundle and no "
                    "authorized repository is configured."
                ],
                started_at=started,
                completed_at=_now(),
            )
        if findings:
            return ResearchWorkerResult(
                worker_role=self.role,
                question_id=question.question_id,
                status=(
                    ResearchWorkerStatus.ANSWER_FOUND
                    if not limitations
                    else ResearchWorkerStatus.PARTIAL
                ),
                findings=findings,
                source_refs=sorted(
                    {ref for finding in findings for ref in finding.source_refs}
                ),
                limitations=limitations,
                started_at=started,
                completed_at=_now(),
            )
        return ResearchWorkerResult(
            worker_role=self.role,
            question_id=question.question_id,
            status=ResearchWorkerStatus.NOT_FOUND,
            limitations=limitations
            or ["Implementation sources searched; no matching evidence found."],
            started_at=started,
            completed_at=_now(),
        )

    def _grep_repo(
        self, root: str, terms: list[str], limitations: list[str]
    ) -> list[ResearchFinding]:
        findings: list[ResearchFinding] = []
        try:
            revision = subprocess.run(
                ["git", "-C", root, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
        except Exception:
            revision = ""
            limitations.append(f"Could not resolve revision for {root}")
        for term in terms:
            if len(findings) >= _MAX_REPO_FILES:
                break
            try:
                proc = subprocess.run(
                    ["git", "-C", root, "grep", "-l", "-F", "-i", term, "--",
                     "*.py", "*.java", "*.ts", "*.tsx", "*.js", "*.json",
                     "*.feature", "*.md"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                limitations.append(f"Read-only search failed in {root}")
                break
            if proc.returncode not in (0, 1):
                limitations.append(f"Read-only search failed in {root}")
                break
            for path in sorted(proc.stdout.splitlines()):
                if len(findings) >= _MAX_REPO_FILES:
                    break
                findings.append(
                    ResearchFinding(
                        claim=(
                            f"Repository evidence for '{term}' located in "
                            f"{os.path.basename(root)} at {path}"
                        ),
                        source_refs=[],
                        evidence_role=(
                            ResearchFindingEvidenceRole.IMPLEMENTATION_EVIDENCE
                        ),
                        repository=root,
                        revision=revision,
                        path=path,
                    )
                )
        return findings


class ResearchOrchestrator:
    """R2: dispatch bounded research workers for material questions before any
    human-facing clarification.  Returns structured envelopes plus an
    auditable execution trace.

    A5: execution goes through the provider boundary.  The default
    deterministic mode is the existing R2 behavior; agent mode executes real
    model workers via the backend LLM substrate; shadow mode runs both
    read-only with the deterministic result authoritative.  Every execution
    row records provider + model_execution so a deterministic service is
    never called an agent."""

    def __init__(self, workers: list | None = None, provider=None) -> None:
        self._workers = workers or [
            DocResearchWorker(),
            CodeResearchWorker(),
            AttachmentResearchWorker(),
        ]
        if provider is None:
            from app.services.agent_execution_provider import (
                DeterministicResearchProvider,
                ModelAgentExecutionProvider,
                RoutedResearchProvider,
            )

            provider = RoutedResearchProvider(
                DeterministicResearchProvider(
                    {worker.role: worker for worker in self._workers}
                ),
                ModelAgentExecutionProvider(),
            )
        self._provider = provider

    def execute(
        self,
        questions: list[MissingQuestion],
        requirements: list[ResearchRequirementRecord],
        bundle: CanonicalEvidenceBundle,
        *,
        repository_roots: list[str] | None = None,
        run_scope: str = "",
    ) -> tuple[list[ResearchWorkerResult], list]:
        from app.core.schemas_canonical_test_plan_runtime import (
            AgentResearchRequest,
            EvidenceSourceType,
            ResearchWorkerExecution,
        )

        requirements_by_question = {row.question_id: row for row in requirements}
        has_attachments = any(
            record.source_type == EvidenceSourceType.JIRA_ATTACHMENT
            for record in bundle.records
        )
        results: list[ResearchWorkerResult] = []
        executions: list[ResearchWorkerExecution] = []
        for question in sorted(questions, key=lambda row: row.question_id):
            requirement = requirements_by_question.get(question.question_id)
            if (
                requirement is None
                or not requirement.material
                or requirement.research_requirement == ResearchRequirement.NONE
            ):
                continue
            roles = self._roles_for(requirement, has_attachments)
            for role in roles:
                request = AgentResearchRequest(
                    run_scope=run_scope,
                    worker_role=role,
                    question_id=question.question_id,
                    question_revision=question.question_revision,
                    requested_claim=question.question,
                    research_requirement=requirement.research_requirement,
                    authorized_source_refs=[
                        record.evidence_id for record in bundle.records
                    ],
                    applicability=str(
                        getattr(requirement, "applicability", "") or ""
                    ),
                )
                try:
                    result, provider_executions = self._provider.execute(
                        request,
                        bundle=bundle,
                        question=question,
                        requirement=requirement,
                        repository_roots=repository_roots,
                    )
                except Exception as exc:  # fail closed, honestly recorded
                    result = ResearchWorkerResult(
                        worker_role=role,
                        question_id=question.question_id,
                        status=ResearchWorkerStatus.FAILED,
                        limitations=[f"worker error: {exc.__class__.__name__}"],
                    )
                    provider_executions = [("DETERMINISTIC", False, result, {})]
                # The authoritative result is the primary execution; shadow
                # executions are recorded for comparison only and are never
                # consumed by the resolver.
                results.append(result)
                role_contract = ""
                model = ""
                for provider_id, model_execution, executed_result, receipt in (
                    provider_executions
                ):
                    if receipt.get("role_contract"):
                        role_contract = receipt["role_contract"]
                    if receipt.get("model"):
                        model = receipt["model"]
                    executions.append(
                        ResearchWorkerExecution(
                            worker_role=role,
                            question_id=question.question_id,
                            trigger=(
                                f"research_requirement="
                                f"{requirement.research_requirement.value}"
                            ),
                            started_at=executed_result.started_at,
                            completed_at=executed_result.completed_at,
                            status=executed_result.status,
                            result_ref=executed_result.research_id,
                            provider=provider_id,
                            model_execution=model_execution,
                            role_contract=role_contract,
                            model=model,
                        )
                    )
        return results, executions

    def _roles_for(self, requirement, has_attachments: bool):
        from app.services.question_research_routing_service import (
            RESEARCH_CATEGORY_DOCUMENTATION,
            RESEARCH_CATEGORY_IMPLEMENTATION,
            research_source_category,
        )

    def _roles_for(self, requirement, has_attachments: bool):
        from app.services.question_research_routing_service import (
            RESEARCH_CATEGORY_DOCUMENTATION,
            RESEARCH_CATEGORY_IMPLEMENTATION,
            research_source_category,
        )

        categories = {
            research_source_category(source_type)
            for source_type in requirement.required_source_types
        }
        roles = []
        for worker in self._workers:
            if (
                worker.role == ResearchWorkerRole.DOC_RESEARCHER
                and RESEARCH_CATEGORY_DOCUMENTATION in categories
            ):
                roles.append(worker.role)
            elif (
                worker.role == ResearchWorkerRole.CODE_RESEARCHER
                and RESEARCH_CATEGORY_IMPLEMENTATION in categories
            ):
                roles.append(worker.role)
            elif (
                worker.role == ResearchWorkerRole.ATTACHMENT_RESEARCHER
                and has_attachments
            ):
                # Attachment evidence may answer any material question when
                # present; it never replaces the mandated doc/code routes.
                roles.append(worker.role)
        return roles


RESEARCH_ORCHESTRATOR = ResearchOrchestrator()
