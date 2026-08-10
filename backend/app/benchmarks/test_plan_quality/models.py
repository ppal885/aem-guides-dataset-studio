from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CANONICAL_COMPONENTS = (
    "Editor",
    "Authoring",
    "Publishing",
    "Platform",
    "Schematron",
    "Integration",
)
JIRA_KEY_RE = re.compile(r"^(?!AC-\d+$)[A-Z][A-Z0-9]+-\d+$")

PerformanceDecision = Literal["required", "conditional", "not_required"]
VersionApplicability = Literal["same_release", "different_release", "unknown"]
GoldenStatus = Literal["seeded", "approved"]
VerificationMethod = Literal[
    "jira_mcp",
    "rag_retrieval",
    "direct_url",
    "repo_read",
    "attachment_read",
    "figma_mcp",
    "log_read",
    "pasted_input",
]


class BenchmarkThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_case_count: int = Field(default=18, ge=1)
    minimum_cases_per_component: int = Field(default=3, ge=1)
    minimum_case_pass_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_gate_pass_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_ac_contract_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_history_precision_at_5: float = Field(default=1.0, ge=0, le=1)
    minimum_history_recall_at_5: float = Field(default=0.75, ge=0, le=1)
    minimum_retrieval_recall_at_10: float = Field(default=0.75, ge=0, le=1)
    minimum_citation_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_performance_decision_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_history_version_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_fingerprint_integrity_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_hallucination_free_rate: float = Field(default=1.0, ge=0, le=1)


class GoldenReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GoldenStatus = "seeded"
    reviewed_by: str = ""
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_approval(self) -> "GoldenReview":
        if self.status == "approved" and not (self.reviewed_by.strip() and self.reviewed_at):
            raise ValueError("approved case goldens require reviewed_by and reviewed_at")
        return self


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    jira_key: str
    component: Literal[
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ]
    customer: str = ""
    query: str
    lifecycle_stage: Literal[
        "Pre-Development UAC",
        "Implementation Review",
        "Post-Fix Validation",
    ] = "Post-Fix Validation"
    expected_history_keys: list[str] = Field(default_factory=list)
    expected_history_versions: dict[str, VersionApplicability] = Field(default_factory=dict)
    expect_no_strong_history: bool = False
    expected_performance_decision: PerformanceDecision
    required_query_terms: list[str] = Field(default_factory=list)
    source_basis: list[str] = Field(default_factory=list, min_length=2)
    review: GoldenReview = Field(default_factory=GoldenReview)

    @model_validator(mode="after")
    def validate_ground_truth(self) -> "GoldenCase":
        self.jira_key = self.jira_key.strip().upper()
        self.expected_history_keys = list(
            dict.fromkeys(key.strip().upper() for key in self.expected_history_keys)
        )
        if not JIRA_KEY_RE.fullmatch(self.jira_key):
            raise ValueError(f"invalid Jira key: {self.jira_key}")
        invalid = [key for key in self.expected_history_keys if not JIRA_KEY_RE.fullmatch(key)]
        if invalid:
            raise ValueError(f"invalid expected Jira keys: {', '.join(invalid)}")
        if self.jira_key in self.expected_history_keys:
            raise ValueError("a case cannot list itself as historical evidence")
        if self.expect_no_strong_history == bool(self.expected_history_keys):
            raise ValueError(
                "exactly one of expected_history_keys or expect_no_strong_history=true is required"
            )
        normalized_versions = {
            key.strip().upper(): value
            for key, value in self.expected_history_versions.items()
        }
        if not normalized_versions and self.expected_history_keys:
            normalized_versions = {key: "unknown" for key in self.expected_history_keys}
        if set(normalized_versions) != set(self.expected_history_keys):
            raise ValueError(
                "expected_history_versions must contain exactly the expected_history_keys"
            )
        self.expected_history_versions = normalized_versions
        if not self.query.strip():
            raise ValueError("query must not be empty")
        self.required_query_terms = list(
            dict.fromkeys(term.strip() for term in self.required_query_terms if term.strip())
        )
        if not self.required_query_terms:
            raise ValueError("required_query_terms must preserve the case's mechanism")
        self.source_basis = [basis.strip() for basis in self.source_basis if basis.strip()]
        if len(self.source_basis) < 2:
            raise ValueError(
                "source_basis must separately explain history and performance goldens"
            )
        return self


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-golden-v1"] = (
        "aem-guides-test-plan-golden-v1"
    )
    benchmark_id: str
    golden_status: GoldenStatus = "seeded"
    approved_by: str = ""
    approved_at: datetime | None = None
    thresholds: BenchmarkThresholds = Field(default_factory=BenchmarkThresholds)
    cases: list[GoldenCase]

    @model_validator(mode="after")
    def validate_suite(self) -> "BenchmarkManifest":
        ids = [case.id for case in self.cases]
        keys = [case.jira_key for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case IDs must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("benchmark Jira keys must be unique")
        if len(self.cases) != self.thresholds.required_case_count:
            raise ValueError(
                f"expected {self.thresholds.required_case_count} cases, found {len(self.cases)}"
            )
        coverage = self.component_coverage()
        missing = [
            component
            for component in CANONICAL_COMPONENTS
            if coverage.get(component, 0) < self.thresholds.minimum_cases_per_component
        ]
        if missing:
            raise ValueError(
                "insufficient canonical component coverage: " + ", ".join(missing)
            )
        decisions = {case.expected_performance_decision for case in self.cases}
        if decisions != {"required", "conditional", "not_required"}:
            raise ValueError(
                "the benchmark must cover required, conditional, and not_required performance decisions"
            )
        if self.golden_status == "approved" and not (self.approved_by and self.approved_at):
            raise ValueError("approved goldens require approved_by and approved_at")
        if self.golden_status == "approved":
            unreviewed = [case.id for case in self.cases if case.review.status != "approved"]
            if unreviewed:
                raise ValueError(
                    "approved manifest requires per-case approval: " + ", ".join(unreviewed)
                )
        return self

    @classmethod
    def load_yaml(cls, path: Path) -> "BenchmarkManifest":
        import yaml

        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def component_coverage(self) -> dict[str, int]:
        return {
            component: sum(1 for case in self.cases if case.component == component)
            for component in CANONICAL_COMPONENTS
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RetrievedJira(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_key: str
    rank: int = Field(ge=1)
    source_ref: str = ""
    mechanism_qualified: Literal[True]
    version_applicability: VersionApplicability

    @model_validator(mode="after")
    def normalize_key(self) -> "RetrievedJira":
        self.jira_key = self.jira_key.strip().upper()
        if not JIRA_KEY_RE.fullmatch(self.jira_key):
            raise ValueError(f"invalid retrieved Jira key: {self.jira_key}")
        return self


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["same_customer", "cross_customer"]
    query: str
    component: Literal[
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ]
    customer: str = ""
    hard_version_filter_applied: Literal[False]
    results: list[RetrievedJira] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_query(self) -> "RetrievalQuery":
        if not self.query.strip():
            raise ValueError("retrieval query must not be empty")
        keys = [result.jira_key for result in self.results]
        ranks = [result.rank for result in self.results]
        if len(keys) != len(set(keys)):
            raise ValueError("retrieval results must not repeat a Jira key")
        if len(ranks) != len(set(ranks)):
            raise ValueError("retrieval result ranks must be unique within a query")
        if self.scope == "cross_customer" and self.customer.strip():
            raise ValueError("cross_customer retrieval must not set customer")
        return self


class RetrievalArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-retrieval-v2"] = (
        "aem-guides-test-plan-retrieval-v2"
    )
    tool: Literal["search_jira_history"]
    indexed_history_run: Literal[True]
    issue: str
    queries: list[RetrievalQuery]

    @model_validator(mode="after")
    def validate_retrieval(self) -> "RetrievalArtifact":
        self.issue = self.issue.strip().upper()
        if not JIRA_KEY_RE.fullmatch(self.issue):
            raise ValueError(f"invalid retrieval issue: {self.issue}")
        if len(self.queries) != 2:
            raise ValueError("retrieval artifact requires exactly two queries")
        scopes = [query.scope for query in self.queries]
        if sorted(scopes) != ["cross_customer", "same_customer"]:
            raise ValueError("retrieval artifact requires one query per scope")
        return self


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal[
        "jira",
        "url",
        "dita",
        "code",
        "attachment",
        "figma",
        "log",
    ]
    source_ref: str
    trust_tier: Literal[
        "authoritative",
        "historical_verified",
        "supporting",
        "candidate",
    ]
    verification_method: VerificationMethod
    source_hash: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> "EvidenceSource":
        self.source_id = self.source_id.strip()
        self.source_ref = self.source_ref.strip()
        if not self.source_id or not self.source_ref:
            raise ValueError("evidence source_id and source_ref must not be empty")
        if self.source_hash and not re.fullmatch(r"sha256:[0-9a-f]{64}", self.source_hash):
            raise ValueError("source_hash must use sha256:<64 lowercase hex characters>")
        return self


class EvidenceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-evidence-catalog-v1"] = (
        "aem-guides-test-plan-evidence-catalog-v1"
    )
    issue: str
    sources: list[EvidenceSource]

    @model_validator(mode="after")
    def validate_catalog(self) -> "EvidenceCatalog":
        self.issue = self.issue.strip().upper()
        if not JIRA_KEY_RE.fullmatch(self.issue):
            raise ValueError(f"invalid evidence catalog issue: {self.issue}")
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence catalog source_id values must be unique")
        return self


class BenchmarkRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-benchmark-run-v1"]
    benchmark_id: str
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_ref: str
    skill_variant: Literal["codex", "claude"]
    created_at: datetime
    goldens_disclosed_to_candidate: Literal[False]


class BenchmarkCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-benchmark-case-input-v1"]
    case_id: str
    jira_key: str
    component: Literal[
        "Editor",
        "Authoring",
        "Publishing",
        "Platform",
        "Schematron",
        "Integration",
    ]
    customer: str = ""
    query: str
    lifecycle_stage: Literal[
        "Pre-Development UAC",
        "Implementation Review",
        "Post-Fix Validation",
    ]


class BenchmarkArtifactFingerprints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-artifact-fingerprints-v1"] = (
        "aem-guides-test-plan-artifact-fingerprints-v1"
    )
    case_id: str
    evidence_snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CaseMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_complete: bool = False
    gate_pass: bool = False
    ac_contract: bool = False
    history_precision_at_5: float = 0.0
    history_recall_at_5: float = 0.0
    retrieval_recall_at_10: float = 0.0
    citation_accuracy: float = 0.0
    performance_decision_accuracy: bool = False
    history_version_accuracy: bool = False
    fingerprint_integrity: bool = False
    hallucination_free: bool = False


class CaseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    jira_key: str
    component: str
    passed: bool
    metrics: CaseMetrics
    selected_history_keys: list[str] = Field(default_factory=list)
    retrieved_history_keys: list[str] = Field(default_factory=list)
    actual_performance_decision: str = ""
    actual_history_versions: dict[str, str] = Field(default_factory=dict)
    evidence_snapshot_id: str = ""
    plan_fingerprint: str = ""
    ac_count: int = 0
    unknown_ac_citations: list[str] = Field(default_factory=list)
    unverified_evidence_sources: list[str] = Field(default_factory=list)
    unverified_jira_keys: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SuiteReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-test-plan-benchmark-report-v1"] = (
        "aem-guides-test-plan-benchmark-report-v1"
    )
    benchmark_id: str
    manifest_fingerprint: str
    golden_status: GoldenStatus
    release_eligible: bool
    candidate_ref: str
    run_root: str
    case_reports: list[CaseReport]
    aggregates: dict[str, Any]
    threshold_failures: list[str] = Field(default_factory=list)
    baseline_failures: list[str] = Field(default_factory=list)
    skill_self_tests_passed: bool = False
    passed: bool = False
