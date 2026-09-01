"""Single mandatory gate for a test plan.

One command, one green/red result. It exists so a partial run cannot pass by
simply not invoking a check: the evidence manifest is REQUIRED, and the manifest
plus the combined plan+appendix are audited together.

It runs, in order:
  1. Manifest presence + completeness, including the five-source availability
     preflight and separate tool evidence for ask_dita_expert product-documentation
     probes, search_jira_history queries, evidence-graph provenance, and the
     internal principal-performance-QA assessment, plus hash-bound source
     requirement fidelity whenever enumerated requirements are active.
  2. Structural validation of the eleven-section bullet-only body
     (validate_test_plan.py).
  3. Deterministic rendering of the concise four-section chat/UI projection
     (render_compact_view.py).
  4. Performance manifest-to-plan alignment: required decisions produce only
     quantified Performance ACs; conditional/not-required decisions do not.
  5. Evidence audit of the combined plan+appendix deliverable and the manifest
     (verify_evidence.py): source paths on disk, cited line numbers in range,
     attachments downloaded + attested, >=3 RAG probes when behaviour matters,
     and fenced code evidence present when anything is Covered / Partially covered.
  6. The script self-tests (protect the gates from silent regression).

Usage:
  python scripts/run_gates.py --plan <body.md> --combined <plan+appendix.md> --manifest <manifest.json>

Exit 0 only when everything passes; any failure prints FAIL lines and exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


CANONICAL_JIRA_COMPONENTS = {
    "Editor",
    "Authoring",
    "Publishing",
    "Platform",
    "Schematron",
    "Integration",
}


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
compact_mod = _load("render_compact_view", "render_compact_view.py")
extract_mod = _load("extract_acs", "extract_acs.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")
graph_manifest_mod = _load("evidence_graph_manifest", "evidence_graph_manifest.py")
performance_mod = _load("performance_contract", "performance_contract.py")
# Reasoning pipeline modules (BehaviorModel -> Hypotheses -> Retrieval -> Verify -> Gate -> Integration).
explorer_mod = _load("semantic_relationship_explorer", "semantic_relationship_explorer.py")
audit_mod = _load("anti_hardcoding_audit", "anti_hardcoding_audit.py")
behavior_mod = _load("behavior_model", "behavior_model.py")
coverage_mod = _load("coverage_hypotheses", "coverage_hypotheses.py")
mq_mod = _load("missing_questions", "missing_questions.py")
verifier_mod = _load("hypothesis_verifier", "hypothesis_verifier.py")
coverage_gate_mod = _load("coverage_gate", "coverage_gate.py")
integration_mod = _load("uac_integration", "uac_integration.py")
disposition_mod = _load("disposition_classifier", "disposition_classifier.py")
oracle_mod = _load("test_oracle_builder", "test_oracle_builder.py")
state_compat_mod = _load("state_compatibility_explorer", "state_compatibility_explorer.py")
cross_surface_mod = _load("cross_surface_resolver", "cross_surface_resolver.py")
struct_equiv_mod = _load("structural_equivalence_verifier", "structural_equivalence_verifier.py")
scenario_reducer_mod = _load("scenario_reducer", "scenario_reducer.py")
authority_mod = _load("evidence_authority_resolver", "evidence_authority_resolver.py")
change_impact_mod = _load("change_impact_explorer", "change_impact_explorer.py")
critic_mod = _load("pre_uac_critic", "pre_uac_critic.py")
impl_grounding_mod = _load("implementation_grounding", "implementation_grounding.py")
cap_elig_mod = _load("capability_eligibility_explorer", "capability_eligibility_explorer.py")
scope_conflict_mod = _load("scope_conflict_resolver", "scope_conflict_resolver.py")
affected_surface_mod = _load("affected_surface_explorer", "affected_surface_explorer.py")
comment_claim_mod = _load("comment_claim_verifier", "comment_claim_verifier.py")
pr_supersession_mod = _load("pr_supersession_check", "pr_supersession_check.py")
concurrency_race_mod = _load("concurrency_race_explorer", "concurrency_race_explorer.py")
enumerated_coverage_mod = _load("enumerated_coverage", "enumerated_coverage.py")
source_requirement_fidelity_mod = _load(
    "source_requirement_fidelity", "source_requirement_fidelity.py"
)
ac_readability_mod = _load("ac_readability", "ac_readability.py")
operational_contract_mod = _load("operational_contract", "operational_contract.py")
feature_class_mod = _load("feature_class_registry", "feature_class_registry.py")
relationship_traversal_mod = _load(
    "relationship_traversal", "relationship_traversal.py"
)
relationship_role_provisioning_mod = _load(
    "relationship_role_provisioning", "role_provisioning.py"
)
relationship_ui_surface_scope_mod = _load(
    "relationship_ui_surface_scope", "ui_surface_scope.py"
)
skill_fingerprint_mod = _load("skill_bundle_fingerprint", "skill_bundle_fingerprint.py")
fluffyjaws_evidence_mod = _load("fluffyjaws_evidence", "fluffyjaws_evidence.py")
temporal_evidence_mod = _load("temporal_evidence", "temporal_evidence.py")
evidence_conflict_resolver_mod = _load("evidence_conflict_resolver", "evidence_conflict_resolver.py")
scope_applicability_mod = _load("scope_applicability", "scope_applicability.py")
ac_language_policy_mod = _load("ac_language_policy", "ac_language_policy.py")
publishing_scope_coverage_mod = _load("publishing_scope_coverage", "publishing_scope_coverage.py")
repro_dimension_matrix_mod = _load("repro_dimension_matrix", "repro_dimension_matrix.py")
acceptance_synthesizer_mod = _load("acceptance_synthesizer", "acceptance_synthesizer.py")
uac_linter_mod = _load("uac_linter", "uac_linter.py")
human_feedback_delta_mod = _load("human_feedback_delta", "human_feedback_delta.py")
entry_point_equivalence_mod = _load("entry_point_equivalence", "entry_point_equivalence.py")
value_provenance_coverage_mod = _load("value_provenance_coverage", "value_provenance_coverage.py")
contract_fact_mod = _load("contract_fact_extractor", "contract_fact_extractor.py")
contract_integrity_mod = _load("contract_integrity_gate", "contract_integrity_gate.py")
domain_router_mod = _load("issue_domain_router", "issue_domain_router.py")
publishing_scope_mod = _load("publishing_scope", "publishing_scope.py")
behavior_graph_mod = _load("behavior_graph", "behavior_graph.py")
semantic_closure_mod = _load("semantic_closure", "semantic_closure.py")
generated_output_mod = _load("generated_output_contract", "generated_output_contract.py")
content_identity_mod = _load("content_identity_contract", "content_identity_contract.py")
acceptance_promotion_mod = _load("acceptance_promotion", "acceptance_promotion.py")
behavioral_completeness_mod = _load("behavioral_completeness", "behavioral_completeness.py")

REQUIRED_MANIFEST_KEYS = (
    "schema_version",
    "issue",
    "attachments",
    "evidence_preflight",
    "rag_tool",
    "rag_probes",
    "jira_history_tool",
    "jira_history_queries",
    "indexed_history_run",
    "evidence_graph",
    "performance_assessment",
    "clones",
    "accepted_uac_present",
    "open_questions",
    "enumerated_requirements",
    "operational_contract",
)

SEMANTIC_MANIFEST_KEYS = (
    "contract_facts",
    "issue_domains",
    "behavior_model",
    "behavior_graph",
    "semantic_closure",
    "coverage_hypotheses",
    "missing_questions",
    "evidence_lifecycle",
    "verifications",
    "dispositions",
    "acceptance_promotions",
)

# These blocks did not exist in the legacy v2 reasoning pipeline. Their presence
# is therefore an unambiguous opt-in to the canonical v3 semantic pipeline even
# when a transitional producer still labels the outer manifest v2.
SEMANTIC_V3_ANCHOR_KEYS = (
    "contract_facts",
    "issue_domains",
    "behavior_graph",
    "semantic_closure",
    "acceptance_promotions",
)

PREFLIGHT_SOURCE_KEYS = (
    "product_rag",
    "jira_history",
    "live_jira",
    "git",
    "figma",
)
PREFLIGHT_STATUSES = {"available", "unavailable", "not_applicable"}
PREFLIGHT_MODES = {"full", "degraded"}
PREFLIGHT_READINESS_IMPACTS = {"none", "draft_only", "blocked"}
UAC_FIDELITY_SCHEMA = "aem-guides-uac-fidelity-v1"
LEGACY_MANIFEST_SCHEMA_VERSION = "aem-guides-evidence-manifest-v2"
MANIFEST_SCHEMA_VERSION = "aem-guides-evidence-manifest-v3"
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {
    LEGACY_MANIFEST_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
}
GATE_RECEIPT_SCHEMA_VERSION = "aem-guides-gate-receipt-v1"
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
PLAN_OQ_RE = re.compile(r"^- (OQ-\d{2}):\s+.+")
PLAN_SCENARIO_RE = re.compile(r"^- P[012]\s+\[(TS-\d{2})\]\s+\[AC-")
PREFLIGHT_SOURCE_LABELS = {
    "product_rag": ("product rag", "ask_dita_expert"),
    "jira_history": ("jira history", "search_jira_history", "indexed jira"),
    "live_jira": ("live jira",),
    "git": ("git", "github", "diff"),
    "figma": ("figma", "design"),
}


def manifest_issue_key(data: dict) -> str:
    issue = data.get("issue") if isinstance(data, dict) else None
    if isinstance(issue, str):
        return issue.strip().upper()
    if isinstance(issue, dict):
        return str(issue.get("key") or issue.get("id") or "").strip().upper()
    return ""


def check_manifest_identity(data: dict) -> list[str]:
    failures: list[str] = []
    if data.get("schema_version") not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        failures.append(
            "manifest schema_version must be one of "
            + ", ".join(sorted(SUPPORTED_MANIFEST_SCHEMA_VERSIONS))
        )
    issue_key = manifest_issue_key(data)
    if not JIRA_KEY_RE.fullmatch(issue_key):
        failures.append("manifest issue must contain a canonical Jira key such as PROJECT-12345")
    return failures


def check_open_questions(data: dict) -> list[str]:
    value = data.get("open_questions")
    if not isinstance(value, list):
        return ["manifest open_questions must be a list of stable OQ-## records"]
    failures: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        tag = f"open_questions[{index}]"
        if not isinstance(entry, dict):
            failures.append(f"{tag} must be an object with id, question, and qa_impact")
            continue
        oq_id = str(entry.get("id", "")).strip()
        if not re.fullmatch(r"OQ-\d{2}", oq_id):
            failures.append(f"{tag}.id must use stable OQ-## form")
        elif oq_id in seen:
            failures.append(f"{tag}.id duplicates {oq_id}")
        seen.add(oq_id)
        if not str(entry.get("question", "")).strip():
            failures.append(f"{tag}.question must be non-empty")
        if not str(entry.get("qa_impact", "")).strip():
            failures.append(f"{tag}.qa_impact must state what the answer changes for QA")
    ordered_ids = [
        str(entry.get("id", "")).strip()
        for entry in value
        if isinstance(entry, dict) and re.fullmatch(r"OQ-\d{2}", str(entry.get("id", "")).strip())
    ]
    expected_ids = [f"OQ-{index:02d}" for index in range(1, len(ordered_ids) + 1)]
    if ordered_ids != expected_ids:
        failures.append("manifest Open Question IDs must be contiguous and ordered starting at OQ-01")
    return failures


def _plan_open_question_ids(plan_text: str) -> set[str]:
    ids: set[str] = set()
    in_section = False
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        heading = re.fullmatch(r"\*\*(.+?)\*\*", line)
        if heading:
            in_section = heading.group(1) == "Open Questions"
            continue
        if in_section:
            match = PLAN_OQ_RE.fullmatch(line)
            if match:
                ids.add(match.group(1))
    return ids


def _plan_scenario_ids(plan_text: str) -> set[str]:
    return {
        match.group(1)
        for line in plan_text.splitlines()
        for match in [PLAN_SCENARIO_RE.match(line.strip())]
        if match
    }


def _plan_ac_records(plan_text: str) -> list[dict[str, str]]:
    criteria, _ = extract_mod.extract(plan_text)
    return criteria


def _plan_ac_text_by_id(plan_text: str) -> dict[str, str]:
    return {item["id"]: item["raw"] for item in _plan_ac_records(plan_text)}


def _plan_open_question_text_by_id(plan_text: str) -> dict[str, str]:
    questions: dict[str, str] = {}
    in_section = False
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        heading = re.fullmatch(r"\*\*(.+?)\*\*", line)
        if heading:
            in_section = heading.group(1) == "Open Questions"
            continue
        if not in_section:
            continue
        match = re.fullmatch(r"- (OQ-\d{2}):\s+(.+)", line)
        if match:
            questions[match.group(1)] = match.group(2)
    return questions


def check_open_question_alignment(data: dict, plan_text: str) -> list[str]:
    manifest_ids = set(_open_question_ids(data))
    plan_ids = _plan_open_question_ids(plan_text)
    if manifest_ids != plan_ids:
        return [
            "manifest open_questions IDs must exactly match visible plan Open Questions; "
            f"manifest={sorted(manifest_ids)}, plan={sorted(plan_ids)}"
        ]
    return []


def check_uac_plan_alignment(data: dict, plan_text: str) -> list[str]:
    criteria = _plan_ac_records(plan_text)
    actual_confirmed = {item["id"] for item in criteria if item["status"] == "Confirmed"}
    actual_proposed = {item["id"] for item in criteria if item["status"] == "Proposed"}
    accepted = data.get("accepted_uac_present")
    if accepted is False:
        failures = []
        if actual_confirmed:
            failures.append(
                "accepted_uac_present is false, so every AC must remain [Proposed]; "
                f"found Confirmed {sorted(actual_confirmed)}"
            )
        if data.get("uac_fidelity") is not None:
            failures.append("uac_fidelity must be omitted when accepted_uac_present is false")
        return failures
    if accepted is not True:
        return ["accepted_uac_present must be explicitly true or false"]

    contract = data.get("uac_fidelity")
    if not isinstance(contract, dict):
        return ["accepted_uac_present is true but uac_fidelity is missing"]
    declared_confirmed = set(contract.get("confirmed_ac_to_clause") or {})
    declared_proposed = set(contract.get("proposed_ac_ids") or [])
    failures: list[str] = []
    if actual_confirmed != declared_confirmed:
        failures.append(
            "uac_fidelity Confirmed AC IDs must exactly match plan statuses; "
            f"manifest={sorted(declared_confirmed)}, plan={sorted(actual_confirmed)}"
        )
    if actual_proposed != declared_proposed:
        failures.append(
            "uac_fidelity Proposed AC IDs must exactly match plan statuses; "
            f"manifest={sorted(declared_proposed)}, plan={sorted(actual_proposed)}"
        )
    return failures


def check_combined_binding(plan_text: str, combined_text: str) -> list[str]:
    """Require combined to be the exact body plus only the permitted appendix."""
    if combined_text == plan_text:
        return []
    body = plan_text.rstrip("\r\n")
    if not combined_text.startswith(body):
        return ["combined artifact does not begin with the exact validated plan body"]
    suffix = combined_text[len(body):]
    appendix = re.compile(
        r"^(?:\r?\n){2,}(?:#{1,2}\s+Appendix A(?:\s+-\s+Automation Evidence)?|"
        r"\*\*Appendix A(?:\s+-\s+Automation Evidence)?\*\*)(?:\r?\n|$)"
    )
    if not appendix.match(suffix):
        return [
            "combined artifact may append only an 'Appendix A - Automation Evidence' "
            "section after the exact validated body"
        ]
    return []


def check_uac_fidelity(data: dict) -> list[str]:
    if not isinstance(data.get("accepted_uac_present"), bool):
        return ["manifest 'accepted_uac_present' is required and must be a boolean"]
    contract = data.get("uac_fidelity")
    if data.get("accepted_uac_present") and contract is None:
        return ["accepted_uac_present is true but manifest 'uac_fidelity' is missing"]
    if contract is None:
        return []
    if not data.get("accepted_uac_present"):
        return ["uac_fidelity must be omitted when accepted_uac_present is false"]
    if not isinstance(contract, dict):
        return ["manifest 'uac_fidelity' must be an object"]

    failures: list[str] = []
    required = (
        "schema_version", "source_ref", "accepted_clause_ids", "out_of_scope_clause_ids",
        "clause_to_ac", "confirmed_ac_to_clause", "proposed_ac_ids", "unresolved_clause_ids",
        "contradictions", "scope_expansions", "status",
    )
    missing = [key for key in required if key not in contract]
    if missing:
        return ["uac_fidelity is missing required keys: " + ", ".join(missing)]
    if contract["schema_version"] != UAC_FIDELITY_SCHEMA:
        failures.append(f"uac_fidelity.schema_version must be {UAC_FIDELITY_SCHEMA}")
    if not isinstance(contract["source_ref"], str) or not contract["source_ref"].strip():
        failures.append("uac_fidelity.source_ref must identify the accepted UAC source")

    accepted = contract["accepted_clause_ids"]
    out_of_scope = contract["out_of_scope_clause_ids"]
    unresolved = contract["unresolved_clause_ids"]
    proposed = contract["proposed_ac_ids"]
    contradictions = contract["contradictions"]
    expansions = contract["scope_expansions"]
    list_fields = {
        "accepted_clause_ids": accepted,
        "out_of_scope_clause_ids": out_of_scope,
        "unresolved_clause_ids": unresolved,
        "proposed_ac_ids": proposed,
        "contradictions": contradictions,
        "scope_expansions": expansions,
    }
    for name, value in list_fields.items():
        if not isinstance(value, list):
            failures.append(f"uac_fidelity.{name} must be a list")
    if failures:
        return failures
    for name, values in (
        ("accepted_clause_ids", accepted),
        ("out_of_scope_clause_ids", out_of_scope),
        ("unresolved_clause_ids", unresolved),
        ("proposed_ac_ids", proposed),
    ):
        if any(not isinstance(value, str) or not value.strip() for value in values):
            failures.append(f"uac_fidelity.{name} must contain non-empty strings")
    if failures:
        return failures

    accepted_set = set(accepted)
    out_of_scope_set = set(out_of_scope)
    unresolved_set = set(unresolved)
    proposed_set = set(proposed)
    if not accepted_set or len(accepted_set) != len(accepted):
        failures.append("uac_fidelity.accepted_clause_ids must contain unique accepted clauses")
    if accepted_set & out_of_scope_set:
        failures.append("accepted and out-of-scope UAC clause IDs must not overlap")
    if not unresolved_set <= accepted_set:
        failures.append("uac_fidelity.unresolved_clause_ids contains an unknown accepted clause")
    if any(not isinstance(ac, str) or not re.fullmatch(r"AC-\d{2}", ac) for ac in proposed):
        failures.append("uac_fidelity.proposed_ac_ids must contain canonical AC-## IDs")

    clause_to_ac = contract["clause_to_ac"]
    confirmed_to_clause = contract["confirmed_ac_to_clause"]
    if not isinstance(clause_to_ac, dict) or not isinstance(confirmed_to_clause, dict):
        failures.append("uac_fidelity clause mappings must be objects")
        return failures
    if any(not isinstance(key, str) or not key for key in clause_to_ac):
        failures.append("uac_fidelity.clause_to_ac keys must be non-empty clause IDs")
    if any(not isinstance(key, str) or not key for key in confirmed_to_clause):
        failures.append("uac_fidelity.confirmed_ac_to_clause keys must be non-empty AC IDs")
    if failures:
        return failures
    unknown_clauses = set(clause_to_ac) - accepted_set
    if unknown_clauses:
        failures.append("uac_fidelity.clause_to_ac contains unknown clauses: " + ", ".join(sorted(unknown_clauses)))
    for clause_id in sorted(accepted_set - unresolved_set):
        ac_ids = clause_to_ac.get(clause_id)
        if not isinstance(ac_ids, list) or not ac_ids:
            failures.append(f"accepted clause {clause_id} has no Confirmed AC mapping")
            continue
        if any(not isinstance(ac, str) or not re.fullmatch(r"AC-\d{2}", ac) for ac in ac_ids):
            failures.append(f"accepted clause {clause_id} has a noncanonical AC mapping")

    confirmed_set = set(confirmed_to_clause)
    if confirmed_set & proposed_set:
        failures.append("an AC cannot be both Confirmed and Proposed in uac_fidelity")
    for ac_id, clause_ids in confirmed_to_clause.items():
        if not re.fullmatch(r"AC-\d{2}", str(ac_id)):
            failures.append(f"uac_fidelity has noncanonical Confirmed AC ID {ac_id}")
            continue
        if not isinstance(clause_ids, list) or not clause_ids:
            failures.append(f"Confirmed {ac_id} has no accepted UAC source clause")
            continue
        invalid = set(clause_ids) - accepted_set
        if invalid:
            failures.append(f"Confirmed {ac_id} references unknown clauses: " + ", ".join(sorted(invalid)))
        for clause_id in set(clause_ids) & accepted_set:
            if ac_id not in (clause_to_ac.get(clause_id) or []):
                failures.append(f"uac_fidelity mapping is not bidirectional for {clause_id} and {ac_id}")
    for clause_id, ac_ids in clause_to_ac.items():
        if isinstance(ac_ids, list):
            for ac_id in ac_ids:
                if ac_id not in confirmed_set:
                    failures.append(f"accepted clause {clause_id} maps to {ac_id}, but it is not declared Confirmed")

    status = contract["status"]
    if status not in ("pass", "blocked"):
        failures.append("uac_fidelity.status must be 'pass' or 'blocked'")
    if status == "blocked":
        failures.append("uac_fidelity.status is blocked; resolve accepted-UAC questions before final delivery")
    if status == "pass" and (unresolved or contradictions or expansions):
        failures.append("uac_fidelity.status cannot be pass with unresolved clauses, contradictions, or scope expansions")
    return failures
PREFLIGHT_RESTRICTION_TERMS = {
    "product_rag": ("behaviour", "behavior", "product documentation", "documented product"),
    "jira_history": ("similar", "historical", "history", "regression learning"),
    "live_jira": ("status", "resolution", "fix version", "comment", "attachment", "mutable"),
    "git": ("implementation", "changed file", "changed line", "root cause", "fix impact", "diff"),
    "figma": ("layout", "interaction", "visual", "prototype", "design behaviour", "design behavior"),
}
PREFLIGHT_CHECK_ACTIONS = (
    "call",
    "fetch",
    "query",
    "search",
    "inspect",
    "read",
    "download",
    "probe",
    "sync",
    "diff",
    "ask_dita_expert",
    "search_jira_history",
    "check_rag_status",
)
PREFLIGHT_FAILURE_MARKERS = (
    "failed",
    "failure",
    "error",
    "exception",
    "unavailable",
    "denied",
    "timeout",
    "timed out",
    "connection refused",
    "http 401",
    "http 403",
    "returned 401",
    "returned 403",
)
PREFLIGHT_CONFIGURATION_SUCCESS_MARKERS = (
    "succeed",
    "returned",
    "response received",
    "completed",
    "verified",
    "inspected",
    "fetched",
    "queried",
    "searched",
    "downloaded",
    "probe result",
    " ran",
)


def _is_timezone_aware_iso8601(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_evidence_preflight(data: dict) -> list[str]:
    failures: list[str] = []
    preflight = data.get("evidence_preflight")
    if not isinstance(preflight, dict):
        return ["evidence_preflight must be an object"]

    mode = str(preflight.get("mode", "")).strip()
    if mode not in PREFLIGHT_MODES:
        failures.append("evidence_preflight.mode must be 'full' or 'degraded'")

    if not _is_timezone_aware_iso8601(preflight.get("checked_at")):
        failures.append("evidence_preflight.checked_at must be a timezone-aware ISO-8601 timestamp")

    sources = preflight.get("sources")
    unavailable_sources: list[str] = []
    if not isinstance(sources, dict):
        failures.append("evidence_preflight.sources must be an object containing all five source checks")
        sources = {}
    source_keys = set(sources)
    missing_sources = set(PREFLIGHT_SOURCE_KEYS) - source_keys
    unexpected_sources = source_keys - set(PREFLIGHT_SOURCE_KEYS)
    if missing_sources:
        failures.append(
            "evidence_preflight.sources is missing: " + ", ".join(sorted(missing_sources))
        )
    if unexpected_sources:
        failures.append(
            "evidence_preflight.sources has unsupported keys: " + ", ".join(sorted(unexpected_sources))
        )

    for source_key in PREFLIGHT_SOURCE_KEYS:
        source = sources.get(source_key)
        if not isinstance(source, dict):
            if source_key not in missing_sources:
                failures.append(f"evidence_preflight.sources.{source_key} must be an object")
            continue
        status = str(source.get("status", "")).strip()
        checked_via = str(source.get("checked_via", "")).strip()
        reason = str(source.get("reason", "")).strip()
        if status not in PREFLIGHT_STATUSES:
            failures.append(
                f"evidence_preflight.sources.{source_key}.status must be available, unavailable, or not_applicable"
            )
        if not checked_via:
            failures.append(f"evidence_preflight.sources.{source_key}.checked_via is required")
        elif status == "available":
            checked_lower = checked_via.lower()
            if any(marker in checked_lower for marker in PREFLIGHT_FAILURE_MARKERS):
                failures.append(
                    f"evidence_preflight.sources.{source_key} cannot be available when checked_via records a failed check"
                )
            elif "configur" in checked_lower and not any(
                marker in checked_lower for marker in PREFLIGHT_CONFIGURATION_SUCCESS_MARKERS
            ):
                failures.append(
                    f"evidence_preflight.sources.{source_key}.checked_via must describe a successful call or inspection, not configuration alone"
                )
            elif not any(action in checked_lower for action in PREFLIGHT_CHECK_ACTIONS):
                failures.append(
                    f"evidence_preflight.sources.{source_key}.checked_via must describe a successful call or inspection, not configuration alone"
                )
        if status in {"unavailable", "not_applicable"} and not reason:
            failures.append(
                f"evidence_preflight.sources.{source_key}.reason is required when status is {status}"
            )
        if status == "unavailable":
            unavailable_sources.append(source_key)

    expected_mode = "degraded" if unavailable_sources else "full"
    if mode in PREFLIGHT_MODES and mode != expected_mode:
        failures.append(
            f"evidence_preflight.mode must be '{expected_mode}' for the recorded source statuses"
        )

    restrictions = preflight.get("claim_restrictions")
    if not isinstance(restrictions, list) or any(
        not isinstance(item, str) or not item.strip() for item in restrictions
    ):
        failures.append("evidence_preflight.claim_restrictions must be a list of non-empty strings")
        restrictions = []
    if mode == "degraded" and not restrictions:
        failures.append("degraded evidence_preflight requires at least one claim restriction")
    restriction_text = " ".join(restrictions).lower()
    for source_key in unavailable_sources:
        if not any(term in restriction_text for term in PREFLIGHT_RESTRICTION_TERMS[source_key]):
            failures.append(
                f"evidence_preflight.claim_restrictions must cover unavailable source '{source_key}'"
            )

    readiness_impact = str(preflight.get("readiness_impact", "")).strip()
    if readiness_impact not in PREFLIGHT_READINESS_IMPACTS:
        failures.append("evidence_preflight.readiness_impact must be none, draft_only, or blocked")
    readiness_reason = str(preflight.get("readiness_impact_reason", "")).strip()
    if readiness_impact in {"draft_only", "blocked"} and not readiness_reason:
        failures.append(
            "evidence_preflight.readiness_impact_reason is required when readiness impact is not none"
        )
    return failures


def _validate_preflight_plan_alignment(data: dict, plan_text: str) -> list[str]:
    preflight = data.get("evidence_preflight")
    if not isinstance(preflight, dict):
        return []
    mode = str(preflight.get("mode", "")).strip()
    sources = preflight.get("sources") if isinstance(preflight.get("sources"), dict) else {}
    readiness_impact = str(preflight.get("readiness_impact", "")).strip()
    boundary = next(
        (
            line.strip()
            for line in plan_text.splitlines()
            if line.strip().lower().startswith("- evidence boundary:")
        ),
        "",
    )
    if not boundary:
        return ["plan must contain an Evidence boundary bullet aligned with evidence_preflight"]
    boundary_lower = boundary.lower()
    if mode in PREFLIGHT_MODES and f"evidence mode: {mode}" not in boundary_lower:
        return [f"Evidence boundary must state 'Evidence mode: {mode}'"]

    failures: list[str] = []
    unavailable_sources = [
        key
        for key in PREFLIGHT_SOURCE_KEYS
        if isinstance(sources.get(key), dict) and sources[key].get("status") == "unavailable"
    ]
    if mode == "degraded":
        for source_key in unavailable_sources:
            if not any(label in boundary_lower for label in PREFLIGHT_SOURCE_LABELS[source_key]):
                failures.append(
                    f"degraded Evidence boundary must name unavailable source '{source_key}'"
                )
        if not any(
            marker in boundary_lower
            for marker in ("unavailable", "unverified", "not verified", "cannot", "restricted")
        ):
            failures.append(
                "degraded Evidence boundary must state what is unavailable or remains unverified"
            )

    plan_lower = plan_text.lower()
    git_unavailable = "git" in unavailable_sources
    if "lifecycle understood as: implementation review" in plan_lower and git_unavailable:
        if readiness_impact not in {"draft_only", "blocked"}:
            failures.append(
                "Implementation Review with unavailable Git evidence must have draft_only or blocked readiness impact"
            )
    if "lifecycle understood as: post-fix validation" in plan_lower and git_unavailable:
        if readiness_impact != "blocked":
            failures.append(
                "Post-Fix Validation with unavailable Git/fix evidence must have blocked readiness impact"
            )
    return failures


def _validate_dual_source_evidence(data: dict) -> list[str]:
    failures: list[str] = []
    if data.get("rag_tool") != "ask_dita_expert":
        failures.append("rag_tool must be 'ask_dita_expert'; product-documentation evidence cannot come from search_jira_history")
    if data.get("jira_history_tool") != "search_jira_history":
        failures.append("jira_history_tool must be 'search_jira_history'; Jira history cannot come from ask_dita_expert")

    probes = data.get("rag_probes")
    behaviour_matters = data.get("behaviour_matters", True)
    if not isinstance(probes, list):
        failures.append("rag_probes must be a list of ask_dita_expert questions")
    else:
        if any(not isinstance(probe, str) or not probe.strip() for probe in probes):
            failures.append("every rag_probes entry must be a non-empty ask_dita_expert question")
        if behaviour_matters and len(probes) < 3:
            failures.append("rag_probes must record at least three ask_dita_expert questions when behaviour matters")
        if not behaviour_matters and not str(data.get("behaviour_not_applicable_reason", "")).strip():
            failures.append("behaviour_matters=false requires behaviour_not_applicable_reason")

    queries = data.get("jira_history_queries")
    unavailable_reason = str(data.get("jira_history_unavailable_reason", "")).strip()
    if not isinstance(queries, list):
        failures.append("jira_history_queries must be a list of search_jira_history call records")
    elif not unavailable_reason:
        scopes: set[str] = set()
        for index, query in enumerate(queries):
            if not isinstance(query, dict):
                failures.append(f"jira_history_queries[{index}] must be an object")
                continue
            scope = str(query.get("scope", "")).strip()
            scopes.add(scope)
            if not str(query.get("query", "")).strip():
                failures.append(f"jira_history_queries[{index}] is missing query")
            component = str(query.get("component", "")).strip()
            if not component:
                failures.append(f"jira_history_queries[{index}] is missing component")
            elif component not in CANONICAL_JIRA_COMPONENTS:
                allowed = ", ".join(sorted(CANONICAL_JIRA_COMPONENTS))
                failures.append(
                    f"jira_history_queries[{index}] component must be one of: {allowed}"
                )
            if scope == "same_customer":
                if not str(query.get("customer", "")).strip() and not str(query.get("customer_unavailable_reason", "")).strip():
                    failures.append(
                        f"jira_history_queries[{index}] same_customer search requires customer or customer_unavailable_reason"
                    )
            elif scope == "cross_customer":
                if str(query.get("customer", "")).strip():
                    failures.append(f"jira_history_queries[{index}] cross_customer search must omit customer")
            else:
                failures.append(
                    f"jira_history_queries[{index}] scope must be 'same_customer' or 'cross_customer'"
                )
        if {"same_customer", "cross_customer"} - scopes:
            failures.append(
                "jira_history_queries must record both same_customer and cross_customer search_jira_history calls"
            )
        if data.get("indexed_history_run") is not True:
            failures.append("indexed_history_run must be true after search_jira_history queries run")
    else:
        if queries:
            failures.append("jira_history_unavailable_reason cannot be combined with recorded Jira-history queries")
        if not isinstance(data.get("indexed_history_run"), str) or not str(data["indexed_history_run"]).strip():
            failures.append("indexed_history_run must record the fallback reason when search_jira_history is unavailable")
    return failures


def check_manifest_completeness(path: str | None) -> list[str]:
    if not path:
        return ["evidence manifest is required but was not supplied (--manifest)"]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"evidence manifest missing or invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return ["evidence manifest must be a JSON object"]
    failures: list[str] = []
    required_keys = list(REQUIRED_MANIFEST_KEYS)
    if (
        data.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and data.get("behaviour_matters", True) is not False
    ):
        required_keys.extend(SEMANTIC_MANIFEST_KEYS)
    for key in required_keys:
        if key not in data:
            failures.append(
                f"manifest is missing required key '{key}' - every plan must declare "
                f"preflight status, both RAG tool paths, their queries, attachments, and clone state"
            )
    failures.extend(check_manifest_identity(data))
    failures.extend(check_open_questions(data))
    failures.extend(_validate_evidence_preflight(data))
    failures.extend(_validate_dual_source_evidence(data))
    failures.extend(graph_manifest_mod.validate_evidence_graph_manifest(data))
    failures.extend(performance_mod.validate_performance_assessment(data))
    clones = data.get("clones")
    if isinstance(clones, list):
        for index, entry in enumerate(clones):
            if not isinstance(entry, dict):
                failures.append(f"manifest clones[{index}] must be an object")
                continue
            ident = entry.get("path", "?")
            synced_with_sha = bool(entry.get("synced")) and bool(entry.get("sha"))
            provisional = bool(entry.get("provisional")) and bool(entry.get("note"))
            if not (synced_with_sha or provisional):
                failures.append(
                    f"clone {ident}: must be either synced with a captured sha, or provisional:true with a note "
                    f"explaining the SHA was not captured - a clone cannot be cited as current evidence unproven"
                )
    elif clones is not None:
        failures.append("manifest 'clones' must be a list")
    failures.extend(check_uac_fidelity(data))
    failures.extend(source_requirement_fidelity_mod.validate_manifest(data))
    return failures


def _load_manifest_dict(manifest_path: str | None) -> dict:
    if not manifest_path or not Path(manifest_path).is_file():
        return {}
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _open_question_ids(data: dict) -> list[str]:
    ids = []
    for oq in (data.get("open_questions") or []):
        if isinstance(oq, str):
            ids.append(oq)
        elif isinstance(oq, dict) and oq.get("id"):
            ids.append(str(oq["id"]))
    return ids


def _mapping_block(data: dict, key: str) -> dict:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _semantic_pipeline_declared(data: dict) -> bool:
    return any(key in data for key in SEMANTIC_V3_ANCHOR_KEYS)


def _text_fragments(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        result: list[str] = []
        for nested in value.values():
            result.extend(_text_fragments(nested))
        return result
    if isinstance(value, list):
        result = []
        for nested in value:
            result.extend(_text_fragments(nested))
        return result
    return []


def _contract_source_texts(data: dict) -> dict[str, str]:
    """Return canonical source text keyed by stable contract-fact source refs.

    Jira fields and attested attachment text are already part of the evidence
    manifest. External captures can be added as hash-bound
    ``contract_source_records`` records. Contract facts must quote one of these
    sources exactly; a free-form source label is not evidence binding.
    """
    result: dict[str, str] = {}
    issue = data.get("issue")
    issue_key = manifest_issue_key(data)
    if isinstance(issue, dict):
        for field, value in issue.items():
            if not isinstance(value, str) or not value:
                continue
            result[f"issue.{field}"] = value
            if issue_key:
                label = str(field).replace("_", " ")
                result[f"Jira {label} {issue_key}"] = value

    for field, label in (
        ("source_acceptance_criteria", "Jira accepted UAC"),
        ("accepted_uac", "Jira accepted UAC"),
    ):
        fragments = _text_fragments(data.get(field))
        if fragments:
            text = "\n".join(fragments)
            result[field] = text
            if issue_key:
                result[f"{label} {issue_key}"] = text

    attachments = data.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            text = next(
                (
                    attachment.get(name)
                    for name in ("raw_text", "extracted_text", "ocr_text", "text")
                    if isinstance(attachment.get(name), str) and attachment.get(name)
                ),
                None,
            )
            if text is None:
                continue
            for name in ("source_ref", "id", "name", "filename"):
                ref = attachment.get(name)
                if isinstance(ref, str) and ref.strip():
                    result[ref] = text

    records = data.get("contract_source_records")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            ref = record.get("source_ref")
            raw_text = record.get("raw_text")
            digest = record.get("sha256")
            if not isinstance(ref, str) or not ref.strip() or not isinstance(raw_text, str):
                continue
            expected = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            artifact_path_text = record.get("artifact_path")
            artifact_digest = record.get("artifact_sha256")
            if digest != expected or not isinstance(artifact_path_text, str):
                continue
            artifact_path = Path(artifact_path_text)
            if not artifact_path.is_absolute() or not artifact_path.is_file():
                continue
            try:
                artifact_bytes = artifact_path.read_bytes()
            except OSError:
                continue
            if (
                hashlib.sha256(artifact_bytes).hexdigest() == artifact_digest
                and artifact_bytes == raw_text.encode("utf-8")
            ):
                result[ref] = raw_text
    return result


def _semantic_material_ids(data: dict) -> list[str]:
    ids = []
    ids.extend(contract_fact_mod.material_fact_ids(data.get("contract_facts")))
    ids.extend(behavior_graph_mod.material_item_ids(data.get("behavior_graph")))
    ids.extend(semantic_closure_mod.material_item_ids(data.get("semantic_closure")))
    ids.extend(generated_output_mod.material_item_ids(data.get("generated_output_contract")))
    ids.extend(content_identity_mod.material_item_ids(data.get("content_identity_contract")))
    return [str(item) for item in ids if str(item).strip()]


def _semantic_provenance_ids(data: dict) -> set[str]:
    result = set(_contract_source_texts(data))
    contract_facts = _mapping_block(data, "contract_facts")
    result.update(
        str(item.get("fact_id"))
        for item in contract_facts.get("facts", []) or []
        if isinstance(item, dict) and item.get("fact_id")
    )
    for item in data.get("evidence_lifecycle", []) or []:
        if isinstance(item, dict) and item.get("evidence_id"):
            result.add(str(item["evidence_id"]))
    return result


def _semantic_candidate_ids(data: dict) -> set[str]:
    result = set(_semantic_material_ids(data))
    result.update(
        str(item.get("hypothesis_id"))
        for item in data.get("coverage_hypotheses", []) or []
        if isinstance(item, dict) and item.get("hypothesis_id")
    )
    return result


def _candidate_authorities(data: dict) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for fact in _mapping_block(data, "contract_facts").get("facts", []) or []:
        if isinstance(fact, dict) and fact.get("fact_id") and fact.get("authority"):
            result.setdefault(str(fact["fact_id"]), set()).add(str(fact["authority"]))
    for edge in _mapping_block(data, "behavior_graph").get("edges", []) or []:
        if isinstance(edge, dict) and edge.get("edge_id") and edge.get("authority"):
            result.setdefault(str(edge["edge_id"]), set()).add(str(edge["authority"]))
    for verification in data.get("verifications", []) or []:
        if not isinstance(verification, dict) or not verification.get("hypothesis_id"):
            continue
        result.setdefault(str(verification["hypothesis_id"]), set()).update(
            str(authority)
            for authority in verification.get("supporting_authorities", []) or []
            if str(authority).strip()
        )
    return result


def _candidate_subjects(data: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for fact in _mapping_block(data, "contract_facts").get("facts", []) or []:
        if isinstance(fact, dict) and fact.get("fact_id") and fact.get("subject"):
            result[str(fact["fact_id"])] = str(fact["subject"])
    for edge in _mapping_block(data, "behavior_graph").get("edges", []) or []:
        if isinstance(edge, dict) and edge.get("edge_id") and edge.get("subject"):
            result[str(edge["edge_id"])] = str(edge["subject"])
    for verification in data.get("verifications", []) or []:
        if (
            isinstance(verification, dict)
            and verification.get("hypothesis_id")
            and verification.get("subject")
        ):
            result[str(verification["hypothesis_id"])] = str(verification["subject"])
    return result


def validate_canonical_semantic_pipeline(
    data: dict,
    *,
    plan_text: str = "",
    include_plan_checks: bool = False,
) -> list[str]:
    """Validate the canonical fact -> domain -> graph -> closure -> promotion path."""
    if not isinstance(data, dict):
        return ["canonical semantic pipeline requires a manifest object"]
    if data.get("behaviour_matters", True) is False:
        return []
    if (
        data.get("schema_version") == LEGACY_MANIFEST_SCHEMA_VERSION
        and not _semantic_pipeline_declared(data)
    ):
        return []
    problems: list[str] = []
    oq_ids = set(_open_question_ids(data))
    problems.extend(
        f"[behavior-model] {problem}"
        for problem in behavior_mod.validate_behavior_model(data.get("behavior_model"))
    )
    problems.extend(
        f"[contract-facts] {problem}"
        for problem in contract_fact_mod.validate_contract_facts(
            data.get("contract_facts"),
            open_question_ids=oq_ids,
            source_texts=_contract_source_texts(data),
        )
    )
    problems.extend(
        f"[domain-router] {problem}"
        for problem in domain_router_mod.validate_issue_domains(
            data.get("issue_domains"),
            manifest=data,
            plan_text=plan_text,
            open_question_ids=oq_ids,
        )
    )
    problems.extend(
        f"[behavior-graph] {problem}"
        for problem in behavior_graph_mod.validate_behavior_graph(
            data.get("behavior_graph"),
            evidence_ids=_semantic_provenance_ids(data),
            open_question_ids=oq_ids,
        )
    )
    material_nodes = behavior_graph_mod.material_node_ids(data.get("behavior_graph"))
    domain_dimensions = domain_router_mod.required_dimensions(data.get("issue_domains"))
    problems.extend(
        f"[semantic-closure] {problem}"
        for problem in semantic_closure_mod.validate_semantic_closure(
            data.get("semantic_closure"),
            material_entity_ids=material_nodes,
            required_dimensions=domain_dimensions,
            open_question_ids=oq_ids,
        )
    )

    active_domains = set(domain_router_mod.active_domains(data.get("issue_domains")))
    if "PUBLISHING" in active_domains:
        problems.extend(
            f"[publishing-scope] {problem}"
            for problem in publishing_scope_mod.validate_publishing_scope(
                data.get("publishing_scope"), open_question_ids=oq_ids
            )
        )
    if generated_output_mod.is_present(data):
        problems.extend(
            f"[generated-output] {problem}"
            for problem in generated_output_mod.validate_generated_output_contract(
                data.get("generated_output_contract"), open_question_ids=oq_ids
            )
        )
    if "ASSETS" in active_domains or content_identity_mod.is_present(data):
        problems.extend(
            f"[content-identity] {problem}"
            for problem in content_identity_mod.validate_content_identity_contract(
                data.get("content_identity_contract"), open_question_ids=oq_ids
            )
        )

    problems.extend(
        f"[missing-questions] {problem}"
        for problem in mq_mod.validate_required_questions(data)
    )
    problems.extend(
        f"[retrieval] {problem}"
        for problem in mq_mod.check_retrieval_discipline(
            data.get("missing_questions", []),
            data.get("evidence_lifecycle", []),
            open_question_ids=oq_ids,
            hypothesis_ids={
                str(item.get("hypothesis_id"))
                for item in data.get("coverage_hypotheses", []) or []
                if isinstance(item, dict) and item.get("hypothesis_id")
            },
        )
    )
    problems.extend(
        f"[coverage] {problem}"
        for problem in coverage_mod.validate_coverage_block(data.get("coverage_hypotheses"))
    )
    problems.extend(
        f"[verification] {problem}"
        for problem in verifier_mod.verify_all(
            data.get("coverage_hypotheses"),
            data.get("verifications"),
            evidence_lifecycle=data.get("evidence_lifecycle"),
            open_question_ids=oq_ids,
        )
    )
    problems.extend(
        f"[disposition] {problem}"
        for problem in disposition_mod.validate_dispositions(data.get("dispositions"))
    )

    plan_ac_records = _plan_ac_records(plan_text) if include_plan_checks else []
    ac_ids = {item["id"] for item in plan_ac_records} if include_plan_checks else None
    ac_status_by_id = (
        {item["id"]: item["status"] for item in plan_ac_records}
        if include_plan_checks
        else None
    )
    contract_fact_block = _mapping_block(data, "contract_facts")
    fact_ids = {
        str(item.get("fact_id"))
        for item in (contract_fact_block.get("facts", []) or [])
        if isinstance(item, dict) and item.get("fact_id")
    }
    problems.extend(
        f"[acceptance-promotion] {problem}"
        for problem in acceptance_promotion_mod.validate_acceptance_promotions(
            data.get("acceptance_promotions"),
            ac_ids=ac_ids,
            known_candidate_ids=_semantic_candidate_ids(data),
            contract_fact_ids=fact_ids,
            candidate_authorities=_candidate_authorities(data),
            candidate_subjects=_candidate_subjects(data),
            dispositions=data.get("dispositions"),
            ac_status_by_id=ac_status_by_id,
            accepted_uac_present=data.get("accepted_uac_present"),
        )
    )
    if include_plan_checks:
        promotion_block = _mapping_block(data, "acceptance_promotions")
        promoted = {
            str(record.get("ac_ref"))
            for record in (promotion_block.get("records", []) or [])
            if isinstance(record, dict)
            and record.get("decision") in ("PROMOTED_CONFIRMED", "PROMOTED_PROPOSED")
        }
        if promoted != ac_ids:
            problems.append(
                "[acceptance-promotion] every visible AC must be promoted exactly by the canonical gate; "
                f"promoted={sorted(promoted)}, plan={sorted(ac_ids)}"
            )
        problems.extend(
            f"[contract-integrity] {problem}"
            for problem in contract_integrity_mod.validate_integrity(
                data.get("contract_facts"), plan_text
            )
        )

    problems.extend(
        f"[behavioral-completeness] {problem}"
        for problem in behavioral_completeness_mod.validate_behavioral_completeness(
            data,
            material_item_ids=_semantic_material_ids(data),
            required_blocks=domain_router_mod.required_blocks(data.get("issue_domains")),
        )
    )
    behavior_graph_block = _mapping_block(data, "behavior_graph")
    graph_candidates = {
        str(edge.get("hypothesis_ref"))
        for edge in behavior_graph_block.get("edges", []) or []
        if isinstance(edge, dict) and edge.get("verification_state") == "INVESTIGATION_CANDIDATE"
    }
    hypothesis_ids = {
        str(item.get("hypothesis_id"))
        for item in data.get("coverage_hypotheses", []) or []
        if isinstance(item, dict) and item.get("hypothesis_id")
    }
    if not graph_candidates <= hypothesis_ids:
        problems.append(
            "[behavior-graph] investigation-candidate edges must enter coverage_hypotheses: "
            + ", ".join(sorted(graph_candidates - hypothesis_ids))
        )
    return problems


def check_canonical_semantic_pipeline(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    if data.get("behaviour_matters", True) is False:
        return [], ["canonical semantic pipeline not required (behaviour_matters is false)"]
    if (
        data.get("schema_version") == LEGACY_MANIFEST_SCHEMA_VERSION
        and not _semantic_pipeline_declared(data)
    ):
        return [], ["canonical semantic pipeline not present in legacy v2 manifest"]
    failures = validate_canonical_semantic_pipeline(
        data, plan_text=plan_text, include_plan_checks=True
    )
    return failures, ["canonical semantic pipeline validated"] if not failures else []


def check_capability_eligibility(manifest_path: str | None, plan_text: str = "") -> tuple[list[str], list[str]]:
    """Decompose same-surface actions into per-capability eligibility predicates.
    Declared block validated fully (incl. multi-select-unknown-must-be-open-question);
    bundling capabilities under one predicate without shared evidence -> NEEDS_REVIEW;
    active-by-signal but undeclared -> REVIEW note."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    notes: list[str] = []
    if cap_elig_mod.is_present(data):
        ms = cap_elig_mod.multiselect_in_scope(data, plan_text)
        failures = [f"[capability-eligibility] {p}" for p in cap_elig_mod.validate_capability_eligibility(
            data["capability_eligibility"], open_question_ids=_open_question_ids(data), multiselect=ms)]
        for grp in cap_elig_mod.bundled_groups_without_evidence(data["capability_eligibility"]):
            notes.append(f"REVIEW capability-eligibility: capabilities [{grp}] are grouped under one predicate "
                         "without shared evidence - same surface does not imply same eligibility")
        for cap in cap_elig_mod.entrypoint_underexplored(data["capability_eligibility"], data, plan_text):
            notes.append(f"REVIEW capability-eligibility: capability [{cap}] shows responsive/multi-form signals "
                         "(direct button vs overflow menu / zoom-dependent) but fewer than two entry points are "
                         "enumerated - each render form can dispatch differently; verify all forms, not just one")
        for cap in cap_elig_mod.config_terms_missing_key(data["capability_eligibility"]):
            notes.append(f"REVIEW capability-eligibility: capability [{cap}] has a CONFIG predicate that names a "
                         "mode/behaviour but cites no actual config key (e.g. xmleditor.autocheckout) - ground the "
                         "config-driven criterion in the real OSGi key/property, not a paraphrase")
        for cap in cap_elig_mod.config_terms_missing_provenance(data["capability_eligibility"]):
            notes.append(f"REVIEW capability-eligibility: capability [{cap}] has a CONFIG key with no key_provenance "
                         "- mark it CODE/PRODUCT_DOC (verified) vs REPORTER/TICKET (unverified) and grep the exact "
                         "key against the product; a reporter-supplied key is frequently a typo/transposition")
        if not failures:
            notes.append("capability eligibility validated")
        return failures, notes
    if data.get("behaviour_matters", True) is False:
        return [], ["capability eligibility skipped (behaviour_matters is false)"]
    if cap_elig_mod.is_active(data, plan_text):
        sig = ", ".join(cap_elig_mod.detect_signals(data, plan_text)[:5])
        return [], [f"REVIEW capability-eligibility: several actions share one surface ({sig}) but no "
                    "capability_eligibility decomposition is declared - do not assume they share one eligibility rule"]
    return [], ["capability eligibility not applicable (no multi-action surface signals)"]


