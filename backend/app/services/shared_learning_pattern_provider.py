"""Fresh tenant-bound approved lessons, adapted to the existing Pattern resolver.

No persistence, acceptance authorship, or local shared-snapshot substitution.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, get_args

from pydantic import ValidationError

from app.core.schemas_qe_pattern_mcp import (
    QePatternProductionStatus, QePatternProvenance, QePatternRecord,
    QePatternValidationStatus, ResolveQePatternsRequest,
    SharedAuthoringGuidance, SharedLearningContext, SharedLearningEnvelope,
    SharedLearningMode,
)

PUBLICATION_CONTRACT = "shared-uac-learning-publication-v1"
MAX_PUBLICATION_BYTES = 2_000_000
MAX_PUBLICATION_LESSONS = 500
PRESENTATION_DELTAS = frozenset({
    "LANGUAGE_SIMPLIFIED", "AC_MERGED", "AC_SPLIT", "IMPLEMENTATION_DETAIL_REMOVED",
})


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _aware_time(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publication timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _load_publication(**kwargs: Any) -> dict[str, Any]:
    from app.services.shared_uac_learning_service import load_shared_learning_publication
    return load_shared_learning_publication(**kwargs)


class SharedLearningPatternLibraryProvider:
    """Read current SQL revisions each time; revocation is never cached."""
    provider_name = "SHARED_UAC_LEARNING"

    def __init__(self, context: SharedLearningContext, *, loader: Callable[..., dict[str, Any]] | None = None) -> None:
        self.context = context
        self.loader = loader or _load_publication
        self.excluded_counts: dict[str, int] = {}
        self.authoring_records: list[QePatternRecord] = []
        self.blocked_reason: str | None = None

    def _exclude(self, reason: str) -> None:
        self.excluded_counts[reason] = self.excluded_counts.get(reason, 0) + 1

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        from app.services.qe_pattern_mcp_service import PatternLibraryInvalid, PatternLibraryUnavailable
        # A provider object may be reused by an injected resolver. No previous
        # exclusions or editorial records may survive a fresh SQL lookup.
        self.excluded_counts = {}
        self.authoring_records = []
        self.blocked_reason = None
        if not self.context.authenticated:
            raise PatternLibraryUnavailable("shared publication requires authenticated tenant access")
        try:
            publication = self.loader(tenant_id=self.context.tenant_id,
                cutoff_at=self.context.cutoff_at,
                excluded_source_case_ids=set(self.context.excluded_source_case_ids))
        except Exception as exc:
            raise PatternLibraryUnavailable("shared publication unavailable") from exc
        try:
            if not isinstance(publication, dict):
                raise ValueError("publication must be an object")
            if len(json.dumps(publication, default=str).encode()) > MAX_PUBLICATION_BYTES:
                raise ValueError("publication exceeds its bound")
            if publication.get("contract_version") != PUBLICATION_CONTRACT:
                raise ValueError("unsupported publication contract")
            if publication.get("tenant_id") != self.context.tenant_id:
                raise ValueError("publication tenant mismatch")
            if publication.get("source_protection_status") == "UNVERIFIED":
                self.blocked_reason = "SHARED_LEARNING_SOURCE_PROTECTION_UNVERIFIED"
                raise PatternLibraryUnavailable("shared source-protection metadata unavailable")
            publication_id = str(publication.get("publication_id") or "")
            if len(publication_id) != 64 or any(c not in "0123456789abcdef" for c in publication_id):
                raise ValueError("publication identity must be a SHA-256 hash")
            lessons = publication.get("lessons")
            if not isinstance(lessons, list) or len(lessons) > MAX_PUBLICATION_LESSONS:
                raise ValueError("publication lessons exceed their bound")
            records: list[QePatternRecord] = []
            seen: set[str] = set()
            for lesson in lessons:
                if not isinstance(lesson, dict):
                    raise ValueError("lesson must be an object")
                lesson_id = str(lesson.get("lesson_id") or "").strip()
                if not lesson_id or len(lesson_id) > 200 or lesson_id in seen:
                    raise ValueError("lesson identities must be bounded and unique")
                seen.add(lesson_id)
                published = _aware_time(lesson.get("published_at"))
                if published > datetime.now(timezone.utc):
                    raise ValueError("publication time cannot be in the future")
                if lesson.get("revoked_at"):
                    self._exclude("REVOKED")
                    continue
                if self.context.cutoff_at and published > self.context.cutoff_at:
                    self._exclude("AFTER_EVIDENCE_CUTOFF")
                    continue
                cases = lesson.get("source_case_ids")
                if not isinstance(cases, list) or not cases:
                    raise ValueError("lesson requires source cases")
                if {str(case).upper() for case in cases} & set(self.context.excluded_source_case_ids):
                    self._exclude("EXCLUDED_SOURCE_CASE")
                    continue
                record = self._record(lesson, publication_id)
                if record.lesson_influence_kind == "AUTHORING_GUIDANCE":
                    self.authoring_records.append(record)
                else:
                    records.append(record)
            return records, publication_id, publication_id
        except (ValueError, TypeError, ValidationError, KeyError) as exc:
            raise PatternLibraryInvalid("shared publication failed validation") from exc

    @staticmethod
    def _record(lesson: dict[str, Any], publication_id: str) -> QePatternRecord:
        from app.core.schemas_canonical_test_plan_runtime import (
            AbstractSignalKind, ChangeSurfaceKind, EvidenceSourceType, IssueDomain,
            SemanticDimension, _safe_handoff_text,
        )
        from app.core.schemas_shared_uac_learning import DeltaType

        if (lesson.get("source") != "HUMAN_FEEDBACK"
                or lesson.get("source_origin") == "AI_PROPOSAL"
                or lesson.get("automatic_authority_promotion") is not False
                or lesson.get("expected_behavior_authority") is not False):
            raise ValueError("shared lessons must be reviewed non-authoritative Human feedback")
        delta_type = lesson.get("delta_type")
        if delta_type not in get_args(DeltaType) or delta_type == "UNCLASSIFIED":
            raise ValueError("shared lessons require a reviewed delta classification")
        if type(lesson.get("version")) is not int or not 1 <= lesson["version"] <= 2_147_483_647:
            raise ValueError("shared lesson revision must be a positive SQL version")
        review, scope = lesson.get("human_approval") or {}, lesson.get("scope") or {}
        if not isinstance(review, dict) or not isinstance(scope, dict):
            raise ValueError("review and scope must be objects")
        if _aware_time(review.get("reviewed_at")) > _aware_time(lesson.get("published_at")):
            raise ValueError("approval must precede publication")
        if set(scope) - {"publishing_modes", "configuration_states", "subject_terms", "deployment_models", "product_versions"}:
            raise ValueError("unrecognized lesson scope qualifier")
        editorial = lesson.get("influence_kind") == "AUTHORING_GUIDANCE"
        if editorial != (delta_type in PRESENTATION_DELTAS):
            raise ValueError("presentation feedback cannot be a discovery pattern")
        for field, enum in (("domains", IssueDomain), ("surfaces", ChangeSurfaceKind),
                ("signals", AbstractSignalKind), ("families", SemanticDimension),
                ("preferred_evidence", EvidenceSourceType)):
            values = lesson.get(field)
            optional = field == "preferred_evidence" or (editorial and field == "families")
            if not isinstance(values, list) or (not optional and not values):
                raise ValueError("lesson selectors must be nonempty lists")
            for value in values:
                enum(value)
        lesson_id, cases = str(lesson["lesson_id"]), lesson["source_case_ids"]
        if any(not isinstance(case, str) or len(case) > 64
                or re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", case) is None for case in cases):
            raise ValueError("source case identities must be normalized Jira provenance")
        groups = lesson.get("independent_support_groups") or []
        guidance = _safe_handoff_text(lesson.get("guidance"), max_length=2000)
        if not guidance or len(guidance) > 2000:
            raise ValueError("lesson requires bounded guidance")
        return QePatternRecord(
            pattern_id="SHARED_" + _hash(lesson_id)[:32].upper(),
            pattern_version=str(lesson.get("version") or ""), lesson_id=lesson_id,
            lesson_kind=lesson.get("kind"),
            lesson_influence_kind=lesson.get("influence_kind", "INVESTIGATION_CANDIDATE"),
            validation_status=QePatternValidationStatus.APPROVED,
            production_status=QePatternProductionStatus.ACTIVE,
            abstract_change_surface=lesson["surfaces"], applicable_domains=lesson["domains"],
            applicable_publishing_modes=scope.get("publishing_modes") or [],
            applicable_configuration_states=scope.get("configuration_states") or [],
            applicable_subject_terms=scope.get("subject_terms") or [],
            applicable_deployment_models=scope.get("deployment_models") or [],
            applicable_product_versions=scope.get("product_versions") or [],
            abstract_signals=lesson["signals"], question_families=lesson["families"],
            relationship_to_explore=[guidance], preferred_evidence_sources=lesson.get("preferred_evidence") or [],
            materiality=lesson.get("materiality"), blocking_default=False,
            human_support_count=len(cases), independent_case_count=len(groups),
            supporting_case_ids=cases, qualifying_human_support_case_ids=cases,
            independent_support_groups=groups,
            counterexamples=lesson.get("counterexamples") or [], hard_negatives=lesson.get("hard_negatives") or [],
            confidence=lesson.get("confidence"), promotion_exception=lesson.get("exception_attestation") or None,
            provenance=QePatternProvenance(source_kind="SHARED_UAC_LEARNING",
                source_locator="shared-uac-learning:" + lesson_id, source_sha256=publication_id,
                source_schema_version=PUBLICATION_CONTRACT, derivation_partition="REVIEWED_OPERATIONAL_FEEDBACK",
                human_backed=True, raw_human_uac_included=False, candidate_source_case_ids=cases,
                approval_overlay_sha256=_hash(review), approval_authority="HUMAN_QE",
                validated_by=review.get("reviewer_id"), validated_at=review.get("reviewed_at"),
                origin_confirmed=review.get("origin_confirmed", False),
                applicability_confirmed=review.get("applicability_confirmed", False),
                counterexamples_checked=review.get("counterexamples_checked", False)))


def resolve_shared_learning(request: ResolveQePatternsRequest, context: SharedLearningContext,
        *, loader: Callable[..., dict[str, Any]] | None = None) -> SharedLearningEnvelope:
    """Resolve the shared lane without changing or replacing baseline patterns."""
    if context.mode == SharedLearningMode.DISABLED:
        # The server-off baseline is identical for every runtime entry point.
        # A redundant benchmark reason must not perturb preparation/output IDs.
        return SharedLearningEnvelope(mode=SharedLearningMode.DISABLED, status="DISABLED")
    if context.benchmark_isolation:
        return SharedLearningEnvelope(mode=SharedLearningMode.DISABLED, status="DISABLED",
            warnings=["SHARED_LEARNING_BENCHMARK_ISOLATION"])
    if not context.authenticated:
        return SharedLearningEnvelope(mode=context.mode, status="UNAVAILABLE",
            warnings=["SHARED_LEARNING_AUTHENTICATED_TENANT_REQUIRED"],
            error_code="SHARED_LEARNING_AUTHENTICATED_TENANT_REQUIRED")
    from app.services.qe_pattern_mcp_service import QePatternResolver
    if request.current_jira_key:
        context = context.model_copy(update={"excluded_source_case_ids": {
            *context.excluded_source_case_ids, request.current_jira_key.upper()}})
    provider = SharedLearningPatternLibraryProvider(context, loader=loader)
    response = QePatternResolver(provider).resolve(request)
    excluded = dict(response.excluded_pattern_counts)
    for code, count in provider.excluded_counts.items():
        excluded[code] = excluded.get(code, 0) + count
    editorial: list[SharedAuthoringGuidance] = []
    if provider.authoring_records and response.pattern_library_sha256:
        class EditorialSnapshot:
            def load(self):
                return provider.authoring_records, response.pattern_library_version, response.pattern_library_sha256
        editorial_response = QePatternResolver(EditorialSnapshot()).resolve(
            request.model_copy(update={"include_analysis_candidates": True}))
        editorial = [SharedAuthoringGuidance(lesson_id=match.pattern.lesson_id,
            lesson_version=match.pattern.pattern_version, lesson_kind=match.pattern.lesson_kind,
            guidance=" ".join(match.pattern.relationship_to_explore),
            publication_id=response.pattern_library_sha256) for match in editorial_response.matched_patterns]
    return SharedLearningEnvelope(mode=context.mode, status=response.provider_status.value,
        publication_id=response.pattern_library_sha256, pattern_count=response.pattern_count,
        matched_patterns=response.matched_patterns if context.mode == SharedLearningMode.ENABLED else [],
        suppressed_patterns=response.suppressed_patterns if context.mode == SharedLearningMode.ENABLED else [],
        shadow_pattern_ids=[row.pattern.pattern_id for row in response.matched_patterns] if context.mode == SharedLearningMode.SHADOW else [],
        shadow_suppressed_pattern_ids=[row.pattern_id for row in response.suppressed_patterns] if context.mode == SharedLearningMode.SHADOW else [],
        authoring_guidance=editorial if context.mode == SharedLearningMode.ENABLED else [],
        shadow_authoring_guidance_ids=[row.lesson_id for row in editorial] if context.mode == SharedLearningMode.SHADOW else [],
        excluded_pattern_counts=excluded, warnings=response.warnings,
        error_code=provider.blocked_reason or response.error_code)
