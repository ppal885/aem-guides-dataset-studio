"""Subject-aware acceptance promotion gate.

Verification answers whether behavior exists.  Promotion separately answers
whether that behavior belongs to the intended product contract.  PR/code/tests
alone therefore never authorize an Acceptance Criterion.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path


SCHEMA_VERSION = "aem-guides-acceptance-promotions-v1"
DECISIONS = ("PROMOTED_CONFIRMED", "PROMOTED_PROPOSED", "REJECTED")


def _policy():
    path = Path(__file__).with_name("data") / "authority_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["subjects"]


SUBJECT_POLICIES = _policy()


def acceptance_authorities(subject="PRODUCT_CONTRACT"):
    return set(SUBJECT_POLICIES.get(subject, {}).get("acceptance_authorities", []))


def validate_acceptance_promotions(
    block,
    *,
    ac_ids=None,
    known_candidate_ids=None,
    contract_fact_ids=None,
    candidate_authorities=None,
    candidate_subjects=None,
    dispositions=None,
    ac_status_by_id=None,
    accepted_uac_present=None,
):
    problems = []
    if not isinstance(block, Mapping):
        return ["acceptance_promotions must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"acceptance_promotions.schema_version must be {SCHEMA_VERSION}")
    records = block.get("records")
    if not isinstance(records, list):
        return problems + ["acceptance_promotions.records must be a list"]
    known = None if known_candidate_ids is None else set(known_candidate_ids)
    fact_ids = None if contract_fact_ids is None else set(contract_fact_ids)
    available_acs = None if ac_ids is None else set(ac_ids)
    authority_by_candidate = {
        str(ref): set(values or [])
        for ref, values in (candidate_authorities or {}).items()
    }
    subject_by_candidate = {
        str(ref): str(subject)
        for ref, subject in (candidate_subjects or {}).items()
        if str(ref).strip() and str(subject).strip()
    }
    disposition_by_id = {
        str(item.get("finding_id")): item
        for item in (dispositions or [])
        if isinstance(item, Mapping) and item.get("finding_id")
    }
    status_by_ac = dict(ac_status_by_id or {})
    seen = set()
    seen_candidates = set()
    seen_acs = set()
    for index, record in enumerate(records):
        tag = f"acceptance_promotions.records[{index}]"
        if not isinstance(record, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        promotion_id = str(record.get("promotion_id", ""))
        if not re.fullmatch(r"AP-\d{2}", promotion_id):
            problems.append(f"{tag}.promotion_id must use AP-## form")
        elif promotion_id in seen:
            problems.append(f"{tag}.promotion_id duplicates {promotion_id}")
        seen.add(promotion_id)
        candidate_ref = str(record.get("candidate_ref", ""))
        if not candidate_ref:
            problems.append(f"{tag}.candidate_ref must be non-empty")
        elif known is not None and candidate_ref not in known:
            problems.append(f"{tag}.candidate_ref {candidate_ref!r} is not a material candidate")
        if candidate_ref in seen_candidates:
            problems.append(f"{tag}.candidate_ref {candidate_ref!r} is promoted more than once")
        elif candidate_ref:
            seen_candidates.add(candidate_ref)
        decision = record.get("decision")
        if decision not in DECISIONS:
            problems.append(f"{tag}.decision must be one of {', '.join(DECISIONS)}")
            continue
        if decision == "REJECTED":
            if not str(record.get("reason", "")).strip():
                problems.append(f"{tag}: REJECTED promotion requires a reason")
            if record.get("ac_ref"):
                problems.append(f"{tag}: REJECTED promotion must not reference an AC")
            continue

        ac_ref = str(record.get("ac_ref", ""))
        if not re.fullmatch(r"AC-\d{2}", ac_ref) or (
            available_acs is not None and ac_ref not in available_acs
        ):
            problems.append(f"{tag}.ac_ref must reference a visible AC")
        if ac_ref in seen_acs:
            problems.append(f"{tag}.ac_ref {ac_ref!r} is promoted more than once")
        elif ac_ref:
            seen_acs.add(ac_ref)
        subject = record.get("subject")
        if subject != "PRODUCT_CONTRACT":
            problems.append(f"{tag}: Acceptance Criteria require PRODUCT_CONTRACT authority")
        if candidate_subjects is not None and subject_by_candidate.get(candidate_ref) != subject:
            problems.append(
                f"{tag}: promotion subject {subject!r} does not match candidate "
                f"{candidate_ref!r} subject {subject_by_candidate.get(candidate_ref)!r}"
            )
        authorities = record.get("intended_behavior_authorities")
        if not isinstance(authorities, list) or not authorities:
            problems.append(f"{tag}.intended_behavior_authorities must be a non-empty list")
            authorities = []
        eligible = acceptance_authorities("PRODUCT_CONTRACT")
        if not set(authorities) & eligible:
            problems.append(
                f"{tag}: PR/code/tests/runtime evidence alone cannot authorize intended product behavior"
            )
        if any(authority not in eligible for authority in authorities):
            problems.append(f"{tag}: intended_behavior_authorities contains an ineligible authority")
        if candidate_authorities is not None and any(
            authority not in authority_by_candidate.get(candidate_ref, set())
            for authority in authorities
        ):
            problems.append(
                f"{tag}: intended behavior authority is not bound to candidate {candidate_ref!r}"
            )
        for field in (
            "scope_established", "observable", "testable", "regression_only",
            "implementation_only", "conflicts_accepted_uac",
        ):
            if not isinstance(record.get(field), bool):
                problems.append(f"{tag}.{field} must be a boolean")
        if record.get("scope_established") is not True:
            problems.append(f"{tag}: scope must be established before AC promotion")
        if record.get("observable") is not True or record.get("testable") is not True:
            problems.append(f"{tag}: promoted AC must be observable and testable")
        if record.get("regression_only") is True:
            problems.append(f"{tag}: regression-only coverage must not become an AC")
        if record.get("implementation_only") is True:
            problems.append(f"{tag}: implementation mechanics must not become an AC")
        if record.get("conflicts_accepted_uac") is True:
            problems.append(f"{tag}: promotion conflicts with Human Accepted AC")
        unresolved = record.get("unresolved_decision_refs", [])
        if not isinstance(unresolved, list):
            problems.append(f"{tag}.unresolved_decision_refs must be a list")
        elif unresolved:
            problems.append(f"{tag}: unresolved product decisions block AC promotion")
        exact_refs = record.get("exact_value_fact_refs", [])
        if not isinstance(exact_refs, list):
            problems.append(f"{tag}.exact_value_fact_refs must be a list")
        elif fact_ids is not None and any(ref not in fact_ids for ref in exact_refs):
            problems.append(f"{tag}.exact_value_fact_refs contains an unknown contract fact")
        expected_disposition = (
            "ACCEPTANCE_CONTRACT" if decision == "PROMOTED_CONFIRMED"
            else "PROPOSED_ACCEPTANCE_CONTRACT"
        )
        if record.get("disposition") != expected_disposition:
            problems.append(f"{tag}.{decision} requires disposition {expected_disposition}")
        disposition_ref = str(record.get("disposition_ref", "")).strip()
        if not disposition_ref:
            problems.append(f"{tag}: promoted candidate requires disposition_ref")
        elif dispositions is not None:
            disposition = disposition_by_id.get(disposition_ref)
            if disposition is None:
                problems.append(f"{tag}: disposition_ref does not exist")
            else:
                refs = disposition.get("source_refs", [])
                if candidate_ref not in refs:
                    problems.append(
                        f"{tag}: referenced disposition does not cover candidate {candidate_ref!r}"
                    )
                if disposition.get("disposition") != expected_disposition:
                    problems.append(
                        f"{tag}: referenced disposition is {disposition.get('disposition')!r}, "
                        f"expected {expected_disposition}"
                    )
                mapped_ac = disposition.get("maps_to_ac")
                if mapped_ac and mapped_ac != ac_ref:
                    problems.append(f"{tag}: referenced disposition maps to a different AC")
        expected_status = "Confirmed" if decision == "PROMOTED_CONFIRMED" else "Proposed"
        if ac_status_by_id is not None and status_by_ac.get(ac_ref) != expected_status:
            problems.append(
                f"{tag}: {decision} must reference a [{expected_status}] AC"
            )
        if decision == "PROMOTED_CONFIRMED" and accepted_uac_present is not True:
            problems.append(
                f"{tag}: PROMOTED_CONFIRMED requires accepted_uac_present=true"
            )
        if decision == "PROMOTED_CONFIRMED" and not set(authorities) & {
            "HUMAN_ACCEPTED_AC", "APPROVED_PRODUCT_DECISION", "EXPLICIT_HUMAN_DECISION"
        }:
            problems.append(
                f"{tag}: PROMOTED_CONFIRMED requires accepted/approved human authority; Jira evidence remains Proposed"
            )
    return problems


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("acceptance_promotions"), Mapping)
