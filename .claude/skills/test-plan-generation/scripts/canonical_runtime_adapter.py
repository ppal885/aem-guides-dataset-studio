#!/usr/bin/env python3
"""Wrap hash-bound, gate-passed skill artifacts in the canonical runtime contract."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import sys
import importlib.util
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "aem-guides-gate-receipt-v1"
REQUIRED_ARTIFACTS = ("plan", "manifest", "combined", "compact", "extracted_acs")
MAX_PATTERN_RESPONSE_BYTES = 2_000_000

# ---------------------------------------------------------------------------
# C2A: read-only canonical runtime artifact projection.
#
# The canonical Python runtime is the production semantic authority.  This
# projection converts a canonical runtime result (a GenerationResult envelope
# dict or a TestPlanPipelineResult dict) into the manifest shape the Skill
# gates can replay - WITHOUT recomputing, inferring, or inventing any semantic
# content.  Fields the runtime does not carry are never synthesized: the
# block is omitted and recorded in the projection metadata as unavailable, so
# replay reports NOT_EVALUABLE instead of a fabricated PASS.
# ---------------------------------------------------------------------------

PROJECTION_ADAPTER_VERSION = "aem-guides-runtime-projection-v1"
UNAVAILABLE_FROM_RUNTIME = "UNAVAILABLE_FROM_RUNTIME"

# Runtime coverage dispositions that map EXACTLY onto C1 coverage classes.
# Everything else is left unmapped (recorded as lossy) - names that merely
# sound similar are never translated.
_COVERAGE_CLASS_MAP = {
    "ACCEPTANCE_CONTRACT": "ACCEPTANCE",
    "PROPOSED_ACCEPTANCE_CONTRACT": "ACCEPTANCE",
    "SEMANTIC_REGRESSION": "QE_REGRESSION",
    "STRUCTURAL_REGRESSION": "QE_REGRESSION",
    "REFERENCE_REGRESSION": "QE_REGRESSION",
    "CROSS_MODE_REGRESSION": "QE_REGRESSION",
    "IMPLEMENTATION_ORACLE": "INVESTIGATION",
    "TECHNICAL_NOTE": "INVESTIGATION",
}


def _runtime_payload(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Accept a pipeline-result dict or a canonical envelope dict and return
    (output_payload, trace, canonical_result_meta)."""

    if not isinstance(result, dict):
        return {}, {}, {}
    canonical = (result.get("qe_review_package") or {}).get("canonical_result") or {}
    if canonical:
        return (
            dict(canonical.get("output_payload") or {}),
            dict(canonical.get("trace") or {}),
            {
                "run_id": canonical.get("run_id", ""),
                "status": canonical.get("status", ""),
                "runtime_id": canonical.get("runtime_id", ""),
                "runtime_version": canonical.get("runtime_version", ""),
                "validation_status": canonical.get("validation_status", ""),
            },
        )
    return (
        dict(result.get("output_payload") or {}),
        dict(result.get("trace") or {}),
        {
            "run_id": result.get("run_id", ""),
            "status": result.get("status", ""),
            "runtime_id": result.get("runtime_id", ""),
            "runtime_version": result.get("runtime_version", ""),
            "validation_status": result.get("validation_status", ""),
        },
    )