def check_affected_surface(manifest_path: str | None, plan_text: str = "") -> tuple[list[str], list[str]]:
    """Force ACs to cover the FULL dimension space of the grounded code surface
    (its operation enum + config keys). Declared block validated (hard fail on an
    uncovered value); active-by-signal but undeclared -> REVIEW note. This is the
    guard for the AC-09/AC-10-class omission (an operation/config value with no AC)."""
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    ac_ids = set(re.findall(r"AC-\d{2}", plan_text or ""))
    if affected_surface_mod.is_present(data):
        failures = [f"[affected-surface] {p}" for p in affected_surface_mod.validate_affected_surface(
            data["affected_surface_dimensions"], ac_ids=ac_ids, open_question_ids=_open_question_ids(data))]
        return failures, ["affected surface dimensions validated"] if not failures else []
    if data.get("behaviour_matters", True) is False:
        return [], ["affected-surface exploration skipped (behaviour_matters is false)"]
    if affected_surface_mod.is_active(data, plan_text):
        return [], ["REVIEW affected-surface: a handler/operation/config artifact is grounded but no "
                    "affected_surface_dimensions enumeration is declared - enumerate the affected surface's operation "
                    "enum and co-located config keys and map each value to a covering AC or an out-of-scope disposition"]
    return [], ["affected surface not applicable (no handler/operation/config artifact grounded)"]


