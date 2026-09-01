"""FJ-17 discovery-to-GitHub-MCP implementation verification handoff.

The module is deliberately not a GitHub client.  It creates a bounded,
provider-neutral request after scope-aware hypothesis verification and applies
only sealed GitHub MCP results that return through canonical implementation
evidence.  Product/acceptance authority remains outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable

from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    BehaviorHypothesis,
    CanonicalEvidenceBundle,
    ChangeSurface,
    ChangeSurfaceKind,
    CurrentnessState,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationRequest,
    GitHubExpectedChangeSurface,
    GitHubImplementationContext,
    GitHubImplementationVerificationHandoff,
    GitHubImplementationVerificationResult,
    GitHubImplementationVerificationStatus,
    HypothesisState,
    MissingQuestion,
    ScopeResolution,
    SemanticDimension,
    VerificationState,
)
from app.services.reasoning_evidence_provider import (
    _safe_provider_reference,
)


_GITHUB_RESULT_RETRIEVAL_PASS = (
    "github-mcp-implementation-verification"  # noqa: S105 - routing label
)
_GITHUB_RESULT_METADATA_KEY = "github_mcp_result"
_IMPLEMENTATION_SOURCE_TYPES = {
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.CODE_DIFF,
    EvidenceSourceType.CURRENT_CODE,
}
_HANDOFF_DIMENSIONS = {
    SemanticDimension.DIRECT_CONSUMERS,
    SemanticDimension.SIBLING_CONSUMERS,
    SemanticDimension.DOWNSTREAM_PROCESSOR,
    SemanticDimension.PERSISTED_STATE,
}
_PATH_OR_SYMBOL_KEYS = {
    "path",
    "paths",
    "file",
    "files",
    "changed_file",
    "changed_files",
    "class",
    "classes",
    "changed_class",
    "changed_classes",
    "method",
    "methods",
    "changed_method",
    "changed_methods",
    "symbol",
    "symbols",
}


@dataclass(frozen=True)
class GitHubImplementationVerificationBatch:
    hypotheses: list[BehaviorHypothesis]
    applied_results: list[GitHubImplementationVerificationResult]
    applied_result_evidence_ids: list[str]
    unresolved_handoff_ids: list[str]
    rejected_result_evidence_ids: list[str]


GitHubImplementationResultAuthorizer = Callable[
    [
        EvidenceRecord,
        GitHubImplementationVerificationResult,
        GitHubImplementationVerificationHandoff,
        str,
    ],
    bool,
]


def is_github_implementation_result_record(record: EvidenceRecord) -> bool:
    content = record.content if isinstance(record.content, dict) else {}
    return bool(
        record.source_type in _IMPLEMENTATION_SOURCE_TYPES
        and record.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION
        and record.retrieval_pass == _GITHUB_RESULT_RETRIEVAL_PASS
        and record.metadata.get(_GITHUB_RESULT_METADATA_KEY) is True
        and content.get("SCHEMA_VERSION")
        == "aem-guides-github-implementation-verification-result-v1"
    )


def _flatten_known_symbols(value: object, *, parent: str = "") -> list[str]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            rows.extend(_flatten_known_symbols(child, parent=normalized))
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            rows.extend(_flatten_known_symbols(child, parent=parent))
    elif parent in _PATH_OR_SYMBOL_KEYS and value not in (None, ""):
        safe = _safe_provider_reference(value)
        if safe:
            rows.append(safe)
    return rows


def _normalize_versions(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        matches = re.findall(
            r"\b\d+(?:\.\d+){1,3}(?:\s*(?:sp|service pack)\s*\d+)?\b",
            text,
        )
        normalized.update(re.sub(r"\s+", " ", match) for match in matches)
        if not matches:
            normalized.add(text)
    return normalized


def _normalize_deployments(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"[_\s-]+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        if re.search(r"\bon\s*prem(?:ise|ises)?\b", text):
            normalized.add("on-prem")
        elif re.search(r"\bcloud(?:\s+service)?\b", text):
            normalized.add("cloud")
        else:
            normalized.add(text)
    return normalized


def _record_matches_scope(record: EvidenceRecord, scope: ScopeResolution) -> bool:
    expected_versions = _normalize_versions(scope.product_versions)
    expected_deployments = _normalize_deployments(scope.deployment_modes)
    actual_versions = _normalize_versions(
        [record.product_version, *record.version_scope.product_versions]
    )
    actual_deployments = _normalize_deployments(
        [record.deployment_model, record.version_scope.deployment_model]
    )
    return bool(
        (not expected_versions or expected_versions.issubset(actual_versions))
        and (
            not expected_deployments
            or expected_deployments.issubset(actual_deployments)
        )
    )


def _result_matches_handoff_context(
    result: GitHubImplementationVerificationResult,
    handoff: GitHubImplementationVerificationHandoff,
) -> bool:
    expected = handoff.jira_pr_context
    actual = result.verified_context
    expected_versions = _normalize_versions(expected.product_versions)
    actual_versions = _normalize_versions(actual.product_versions)
    expected_deployments = _normalize_deployments(expected.deployment_modes)
    actual_deployments = _normalize_deployments(actual.deployment_modes)
    if (
        actual.jira_key != expected.jira_key
        or actual.pull_request_references != expected.pull_request_references
        or actual.source_evidence_ids != expected.source_evidence_ids
        or not expected_versions.issubset(actual_versions)
        or not expected_deployments.issubset(actual_deployments)
        or result.inspection.blast_radius_contract
        != handoff.blast_radius_contract
        or set(result.inspection.blast_radius_completed_targets)
        != set(handoff.blast_radius_scope)
    ):
        return False
    terminal = result.status in {
        GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
        GitHubImplementationVerificationStatus.UNRELATED_PATH,
    }
    if terminal and expected.repository_revisions:
        return bool(
            result.primary_repository_revision
            and result.primary_repository_revision in expected.repository_revisions
        )
    return True


def _result_from_record(
    record: EvidenceRecord,
) -> GitHubImplementationVerificationResult | None:
    if not is_github_implementation_result_record(record):
        return None
    if (
        record.requirement_authority != AuthorityClass.IMPLEMENTATION_CONFIRMED
        or record.currentness
        not in {CurrentnessState.CURRENT, CurrentnessState.VERSION_SPECIFIC}
        or record.verification_status
        not in {
            VerificationState.VERIFIED_REVISION,
            VerificationState.VERIFIED_SOURCE,
        }
    ):
        return None
    try:
        result = GitHubImplementationVerificationResult.model_validate(record.content)
    except ValidationError:
        return None
    terminal = result.status in {
        GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
        GitHubImplementationVerificationStatus.UNRELATED_PATH,
    }
    if terminal:
        if record.verification_status != VerificationState.VERIFIED_REVISION:
            return None
        revision = record.version_scope.repository_revision
        if not revision or revision != result.primary_repository_revision:
            return None
    return result


class GitHubImplementationVerificationService:
    """Create and consume FJ-17 records without introducing a new runtime stage."""

    def __init__(
        self,
        *,
        result_authorizer: GitHubImplementationResultAuthorizer | None = None,
    ) -> None:
        # Production defaults to handoff-only.  An authenticated GitHub adapter
        # must inject a non-serializable authorizer before results can become
        # implementation truth.
        self._result_authorizer = result_authorizer

    def create_handoffs(
        self,
        *,
        request: GenerationRequest,
        scope: ScopeResolution,
        surfaces: list[ChangeSurface],
        evidence: CanonicalEvidenceBundle,
        questions: list[MissingQuestion],
        hypotheses: list[BehaviorHypothesis],
    ) -> list[GitHubImplementationVerificationHandoff]:
        questions_by_id = {row.question_id: row for row in questions}
        implementation_records = [
            row
            for row in evidence.records
            if row.source_type in _IMPLEMENTATION_SOURCE_TYPES
            and not is_github_implementation_result_record(row)
        ]
        implementation_evidence_ids = {
            row.evidence_id for row in implementation_records
        }
        relevant_surfaces = [
            row
            for row in surfaces
            if not implementation_evidence_ids
            or not row.source_evidence_ids
            or set(row.source_evidence_ids) & implementation_evidence_ids
        ]
        if not relevant_surfaces:
            relevant_surfaces = [
                ChangeSurface(
                    kind=ChangeSurfaceKind.CHANGED_ENTITY,
                    entity=row.source_reference,
                    source_evidence_ids=[row.evidence_id],
                    confidence=row.evidence_confidence,
                )
                for row in implementation_records
            ]
        ranked_surfaces = sorted(
            {row.surface_id: row for row in relevant_surfaces}.values(),
            key=lambda row: (-row.confidence, row.surface_id),
        )
        selected_surfaces = ranked_surfaces[:20]
        omitted_surface_count = max(0, len(ranked_surfaces) - len(selected_surfaces))
        expected_surfaces = [
            GitHubExpectedChangeSurface(
                surface_id=row.surface_id,
                kind=row.kind,
                entity=_safe_provider_reference(row.entity),
                source_evidence_ids=row.source_evidence_ids,
            )
            for row in selected_surfaces
        ]
        context_evidence_ids = implementation_evidence_ids | {
            evidence_id
            for row in relevant_surfaces
            for evidence_id in row.source_evidence_ids
        }
        known_symbols = {
            _safe_provider_reference(row.entity)
            for row in relevant_surfaces
            if _safe_provider_reference(row.entity)
        }
        for record in implementation_records:
            known_symbols.update(_flatten_known_symbols(record.content))
        source_references = sorted(
            {
                _safe_provider_reference(row.source_reference)
                for row in implementation_records
                if row.source_type
                in {
                    EvidenceSourceType.CURRENT_PR,
                    EvidenceSourceType.IMPLEMENTATION_DIFF,
                    EvidenceSourceType.CODE_DIFF,
                }
                and _safe_provider_reference(row.source_reference)
            }
        )
        revisions = sorted(
            {
                row.version_scope.repository_revision
                for row in implementation_records
                if row.version_scope.repository_revision
            }
        )
        rows: list[GitHubImplementationVerificationHandoff] = []
        for hypothesis in hypotheses:
            question = questions_by_id.get(hypothesis.derived_from_question_id)
            if (
                question is None
                or question.authority_subject
                != AuthoritySubject.ACTUAL_IMPLEMENTATION
                or question.dimension not in _HANDOFF_DIMENSIONS
                or hypothesis.state != HypothesisState.UNRESOLVED
            ):
                continue
            rows.append(
                GitHubImplementationVerificationHandoff(
                    question_id=question.question_id,
                    hypothesis_id=hypothesis.hypothesis_id,
                    implementation_question=question.question,
                    expected_change_surface=expected_surfaces,
                    omitted_change_surface_count=omitted_surface_count,
                    symbols_or_paths_if_known=sorted(known_symbols)[:200],
                    why_code_verification_required=(
                        "Material implementation applicability remains unresolved "
                        "after scope-aware local and semantic verification."
                    ),
                    jira_pr_context=GitHubImplementationContext(
                        jira_key=request.jira_key,
                        pull_request_references=source_references,
                        repository_revisions=revisions,
                        product_versions=scope.product_versions,
                        deployment_modes=scope.deployment_modes,
                        source_evidence_ids=sorted(context_evidence_ids),
                    ),
                    blast_radius_contract="VALUE_DATA_STATE_FLOW_V2",
                    materiality="P0" if question.blocking else "P1",
                )
            )
        return sorted(
            {row.handoff_id: row for row in rows}.values(),
            key=lambda row: row.handoff_id,
        )

    def apply_results(
        self,
        *,
        scope: ScopeResolution,
        evidence: CanonicalEvidenceBundle,
        handoffs: list[GitHubImplementationVerificationHandoff],
        hypotheses: list[BehaviorHypothesis],
    ) -> GitHubImplementationVerificationBatch:
        handoffs_by_id = {row.handoff_id: row for row in handoffs}
        hypotheses_by_id = {row.hypothesis_id: row for row in hypotheses}
        valid: dict[
            str,
            list[tuple[GitHubImplementationVerificationResult, EvidenceRecord]],
        ] = {}
        rejected_ids: list[str] = []
        for record in evidence.records:
            if not (
                record.retrieval_pass == _GITHUB_RESULT_RETRIEVAL_PASS
                or record.metadata.get(_GITHUB_RESULT_METADATA_KEY) is True
            ):
                continue
            result = _result_from_record(record)
            if result is None:
                rejected_ids.append(record.evidence_id)
                continue
            handoff = handoffs_by_id.get(result.handoff_id)
            hypothesis = hypotheses_by_id.get(result.hypothesis_id)
            if (
                handoff is None
                or hypothesis is None
                or result.question_id != handoff.question_id
                or result.hypothesis_id != handoff.hypothesis_id
                or result.trace_id != handoff.trace_id
                or not _result_matches_handoff_context(result, handoff)
                or hypothesis.derived_from_question_id != handoff.question_id
            ):
                rejected_ids.append(record.evidence_id)
                continue
            if self._result_authorizer is None:
                rejected_ids.append(record.evidence_id)
                continue
            try:
                authorized = self._result_authorizer(
                    record,
                    result,
                    handoff,
                    evidence.tenant_id,
                )
            except Exception:
                authorized = False
            if authorized is not True:
                rejected_ids.append(record.evidence_id)
                continue
            valid.setdefault(result.handoff_id, []).append((result, record))

        updated_by_origin: dict[str, BehaviorHypothesis] = {}
        applied_results: list[GitHubImplementationVerificationResult] = []
        applied_evidence_ids: list[str] = []
        unresolved_handoff_ids: list[str] = []
        for handoff in handoffs:
            origin = hypotheses_by_id.get(handoff.hypothesis_id)
            candidates = valid.get(handoff.handoff_id, [])
            if origin is None or len(candidates) != 1:
                unresolved_handoff_ids.append(handoff.handoff_id)
                if len(candidates) > 1:
                    rejected_ids.extend(record.evidence_id for _, record in candidates)
                continue
            result, record = candidates[0]
            terminal = result.status in {
                GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
                GitHubImplementationVerificationStatus.UNRELATED_PATH,
            }
            if terminal and not _record_matches_scope(record, scope):
                rejected_ids.append(record.evidence_id)
                unresolved_handoff_ids.append(handoff.handoff_id)
                continue
            if result.status == GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED:
                state = HypothesisState.CONFIRMED
                support = sorted(
                    set(origin.supporting_evidence_ids) | {record.evidence_id}
                )
                contradict = list(origin.contradicting_evidence_ids)
                confidence = 1.0
            elif result.status == GitHubImplementationVerificationStatus.UNRELATED_PATH:
                state = HypothesisState.REJECTED
                support = list(origin.supporting_evidence_ids)
                contradict = sorted(
                    set(origin.contradicting_evidence_ids) | {record.evidence_id}
                )
                confidence = 1.0
            else:
                state = HypothesisState.UNRESOLVED
                support = list(origin.supporting_evidence_ids)
                contradict = list(origin.contradicting_evidence_ids)
                confidence = 0.0
                unresolved_handoff_ids.append(handoff.handoff_id)
            updated_by_origin[origin.hypothesis_id] = BehaviorHypothesis(
                statement=origin.statement,
                state=state,
                supporting_evidence_ids=support,
                contradicting_evidence_ids=contradict,
                verification_evidence_ids=sorted(
                    set(origin.verification_evidence_ids) | {record.evidence_id}
                ),
                verification_origin_hypothesis_id=origin.hypothesis_id,
                derived_from_question_id=origin.derived_from_question_id,
                confidence=confidence,
            )
            applied_results.append(result)
            applied_evidence_ids.append(record.evidence_id)

        updated = [
            updated_by_origin.get(row.hypothesis_id, row) for row in hypotheses
        ]
        return GitHubImplementationVerificationBatch(
            hypotheses=sorted(updated, key=lambda row: row.hypothesis_id),
            applied_results=sorted(applied_results, key=lambda row: row.result_id),
            applied_result_evidence_ids=sorted(set(applied_evidence_ids)),
            unresolved_handoff_ids=sorted(set(unresolved_handoff_ids)),
            rejected_result_evidence_ids=sorted(set(rejected_ids)),
        )


GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE = (
    GitHubImplementationVerificationService()
)


__all__ = [
    "GITHUB_IMPLEMENTATION_VERIFICATION_SERVICE",
    "GitHubImplementationResultAuthorizer",
    "GitHubImplementationVerificationBatch",
    "GitHubImplementationVerificationService",
    "is_github_implementation_result_record",
]