def project_runtime_result(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project a canonical runtime result into a gate-manifest projection.

    Returns (manifest, projection_metadata).  Read-only: the input is never
    mutated, and no missing semantic artifact is ever fabricated.
    """

    payload, trace, info = _runtime_payload(result)
    manifest: dict[str, Any] = {}
    projected: list[str] = []
    unavailable: list[str] = []
    lossy: list[str] = []
    derived: list[str] = []
    warnings: list[str] = []

    # Research routing: runtime records carry the same contract fields.
    # Materiality lives on the requirement record - join by requirement_id;
    # never assume it.
    research_records = payload.get("question_research") or []
    requirement_by_id = {
        row.get("requirement_id"): row
        for row in (payload.get("research_requirements") or [])
    }
    if research_records:
        items = []
        for row in research_records:
            requirement = requirement_by_id.get(row.get("requirement_id")) or {}
            item = {
                "question_ref": row.get("question_id"),
                "research_requirement": row.get("research_requirement"),
                "research_status": row.get("research_status"),
                "research_requests": list(row.get("research_request_ids") or []),
                "research_evidence_ids": list(row.get("evidence_ids") or []),
                "reason": row.get("reason", ""),
            }
            if "material" in requirement:
                item["material"] = bool(requirement["material"])
            else:
                lossy.append("question_research.material")
            items.append(item)
        manifest["question_research"] = {"items": items}
        projected.append("question_research")
    else:
        unavailable.append("question_research")

    # Missing questions: identity/state preserved for cross-reference checks.
    questions = payload.get("missing_questions") or []
    if questions:
        manifest["missing_questions"] = [
            {
                "question_id": row.get("question_id"),
                "question_ref": row.get("question_id"),
                "question": row.get("question_text") or row.get("question"),
                "blocking": bool(row.get("blocking")),
                "open_question_class": row.get("open_question_class"),
                "question_revision": row.get("question_revision"),
            }
            for row in questions
        ]
        projected.append("missing_questions")
    # The runtime does not carry the Q1 planner contract (category,
    # why_material, triggering evidence, acceptance impact, budget).
    unavailable.append("question_plan")
    unavailable.append("question_resolutions")

    # Existing-vs-new behavior classification: same field names, rebound target.
    classifications = payload.get("behavior_classifications") or []
    if classifications:
        manifest["behavior_classification"] = {
            "items": [
                {
                    "target_ref": row.get("disposition_id"),
                    "behavior_class": row.get("behavior_class"),
                    "existing_evidence_ids": list(row.get("existing_evidence_ids") or []),
                    "requested_evidence_ids": list(row.get("requested_evidence_ids") or []),
                    "change_evidence_ids": list(row.get("change_evidence_ids") or []),
                    "rationale": row.get("rationale", ""),
                }
                for row in classifications
            ]
        }
        projected.append("behavior_classification")
    else:
        unavailable.append("behavior_classification")

    # Coverage: C2B-C1 canonical coverage decisions project losslessly when
    # the new fields exist; legacy artifacts keep honest UNAVAILABLE markers.
    dispositions = payload.get("coverage_dispositions") or []
    sufficiency_present = bool(payload.get("sufficiency"))
    if dispositions:
        claim_coverage_refs = {
            ref
            for record in (payload.get("sufficiency") or [])
            for ref in (record.get("coverage_refs") or [])
        }
        research_by_question = {
            row.get("question_id"): row
            for row in (payload.get("question_research") or [])
        }
        any_priority = any(row.get("priority") for row in dispositions)
        items = []
        for row in dispositions:
            if sufficiency_present and row.get("disposition_id") not in claim_coverage_refs:
                # C2B-S1: when the canonical sufficiency artifact exists, the
                # projected coverage surface is exactly the acceptance-relevant
                # claims the artifact speaks for; other dispositions remain in
                # _runtime for audit and are never given invented assessments.
                continue
            question_ids = list(row.get("source_question_ids") or [])
            items.append(
                {
                    "coverage_id": row.get("disposition_id"),
                    "behavior": row.get("candidate"),
                    "question_ids": question_ids,
                    "evidence_ids": list(row.get("evidence_ids") or []),
                    "research_ids": sorted(
                        {
                            research_by_question[q]["research_id"]
                            for q in question_ids
                            if q in research_by_question
                            and research_by_question[q].get("research_id")
                        }
                    ),
                    "coverage_class": (
                        row.get("coverage_class")
                        or _COVERAGE_CLASS_MAP.get(
                            row.get("disposition"), UNAVAILABLE_FROM_RUNTIME
                        )
                    ),
                    "priority": row.get("priority") or UNAVAILABLE_FROM_RUNTIME,
                    "contract_type": row.get("contract_type")
                    or UNAVAILABLE_FROM_RUNTIME,
                    "surface": row.get("surface", ""),
                    "state_or_transition": row.get("state_or_transition", ""),
                    "configuration": row.get("configuration", ""),
                    "applicability": row.get("applicability", ""),
                    "variants": [
                        {"label": str(v), "evidence_ids": []}
                        for v in (row.get("variants") or [])
                    ],
                    "reason": row.get("rationale", ""),
                    "acceptance_impact": row.get("acceptance_impact", ""),
                    "sufficiency_ref": row.get("sufficiency_ref", ""),
                    "dimensions_considered": [],
                }
            )
        manifest["coverage_decisions"] = {"items": items}
        projected.append("coverage_decisions")
        if not any_priority:
            lossy.append("coverage_decisions.priority")
        if sufficiency_present:
            lossy.append("coverage_decisions.non_claim_dispositions")
    else:
        unavailable.append("coverage_decisions")

    # Human clarifications (P1) project losslessly from the trace.
    clarifications = trace.get("human_clarifications") or []
    if clarifications:
        manifest["human_clarifications"] = clarifications
        projected.append("human_clarifications")

    # C2B-S1: the canonical claim-sufficiency artifact projects losslessly.
    # Legacy artifacts without it stay NOT_EVALUABLE - never reinterpreted.
    sufficiency = payload.get("sufficiency") or []
    if sufficiency:
        _establishing = {
            "ACCEPTED_PRODUCT_REQUIREMENT",
            "CONFIRMED_PRODUCT_DECISION",
            "OFFICIAL_PRODUCT_CONTRACT",
            "SPECIFICATION_AUTHORITY",
            "CUSTOMER_REQUEST",
            "IMPLEMENTATION_CONFIRMED",
            "HUMAN_CLARIFICATION",
        }

        def _q_status(record: dict[str, Any]) -> dict[str, Any]:
            return {
                "question_ref": None,  # set by caller
                "sufficiency_status": record.get("status"),
                "decision_reason": record.get("decision_reason", ""),
                "authority_status": (
                    "ESTABLISHING"
                    if record.get("authority_basis") in _establishing
                    else "NON_ESTABLISHING"
                ),
                "research_completion": record.get("research_completion")
                or "NOT_REQUIRED",
                "applicability_status": record.get("applicability", "UNCLEAR"),
                "currentness_status": record.get("currentness", "UNKNOWN"),
                "contradiction_status": (
                    "CONFLICTING" if record.get("contradictions") else "NONE"
                ),
                "supported_claims": (
                    [record["claim_text"]]
                    if record.get("status") == "SUFFICIENT" and record.get("claim_text")
                    else [record["established_portion"]]
                    if record.get("status") == "PARTIAL"
                    and record.get("established_portion")
                    else []
                ),
                "unsupported_claims": list(record.get("limitations") or []),
                "limitations": list(record.get("limitations") or []),
                "evidence_ids": list(record.get("evidence_refs") or []),
                "research_ids": list(record.get("research_refs") or []),
            }

        _rank = {"CONFLICTED": 3, "INSUFFICIENT": 2, "PARTIAL": 1, "SUFFICIENT": 0}

        # One question assessment per question (worst status across claims).
        by_question: dict[str, list[dict[str, Any]]] = {}
        for record in sufficiency:
            for question_ref in record.get("question_refs") or []:
                by_question.setdefault(question_ref, []).append(record)
        question_assessments = []
        for question_ref in sorted(by_question):
            rows = by_question[question_ref]
            worst = max(rows, key=lambda row: _rank.get(row.get("status"), 0))
            merged = _q_status(worst)
            merged["question_ref"] = question_ref
            merged["evidence_ids"] = sorted(
                {ev for row in rows for ev in (row.get("evidence_refs") or [])}
            )
            merged["research_ids"] = sorted(
                {r for row in rows for r in (row.get("research_refs") or [])}
            )
            portions = [
                row["established_portion"]
                for row in rows
                if row.get("status") == "PARTIAL" and row.get("established_portion")
            ]
            if worst.get("status") == "PARTIAL" and portions:
                merged["supported_claims"] = sorted(set(portions))
            question_assessments.append(merged)

        # One coverage assessment per coverage ref (worst status across claims).
        by_coverage: dict[str, list[dict[str, Any]]] = {}
        for record in sufficiency:
            for coverage_ref in record.get("coverage_refs") or []:
                by_coverage.setdefault(coverage_ref, []).append(record)
        coverage_assessments = []
        coverage_by_id = {
            row.get("coverage_id"): row
            for row in (manifest.get("coverage_decisions") or {}).get("items", [])
        }
        for coverage_ref in sorted(by_coverage):
            rows = by_coverage[coverage_ref]
            worst = max(rows, key=lambda row: _rank.get(row.get("status"), 0))
            coverage = coverage_by_id.get(coverage_ref) or {}
            coverage_assessments.append(
                {
                    "coverage_ref": coverage_ref,
                    "sufficiency_status": worst.get("status"),
                    "sufficiency_reason": worst.get("decision_reason", ""),
                    "established_portion": worst.get("established_portion", ""),
                    "question_refs": sorted(coverage.get("question_ids") or []),
                    "evidence_ids": sorted(coverage.get("evidence_ids") or []),
                    "research_ids": sorted(coverage.get("research_ids") or []),
                }
            )

        manifest["evidence_sufficiency"] = {
            "question_assessments": question_assessments,
            "coverage_assessments": coverage_assessments,
            # Claim-level rows carry the exact canonical decision per promoted
            # candidate; the Skill gate validates the assessment lists above,
            # and replay promotion checks bind here.
            "claim_assessments": [
                {
                    "claim_ref": record.get("claim_ref"),
                    "sufficiency_status": record.get("status"),
                    "sufficiency_id": record.get("sufficiency_id"),
                    "decision_reason": record.get("decision_reason", ""),
                    "established_portion": record.get("established_portion", ""),
                    "evidence_ids": list(record.get("evidence_refs") or []),
                    "research_ids": list(record.get("research_refs") or []),
                }
                for record in sufficiency
            ],
        }
        projected.append("evidence_sufficiency")
    else:
        unavailable.append("evidence_sufficiency")

    # Gate verdicts + promotion state are replay inputs, not gate manifests.
    manifest["_runtime"] = {
        "gate_decisions": payload.get("gate_decisions") or [],
        "promotion_decisions": payload.get("promotion_decisions") or [],
        "acceptance_candidates": payload.get("acceptance_candidates") or [],
        "candidate_lifecycle": payload.get("candidate_lifecycle") or [],
        "coverage_dispositions_all": payload.get("coverage_dispositions") or [],
        "stage_trace": [row.get("stage") for row in trace.get("stage_trace") or []],
        "status": info.get("status", ""),
        "validation_status": info.get("validation_status", ""),
    }
    projected.append("_runtime")

    # Writer handoff (derived from canonical coverage state - never
    # fabricated): exactly the accepted (non-EXCLUDED) coverage decisions,
    # which includes every P0 decision by construction.  The canonical
    # promotion gate remains the authority on which ACCEPTANCE-class rows
    # become ACs; the handoff is the coverage package, not the AC set.
    if manifest.get("coverage_decisions"):
        handoff = sorted(
            row["coverage_id"]
            for row in manifest["coverage_decisions"]["items"]
            if row.get("priority") != "EXCLUDED"
        )
        manifest["coverage_decisions"]["writer_handoff"] = handoff
        derived.append("coverage_decisions.writer_handoff")

    # Blocks the runtime does not produce at all - replay must report
    # NOT_EVALUABLE, never a fabricated PASS.
    unavailable.extend(
        [
            "doc_research",
            "coverage_equivalence",
            "requirement_lineage",
            "historical_jira_assessment",
            "retrieval_requests",
            "retrieval_results",
        ]
    )

    metadata = {
        "runtime_schema_version": info.get("runtime_version", ""),
        "adapter_version": PROJECTION_ADAPTER_VERSION,
        "runtime_revision": info.get("run_id", ""),
        "projected_fields": sorted(projected),
        "unavailable_fields": sorted(set(unavailable)),
        "lossy_fields": sorted(set(lossy)),
        "derived_fields": sorted(set(derived)),
        "warnings": warnings,
    }
    manifest["_projection"] = metadata
    return manifest, metadata


class _NoPatternRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a shared-learning Bearer token through a redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _remote_base_url(value: object) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    if parsed.path not in {"", "/"}:
        return ""
    if parsed.scheme == "http" and not _private_http_allowed(parsed.hostname):
        return ""
    return raw


def _private_http_allowed(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and address.is_loopback:
        return True
    return os.environ.get("AEM_STUDIO_ALLOW_INSECURE_HTTP", "").casefold() in {
        "1", "true", "yes",
    }


def _remote_timeout(value: object) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 15.0
    return timeout if 0 < timeout <= 60 else 15.0


class RemoteApprovedPatternResolver:
    """Keep local TRAIN baseline and import only VM-governed shared learning.

    The VM derives actor/tenant authorization from the Bearer credential.  Client
    manifests cannot supply credentials or elevate the server's learning mode.
    """

    def __init__(
        self,
        *,
        baseline_resolver: Any,
        response_model: Any,
        envelope_model: Any,
        mode_enum: Any,
        tenant_id: str,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        opener: Any | None = None,
    ) -> None:
        self._baseline = baseline_resolver
        self._response_model = response_model
        self._envelope_model = envelope_model
        self._mode = mode_enum
        self._tenant_id = str(tenant_id or "kone").strip() or "kone"
        self._base_url = _remote_base_url(
            base_url if base_url is not None else os.environ.get("AEM_STUDIO_URL", "")
        )
        self._token = str(
            token if token is not None else os.environ.get("AEM_STUDIO_TOKEN", "")
        ).strip()
        self._timeout = _remote_timeout(
            timeout if timeout is not None else os.environ.get("AEM_STUDIO_TIMEOUT_SECONDS", "15")
        )
        self._opener = opener or urllib.request.build_opener(_NoPatternRedirect())

    @staticmethod
    def _attach(baseline: Any, envelope: Any) -> Any:
        copier = getattr(baseline, "model_copy", None)
        if callable(copier):
            return copier(update={"shared_learning": envelope})
        baseline.shared_learning = envelope
        return baseline

    def _disabled(self, baseline: Any) -> Any:
        return self._attach(
            baseline,
            self._envelope_model(
                mode=self._mode.DISABLED,
                status="DISABLED",
                warnings=["Shared Human learning disabled by the local client."],
            ),
        )

    def _unavailable(self, baseline: Any, error_code: str) -> Any:
        return self._attach(
            baseline,
            self._envelope_model(
                mode=self._mode.SHADOW,
                status="UNAVAILABLE",
                pattern_count=0,
                matched_patterns=[],
                suppressed_patterns=[],
                shadow_pattern_ids=[],
                shadow_suppressed_pattern_ids=[],
                authoring_guidance=[],
                shadow_authoring_guidance_ids=[],
                warnings=[
                    "Shared Human learning unavailable; the existing approved TRAIN baseline was retained."
                ],
                error_code=error_code,
            ),
        )

    def _shadow_clamp(self, envelope: Any) -> Any:
        """Reduce an enabled server envelope to trace-only shadow information."""

        if getattr(envelope, "mode", None) != self._mode.ENABLED:
            return envelope

        def unique(values: list[str]) -> list[str]:
            return list(dict.fromkeys(value for value in values if value))

        matched_ids = [
            str(getattr(getattr(row, "pattern", None), "pattern_id", ""))
            for row in (getattr(envelope, "matched_patterns", None) or [])
        ]
        suppressed_ids = [
            str(getattr(row, "pattern_id", ""))
            for row in (getattr(envelope, "suppressed_patterns", None) or [])
        ]
        guidance_ids = [
            str(getattr(row, "lesson_id", ""))
            for row in (getattr(envelope, "authoring_guidance", None) or [])
        ]
        return self._envelope_model(
            mode=self._mode.SHADOW,
            status=envelope.status,
            publication_id=getattr(envelope, "publication_id", None),
            pattern_count=int(getattr(envelope, "pattern_count", 0) or 0),
            matched_patterns=[],
            suppressed_patterns=[],
            shadow_pattern_ids=unique([
                *(getattr(envelope, "shadow_pattern_ids", None) or []), *matched_ids
            ]),
            shadow_suppressed_pattern_ids=unique([
                *(getattr(envelope, "shadow_suppressed_pattern_ids", None) or []),
                *suppressed_ids,
            ]),
            authoring_guidance=[],
            shadow_authoring_guidance_ids=unique([
                *(getattr(envelope, "shadow_authoring_guidance_ids", None) or []),
                *guidance_ids,
            ]),
            excluded_pattern_counts=dict(
                getattr(envelope, "excluded_pattern_counts", None) or {}
            ),
            warnings=[
                *(getattr(envelope, "warnings", None) or []),
                "Shared Human learning was reduced to SHADOW by the local client ceiling.",
            ],
            error_code=getattr(envelope, "error_code", None),
        )

    def _fetch(self, request: Any, context: Any | None) -> Any:
        payload = request.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 1_000_000:
            raise ValueError("pattern request too large")

        tenant_id = str(getattr(context, "tenant_id", "") or self._tenant_id).strip()
        query_items: list[tuple[str, str]] = [("tenant_id", tenant_id)]
        cutoff = getattr(context, "cutoff_at", None)
        if cutoff is not None:
            query_items.append(("cutoff_at", cutoff.isoformat()))
        for case_id in sorted(getattr(context, "excluded_source_case_ids", None) or []):
            query_items.append(("excluded_source_case_ids", str(case_id)))
        url = (
            f"{self._base_url}/api/v1/mcp/resolve-qe-patterns?"
            + urllib.parse.urlencode(query_items)
        )
        http_request = urllib.request.Request(
            url,
            data=encoded,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "aem-guides-canonical-adapter/1",
            },
            method="POST",
        )
        response = self._opener.open(http_request, timeout=self._timeout)
        with response:
            raw = response.read(MAX_PATTERN_RESPONSE_BYTES + 1)
        if len(raw) > MAX_PATTERN_RESPONSE_BYTES:
            raise ValueError("pattern response too large")
        decoded = json.loads(raw.decode("utf-8"))
        return self._response_model.model_validate(decoded)

    def resolve(self, request: Any) -> Any:
        # Legacy callers have no server-owned tenant/exclusion context.  Keep them on
        # the approved local TRAIN baseline and make the absence of shared influence
        # explicit instead of performing an under-scoped remote lookup.
        return self._disabled(self._baseline.resolve(request))

    def resolve_for_runtime(self, request: Any, context: Any | None) -> Any:
        # Calling resolve() without the contextual API intentionally keeps shared
        # state out of the existing TRAIN resolver.
        baseline = self._baseline.resolve(request)
        client_mode = os.environ.get("SHARED_UAC_LEARNING_MODE", "SHADOW").strip().upper()
        context_mode = getattr(context, "mode", None)
        if (
            client_mode == "DISABLED"
            or context_mode == self._mode.DISABLED
            or bool(getattr(context, "benchmark_isolation", False))
        ):
            return self._disabled(baseline)
        if not self._base_url:
            return self._unavailable(baseline, "SHARED_LEARNING_URL_NOT_CONFIGURED")
        if not self._token or self._token == "dev-bypass" or any(
            character in self._token for character in "\r\n"
        ):
            return self._unavailable(baseline, "SHARED_LEARNING_PERSONAL_TOKEN_REQUIRED")
        try:
            remote = self._fetch(request, context)
            envelope = remote.shared_learning
            if envelope is None:
                return self._unavailable(baseline, "SHARED_LEARNING_ENVELOPE_MISSING")
            context_mode_value = str(
                getattr(getattr(context, "mode", None), "value", getattr(context, "mode", ""))
            ).upper()
            if client_mode != "ENABLED" or (
                context_mode_value and context_mode_value != "ENABLED"
            ):
                envelope = self._shadow_clamp(envelope)
            # Deliberately discard the remote TRAIN result.  Only the independently
            # validated shared publication crosses this boundary, so a VM baseline
            # drift cannot replace the local approved TRAIN corpus.
            return self._attach(baseline, envelope)
        except urllib.error.HTTPError as exc:
            return self._unavailable(baseline, f"SHARED_LEARNING_HTTP_{exc.code}")
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            AttributeError,
        ):
            return self._unavailable(baseline, "SHARED_LEARNING_REMOTE_UNAVAILABLE")


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


skill_fingerprint_mod = _load(
    "skill_bundle_fingerprint_for_adapter", "skill_bundle_fingerprint.py"
)


def _repository_root(explicit: str | None = None) -> Path:
    for direct in (explicit, os.environ.get("AEM_STUDIO_REPO")):
        if direct:
            candidate = Path(direct).expanduser().resolve()
            if (candidate / "backend" / "app").is_dir():
                return candidate
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / "backend" / "app").is_dir():
                return parent
    raise RuntimeError(
        "Cannot locate the Dataset Studio repository containing backend/app; "
        "pass --repo-root or set AEM_STUDIO_REPO"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_path(receipt_file: Path, raw_path: object) -> Path:
    path = Path(str(raw_path or ""))
    if not path.is_absolute():
        path = receipt_file.parent / path
    return path.resolve()


def verify_receipt(
    receipt_file: Path,
    *,
    jira_key: str,
    plan_path: Path,
    manifest_path: Path,
    skill_root: Path | None = None,
) -> dict:
    receipt_file = receipt_file.resolve()
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError(f"receipt schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("passed") is not True or receipt.get("postable") is not True:
        raise ValueError("receipt must record passed=true and postable=true")
    if str(receipt.get("issue", "")).upper() != jira_key.upper():
        raise ValueError("receipt issue does not match --jira-key")

    executing_skill_root = (
        skill_root.resolve()
        if skill_root is not None
        else Path(__file__).resolve().parent.parent
    )
    skill_fingerprint_mod.verify(
        receipt.get("validator"), expected_root=executing_skill_root
    )

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("receipt artifacts must be an object")
    resolved: dict[str, Path] = {}
    for name in REQUIRED_ARTIFACTS:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise ValueError(f"receipt is missing artifacts.{name}")
        path = _receipt_path(receipt_file, record.get("path"))
        expected = str(record.get("sha256", "")).lower()
        if not path.is_file():
            raise ValueError(f"receipt artifact does not exist: {path}")
        if not expected or _sha256(path) != expected:
            raise ValueError(f"receipt hash mismatch for artifacts.{name}")
        resolved[name] = path

    if resolved["plan"] != plan_path.resolve():
        raise ValueError("receipt plan path does not match --plan")
    if resolved["manifest"] != manifest_path.resolve():
        raise ValueError("receipt manifest path does not match --manifest")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jira-key", required=False)
    parser.add_argument("--tenant-id", default="kone")
    parser.add_argument("--manifest", type=Path, required=False)
    parser.add_argument("--plan", type=Path, required=False)
    parser.add_argument("--receipt", type=Path, required=False)
    parser.add_argument("--claude-question-submission", type=Path)
    parser.add_argument("--out", type=Path, required=False)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--project-result",
        type=Path,
        default=None,
        help="C2A: project a saved canonical runtime result (GenerationResult or "
        "pipeline result JSON) into a read-only gate-manifest projection and "
        "write it to --out. No semantic content is recomputed or invented.",
    )
    args = parser.parse_args()

    if args.project_result is not None:
        if args.out is None:
            print("ERROR: --project-result requires --out", file=sys.stderr)
            return 2
        try:
            result = json.loads(args.project_result.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read runtime result: {exc}", file=sys.stderr)
            return 2
        manifest, metadata = project_runtime_result(result)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(args.out)
        print(
            "projection: "
            f"{len(metadata['projected_fields'])} projected, "
            f"{len(metadata['unavailable_fields'])} unavailable, "
            f"{len(metadata['lossy_fields'])} lossy"
        )
        return 0

    missing = [
        name
        for name in ("jira_key", "manifest", "plan", "receipt", "out")
        if getattr(args, name) is None
    ]
    if missing:
        print(
            "ERROR: missing required arguments: " + ", ".join(f"--{m}" for m in missing),
            file=sys.stderr,
        )
        return 2

    try:
        verify_receipt(
            args.receipt,
            jira_key=args.jira_key,
            plan_path=args.plan,
            manifest_path=args.manifest,
        )
        root = _repository_root(args.repo_root)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: canonical runtime adaptation refused: {exc}", file=sys.stderr)
        return 2

    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.core.schemas_canonical_test_plan_runtime import (  # noqa: PLC0415
        ClaudeMissingQuestionSubmission,
        GenerationProfile,
        RuntimeEntryPoint,
    )
    from app.core.schemas_qe_pattern_mcp import (  # noqa: PLC0415
        ResolveQePatternsResponse,
        SharedLearningEnvelope,
        SharedLearningMode,
    )
    from app.services.canonical_test_plan_runtime import (  # noqa: PLC0415
        CanonicalTestPlanRuntime,
    )
    from app.services.qe_pattern_mcp_service import QePatternResolver  # noqa: PLC0415

    canonical_runtime = CanonicalTestPlanRuntime(
        pattern_resolver=RemoteApprovedPatternResolver(
            baseline_resolver=QePatternResolver(),
            response_model=ResolveQePatternsResponse,
            envelope_model=SharedLearningEnvelope,
            mode_enum=SharedLearningMode,
            tenant_id=args.tenant_id,
        )
    )

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan_markdown = args.plan.read_text(encoding="utf-8")
    claude_question_submission = None
    if args.claude_question_submission is not None:
        try:
            if args.claude_question_submission.stat().st_size > 2_000_000:
                raise ValueError("Claude question submission exceeds 2 MB")
            claude_question_submission = (
                ClaudeMissingQuestionSubmission.model_validate_json(
                    args.claude_question_submission.read_text(encoding="utf-8")
                )
            )
        except (OSError, ValueError) as exc:
            print(
                f"ERROR: invalid Claude question submission: {exc}",
                file=sys.stderr,
            )
            return 2
    request = canonical_runtime.build_request(
        jira_key=args.jira_key,
        tenant_id=args.tenant_id,
        entry_point=RuntimeEntryPoint.CODEX_SKILL,
        generation_profile=GenerationProfile.CODEX_CANONICAL,
    )
    result = canonical_runtime.adapt_codex_artifacts(
        request=request,
        manifest=manifest,
        plan_markdown=plan_markdown,
        gate_status="passed",
        claude_question_submission=claude_question_submission,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.out)
    return 0 if result.status in {"completed", "needs_human_review"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