def check_comment_claims(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest `comment_claims` block when present (optional, backward-
    compatible). When a Jira comment's current-behaviour claim is recorded, it must carry
    a real verification outcome (code/diff evidence, or an Open Question) - never an
    unreconciled assertion. When comment text LOOKS like a current-behaviour claim but
    nothing is recorded, this is a non-blocking REVIEW note, not a failure - the heuristic
    cannot reliably tell a stale RCA from harmless chatter."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    if comment_claim_mod.is_present(data):
        failures = [f"[comment-claims] {p}" for p in comment_claim_mod.validate_comment_claims(
            data["comment_claims"], open_question_ids=_open_question_ids(data))]
        return failures, ["comment claims validated"] if not failures else []
    hits = comment_claim_mod.likely_claims_in_comments(data)
    if hits:
        return [], [f"REVIEW comment-claims: comment text with current-behaviour phrasing was found "
                    f"({len(hits)} candidate(s)) but no comment_claims entries are recorded - verify each such "
                    f"claim against the diff/code and record VERIFIED_TRUE / VERIFIED_FALSE / STALE_SUPERSEDED / "
                    f"UNVERIFIABLE rather than repeating the comment as fact"]
    return [], ["comment claims not applicable (no current-behaviour comment phrasing detected)"]


def check_pr_supersession(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest `pr_references` block when present (optional, backward-
    compatible). Only activates a hard requirement when more than one PR/branch is
    listed: exactly one must be marked AUTHORITATIVE with a comparison_note, or every
    non-authoritative entry must be UNRESOLVED with an Open Question."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    if not pr_supersession_mod.is_present(data):
        return [], ["pr supersession not applicable (no pr_references declared)"]
    failures = [f"[pr-supersession] {p}" for p in pr_supersession_mod.validate_pr_references(
        data["pr_references"], open_question_ids=_open_question_ids(data))]
    return failures, ["pr_references reconciled"] if not failures else []


def check_concurrency_race(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    ac_ids = {item["id"] for item in _plan_ac_records(plan_text)}
    oq_ids = set(_open_question_ids(data))
    hits = concurrency_race_mod.likely_event_driven(data)
    if not concurrency_race_mod.is_present(data):
        if hits:
            return [
                "[concurrency-race] event/async signals require concurrency_race_analysis "
                "with explicit dispositions for all recurring race patterns"
            ], []
        return [], ["concurrency race analysis not applicable"]

    block = data["concurrency_race_analysis"]
    failures = concurrency_race_mod.validate_concurrency_race_analysis(
        block, ac_ids=ac_ids, open_question_ids=oq_ids
    )
    if block.get("active") is False and hits:
        failures.append(
            "concurrency_race_analysis.active cannot be false while event/async signals remain"
        )
    return [f"[concurrency-race] {problem}" for problem in failures], (
        ["concurrency race patterns dispositioned"] if not failures else []
    )


def check_feature_class_coverage(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    """Validate declared feature classes; keep heuristic detection advisory."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    ac_ids = {item["id"] for item in _plan_ac_records(plan_text)}
    failures, notes = feature_class_mod.validate_feature_classification(
        data,
        plan_text,
        ac_ids=ac_ids,
        open_question_ids=set(_open_question_ids(data)),
    )
    return [f"[feature-class] {problem}" for problem in failures], notes


def check_relationship_traversal(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    """Run the umbrella relationship gate and its role/UI cross-checks."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []

    ac_ids = {item["id"] for item in _plan_ac_records(plan_text)}
    open_question_ids = set(_open_question_ids(data))
    failures, notes = relationship_traversal_mod.check_relationship_traversal(
        data,
        ac_ids=ac_ids,
        open_question_ids=open_question_ids,
        plan_text=plan_text,
        issue_text=data.get("issue", ""),
        behavior_model=data.get("behavior_model", ""),
    )
    failures = [f"[relationship-traversal] {problem}" for problem in failures]

    block = data.get("construct_relationships")
    if not isinstance(block, dict):
        return failures, notes
    edges = block.get("edges")
    if not isinstance(edges, list):
        edges = []

    auth_edge_terms = re.compile(
        r"\b(?:access|admin|auth(?:orization)?|group|member|permission|privilege|role)\b",
        re.IGNORECASE,
    )
    auth_precondition_present = any(
        isinstance(edge, dict)
        and edge.get("relation_type") == "PRECONDITION"
        and auth_edge_terms.search(str(edge.get("neighbor", "")))
        for edge in edges
    )
    role_block = data.get("role_provisioning")
    if auth_precondition_present and not isinstance(role_block, dict):
        failures.append(
            "[relationship-role] authorization PRECONDITION edges require role_provisioning"
        )
    elif isinstance(role_block, dict):
        failures.extend(
            f"[relationship-role] {problem}"
            for problem in relationship_role_provisioning_mod.validate_precondition_edges(
                role_block,
                edges,
                ac_ids=ac_ids,
                plan_text=plan_text,
            )
        )

    # FluffyJaws supporting-discovery evidence (optional, backward-compatible).
    # Absent -> clean pass. When present, enforce the SUPPORTING_DISCOVERY
    # authority invariant and the no-direct-AC-promotion rule.
    failures.extend(
        f"[fluffyjaws] {problem}"
        for problem in fluffyjaws_evidence_mod.validate_block(data)
    )

    # Temporal / version-aware evidence (UACFIX-01, optional, backward-compatible).
    # Absent temporal metadata -> clean pass. When records opt in, enforce the
    # applicability state machine and forbid UNKNOWN/superseded evidence silently
    # grounding a current AC.
    failures.extend(
        f"[temporal-evidence] {problem}"
        for problem in temporal_evidence_mod.validate(data)
    )

    # Evidence-conflict resolver (UACFIX-02, optional, backward-compatible).
    # Absent -> clean pass. When present, enforce question-specific authority,
    # the implementation-deviation-is-a-defect rule, and no-FluffyJaws-winner.
    failures.extend(
        f"[conflict-resolver] {problem}"
        for problem in evidence_conflict_resolver_mod.validate(data)
    )

    # Scope-applicability (UACFIX-03, optional, backward-compatible). Absent -> pass.
    # Prevents name-only scope expansion; unresolved shared-path scope -> Open Question.
    failures.extend(
        f"[scope-applicability] {problem}"
        for problem in scope_applicability_mod.validate(data)
    )

    # Reproduction-dimension matrix (UACFIX-05, optional, backward-compatible).
    # Absent -> pass. Material customer-only/unresolved differences -> Open Question.
    failures.extend(
        f"[repro-matrix] {problem}"
        for problem in repro_dimension_matrix_mod.validate(data)
    )

    # Acceptance-contract synthesizer (UACFIX-06, optional, backward-compatible).
    # Absent, or no synthesis_group declared -> pass. Enforces customer-observable
    # grouping and internal->external traceability of synthesized ACs.
    failures.extend(
        f"[acceptance-synthesizer] {problem}"
        for problem in acceptance_synthesizer_mod.validate(data)
    )

    # Human-feedback delta learner (UACFIX-08, optional, backward-compatible).
    # Absent -> pass. Human-only supervision; language deltas are not discovery learning.
    failures.extend(
        f"[human-feedback-delta] {problem}"
        for problem in human_feedback_delta_mod.validate(data)
    )

    # Entry-point equivalence (UACFIX-04, optional, backward-compatible). Absent -> pass.
    # Same user intent != same implementation; shared regression needs shared-path evidence.
    failures.extend(
        f"[entry-point] {problem}"
        for problem in entry_point_equivalence_mod.validate(data)
    )

    # UAC language & readability policy (UACFIX-LANGUAGE-01, optional, backward-compatible).
    # Absent ac_synthesis -> pass. Enforces MATERIAL_CANDIDATE_LOSS=0 and language lints.
    failures.extend(
        f"[ac-language] {problem}"
        for problem in ac_language_policy_mod.validate(data)
    )

    ui_block = data.get("ui_surface_scope")
    ui_edge_present = any(
        isinstance(edge, dict)
        and edge.get("relation_type") == "CONSUMER"
        and edge.get("neighbor_kind") == "UI_SURFACE"
        for edge in edges
    )
    if ui_edge_present and not isinstance(ui_block, dict):
        failures.append(
            "[relationship-ui] UI_SURFACE CONSUMER edges require ui_surface_scope"
        )
    elif isinstance(ui_block, dict):
        ui_failures, ui_notes = (
            relationship_ui_surface_scope_mod.validate_consumer_edges(
                ui_block,
                edges,
                ac_ids=ac_ids,
                open_question_ids=open_question_ids,
                plan_text=plan_text,
            )
        )
        failures.extend(
            f"[relationship-ui] {problem}" for problem in ui_failures
        )
        notes.extend(ui_notes)

    if not failures:
        notes.append("construct relationships and cross-dimensions validated")
    return failures, notes


def check_enumerated_coverage(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    detected_count = enumerated_coverage_mod.likely_enumerated(data)
    if not enumerated_coverage_mod.is_present(data):
        return [
            "[enumerated-coverage] manifest requires a versioned enumerated_requirements "
            "block, active or explicitly inactive with a reason"
        ], []
    ac_ids = {item["id"] for item in _plan_ac_records(plan_text)}
    failures = enumerated_coverage_mod.validate_enumerated_requirements(
        data["enumerated_requirements"],
        ac_ids=ac_ids,
        open_question_ids=set(_open_question_ids(data)),
        detected_count=detected_count,
    )
    return [f"[enumerated-coverage] {problem}" for problem in failures], (
        ["reporter-enumerated requirements dispositioned"] if not failures else []
    )


def check_source_requirement_fidelity(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    """Bind every enumerated source item and semantic atom to the actual plan.

    Authority remains the job of accepted-UAC/status validation.  This check is
    mandatory whenever ``enumerated_requirements.active`` is true, including a
    Proposed-only plan with ``accepted_uac_present=false``.
    """
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    structural = source_requirement_fidelity_mod.validate_manifest(data)
    complete = source_requirement_fidelity_mod.validate_manifest(
        data,
        ac_text_by_id=_plan_ac_text_by_id(plan_text),
        open_question_text_by_id=_plan_open_question_text_by_id(plan_text),
    )
    # Manifest completeness already reports structural failures.  Keep this
    # stage focused on source-to-plan semantic loss.
    remaining = list(complete)
    for problem in structural:
        if problem in remaining:
            remaining.remove(problem)
    failures = [f"[source-fidelity] {problem}" for problem in remaining]
    required = source_requirement_fidelity_mod.is_required(data)
    notes = ["source requirement fidelity validated"] if required and not structural and not failures else []
    return failures, notes


def check_ac_readability(
    plan_text: str, manifest_path: str | None = None
) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    scope = data.get("ui_surface_scope") if isinstance(data, dict) else None
    surfaces = []
    if isinstance(scope, dict):
        for entry in scope.get("render_surfaces") or []:
            if isinstance(entry, dict) and str(entry.get("surface", "")).strip():
                surfaces.append(str(entry["surface"]).strip())
    failures, notes = ac_readability_mod.review_plan(
        plan_text, named_surfaces=surfaces
    )
    return [f"[ac-readability] {problem}" for problem in failures], notes


def check_operational_contract(
    manifest_path: str | None, plan_text: str = ""
) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    ac_ids = {item["id"] for item in _plan_ac_records(plan_text)}
    failures = operational_contract_mod.validate_manifest(
        data,
        plan_text=plan_text,
        ac_ids=ac_ids,
        open_question_ids=set(_open_question_ids(data)),
        scenario_ids=_plan_scenario_ids(plan_text),
    )
    return [f"[operational-contract] {problem}" for problem in failures], (
        ["operational incident/job contract dispositioned"] if not failures else []
    )


def check_scope_conflict(manifest_path: str | None, plan_text: str = "") -> tuple[list[str], list[str]]:
    """Reconcile reported Jira scope vs current fix scope; keep problems as separate threads.
    A material scope mismatch with no open question exposing it is a hard FAIL."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    failures = []
    notes = []
    if scope_conflict_mod.is_present(data):
        failures.extend(
            f"[scope-conflict] {problem}"
            for problem in scope_conflict_mod.validate_scope_conflict(
                data["scope_conflict"], open_question_ids=_open_question_ids(data)
            )
        )
        if not failures:
            notes.append("scope conflict reconciled")
    elif data.get("behaviour_matters", True) is False:
        notes.append("scope reconciliation skipped (behaviour_matters is false)")
    elif scope_conflict_mod.is_active(data, plan_text):
        notes.append(
            "REVIEW scope-conflict: a fix/PR is present alongside multiple reported "
            "problems but no scope_conflict reconciliation is declared - compare Jira "
            "scope vs fix scope and keep threads separate"
        )
    else:
        notes.append("scope reconciliation not applicable (no fix-vs-multi-problem signal)")

    candidates = scope_conflict_mod.implementation_scope_candidates(plan_text)
    authority_block = data.get("implementation_scope_authority")
    if isinstance(authority_block, dict):
        authority_failures = scope_conflict_mod.validate_implementation_scope_authority(
            authority_block,
            candidates=candidates,
            open_question_ids=_open_question_ids(data),
        )
        failures.extend(
            f"[scope-authority] {problem}" for problem in authority_failures
        )
        if not authority_failures:
            notes.append("implementation-only AC scope decisions validated")
    elif candidates:
        notes.append(
            "REVIEW scope-authority: implementation-only evidence found for "
            + ", ".join(item["ac_ref"] for item in candidates)
            + "; keep each AC Proposed and map it to an Open Question unless a "
            "product-authority source approves the behavior"
        )
    return failures, notes


def check_reasoning_required(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Mandatory reasoning pipeline for behavioural tickets: a behavior_model is
    required when behaviour_matters is not false, and verifications are required when
    coverage_hypotheses are declared. Pure internal code bugs opt out with
    behaviour_matters:false."""
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    if data.get("behaviour_matters", True) is False:
        return [], ["reasoning pipeline not required (behaviour_matters is false)"]
    if (
        data.get("schema_version") == LEGACY_MANIFEST_SCHEMA_VERSION
        and not _semantic_pipeline_declared(data)
    ):
        return [], ["reasoning pipeline not present in legacy v2 manifest"]
    failures = []
    for key in SEMANTIC_MANIFEST_KEYS:
        if key not in data:
            failures.append(
                f"[reasoning-required] {key} block is mandatory when behaviour_matters is true"
            )
    if coverage_mod.is_present(data) and data.get("coverage_hypotheses") and not verifier_mod.is_present(data):
        failures.append(
            "[reasoning-required] coverage_hypotheses are declared but no verifications block exists - every "
            "candidate must reach a terminal verdict before the plan is delivered"
        )
    return failures, ["reasoning pipeline requirements satisfied"] if not failures else []


def check_behavior_model(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not behavior_mod.is_present(data):
        return [], ["behavior model check skipped (no behavior_model block declared)"]
    failures = [f"[behavior-model] {p}" for p in behavior_mod.validate_behavior_model(data["behavior_model"])]
    return failures, ["behavior model validated"] if not failures else []


def check_coverage_hypotheses(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not coverage_mod.is_present(data):
        return [], ["coverage-hypotheses check skipped (no coverage_hypotheses block)"]
    failures = [f"[coverage] {p}" for p in coverage_mod.validate_coverage_block(data["coverage_hypotheses"])]
    return failures, ["coverage hypotheses validated"] if not failures else []


def check_retrieval(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not mq_mod.is_present(data):
        return [], ["retrieval-discipline check skipped (no missing_questions/evidence_lifecycle)"]
    failures = [f"[retrieval] {p}" for p in mq_mod.check_retrieval_discipline(
        data.get("missing_questions", []),
        data.get("evidence_lifecycle", []),
        open_question_ids=set(_open_question_ids(data)),
        hypothesis_ids={
            str(item.get("hypothesis_id"))
            for item in data.get("coverage_hypotheses", []) or []
            if isinstance(item, dict) and item.get("hypothesis_id")
        },
    )]
    return failures, ["retrieval discipline validated"] if not failures else []


def check_verifications(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not verifier_mod.is_present(data):
        return [], ["hypothesis-verification check skipped (no verifications block)"]
    failures = [f"[verify-hyp] {p}" for p in verifier_mod.verify_all(
        data.get("coverage_hypotheses", []),
        data.get("verifications", []),
        evidence_lifecycle=data.get("evidence_lifecycle", []),
        open_question_ids=set(_open_question_ids(data)),
    )]
    return failures, ["hypothesis verifications validated"] if not failures else []


def check_semantic_coverage(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    semantics = data.get("dita_semantics")
    if not isinstance(semantics, dict) or not semantics.get("active"):
        return [], ["DITA semantic gate skipped (no active DITA semantics)"]
    _overall, _dims, failures = explorer_mod.evaluate_semantic_gate(semantics)
    return failures, [f"DITA semantic gate: {_overall}"]


def check_implementation_grounding(manifest_path: str | None, plan_text: str = "") -> tuple[list[str], list[str]]:
    """Force API/operation/backend tickets to be grounded in the actual handler code.

    - When an `implementation_grounding` block is declared, validate it fully (hard fail).
    - When it is NOT declared but the plan names a code artifact AND asserts current
      behaviour about it, FAIL: the handler must be inspected and cited before such an AC.
    - When signals exist but no current-behaviour assertion is made, emit a REVIEW note.
    """
    data = _load_manifest_dict(manifest_path)
    if not data:
        return [], []
    if impl_grounding_mod.is_present(data):
        block = data["implementation_grounding"]
        failures = [f"[impl-grounding] {p}" for p in
                    impl_grounding_mod.validate_implementation_grounding(
                        block, open_question_ids=_open_question_ids(data))]
        notes = []
        for cap in impl_grounding_mod.config_key_artifacts_missing_provenance(block):
            notes.append(f"REVIEW impl-grounding: config_key '{cap}' declares no key_provenance - mark it "
                         "CODE/PRODUCT_DOC (verified) or REPORTER/TICKET (unverified), and grep the exact key "
                         "against the product before it grounds an AC (reporter-supplied keys are often typos)")
        if not failures:
            notes.append("implementation grounding validated")
        return failures, notes
    if data.get("behaviour_matters", True) is False:
        return [], ["implementation grounding skipped (behaviour_matters is false)"]
    if impl_grounding_mod.is_active(data, plan_text):
        signals = ", ".join(impl_grounding_mod.detect_signals(data, plan_text)[:6])
        if impl_grounding_mod.asserts_current_behavior(plan_text):
            return ([f"[impl-grounding] the plan names a code artifact/API ({signals}) and asserts current behaviour, "
                     "but no implementation_grounding block cites the inspected handler - read the handler "
                     "(clone/GitHub) and ground each current-behaviour AC in a file:line, and verify the ticket's "
                     "premise against the code before delivery"], [])
        return [], [f"REVIEW impl-grounding: API/implementation signals detected ({signals}); add an "
                    "implementation_grounding block citing the inspected handler if any AC asserts current behaviour"]
    return [], ["implementation grounding not applicable (no API/implementation signals)"]


def check_coverage_gate(manifest_path: str | None) -> tuple[list[str], list[str]]:
    data = _load_manifest_dict(manifest_path)
    if not coverage_gate_mod.is_present(data):
        return [], ["semantic coverage gate skipped (no reasoning blocks declared)"]
    result = coverage_gate_mod.evaluate(data)
    notes = [f"semantic coverage gate: {result['semantic_gate']}"]
    notes += [f"REVIEW {rr}" for rr in result["review_reasons"]]
    if result["semantic_gate"] == "FAIL":
        return [f"[coverage-gate] {b}" for b in result["blocking_reasons"]], notes
    if result["semantic_gate"] == "NEEDS_REVIEW":
        return [
            f"[coverage-gate] unresolved review: {reason}"
            for reason in result["review_reasons"]
        ], notes
    return [], notes


def run(plan_path: str, combined_path: str, manifest_path: str | None, jira_keys_path: str | None,
        skip_self_tests: bool) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []

    failures += [f"[manifest] {f}" for f in check_manifest_completeness(manifest_path)]

    body = Path(plan_path).read_text(encoding="utf-8")
    failures += [f"[validate] {e}" for e in validate_mod.validate(body)]
    _arf, _arn = check_ac_readability(body, manifest_path)
    failures += _arf
    notes += _arn
    if manifest_path and Path(manifest_path).is_file():
        try:
            manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest_data = {}
        if isinstance(manifest_data, dict):
            failures += [
                f"[open-questions] {problem}"
                for problem in check_open_question_alignment(manifest_data, body)
            ]
            failures += [
                f"[uac-fidelity] {problem}"
                for problem in check_uac_plan_alignment(manifest_data, body)
            ]
            failures += [
                f"[publishing-scope] {problem}"
                for problem in publishing_scope_coverage_mod.validate(manifest_data, body)
            ]
            failures += [
                f"[uac-linter] {problem}"
                for problem in uac_linter_mod.validate(manifest_data, body)
            ]
            failures += [
                f"[value-provenance] {problem}"
                for problem in value_provenance_coverage_mod.validate(manifest_data, body)
            ]
            failures += [
                f"[performance] {problem}"
                for problem in performance_mod.validate_plan_alignment(manifest_data, body)
            ]
            failures += [
                f"[preflight] {problem}"
                for problem in _validate_preflight_plan_alignment(manifest_data, body)
            ]
    compact, compact_problems = compact_mod.project(body)
    failures += [f"[compact-view] {problem}" for problem in compact_problems]
    if compact:
        notes.append("four-section compact view renderable")

    combined = Path(combined_path).read_text(encoding="utf-8")
    failures += [
        f"[artifact-binding] {problem}"
        for problem in check_combined_binding(body, combined)
    ]
    jira_keys = verify_mod._load_manifest(jira_keys_path)
    v_fail, v_notes = verify_mod.verify(combined, jira_keys)
    failures += [f"[verify] {f}" for f in v_fail]
    notes += v_notes
    if manifest_path and Path(manifest_path).is_file():
        a_fail, a_notes = verify_mod.verify_attachments(manifest_path)
        failures += [f"[verify] {f}" for f in a_fail]
        notes += a_notes
        # Config-key reality: a CODE/OSGI-provenance config_key must exist in the clone.
        try:
            _croots = [c.get("path") for c in (json.loads(Path(manifest_path).read_text(encoding="utf-8")).get("clones") or [])
                       if isinstance(c, dict) and c.get("path")]
        except (OSError, json.JSONDecodeError):
            _croots = []
        ck_fail, ck_notes = verify_mod.verify_config_keys(manifest_path, _croots)
        failures += [f"[verify] {f}" for f in ck_fail]
        notes += ck_notes

    # Anti-hardcoding audit of the skill's own scripts/prompts.
    hc_fail, hc_notes = audit_mod.audit_paths([Path(__file__).resolve().parent.parent])
    failures += [f"[anti-hardcoding] {f}" for f in hc_fail]
    notes += hc_notes

    # Reasoning pipeline: mandatory-for-behavioural, then each stage's gate.
    for _checker in (check_reasoning_required, check_behavior_model, check_coverage_hypotheses,
                     check_retrieval, check_verifications, check_semantic_coverage, check_coverage_gate):
        _f, _n = _checker(manifest_path)
        failures += _f
        notes += _n
    _csf, _csn = check_canonical_semantic_pipeline(manifest_path, body)
    failures += _csf
    notes += _csn
    # Implementation grounding: API/operation/backend tickets must cite the inspected handler.
    _igf, _ign = check_implementation_grounding(manifest_path, body)
    failures += _igf
    notes += _ign
    # Capability eligibility: same-surface actions decomposed per capability.
    _cef, _cen = check_capability_eligibility(manifest_path, body)
    failures += _cef
    notes += _cen
    # Scope conflict: reconcile reported Jira scope vs current fix scope.
    _asf, _asn = check_affected_surface(manifest_path, body)
    failures += _asf
    notes += _asn
    # Comment-claim reconciliation: a Jira comment's own claim about current code must
    # be verified against the diff/code, not accepted as fact.
    _ccf, _ccn = check_comment_claims(manifest_path)
    failures += _ccf
    notes += _ccn
    # PR supersession: when a ticket has more than one PR/branch, exactly one must be
    # reconciled as authoritative before grounding on it.
    _prsf, _prsn = check_pr_supersession(manifest_path)
    failures += _prsf
    notes += _prsn
    _fcf, _fcn = check_feature_class_coverage(manifest_path, body)
    failures += _fcf
    notes += _fcn
    _rtf, _rtn = check_relationship_traversal(manifest_path, body)
    failures += _rtf
    notes += _rtn
    _crf, _crn = check_concurrency_race(manifest_path, body)
    failures += _crf
    notes += _crn
    _ecf, _ecn = check_enumerated_coverage(manifest_path, body)
    failures += _ecf
    notes += _ecn
    _srf, _srn = check_source_requirement_fidelity(manifest_path, body)
    failures += _srf
    notes += _srn
    _ocf, _ocn = check_operational_contract(manifest_path, body)
    failures += _ocf
    notes += _ocn
    _scf, _scn = check_scope_conflict(manifest_path, body)
    failures += _scf
    notes += _scn
    # Final Pre-UAC integration cross-checks the plan body against the reasoning blocks.
    _if, _in = integration_mod.check_integration(_load_manifest_dict(manifest_path), body)
    failures += _if
    notes += _in
    _dm = _load_manifest_dict(manifest_path)
    if disposition_mod.is_present(_dm):
        failures += [f"[disposition] {p}" for p in disposition_mod.validate_dispositions(_dm["dispositions"])]
    if coverage_gate_mod.is_present(_dm):
        failures += [f"[disposition] {p}" for p in disposition_mod.check_plan_acceptance_criteria(body)]
        if oracle_mod.is_present(_dm):
            failures += [f"[oracle] {p}" for p in oracle_mod.validate_scenario_oracles(_dm["scenario_oracles"])]
        if coverage_gate_mod.is_present(_dm):
            failures += [f"[oracle] {p}" for p in oracle_mod.check_plan_scenarios(body)]
        if state_compat_mod.is_present(_dm):
            failures += [f"[state-compat] {p}" for p in state_compat_mod.validate_state_compatibility(_dm["state_compatibility"])]
        elif coverage_gate_mod.is_present(_dm) and state_compat_mod.is_active(_dm):
            failures.append(
                "[state-compat] state-lifecycle signals detected ("
                + ", ".join(state_compat_mod.detect_signals(_dm))
                + ") but no state_compatibility exploration recorded - address CLEAN/FIXED/BUGGY-old "
                "state and whether old-state recovery is required")
        if cross_surface_mod.is_present(_dm):
            failures += [f"[cross-surface] {p}" for p in cross_surface_mod.validate_cross_surface(_dm["cross_surface"])]
        elif coverage_gate_mod.is_present(_dm) and cross_surface_mod.multi_output_signal(_dm):
            notes.append("REVIEW cross-surface: multiple output surfaces in scope but no cross_surface "
                         "classification (separate REFERENCE_ORACLE from evidence-backed REGRESSION_TARGET)")
        if struct_equiv_mod.is_present(_dm):
            failures += [f"[struct-equiv] {p}" for p in struct_equiv_mod.validate_structural_equivalence(_dm["structural_equivalence"])]
        if scenario_reducer_mod.is_present(_dm):
            failures += [f"[scenario-reduce] {p}" for p in scenario_reducer_mod.validate_reduction(_dm["scenario_reduction"])]
        if authority_mod.is_present(_dm):
            failures += [f"[evidence-authority] {p}" for p in authority_mod.validate_evidence_authority(_dm["evidence_authority"])]
        if change_impact_mod.is_present(_dm):
            failures += [f"[change-impact] {p}" for p in change_impact_mod.validate_change_impact(_dm["change_impact"])]
        elif coverage_gate_mod.is_present(_dm) and change_impact_mod.has_change_signal(_dm):
            notes.append("REVIEW change-impact: a fix/diff is available but no change_impact trace recorded "
                         "(changed -> callers -> shared models -> state -> downstream -> outputs)")
        failures += [f"[critic] {p}" for p in critic_mod.validate_repair_bound(_dm)]
        if coverage_gate_mod.is_present(_dm):
            crit = critic_mod.critique(_dm, body)
            notes.append(f"pre-UAC critic: {crit['verdict']}")
            for qid, prompt in critic_mod.QUESTIONS:
                verdict, reason = crit["questions"].get(qid, ("CLEAN", ""))
                if verdict != "CLEAN":
                    notes.append(f"CRITIC [{verdict}] {prompt}" + (f" - {reason}" if reason else ""))

    if not skip_self_tests:
        try:
            self_tests = _load("test_skill_scripts", "test_skill_scripts.py")
            self_tests.test_validator()
            self_tests.test_ac_readability()
            self_tests.test_verifier()
            self_tests.test_attachment_manifest()
            self_tests.test_run_gates()
            self_tests.test_extract_acs()
            self_tests.test_compact_view()
            self_tests.test_semantic_explorer()
            self_tests.test_anti_hardcoding()
            self_tests.test_behavior_model()
            self_tests.test_coverage_hypotheses()
            self_tests.test_missing_questions()
            self_tests.test_hypothesis_verifier()
            self_tests.test_coverage_gate()
            self_tests.test_uac_integration()
            self_tests.test_reasoning_required()
            self_tests.test_relevance_prioritizer()
            self_tests.test_disposition_classifier()
            self_tests.test_oracle_builder()
            self_tests.test_state_compatibility()
            self_tests.test_cross_surface_resolver()
            self_tests.test_structural_equivalence()
            self_tests.test_scenario_reducer()
            self_tests.test_evidence_authority()
            self_tests.test_change_impact()
            self_tests.test_pre_uac_critic()
            self_tests.test_implementation_grounding()
            self_tests.test_capability_eligibility()
            self_tests.test_scope_conflict()
            self_tests.test_affected_surface()
            self_tests.test_feature_class_registry()
            self_tests.test_relationship_traversal()
            self_tests.test_configuration_enumeration_scope()
            self_tests.test_ui_surface_scope()
            self_tests.test_role_provisioning()
            self_tests.test_fluffyjaws_evidence()
            self_tests.test_temporal_evidence()
            self_tests.test_evidence_conflict_resolver()
            self_tests.test_scope_applicability()
            self_tests.test_ac_language_policy()
            self_tests.test_publishing_scope_coverage()
            self_tests.test_repro_dimension_matrix()
            self_tests.test_acceptance_synthesizer()
            self_tests.test_uac_linter()
            self_tests.test_human_feedback_delta()
            self_tests.test_entry_point_equivalence()
            self_tests.test_value_provenance_coverage()
            self_tests.test_terminal_states()
            self_tests.test_concurrency_race()
            self_tests.test_enumerated_coverage()
            self_tests.test_source_requirement_fidelity()
            self_tests.test_ac_decidability()
            self_tests.test_operational_contract()
            self_tests.test_gate_receipt_and_adapter()
            self_tests.test_contract_facts_and_integrity()
            self_tests.test_issue_domain_routing_and_publishing_scope()
            self_tests.test_behavior_graph_relation_ontology()
            self_tests.test_semantic_closure_required()
            self_tests.test_missing_question_directed_retrieval_by_subject()
            self_tests.test_coverage_disposition_completeness()
            self_tests.test_acceptance_promotion_authority()
            self_tests.test_generated_output_contract()
            self_tests.test_generated_artifact_delivery_regression()
            self_tests.test_content_identity_lifecycle_regression()
            self_tests.test_postability_semantic_reviews()
            notes.append("self-tests green")
        except AssertionError as exc:
            failures.append(f"[self-tests] {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any self-test breakage as a gate failure
            failures.append(f"[self-tests] error: {exc}")

    return failures, notes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def _derived_artifact_paths(receipt_path: Path) -> tuple[Path, Path]:
    base = receipt_path.name[:-5] if receipt_path.name.endswith(".json") else receipt_path.name
    return (
        receipt_path.with_name(base + ".compact.md"),
        receipt_path.with_name(base + ".acceptance-criteria.json"),
    )


def _postability_review_present(notes: list[str]) -> bool:
    """Return true for advisory findings that must be resolved before Jira posting."""
    return any(
        str(note).startswith("REVIEW ")
        or str(note).startswith("CRITIC [NEEDS_REVIEW]")
        for note in notes
    )


def write_gate_receipt(
    *,
    receipt_path: str,
    plan_path: str,
    combined_path: str,
    manifest_path: str,
    passed: bool,
    postable: bool,
    skill_root: str | Path | None = None,
) -> Path:
    """Atomically write derived artifacts and their hash-bound gate receipt."""
    receipt = Path(receipt_path).resolve()
    plan = Path(plan_path).resolve()
    combined = Path(combined_path).resolve()
    manifest = Path(manifest_path).resolve()
    executing_skill_root = (
        Path(skill_root).resolve()
        if skill_root is not None
        else Path(__file__).resolve().parent.parent
    )
    compact_path, extracted_path = _derived_artifact_paths(receipt)

    plan_text = plan.read_text(encoding="utf-8")
    compact, compact_problems = compact_mod.project(plan_text)
    criteria, extraction_problems = extract_mod.extract(plan_text)
    if passed and (compact_problems or extraction_problems):
        raise ValueError(
            "cannot issue a passed receipt for invalid compact/extracted AC artifacts"
        )
    _atomic_write(compact_path, compact if not compact_problems else "")
    _atomic_write(
        extracted_path,
        json.dumps(criteria if not extraction_problems else [], indent=2, ensure_ascii=False)
        + "\n",
    )

    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest_data = {}
    payload = {
        "schema_version": GATE_RECEIPT_SCHEMA_VERSION,
        "passed": bool(passed),
        "postable": bool(postable),
        "issue": manifest_issue_key(manifest_data),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validator": skill_fingerprint_mod.fingerprint(executing_skill_root),
        "artifacts": {
            "plan": {"path": str(plan), "sha256": _sha256(plan)},
            "manifest": {"path": str(manifest), "sha256": _sha256(manifest)},
            "combined": {"path": str(combined), "sha256": _sha256(combined)},
            "compact": {"path": str(compact_path), "sha256": _sha256(compact_path)},
            "extracted_acs": {
                "path": str(extracted_path),
                "sha256": _sha256(extracted_path),
            },
        },
    }
    _atomic_write(receipt, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Single mandatory gate for an AEM Guides test plan.")
    parser.add_argument("--plan", required=True, help="the eleven-section bullet-only plan body")
    parser.add_argument("--combined", required=True, help="plan body + Appendix A (the delivered file)")
    parser.add_argument("--manifest", required=True, help="evidence manifest JSON")
    parser.add_argument("--jira-keys", dest="jira_keys", default=None)
    parser.add_argument("--skip-self-tests", action="store_true")
    parser.add_argument(
        "--receipt",
        help="atomic gate receipt path (default: <combined>.gate-receipt.json)",
    )
    args = parser.parse_args()

    failures, notes = run(args.plan, args.combined, args.manifest, args.jira_keys, args.skip_self_tests)

    receipt_path = args.receipt or f"{args.combined}.gate-receipt.json"
    passed = not failures
    postability_review = _postability_review_present(notes)
    postable = passed and not args.skip_self_tests and not postability_review
    if passed and postability_review:
        notes.append(
            "posting blocked until all semantic, readability, and scope REVIEW items are resolved"
        )
    try:
        written_receipt = write_gate_receipt(
            receipt_path=receipt_path,
            plan_path=args.plan,
            combined_path=args.combined,
            manifest_path=args.manifest,
            passed=passed,
            postable=postable,
        )
        notes.append(
            f"gate receipt: {written_receipt} "
            f"({'postable' if postable else 'not postable'})"
        )
    except Exception as exc:  # noqa: BLE001 - a missing receipt must fail closed
        failures.append(f"[receipt] could not write hash-bound gate receipt: {exc}")

    for note in notes:
        print(f"NOTE: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"\nGATE FAILED ({len(failures)} issue(s)) - do not deliver this plan as validated.")
        return 1
    print("\nGATE PASSED - manifest complete, structure valid, compact view renderable, evidence verified"
          + ("." if args.skip_self_tests else ", self-tests green."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
