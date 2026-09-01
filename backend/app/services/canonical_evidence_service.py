"""Canonical evidence normalization, authority, currentness, and visibility.

This module is adapter-only: it never retrieves data.  Callers pass evidence
already obtained through the existing Jira, RAG, repository, design, or
feedback integrations and receive deterministic source-native records.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthorityResolution,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    CompatibilityProjectionLink,
    CurrentnessState,
    EvidenceDirectness,
    EvidenceRecord,
    EvidenceSourceType,
    LifecycleState,
    LegacyCompatibilityProjection,
    ProductOwnership,
    ProductContractOwnership,
    ResolutionState,
    RuntimePrincipal,
    SourceVisibility,
    FeedbackClassification,
    GITHUB_IMPLEMENTATION_RESULT_SCHEMA,
    GitHubImplementationVerificationResult,
    GitHubImplementationVerificationStatus,
    UserFeedbackCandidate,
    UiApplicability,
    VerificationState,
    VersionScope,
    VisibilityClass,
    stable_sha256,
)


_SECRET_KEY_RE = re.compile(
    r"(?:authorization|proxy[_-]?authorization|password|passwd|secret|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|cookie|set[_-]?cookie)$",
    re.IGNORECASE,
)
_SECRET_VALUE_RES = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
_AUTHORIZATION_FIELD_RE = re.compile(
    r"(?im)\b(authorization|proxy[_-]?authorization)\b[\"']?\s*[:=]\s*[^\r\n]+"
)
_REDACTED = "[REDACTED]"
_SEALED_ANSWER_FIELD = "ground" + "_" + "truth"
_FORBIDDEN_GENERATION_FIELDS = {
    "acceptance_criteria",
    "authoritative_uac",
    _SEALED_ANSWER_FIELD,
    "human_uac",
    "post_uac_evidence",
    "uac_workflow_status",
}


_AUTHORITY_CLASS_RANK = {
    AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT: 100,
    AuthorityClass.CONFIRMED_PRODUCT_DECISION: 97,
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT: 90,
    AuthorityClass.SPECIFICATION_AUTHORITY: 90,
    AuthorityClass.IMPLEMENTATION_CONFIRMED: 85,
    AuthorityClass.HISTORICAL_EXPECTATION: 60,
    AuthorityClass.TECHNICALLY_INFERRED: 45,
    AuthorityClass.USER_EXPECTATION: 35,
    AuthorityClass.CUSTOMER_REQUEST: 30,
    AuthorityClass.PROPOSED: 20,
    AuthorityClass.PENDING_HUMAN_REVIEW: 10,
    AuthorityClass.UNKNOWN: 0,
}

_SUBJECT_SOURCE_RANK: dict[AuthoritySubject, dict[EvidenceSourceType, int]] = {
    AuthoritySubject.PRODUCT_CONTRACT: {
        EvidenceSourceType.ACCEPTED_UAC: 1000,
        EvidenceSourceType.PRODUCT_DECISION: 950,
        EvidenceSourceType.ENGINEERING_DECISION: 925,
        EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA: 900,
        EvidenceSourceType.JIRA_DESCRIPTION: 875,
        EvidenceSourceType.CURRENT_JIRA: 850,
        EvidenceSourceType.CUSTOMER_REQUEST: 800,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: 700,
        EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION: 700,
        EvidenceSourceType.CURRENT_PR: 500,
        EvidenceSourceType.CURRENT_CODE: 475,
        EvidenceSourceType.IMPLEMENTATION_DIFF: 475,
        EvidenceSourceType.MODEL_INFERENCE: 0,
    },
    AuthoritySubject.DITA_SEMANTICS: {
        EvidenceSourceType.DITA_SPECIFICATION: 1000,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: 900,
        EvidenceSourceType.DITA_OT_DOCUMENTATION: 800,
        EvidenceSourceType.CURRENT_CODE: 700,
        EvidenceSourceType.CURRENT_PR: 700,
        EvidenceSourceType.HISTORICAL_JIRA: 500,
        EvidenceSourceType.MODEL_INFERENCE: 0,
    },
    AuthoritySubject.ACTUAL_IMPLEMENTATION: {
        EvidenceSourceType.CURRENT_PR: 1000,
        EvidenceSourceType.IMPLEMENTATION_DIFF: 1000,
        EvidenceSourceType.CODE_DIFF: 1000,
        EvidenceSourceType.CURRENT_CODE: 975,
        EvidenceSourceType.EXISTING_AUTOMATION: 950,
        EvidenceSourceType.UI_OBSERVATION: 925,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: 700,
        EvidenceSourceType.HISTORICAL_JIRA: 400,
        EvidenceSourceType.MODEL_INFERENCE: 0,
    },
    AuthoritySubject.CURRENT_UI: {
        EvidenceSourceType.UI_OBSERVATION: 1000,
        EvidenceSourceType.OBSERVED_UI_FLOW: 1000,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION: 1000,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: 900,
        EvidenceSourceType.HISTORICAL_JIRA: 400,
        EvidenceSourceType.MODEL_INFERENCE: 0,
    },
}


def _authority_rank(
    record: EvidenceRecord, subject: AuthoritySubject
) -> tuple[int, int]:
    """Return a subject-specific rank; confidence is deliberately excluded."""

    source_rank = _SUBJECT_SOURCE_RANK[subject].get(record.source_type, 100)
    return source_rank, _AUTHORITY_CLASS_RANK[record.authority_class]


def redact_sensitive(value: Any, *, parent_key: str = "") -> Any:
    """Recursively redact credential-shaped fields without changing source data."""

    if _SECRET_KEY_RE.search(parent_key):
        return _REDACTED
    if isinstance(value, dict):
        return {
            str(key): redact_sensitive(child, parent_key=str(key))
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive(child, parent_key=parent_key) for child in value]
    if isinstance(value, str):
        redacted = _AUTHORIZATION_FIELD_RE.sub(
            lambda match: f"{match.group(1)}={_REDACTED}",
            value,
        )
        for pattern in _SECRET_VALUE_RES:
            redacted = pattern.sub(_REDACTED, redacted)
        return redacted
    return value


def assert_generation_safe(
    value: Any, *, source_path: str = "", sealed_benchmark: bool = False
) -> None:
    """Fail closed if a generation adapter receives evaluator-only answer data."""

    if source_path:
        normalized = source_path.replace("\\", "/").casefold()
        if "/private/" in f"/{normalized.strip('/')}/":
            raise ValueError(
                "generation evidence cannot come from a private benchmark path"
            )
    if isinstance(value, dict):
        names = {str(key).casefold() for key in value}
        forbidden = names & _FORBIDDEN_GENERATION_FIELDS if sealed_benchmark else set()
        if forbidden:
            raise ValueError(
                f"generation evidence contains evaluator-only fields: {sorted(forbidden)}"
            )
        for child in value.values():
            assert_generation_safe(child, sealed_benchmark=sealed_benchmark)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            assert_generation_safe(child, sealed_benchmark=sealed_benchmark)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(
            value.get("name") or value.get("value") or value.get("id") or ""
        ).strip()
    return str(value).strip()


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)})
    text = _text(value)
    return [text] if text else []


def _canonical_uri(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        if not parsed.scheme or not parsed.netloc:
            return text
        path = parsed.path.rstrip("/") or "/"
        return urlunsplit(
            (parsed.scheme.casefold(), parsed.netloc.casefold(), path, parsed.query, "")
        )
    except Exception:
        return text


def _source_key(prefix: str, row: Any, *fields: str, fallback: str = "") -> str:
    if isinstance(row, dict):
        for field in fields:
            value = row.get(field)
            if value:
                return f"{prefix}:{_canonical_uri(value)}"
    if fallback:
        return f"{prefix}:{fallback}"
    return f"{prefix}:{stable_sha256(redact_sensitive(row))[:24]}"


def _ownership_from_issue(issue: dict[str, Any]) -> ProductOwnership:
    component = _text(issue.get("component"))
    if not component:
        component = ", ".join(_values(issue.get("components")))
    area = _text(issue.get("product_area") or issue.get("feature") or component)
    product_text = " ".join(
        _text(issue.get(field))
        for field in ("product", "summary", "description", "component")
    ).casefold()
    contract = (
        ProductContractOwnership.AEM_ASSETS_PLATFORM_CONTRACT
        if "aem assets" in product_text or "assets platform" in product_text
        else ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT
    )
    return ProductOwnership(
        product=(
            "AEM Assets"
            if contract == ProductContractOwnership.AEM_ASSETS_PLATFORM_CONTRACT
            else "AEM Guides"
        ),
        product_area=area,
        component=component,
        capability=_text(issue.get("capability") or issue.get("feature")),
        surface=_text(issue.get("surface")),
        contract_ownership=contract,
        owner_status="inferred" if component or area else "unknown",
    )


def _visibility(
    tenant_id: str,
    *,
    classification: VisibilityClass = VisibilityClass.TENANT,
    allowed_roles: Iterable[str] = (),
    customer_data: bool = False,
) -> SourceVisibility:
    return SourceVisibility(
        classification=classification,
        tenant_id=tenant_id,
        allowed_roles=list(allowed_roles),
        contains_customer_data=customer_data,
        redacted=True,
    )


def _record(
    *,
    source_type: EvidenceSourceType,
    source_key: str,
    tenant_id: str,
    content: Any,
    authority_class: AuthorityClass,
    authority_subject: AuthoritySubject | None = None,
    authority_score: float,
    confidence: float,
    verification_state: VerificationState,
    currentness: CurrentnessState,
    lifecycle: LifecycleState = LifecycleState.INSPECTED,
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
    source_uri: str = "",
    source_native_id: str = "",
    title: str = "",
    version_scope: VersionScope | None = None,
    ownership: ProductOwnership | None = None,
    visibility: SourceVisibility | None = None,
    claim_keys: Iterable[str] = (),
    derived_from: Iterable[str] = (),
    supersedes: Iterable[str] = (),
    feedback: UserFeedbackCandidate | None = None,
    rejected_reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> EvidenceRecord:
    safe_content = redact_sensitive(content)
    safe_metadata = redact_sensitive(metadata or {})
    scope = version_scope or VersionScope()
    owner = ownership or ProductOwnership()
    lineage = list(derived_from)
    if directness == EvidenceDirectness.DERIVED and not lineage:
        lineage = [source_key]
    extracted = []
    if isinstance(safe_content, dict):
        extracted = _values(
            safe_content.get("extracted_facts") or safe_content.get("facts")
        )
    inspected = lifecycle in {LifecycleState.INSPECTED, LifecycleState.USED}
    used = lifecycle == LifecycleState.USED
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=authority_subject,
        source_reference=source_key,
        source_location=_canonical_uri(source_uri),
        source_native_id=source_native_id,
        tenant_id=tenant_id,
        product=owner.product,
        product_area=owner.product_area,
        capability=owner.capability,
        surface=owner.surface,
        content=safe_content,
        extracted_facts=extracted,
        source_timestamp=scope.source_updated_at,
        retrieved_at=scope.retrieved_at,
        product_version=",".join(scope.product_versions),
        dita_version=scope.dita_version,
        deployment_model=scope.deployment_model,
        environment=scope.environment,
        currentness=currentness,
        ui_applicability=(
            UiApplicability.APPLICABLE_CURRENT
            if source_type
            in {
                EvidenceSourceType.UI_OBSERVATION,
                EvidenceSourceType.OBSERVED_UI_FLOW,
                EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            }
            and currentness == CurrentnessState.CURRENT
            else UiApplicability.POSSIBLY_APPLICABLE
            if source_type
            in {
                EvidenceSourceType.UI_OBSERVATION,
                EvidenceSourceType.OBSERVED_UI_FLOW,
                EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            }
            else UiApplicability.UNKNOWN
        ),
        evidence_confidence=confidence,
        requirement_authority=authority_class,
        verification_status=verification_state,
        lifecycle_status=lifecycle,
        evidence_role=_text(safe_metadata.get("evidence_role")) or "UNKNOWN",
        retrieval_query=_text(
            safe_metadata.get("retrieval_query")
            or safe_metadata.get("retrieved_by_query")
        ),
        retrieval_pass=_text(safe_metadata.get("retrieval_pass")),
        retrieved_by_query=_values(safe_metadata.get("retrieved_by_query")),
        entered_compatibility_input=bool(
            safe_metadata.get("entered_compatibility_input", False)
        ),
        inspected=inspected,
        used=used,
        rejected_reason=rejected_reason,
        directness=directness,
        version_scope=scope,
        ownership=owner,
        visibility=visibility or _visibility(tenant_id),
        claim_keys=list(claim_keys),
        derived_from=lineage,
        supersedes=list(supersedes),
        feedback=feedback,
        metadata={
            **safe_metadata,
            "title": title,
            "legacy_authority_score": authority_score,
        },
    )


def _record_rows(
    rows: Any,
    *,
    tenant_id: str,
    source_type: EvidenceSourceType,
    prefix: str,
    authority: AuthorityClass,
    authority_score: float,
    confidence: float,
    verification: VerificationState,
    currentness: CurrentnessState,
    ownership: ProductOwnership,
    fields: tuple[str, ...],
    public: bool = False,
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
) -> list[EvidenceRecord]:
    if isinstance(rows, dict):
        rows = rows.get("results") or rows.get("items") or rows.get("evidence") or []
    if not isinstance(rows, list):
        return []
    records: list[EvidenceRecord] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            row = {"value": row}
        uri = _canonical_uri(
            row.get("canonical_url")
            or row.get("source_url")
            or row.get("url")
            or row.get("path")
        )
        revision = _text(
            row.get("source_hash")
            or row.get("revision")
            or row.get("commit_sha")
            or row.get("head_sha")
        )
        state = currentness
        if (
            source_type
            in {
                EvidenceSourceType.REPOSITORY_CODE,
                EvidenceSourceType.IMPLEMENTATION_DIFF,
                EvidenceSourceType.PULL_REQUEST,
                EvidenceSourceType.AUTOMATION,
            }
            and not revision
        ):
            state = CurrentnessState.UNVERSIONED
        records.append(
            _record(
                source_type=source_type,
                source_key=_source_key(prefix, row, *fields, fallback=str(index)),
                source_uri=uri,
                source_native_id=_text(
                    row.get("id") or row.get("chunk_id") or row.get("source_record_id")
                ),
                tenant_id=tenant_id,
                title=_text(row.get("title") or row.get("summary") or row.get("name")),
                content=row,
                authority_class=authority,
                authority_score=authority_score,
                confidence=confidence,
                verification_state=verification,
                currentness=state,
                directness=directness,
                version_scope=VersionScope(
                    product_versions=_values(
                        row.get("product_versions") or row.get("versions")
                    ),
                    dita_version=_text(
                        row.get("dita_version") or row.get("dita_spec_version")
                    ),
                    deployment_model=_text(row.get("deployment_model")),
                    repository=_text(row.get("repository") or row.get("repo_id")),
                    repository_revision=revision,
                    branch=_text(row.get("branch")),
                    dirty=row.get("dirty")
                    if isinstance(row.get("dirty"), bool)
                    else None,
                    source_updated_at=_text(
                        row.get("updated_at") or row.get("source_updated_at")
                    ),
                    retrieved_at=_text(row.get("retrieved_at")),
                    environment=_text(row.get("environment")),
                ),
                ownership=ownership,
                visibility=_visibility(
                    tenant_id,
                    classification=VisibilityClass.PUBLIC
                    if public
                    else VisibilityClass.INTERNAL,
                    customer_data=source_type == EvidenceSourceType.HISTORICAL_JIRA,
                ),
                claim_keys=_values(row.get("claim_keys")),
                metadata={
                    "retrieved_by_query": row.get("query")
                    or row.get("retrieval_query")
                    or row.get("search_query")
                    or [],
                    "retrieval_pass": row.get("retrieval_pass") or "existing-adapter",
                    "evidence_role": row.get("evidence_role") or "SUPPORTING",
                },
            )
        )
    return records


def _jira_records(packet: dict[str, Any], tenant_id: str) -> list[EvidenceRecord]:
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    jira_key = _text(packet.get("jira_key") or issue.get("issue_key")).upper()
    source = _text(issue.get("source") or issue.get("lookup_source"))
    live = source == "jira_api"
    ownership = _ownership_from_issue(issue)
    version_scope = VersionScope(
        product_versions=_values(issue.get("affected_versions"))
        + _values(issue.get("fix_versions")),
        dita_version=_text(issue.get("dita_version")),
        deployment_model=_text(issue.get("deployment_model")),
        source_updated_at=_text(issue.get("updated") or issue.get("updated_at")),
        retrieved_at=_text(issue.get("retrieved_at")),
        environment=_text(issue.get("environment")),
    )
    records = [
        _record(
            source_type=EvidenceSourceType.CURRENT_JIRA,
            source_key=f"jira:{jira_key}",
            source_uri=f"jira://{jira_key}",
            source_native_id=jira_key,
            tenant_id=tenant_id,
            title=_text(issue.get("summary") or issue.get("title")),
            content=issue,
            authority_class=AuthorityClass.CURRENT_JIRA,
            authority_score=0.95,
            confidence=1.0 if live else 0.75,
            verification_state=(
                VerificationState.VERIFIED_LIVE if live else VerificationState.CACHED
            ),
            currentness=CurrentnessState.CURRENT if live else CurrentnessState.UNKNOWN,
            version_scope=version_scope,
            ownership=ownership,
            visibility=_visibility(tenant_id, customer_data=True),
            claim_keys=[f"jira:{jira_key}:current-ticket"],
            metadata={"source": source},
        )
    ]

    description = issue.get("description")
    if description not in (None, "", [], {}):
        records.append(
            _record(
                source_type=EvidenceSourceType.JIRA_DESCRIPTION,
                source_key=f"jira:{jira_key}:description",
                source_uri=f"jira://{jira_key}#description",
                source_native_id=jira_key,
                tenant_id=tenant_id,
                title=f"{jira_key} description",
                content=description,
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authority_score=0.8,
                confidence=1.0 if live else 0.75,
                verification_state=(
                    VerificationState.VERIFIED_LIVE
                    if live
                    else VerificationState.CACHED
                ),
                currentness=CurrentnessState.CURRENT
                if live
                else CurrentnessState.VERSION_UNKNOWN,
                version_scope=version_scope,
                ownership=ownership,
                visibility=_visibility(tenant_id, customer_data=True),
                claim_keys=[f"jira:{jira_key}:description"],
                metadata={
                    "source": source,
                    "evidence_role": "ISSUE_INPUT",
                    "retrieval_pass": "jira-intake",
                },
            )
        )

    acceptance = (
        issue.get("acceptance_criteria")
        or issue.get("acceptanceCriteria")
        or issue.get("acceptance_conditions")
    )
    if acceptance not in (None, "", [], {}):
        labels = {value.casefold() for value in _values(issue.get("labels"))}
        accepted = bool({"uac_done", "accepted_uac", "uac-approved"} & labels)
        records.append(
            _record(
                source_type=EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                source_key=f"jira:{jira_key}:acceptance-criteria",
                source_uri=f"jira://{jira_key}#acceptance-criteria",
                source_native_id=jira_key,
                tenant_id=tenant_id,
                title=f"{jira_key} Jira acceptance criteria",
                content=acceptance,
                authority_class=(
                    AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT
                    if accepted
                    else AuthorityClass.PROPOSED
                ),
                authority_score=1.0 if accepted else 0.6,
                confidence=1.0 if live else 0.75,
                verification_state=(
                    VerificationState.VERIFIED_LIVE
                    if live
                    else VerificationState.CACHED
                ),
                currentness=CurrentnessState.CURRENT
                if live
                else CurrentnessState.VERSION_UNKNOWN,
                version_scope=version_scope,
                ownership=ownership,
                visibility=_visibility(tenant_id, customer_data=True),
                claim_keys=[f"jira:{jira_key}:acceptance-contract"],
                metadata={
                    "accepted_label_present": accepted,
                    "evidence_role": "REQUIREMENT_CANDIDATE",
                    "retrieval_pass": "jira-intake",
                },
            )
        )

    linked_rows = (
        issue.get("issuelinks")
        or issue.get("issue_links")
        or packet.get("linked_jiras")
        or []
    )
    records.extend(
        _record_rows(
            linked_rows,
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.LINKED_JIRA,
            prefix="linked-jira",
            authority=AuthorityClass.HISTORICAL_EXPECTATION,
            authority_score=0.55,
            confidence=0.65,
            verification=(
                VerificationState.VERIFIED_LIVE if live else VerificationState.CACHED
            ),
            currentness=CurrentnessState.VERSION_UNKNOWN,
            ownership=ownership,
            fields=("jira_key", "issue_key", "key", "id"),
        )
    )

    current_uac = packet.get("current_uac_contract")
    if not isinstance(current_uac, dict):
        current_uac = issue.get("current_uac_contract")
    if isinstance(current_uac, dict) and current_uac:
        confirmed = bool(
            current_uac.get("confirmed_ac_eligible")
            or current_uac.get("accepted_label_present")
            or current_uac.get("uac_done_present")
        )
        records.append(
            _record(
                source_type=(
                    EvidenceSourceType.ACCEPTED_UAC
                    if confirmed
                    else EvidenceSourceType.DRAFT_UAC
                ),
                source_key=f"jira:{jira_key}:uac",
                source_native_id=_text(current_uac.get("source_snapshot_id")),
                tenant_id=tenant_id,
                title=f"{jira_key} acceptance contract",
                content=current_uac,
                authority_class=(
                    AuthorityClass.CURRENT_ACCEPTED_UAC
                    if confirmed
                    else AuthorityClass.CURRENT_JIRA
                ),
                authority_score=1.0 if confirmed else 0.8,
                confidence=1.0 if live else 0.75,
                verification_state=(
                    VerificationState.VERIFIED_LIVE
                    if live
                    else VerificationState.CACHED
                ),
                currentness=CurrentnessState.CURRENT
                if live
                else CurrentnessState.UNKNOWN,
                ownership=ownership,
                visibility=_visibility(tenant_id, customer_data=True),
                claim_keys=[f"jira:{jira_key}:acceptance-contract"],
            )
        )

    comments = issue.get("comments") or packet.get("jira_comments") or []
    if isinstance(comments, dict):
        comments = comments.get("comments") or comments.get("values") or []
    for index, comment in enumerate(comments if isinstance(comments, list) else []):
        row = comment if isinstance(comment, dict) else {"body": comment}
        native_id = _text(row.get("id") or row.get("comment_id") or index)
        records.append(
            _record(
                source_type=EvidenceSourceType.JIRA_COMMENT,
                source_key=f"jira:{jira_key}:comment:{native_id}",
                source_native_id=native_id,
                tenant_id=tenant_id,
                title=f"{jira_key} comment {native_id}",
                content=row,
                authority_class=AuthorityClass.CURRENT_JIRA,
                authority_score=0.88,
                confidence=0.95 if live else 0.7,
                verification_state=(
                    VerificationState.VERIFIED_LIVE
                    if live
                    else VerificationState.CACHED
                ),
                currentness=CurrentnessState.CURRENT
                if live
                else CurrentnessState.UNKNOWN,
                ownership=ownership,
                visibility=_visibility(tenant_id, customer_data=True),
                claim_keys=_values(row.get("claim_keys")),
            )
        )

    attachments = issue.get("attachments") or packet.get("attachments") or []
    if isinstance(attachments, dict):
        attachments = attachments.get("attachments") or attachments.get("items") or []
    for index, attachment in enumerate(
        attachments if isinstance(attachments, list) else []
    ):
        row = attachment if isinstance(attachment, dict) else {"filename": attachment}
        native_id = _text(row.get("id") or row.get("attachment_id") or index)
        analyzed = bool(
            row.get("analyzed") or row.get("analysis") or row.get("excerpt")
        )
        records.append(
            _record(
                source_type=EvidenceSourceType.JIRA_ATTACHMENT,
                source_key=f"jira:{jira_key}:attachment:{native_id}",
                source_uri=_text(row.get("content") or row.get("url")),
                source_native_id=native_id,
                tenant_id=tenant_id,
                title=_text(row.get("filename") or row.get("name")),
                content=row,
                authority_class=AuthorityClass.CURRENT_JIRA,
                authority_score=0.9,
                confidence=0.95 if analyzed else 0.4,
                verification_state=(
                    VerificationState.ANALYZED
                    if analyzed
                    else VerificationState.UNVERIFIED
                ),
                currentness=CurrentnessState.CURRENT
                if live
                else CurrentnessState.UNKNOWN,
                lifecycle=(
                    LifecycleState.INSPECTED if analyzed else LifecycleState.RETRIEVED
                ),
                ownership=ownership,
                visibility=_visibility(tenant_id, customer_data=True),
                claim_keys=_values(row.get("claim_keys")),
                metadata={"analyzed": analyzed},
            )
        )
    return records


def _historical_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    history = packet.get("jira_history_searches")
    if isinstance(history, dict):
        for scope in ("same_customer", "cross_customer"):
            block = history.get(scope)
            if not isinstance(block, dict):
                continue
            for row in block.get("results") or []:
                if isinstance(row, dict):
                    result.append({**row, "history_scope": scope})
    return result


def _repository_records(
    packet: dict[str, Any], tenant_id: str, ownership: ProductOwnership
) -> list[EvidenceRecord]:
    repo = packet.get("repository_evidence")
    if not isinstance(repo, dict):
        return []
    records: list[EvidenceRecord] = []
    for index, row in enumerate(repo.get("repositories") or []):
        if not isinstance(row, dict):
            continue
        repo_id = _text(
            row.get("id") or row.get("repository") or row.get("name") or index
        )
        revision = _text(
            row.get("post_sync_sha") or row.get("head_sha") or row.get("commit_sha")
        )
        repo_owner = ProductOwnership(
            product="AEM Guides",
            product_area=ownership.product_area,
            component=ownership.component,
            repository=repo_id,
            contract_ownership=ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE,
            layer=_text(row.get("layer"))
            if _text(row.get("layer"))
            in {
                "frontend",
                "backend",
                "cross_layer",
                "automation",
                "documentation",
                "design",
                "unknown",
            }
            else "unknown",
            owner_status="confirmed" if repo_id else "unknown",
        )
        records.append(
            _record(
                source_type=EvidenceSourceType.REPOSITORY_CODE,
                source_key=f"repo:{repo_id}:{revision or 'unversioned'}",
                source_native_id=repo_id,
                tenant_id=tenant_id,
                title=f"Repository evidence: {repo_id}",
                content=row,
                authority_class=AuthorityClass.CURRENT_IMPLEMENTATION,
                authority_score=0.9,
                confidence=0.95 if revision else 0.55,
                verification_state=(
                    VerificationState.VERIFIED_REVISION
                    if revision
                    else VerificationState.UNVERIFIED
                ),
                currentness=(
                    CurrentnessState.CURRENT
                    if revision
                    else CurrentnessState.UNVERSIONED
                ),
                version_scope=VersionScope(
                    repository=repo_id,
                    repository_revision=revision,
                    branch=_text(row.get("branch")),
                    dirty=row.get("dirty")
                    if isinstance(row.get("dirty"), bool)
                    else None,
                    retrieved_at=_text(row.get("retrieved_at")),
                ),
                ownership=repo_owner,
                visibility=_visibility(
                    tenant_id, classification=VisibilityClass.INTERNAL
                ),
                claim_keys=_values(row.get("claim_keys")),
            )
        )
        automation_matches = [
            match
            for match in row.get("matches") or []
            if isinstance(match, dict)
            and any(
                token in _text(match.get("path")).casefold()
                for token in ("test", "spec", "feature", "automation")
            )
        ]
        if automation_matches:
            records.append(
                _record(
                    source_type=EvidenceSourceType.AUTOMATION,
                    source_key=f"automation:{repo_id}:{revision or 'unversioned'}",
                    tenant_id=tenant_id,
                    title=f"Automation evidence: {repo_id}",
                    content=automation_matches,
                    authority_class=AuthorityClass.VERIFIED_AUTOMATION,
                    authority_score=0.72,
                    confidence=0.9 if revision else 0.5,
                    verification_state=(
                        VerificationState.VERIFIED_REVISION
                        if revision
                        else VerificationState.UNVERIFIED
                    ),
                    currentness=(
                        CurrentnessState.CURRENT
                        if revision
                        else CurrentnessState.UNVERSIONED
                    ),
                    version_scope=VersionScope(
                        repository=repo_id,
                        repository_revision=revision,
                        dirty=row.get("dirty")
                        if isinstance(row.get("dirty"), bool)
                        else None,
                    ),
                    ownership=ProductOwnership(
                        product="AEM Guides",
                        repository=repo_id,
                        layer="automation",
                        contract_ownership=ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE,
                        owner_status="confirmed",
                    ),
                    visibility=_visibility(
                        tenant_id, classification=VisibilityClass.INTERNAL
                    ),
                )
            )
    return records


def _graph_leaf_records(
    packet: dict[str, Any], tenant_id: str, ownership: ProductOwnership
) -> list[EvidenceRecord]:
    graph = packet.get("evidence_graph")
    if not isinstance(graph, dict):
        return []
    leaves: list[dict[str, Any]] = []
    for path in graph.get("evidence_paths") or []:
        if isinstance(path, dict):
            leaves.extend(
                row for row in path.get("leaf_citations") or [] if isinstance(row, dict)
            )
    records: list[EvidenceRecord] = []
    for index, row in enumerate(leaves):
        native = _text(
            row.get("leaf_id")
            or row.get("source_hash")
            or row.get("source_record_id")
            or index
        )
        records.append(
            _record(
                source_type=EvidenceSourceType.EVIDENCE_GRAPH_LEAF,
                source_key=f"graph-leaf:{native}",
                source_uri=_text(row.get("source_ref")),
                source_native_id=native,
                tenant_id=tenant_id,
                title=_text(row.get("title") or row.get("source_type")),
                content=row,
                authority_class=AuthorityClass.MODEL_INFERENCE,
                authority_score=0.1,
                confidence=float(row.get("confidence") or 0.5),
                verification_state=VerificationState.VERIFIED_SOURCE,
                currentness=CurrentnessState.UNKNOWN,
                directness=EvidenceDirectness.DERIVED,
                ownership=ownership,
                visibility=_visibility(
                    tenant_id, classification=VisibilityClass.INTERNAL
                ),
                claim_keys=_values(row.get("claim_keys")),
                metadata={"graph_path_is_not_authority": True},
            )
        )
    return records


GitHubImplementationResultVerifier = Callable[
    [GitHubImplementationVerificationResult, str], bool
]


def _github_implementation_verification_records(
    value: Any,
    tenant_id: str,
    *,
    result_verifier: GitHubImplementationResultVerifier,
) -> tuple[list[EvidenceRecord], int]:
    """Normalize results only after a non-serializable trust callback approves."""

    value = value or []
    if isinstance(value, dict):
        rows = value.get("results") or value.get("items") or [value]
    else:
        rows = value
    if not isinstance(rows, list):
        return [], 1
    records: list[EvidenceRecord] = []
    invalid_count = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid_count += 1
            continue
        try:
            result = GitHubImplementationVerificationResult.model_validate(
                row
            )
        except Exception:
            # Provider/transport evidence is optional.  Malformed results are
            # exposed as unavailable and cannot make generation fail or attest
            # implementation truth.
            invalid_count += 1
            continue
        try:
            trusted = result_verifier(result, tenant_id)
        except Exception:
            trusted = False
        if trusted is not True:
            invalid_count += 1
            continue
        terminal = result.status in {
            GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
            GitHubImplementationVerificationStatus.UNRELATED_PATH,
        }
        context = result.verified_context
        records.append(
            _record(
                source_type=EvidenceSourceType.IMPLEMENTATION_DIFF,
                authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
                source_key=f"github-mcp:{result.result_id}",
                source_uri=(result.source_references[0] if result.source_references else ""),
                source_native_id=result.result_id,
                tenant_id=tenant_id,
                title="GitHub MCP implementation verification result",
                content=result.model_dump(mode="json", by_alias=True),
                authority_class=AuthorityClass.IMPLEMENTATION_CONFIRMED,
                authority_score=1.0 if terminal else 0.8,
                confidence=1.0 if terminal else 0.0,
                verification_state=(
                    VerificationState.VERIFIED_REVISION
                    if terminal
                    else VerificationState.VERIFIED_SOURCE
                ),
                currentness=(
                    CurrentnessState.VERSION_SPECIFIC
                    if context.product_versions or context.deployment_modes
                    else CurrentnessState.CURRENT
                ),
                version_scope=VersionScope(
                    product_versions=context.product_versions,
                    deployment_model=(
                        context.deployment_modes[0]
                        if len(context.deployment_modes) == 1
                        else ""
                    ),
                    repository_revision=result.primary_repository_revision,
                ),
                ownership=ProductOwnership(
                    product="AEM Guides",
                    contract_ownership=(
                        ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE
                    ),
                    owner_status="confirmed" if terminal else "unknown",
                ),
                visibility=_visibility(
                    tenant_id, classification=VisibilityClass.INTERNAL
                ),
                claim_keys=[
                    f"github-implementation:{result.question_id}:{result.handoff_id}"
                ],
                metadata={
                    "github_mcp_result": True,
                    "retrieval_pass": "github-mcp-implementation-verification",
                    "evidence_role": "IMPLEMENTATION_APPLICABILITY_VERIFICATION",
                    "acceptance_authority": False,
                },
            )
        )
    return records, invalid_count


def normalize_trusted_github_implementation_results(
    results: Any,
    *,
    tenant_id: str,
    result_verifier: GitHubImplementationResultVerifier,
) -> CanonicalEvidenceBundle:
    """Build evidence from results delivered by an authenticated GitHub adapter.

    The callable is deliberately not representable in a Jira/manifest packet.
    Raw packet fields therefore cannot self-attest implementation truth.
    """

    if not callable(result_verifier):
        raise TypeError("a trusted GitHub result verifier is required")
    records, invalid_count = _github_implementation_verification_records(
        results,
        tenant_id,
        result_verifier=result_verifier,
    )
    return build_bundle(
        records,
        tenant_id=tenant_id,
        unavailable_sources=(
            ["GITHUB_MCP_IMPLEMENTATION_VERIFICATION_REJECTED"]
            if invalid_count
            else []
        ),
    )


def normalize_legacy_packet(
    packet: dict[str, Any], *, tenant_id: str
) -> CanonicalEvidenceBundle:
    """Normalize the existing heterogeneous packet without changing it."""

    assert_generation_safe(packet)
    records = _jira_records(packet, tenant_id)
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    ownership = _ownership_from_issue(issue)
    special_sources = (
        (
            "product_decisions",
            EvidenceSourceType.PRODUCT_DECISION,
            AuthorityClass.CONFIRMED_PRODUCT_DECISION,
            ownership,
        ),
        (
            "engineering_decisions",
            EvidenceSourceType.ENGINEERING_DECISION,
            AuthorityClass.TECHNICALLY_INFERRED,
            ownership,
        ),
        (
            "customer_requests",
            EvidenceSourceType.CUSTOMER_REQUEST,
            AuthorityClass.CUSTOMER_REQUEST,
            ProductOwnership(
                product="AEM Guides",
                contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            ),
        ),
        (
            "customer_workflows",
            EvidenceSourceType.CUSTOMER_WORKFLOW,
            AuthorityClass.USER_EXPECTATION,
            ProductOwnership(
                product="AEM Guides",
                contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            ),
        ),
        (
            "workarounds",
            EvidenceSourceType.WORKAROUND,
            AuthorityClass.USER_EXPECTATION,
            ProductOwnership(
                product="AEM Guides",
                contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            ),
        ),
        (
            "business_impacts",
            EvidenceSourceType.BUSINESS_IMPACT,
            AuthorityClass.USER_EXPECTATION,
            ProductOwnership(
                product="AEM Guides",
                contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            ),
        ),
        (
            "scale_signals",
            EvidenceSourceType.SCALE_SIGNAL,
            AuthorityClass.USER_EXPECTATION,
            ProductOwnership(
                product="AEM Guides",
                contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            ),
        ),
        (
            "ui_observations",
            EvidenceSourceType.UI_OBSERVATION,
            AuthorityClass.TECHNICALLY_INFERRED,
            ProductOwnership(
                product="AEM Guides",
                layer="design",
                contract_ownership=ProductContractOwnership.OBSERVED_UI_STATE,
            ),
        ),
        (
            "observed_ui_flows",
            EvidenceSourceType.OBSERVED_UI_FLOW,
            AuthorityClass.TECHNICALLY_INFERRED,
            ProductOwnership(
                product="AEM Guides",
                layer="design",
                contract_ownership=ProductContractOwnership.OBSERVED_UI_STATE,
            ),
        ),
        (
            "screenshot_reproductions",
            EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            AuthorityClass.TECHNICALLY_INFERRED,
            ProductOwnership(
                product="AEM Guides",
                layer="design",
                contract_ownership=ProductContractOwnership.OBSERVED_UI_STATE,
            ),
        ),
    )
    for field, source_type, authority, source_owner in special_sources:
        records.extend(
            _record_rows(
                packet.get(field),
                tenant_id=tenant_id,
                source_type=source_type,
                prefix=field,
                authority=authority,
                authority_score=0.7,
                confidence=0.75,
                verification=VerificationState.VERIFIED_SOURCE,
                currentness=CurrentnessState.CURRENT,
                ownership=source_owner,
                fields=("id", "source_reference", "url", "path"),
            )
        )
    records.extend(
        _record_rows(
            packet.get("experience_league_evidence"),
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.OFFICIAL_DOCUMENTATION,
            prefix="doc",
            authority=AuthorityClass.OFFICIAL_DOCUMENTATION,
            authority_score=0.8,
            confidence=0.8,
            verification=VerificationState.VERIFIED_SOURCE,
            currentness=CurrentnessState.UNKNOWN,
            ownership=ProductOwnership(
                product="AEM Guides",
                layer="documentation",
                contract_ownership=ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT,
            ),
            fields=("canonical_url", "source_url", "chunk_id", "source_hash"),
            public=True,
        )
    )
    records.extend(
        _record_rows(
            packet.get("learned_behavior_evidence"),
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.OFFICIAL_DOCUMENTATION,
            prefix="learned-doc",
            authority=AuthorityClass.OFFICIAL_DOCUMENTATION,
            authority_score=0.76,
            confidence=0.7,
            verification=VerificationState.CACHED,
            currentness=CurrentnessState.UNKNOWN,
            ownership=ProductOwnership(
                product="AEM Guides",
                layer="documentation",
                contract_ownership=ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT,
            ),
            fields=("canonical_url", "source_url", "chunk_id", "source_hash"),
            public=True,
        )
    )
    records.extend(
        _record_rows(
            packet.get("aem_assets_documentation"),
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
            prefix="aem-assets-doc",
            authority=AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
            authority_score=0.8,
            confidence=0.8,
            verification=VerificationState.VERIFIED_SOURCE,
            currentness=CurrentnessState.VERSION_UNKNOWN,
            ownership=ProductOwnership(
                product="AEM Assets",
                layer="documentation",
                contract_ownership=ProductContractOwnership.AEM_ASSETS_PLATFORM_CONTRACT,
            ),
            fields=("canonical_url", "source_url", "chunk_id", "source_hash"),
            public=True,
        )
    )
    records.extend(
        _record_rows(
            packet.get("dita_spec_evidence"),
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.DITA_SPECIFICATION,
            prefix="dita-spec",
            authority=AuthorityClass.AUTHORITATIVE_SPECIFICATION,
            authority_score=0.82,
            confidence=0.82,
            verification=VerificationState.VERIFIED_SOURCE,
            currentness=CurrentnessState.UNKNOWN,
            ownership=ProductOwnership(
                product="DITA",
                layer="documentation",
                contract_ownership=ProductContractOwnership.DITA_SPECIFICATION_CONTRACT,
            ),
            fields=("canonical_url", "source_url", "chunk_id", "source_hash"),
            public=True,
        )
    )
    publishing = packet.get("publishing_transform_context")
    publishing_rows: Any = publishing
    if isinstance(publishing, dict):
        publishing_rows = (
            publishing.get("evidence")
            or publishing.get("results")
            or publishing.get("sources")
            or ([publishing] if publishing else [])
        )
    records.extend(
        _record_rows(
            publishing_rows,
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.DITA_OT,
            prefix="dita-ot",
            authority=AuthorityClass.CURRENT_IMPLEMENTATION,
            authority_score=0.78,
            confidence=0.75,
            verification=VerificationState.VERIFIED_SOURCE,
            currentness=CurrentnessState.UNKNOWN,
            ownership=ProductOwnership(
                product="DITA-OT",
                layer="backend",
                contract_ownership=ProductContractOwnership.DITA_OT_PROCESSING_BEHAVIOR,
            ),
            fields=("canonical_url", "source_url", "path", "source_hash"),
            public=True,
        )
    )
    records.extend(
        _record_rows(
            _historical_rows(packet),
            tenant_id=tenant_id,
            source_type=EvidenceSourceType.HISTORICAL_JIRA,
            prefix="historical-jira",
            authority=AuthorityClass.VERIFIED_HISTORICAL,
            authority_score=0.62,
            confidence=0.72,
            verification=VerificationState.VERIFIED_SOURCE,
            currentness=CurrentnessState.STALE,
            ownership=ownership,
            fields=(
                "jira_key",
                "issue_key",
                "source_record_id",
                "evidence_snapshot_id",
            ),
        )
    )
    records.extend(_repository_records(packet, tenant_id, ownership))
    for field, source_type, prefix in (
        (
            "implementation_diff_evidence",
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            "diff",
        ),
        ("pull_request_evidence", EvidenceSourceType.PULL_REQUEST, "pr"),
        ("design_evidence", EvidenceSourceType.DESIGN_UI, "design"),
        ("automation_evidence", EvidenceSourceType.AUTOMATION, "automation"),
    ):
        value = packet.get(field)
        if not value:
            continue
        rows = value if isinstance(value, list) else [value]
        records.extend(
            _record_rows(
                rows,
                tenant_id=tenant_id,
                source_type=source_type,
                prefix=prefix,
                authority=(
                    AuthorityClass.CURRENT_DESIGN
                    if source_type == EvidenceSourceType.DESIGN_UI
                    else AuthorityClass.VERIFIED_AUTOMATION
                    if source_type == EvidenceSourceType.AUTOMATION
                    else AuthorityClass.CURRENT_IMPLEMENTATION
                ),
                authority_score=0.85,
                confidence=0.8,
                verification=VerificationState.VERIFIED_REVISION,
                currentness=CurrentnessState.CURRENT,
                ownership=(
                    ProductOwnership(
                        product="AEM Guides",
                        layer="design",
                        contract_ownership=ProductContractOwnership.OBSERVED_UI_STATE,
                    )
                    if source_type == EvidenceSourceType.DESIGN_UI
                    else ProductOwnership(
                        product="AEM Guides",
                        contract_ownership=ProductContractOwnership.CURRENT_IMPLEMENTATION_EVIDENCE,
                    )
                ),
                fields=("id", "url", "path", "commit_sha", "revision"),
            )
        )
    records.extend(_graph_leaf_records(packet, tenant_id, ownership))
    # Serialized Jira/manifest input is not a trusted GitHub transport.  Keep
    # any supplied result trace-only and fail closed until an authenticated
    # adapter invokes normalize_trusted_github_implementation_results().
    untrusted_github_results = bool(
        packet.get("github_mcp_implementation_verification")
    )
    # Legacy planning seeds and QA preview prose are compatibility diagnostics,
    # not evidence. Feeding them back would create a second, prompt-shaped
    # reasoning path before the canonical contract and coverage gates.
    feedback_rows = packet.get("user_feedback") or packet.get("customer_feedback") or []
    if isinstance(feedback_rows, dict):
        feedback_rows = (
            feedback_rows.get("items")
            or feedback_rows.get("results")
            or [feedback_rows]
        )
    for feedback_row in feedback_rows if isinstance(feedback_rows, list) else []:
        if isinstance(feedback_row, dict):
            records.append(
                normalize_user_feedback(
                    feedback_row,
                    tenant_id=tenant_id,
                    jira_key=_text(packet.get("jira_key")),
                )
            )
    return build_bundle(
        records,
        tenant_id=tenant_id,
        issue_facts=redact_sensitive(issue),
        unavailable_sources=(
            ["GITHUB_MCP_IMPLEMENTATION_VERIFICATION_UNTRUSTED_INPUT"]
            if untrusted_github_results
            else []
        ),
    )


def normalize_codex_manifest(
    manifest: dict[str, Any], *, tenant_id: str, jira_key: str
) -> CanonicalEvidenceBundle:
    """Adapt a model-authored skill manifest after its existing gate passes."""

    assert_generation_safe(manifest)
    issue = manifest.get("issue") if isinstance(manifest.get("issue"), dict) else {}
    packet = {
        "jira_key": jira_key,
        "tenant_id": tenant_id,
        "issue": issue or {"issue_key": jira_key, "source": "codex_manifest"},
        "current_uac_contract": manifest.get("current_uac_contract") or {},
        "jira_comments": manifest.get("comments") or [],
        "attachments": manifest.get("attachments") or [],
        "experience_league_evidence": manifest.get("rag_evidence")
        or manifest.get("documentation_evidence")
        or [],
        "dita_spec_evidence": manifest.get("dita_evidence") or [],
        "publishing_transform_context": manifest.get("dita_ot_evidence") or {},
        "jira_history_searches": manifest.get("jira_history_searches") or {},
        "repository_evidence": manifest.get("repository_evidence") or {},
        "implementation_diff_evidence": manifest.get("implementation_diff_evidence")
        or {},
        "pull_request_evidence": manifest.get("pull_request_evidence") or {},
        "design_evidence": manifest.get("design_evidence") or {},
        "automation_evidence": manifest.get("automation_evidence") or {},
        "evidence_graph": manifest.get("evidence_graph") or {},
        "product_decisions": manifest.get("product_decisions") or [],
        "engineering_decisions": manifest.get("engineering_decisions") or [],
        "customer_requests": manifest.get("customer_requests") or [],
        "customer_workflows": manifest.get("customer_workflows") or [],
        "workarounds": manifest.get("workarounds") or [],
        "business_impacts": manifest.get("business_impacts") or [],
        "scale_signals": manifest.get("scale_signals") or [],
        "user_feedback": manifest.get("user_feedback") or [],
        "aem_assets_documentation": manifest.get("aem_assets_documentation") or [],
        "ui_observations": manifest.get("ui_observations") or [],
        "observed_ui_flows": manifest.get("observed_ui_flows") or [],
        "screenshot_reproductions": manifest.get("screenshot_reproductions") or [],
    }
    bundle = normalize_legacy_packet(packet, tenant_id=tenant_id)
    manifest_record = _record(
        source_type=EvidenceSourceType.CODEX_MANIFEST,
        source_key=f"codex-manifest:{jira_key}",
        tenant_id=tenant_id,
        title=f"Codex evidence manifest for {jira_key}",
        content=manifest,
        authority_class=AuthorityClass.MODEL_INFERENCE,
        authority_score=0.1,
        confidence=0.6,
        verification_state=VerificationState.VERIFIED_SOURCE,
        currentness=CurrentnessState.UNKNOWN,
        lifecycle=LifecycleState.INSPECTED,
        directness=EvidenceDirectness.DERIVED,
        visibility=_visibility(tenant_id, classification=VisibilityClass.INTERNAL),
        metadata={
            "gate_authority": "run_gates.py",
            "manifest_is_not_product_authority": True,
        },
    )
    return build_bundle(
        [*bundle.records, manifest_record],
        tenant_id=tenant_id,
        issue_facts=bundle.issue_facts,
        unavailable_sources=bundle.unavailable_sources,
    )


def normalize_benchmark_public_input(
    row: dict[str, Any], *, tenant_id: str, split: str, source_path: str = ""
) -> CanonicalEvidenceBundle:
    """Normalize a public V2 input; evaluator/private fields fail closed."""

    assert_generation_safe(row, source_path=source_path, sealed_benchmark=True)
    record_id = _text(row.get("record_id") or row.get("jira_key")).upper()
    record = _record(
        source_type=EvidenceSourceType.BENCHMARK_PUBLIC_INPUT,
        source_key=f"benchmark:v2:{split}:{record_id}",
        source_native_id=record_id,
        tenant_id=tenant_id,
        title=f"Benchmark V2 {split} public input {record_id}",
        content=row,
        authority_class=AuthorityClass.CURRENT_JIRA,
        authority_score=0.9,
        confidence=1.0,
        verification_state=VerificationState.VERIFIED_SOURCE,
        currentness=CurrentnessState.CURRENT,
        visibility=_visibility(tenant_id, classification=VisibilityClass.INTERNAL),
        claim_keys=[f"jira:{record_id}:pre-uac-input"],
        metadata={"benchmark_version": "V2", "split": split, "answers_loaded": False},
    )
    return build_bundle(
        [record], tenant_id=tenant_id, issue_facts=redact_sensitive(row)
    )


def normalize_user_feedback(
    row: dict[str, Any], *, tenant_id: str, jira_key: str
) -> EvidenceRecord:
    """Normalize feedback as a non-authoritative candidate only."""

    safe = redact_sensitive(row)
    candidate_id = _text(row.get("id") or row.get("candidate_id")) or (
        f"feedback:{stable_sha256(safe)[:24]}"
    )
    event = _text(row.get("event_type"))
    allowed = {
        "review_decision",
        "ac_edit",
        "execution_outcome",
        "escaped_defect",
    }
    raw_classes = _values(row.get("classifications") or row.get("classification"))
    classes: list[FeedbackClassification] = []
    for value in raw_classes:
        try:
            classes.append(FeedbackClassification(value.strip().upper()))
        except ValueError:
            continue
    if not classes:
        classes = [
            FeedbackClassification.USER_EXPECTATION
            if event == "ac_edit"
            else FeedbackClassification.USER_OBSERVATION
        ]
    permitted_scopes = {
        "experienced_state",
        "workflow",
        "impact",
        "scale_frequency",
    }
    candidate = UserFeedbackCandidate(
        candidate_id=candidate_id,
        classifications=classes,
        event_type=event if event in allowed else "other",  # type: ignore[arg-type]
        plan_fingerprint=_text(row.get("plan_fingerprint")),
        evidence_bundle_id=_text(
            row.get("evidence_bundle_id") or row.get("evidence_snapshot_id")
        ),
        ac_fingerprint=_text(row.get("ac_fingerprint")),
        execution_environment=_text(row.get("execution_environment")),
        escaped_defect_jira=_text(row.get("escaped_defect_jira")),
        corroborating_evidence_ids=_values(row.get("corroborating_evidence_ids")),
        promotion_state=(
            _text(row.get("promotion_state"))
            if _text(row.get("promotion_state"))
            in {"candidate", "corroborated", "rejected"}
            else "candidate"
        ),  # type: ignore[arg-type]
        automatic_authority_promotion=False,
        authoritative_for=[
            value
            for value in _values(row.get("authoritative_for"))
            if value in permitted_scopes
        ],  # type: ignore[list-item]
        intended_behavior_authority=False,
    )
    feedback_authority = (
        AuthorityClass.USER_EXPECTATION
        if candidate.authoritative_for
        else AuthorityClass.PENDING_HUMAN_REVIEW
    )
    return _record(
        source_type=EvidenceSourceType.USER_FEEDBACK,
        source_key=f"feedback:{jira_key}:{candidate_id}",
        source_native_id=candidate_id,
        tenant_id=tenant_id,
        title=f"Feedback candidate for {jira_key}",
        content=safe,
        authority_class=feedback_authority,
        authority_score=0.2,
        confidence=0.5,
        verification_state=VerificationState.UNVERIFIED,
        currentness=CurrentnessState.UNKNOWN,
        lifecycle=LifecycleState.INSPECTED,
        directness=EvidenceDirectness.DIRECT,
        ownership=ProductOwnership(
            product="AEM Guides",
            contract_ownership=ProductContractOwnership.USER_REPORTED_BEHAVIOR,
            owner_status="confirmed",
        ),
        visibility=_visibility(
            tenant_id,
            classification=VisibilityClass.RESTRICTED,
            allowed_roles=["quality_admin"],
        ),
        feedback=candidate,
        metadata={"may_change_generation_automatically": False},
    )


def resolve_authority(records: Iterable[EvidenceRecord]) -> list[AuthorityResolution]:
    """Resolve each claim independently for each authority subject.

    This intentionally allows the accepted contract and current implementation
    to disagree without either overwriting the other.  Confidence is not part
    of the ordering; it remains an independent evidence-quality axis.
    """

    raw_groups: dict[tuple[str, AuthoritySubject], list[EvidenceRecord]] = defaultdict(
        list
    )
    for record in records:
        subject = record.authority_subject or AuthoritySubject.PRODUCT_CONTRACT
        for claim_key in record.claim_keys:
            raw_groups[(claim_key, subject)].append(record)
    groups: dict[tuple[str, AuthoritySubject], list[EvidenceRecord]] = {}
    product_domains = {
        ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT,
        ProductContractOwnership.AEM_ASSETS_PLATFORM_CONTRACT,
        ProductContractOwnership.DITA_SPECIFICATION_CONTRACT,
        ProductContractOwnership.DITA_OT_PROCESSING_BEHAVIOR,
    }
    for (claim_key, subject), rows in raw_groups.items():
        if subject != AuthoritySubject.PRODUCT_CONTRACT:
            groups[(claim_key, subject)] = rows
            continue
        domains = {
            row.ownership.contract_ownership
            for row in rows
            if row.ownership.contract_ownership in product_domains
        }
        if len(domains) <= 1:
            groups[(claim_key, subject)] = rows
            continue
        for domain in sorted(domains, key=lambda value: value.value):
            groups[(f"{claim_key}@{domain.value}", subject)] = [
                row for row in rows if row.ownership.contract_ownership == domain
            ]
        cross_product = [
            row
            for row in rows
            if row.ownership.contract_ownership not in product_domains
        ]
        if cross_product:
            groups[(f"{claim_key}@UNKNOWN_CROSS_PRODUCT_DEPENDENCY", subject)] = (
                cross_product
            )
    decisions: list[AuthorityResolution] = []
    for (claim_key, subject), rows in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        rows = sorted(
            rows,
            key=lambda row: (
                _authority_rank(row, subject),
                row.verification_state.value,
                row.evidence_id,
            ),
            reverse=True,
        )
        active = [
            row
            for row in rows
            if row.currentness
            not in {CurrentnessState.STALE, CurrentnessState.SUPERSEDED}
        ]
        if not active:
            decisions.append(
                AuthorityResolution(
                    claim_key=claim_key,
                    subject=subject,
                    status=ResolutionState.STALE,
                    selected_evidence_ids=[],
                    competing_evidence_ids=[row.evidence_id for row in rows],
                    reason="Only stale or superseded evidence remains.",
                )
            )
            continue
        top_rank = _authority_rank(active[0], subject)
        top = [row for row in active if _authority_rank(row, subject) == top_rank]
        distinct = {row.content_sha256 for row in top}
        if len(distinct) > 1:
            decisions.append(
                AuthorityResolution(
                    claim_key=claim_key,
                    subject=subject,
                    status=ResolutionState.CONFLICTED,
                    selected_evidence_ids=[],
                    competing_evidence_ids=[row.evidence_id for row in top],
                    reason="Equal-authority current evidence disagrees; no claim was overwritten.",
                )
            )
            continue
        selected = top[0]
        stale_ids = [
            row.evidence_id
            for row in rows
            if row.evidence_id != selected.evidence_id
            and row.currentness in {CurrentnessState.STALE, CurrentnessState.SUPERSEDED}
        ]
        unknown_currentness = selected.currentness in {
            CurrentnessState.UNKNOWN,
            CurrentnessState.UNVERSIONED,
        }
        decisions.append(
            AuthorityResolution(
                claim_key=claim_key,
                subject=subject,
                status=(
                    ResolutionState.UNKNOWN
                    if unknown_currentness
                    else ResolutionState.SUPERSEDED
                    if stale_ids
                    else ResolutionState.RESOLVED
                ),
                selected_evidence_ids=[selected.evidence_id],
                competing_evidence_ids=[
                    row.evidence_id
                    for row in rows
                    if row.evidence_id != selected.evidence_id
                ],
                reason=(
                    "Selected evidence lacks a verifiable current revision."
                    if unknown_currentness
                    else "Current higher-authority evidence supersedes retained older evidence."
                    if stale_ids
                    else f"Selected the highest-authority current evidence for {subject.value}."
                ),
            )
        )
    return decisions


def build_bundle(
    records: Iterable[EvidenceRecord],
    *,
    tenant_id: str,
    issue_facts: dict[str, Any] | None = None,
    unavailable_sources: Iterable[str] = (),
) -> CanonicalEvidenceBundle:
    rows = list(records)
    return CanonicalEvidenceBundle(
        tenant_id=tenant_id,
        records=rows,
        issue_facts=redact_sensitive(issue_facts or {}),
        authority_resolutions=resolve_authority(rows),
        unavailable_sources=list(unavailable_sources),
    )


_LEGACY_PATH_BY_SOURCE_TYPE: dict[EvidenceSourceType, str] = {
    EvidenceSourceType.CURRENT_JIRA: "$.issue",
    EvidenceSourceType.JIRA_DESCRIPTION: "$.issue.description",
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA: "$.issue.acceptance_criteria",
    EvidenceSourceType.JIRA_COMMENT: "$.jira_comments",
    EvidenceSourceType.JIRA_ATTACHMENT: "$.attachments",
    EvidenceSourceType.LINKED_JIRA: "$.linked_jiras",
    EvidenceSourceType.ACCEPTED_UAC: "$.current_uac_contract",
    EvidenceSourceType.DRAFT_UAC: "$.current_uac_contract",
    EvidenceSourceType.PRODUCT_DECISION: "$.product_decisions",
    EvidenceSourceType.ENGINEERING_DECISION: "$.engineering_decisions",
    EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION: "$.experience_league_evidence",
    EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION: "$.aem_assets_documentation",
    EvidenceSourceType.DITA_SPECIFICATION: "$.dita_spec_evidence",
    EvidenceSourceType.DITA_OT_DOCUMENTATION: "$.publishing_transform_context",
    EvidenceSourceType.CURRENT_CODE: "$.repository_evidence",
    EvidenceSourceType.CURRENT_PR: "$.pull_request_evidence",
    EvidenceSourceType.IMPLEMENTATION_DIFF: "$.implementation_diff_evidence",
    EvidenceSourceType.CODE_DIFF: "$.implementation_diff_evidence",
    EvidenceSourceType.HISTORICAL_JIRA: "$.jira_history_searches",
    EvidenceSourceType.EXISTING_AUTOMATION: "$.automation_evidence",
    EvidenceSourceType.UI_OBSERVATION: "$.ui_observations",
    EvidenceSourceType.OBSERVED_UI_FLOW: "$.observed_ui_flows",
    EvidenceSourceType.SCREENSHOT_REPRODUCTION: "$.screenshot_reproductions",
    EvidenceSourceType.USER_FEEDBACK: "$.user_feedback",
    EvidenceSourceType.CUSTOMER_REQUEST: "$.customer_requests",
    EvidenceSourceType.CUSTOMER_WORKFLOW: "$.customer_workflows",
    EvidenceSourceType.WORKAROUND: "$.workarounds",
    EvidenceSourceType.BUSINESS_IMPACT: "$.business_impacts",
    EvidenceSourceType.SCALE_SIGNAL: "$.scale_signals",
    EvidenceSourceType.EVIDENCE_GRAPH_LEAF: "$.evidence_graph",
    EvidenceSourceType.MODEL_INFERENCE: "$.planning_seeds",
}


def build_legacy_compatibility_projection(
    packet: dict[str, Any], bundle: CanonicalEvidenceBundle
) -> LegacyCompatibilityProjection:
    """Return an unchanged packet with deterministic evidence-ID path links."""

    links: dict[str, list[str]] = defaultdict(list)
    for record in bundle.records:
        content = record.content if isinstance(record.content, dict) else {}
        legacy_path = (
            "$.github_mcp_implementation_verification"
            if content.get("SCHEMA_VERSION") == GITHUB_IMPLEMENTATION_RESULT_SCHEMA
            else _LEGACY_PATH_BY_SOURCE_TYPE.get(record.source_type)
        )
        if legacy_path:
            links[legacy_path].append(record.evidence_id)
    return LegacyCompatibilityProjection(
        legacy_payload=copy.deepcopy(packet),
        evidence_links=[
            CompatibilityProjectionLink(legacy_path=path, evidence_ids=evidence_ids)
            for path, evidence_ids in sorted(links.items())
        ],
    )


def apply_usage_lifecycle(
    bundle: CanonicalEvidenceBundle,
    *,
    used_source_types: Iterable[EvidenceSourceType] = (),
    rejected_source_types: Iterable[EvidenceSourceType] = (),
    ignored_source_types: Iterable[EvidenceSourceType] = (),
    entered_evidence_ids: Iterable[str] = (),
    rejection_reason: str = "No active consumer in the selected compatibility generator.",
) -> CanonicalEvidenceBundle:
    """Create a run-specific bundle with explicit evidence consumption states."""

    used_types = set(used_source_types)
    rejected_types = set(rejected_source_types)
    ignored_types = set(ignored_source_types)
    entered_ids = set(entered_evidence_ids)
    records: list[EvidenceRecord] = []
    for record in bundle.records:
        entered = record.evidence_id in entered_ids
        if (
            record.lifecycle_status
            in {
                LifecycleState.RETRIEVED,
                LifecycleState.AVAILABLE_NOT_INSPECTED,
                LifecycleState.UNAVAILABLE,
            }
            and not record.inspected
        ):
            records.append(
                record.model_copy(update={"entered_compatibility_input": entered})
            )
            continue
        if record.source_type in used_types:
            records.append(
                record.model_copy(
                    update={
                        "lifecycle_status": LifecycleState.USED,
                        "inspected": True,
                        "used": True,
                        "rejected_reason": "",
                        "entered_compatibility_input": entered,
                    }
                )
            )
        elif record.source_type in rejected_types:
            records.append(
                record.model_copy(
                    update={
                        "lifecycle_status": LifecycleState.REJECTED,
                        "inspected": True,
                        "used": False,
                        "rejected_reason": rejection_reason,
                        "entered_compatibility_input": entered,
                    }
                )
            )
        elif record.source_type in ignored_types:
            records.append(
                record.model_copy(
                    update={
                        "lifecycle_status": LifecycleState.IGNORED_BY_COMPATIBILITY_PATH,
                        "inspected": True,
                        "used": False,
                        "rejected_reason": rejection_reason,
                        "entered_compatibility_input": entered,
                    }
                )
            )
        else:
            records.append(
                record.model_copy(
                    update={
                        "lifecycle_status": LifecycleState.INSPECTED,
                        "inspected": True,
                        "used": False,
                        "rejected_reason": "",
                        "entered_compatibility_input": entered,
                    }
                )
            )
    return build_bundle(
        records,
        tenant_id=bundle.tenant_id,
        issue_facts=bundle.issue_facts,
        unavailable_sources=bundle.unavailable_sources,
    )


def mark_evidence_used(
    bundle: CanonicalEvidenceBundle,
    evidence_ids: Iterable[str],
) -> CanonicalEvidenceBundle:
    """Mark exact verifier-cited records USED without changing source identity."""

    consumed = {str(value).strip() for value in evidence_ids if str(value).strip()}
    available = {record.evidence_id for record in bundle.records}
    missing = sorted(consumed - available)
    if missing:
        raise ValueError("cannot consume evidence absent from the canonical bundle")
    records: list[EvidenceRecord] = []
    for record in bundle.records:
        if record.evidence_id not in consumed or record.used:
            records.append(record)
            continue
        if record.lifecycle_status != LifecycleState.INSPECTED:
            raise ValueError("only inspected evidence can transition to used")
        records.append(
            record.model_copy(
                update={
                    "lifecycle_status": LifecycleState.USED,
                    "inspected": True,
                    "used": True,
                    "rejected_reason": "",
                }
            )
        )
    return build_bundle(
        records,
        tenant_id=bundle.tenant_id,
        issue_facts=bundle.issue_facts,
        unavailable_sources=bundle.unavailable_sources,
    )


def merge_bundles(
    bundles: Iterable[CanonicalEvidenceBundle], *, tenant_id: str
) -> CanonicalEvidenceBundle:
    records: list[EvidenceRecord] = []
    issue_facts: dict[str, Any] = {}
    unavailable_sources: list[str] = []
    for bundle in bundles:
        if bundle.tenant_id != tenant_id:
            raise ValueError("cannot merge canonical bundles across tenants")
        records.extend(bundle.records)
        issue_facts.update(bundle.issue_facts)
        unavailable_sources.extend(bundle.unavailable_sources)
    return build_bundle(
        records,
        tenant_id=tenant_id,
        issue_facts=issue_facts,
        unavailable_sources=unavailable_sources,
    )


def record_visible_to(record: EvidenceRecord, principal: RuntimePrincipal) -> bool:
    visibility = record.visibility
    if visibility.classification == VisibilityClass.PUBLIC:
        return True
    if visibility.tenant_id != principal.tenant_id:
        return False
    if visibility.classification in {VisibilityClass.TENANT, VisibilityClass.INTERNAL}:
        return True
    return (
        bool(set(visibility.allowed_roles) & set(principal.roles))
        or "system" in principal.roles
    )


def visible_bundle(
    bundle: CanonicalEvidenceBundle, principal: RuntimePrincipal
) -> CanonicalEvidenceBundle:
    if bundle.tenant_id != principal.tenant_id:
        raise ValueError("principal cannot consume another tenant's evidence bundle")
    return build_bundle(
        [record for record in bundle.records if record_visible_to(record, principal)],
        tenant_id=bundle.tenant_id,
        issue_facts=bundle.issue_facts,
        unavailable_sources=bundle.unavailable_sources,
    )


def redacted_trace_payload(value: Any) -> Any:
    """Public helper used by runtime trace/artifact serialization."""

    return redact_sensitive(value)


__all__ = [
    "apply_usage_lifecycle",
    "assert_generation_safe",
    "build_bundle",
    "build_legacy_compatibility_projection",
    "merge_bundles",
    "mark_evidence_used",
    "normalize_benchmark_public_input",
    "normalize_codex_manifest",
    "normalize_legacy_packet",
    "normalize_trusted_github_implementation_results",
    "normalize_user_feedback",
    "record_visible_to",
    "redact_sensitive",
    "redacted_trace_payload",
    "resolve_authority",
    "visible_bundle",
]
