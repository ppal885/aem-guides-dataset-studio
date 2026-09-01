"""Content identity/version contract for assets and referenced content."""

from __future__ import annotations

import re
from collections.abc import Mapping


SCHEMA_VERSION = "aem-guides-content-identity-contract-v1"
SELECTION_POLICIES = ("CURRENT", "LATEST", "PINNED", "SOURCE_DEFINED", "UNRESOLVED")
FALLBACK_POLICIES = ("NO_FALLBACK", "FAIL", "APPROVED_FALLBACK", "UNRESOLVED")
OPERATIONS = ("CREATE", "UPDATE", "MOVE", "RENAME", "REPUBLISH", "REFERENCE_RESOLUTION", "GENERATED_OUTPUT")
APPLICABILITY = ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED")
STATUSES = ("COVERED", "INVESTIGATED_AND_REJECTED", "UNRESOLVED_AND_EXPOSED")
MIGRATION_BEHAVIORS = ("NOT_APPLICABLE", "UNCHANGED", "MIGRATE", "UNRESOLVED")


def validate_content_identity_contract(block, *, open_question_ids=None, **_kwargs):
    problems = []
    if not isinstance(block, Mapping):
        return ["content_identity_contract must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"content_identity_contract.schema_version must be {SCHEMA_VERSION}")
    if not str(block.get("identity_source", "")).strip():
        problems.append("content_identity_contract.identity_source must be non-empty")
    selection = block.get("selection_policy")
    if selection not in SELECTION_POLICIES:
        problems.append(f"content_identity_contract.selection_policy must be one of {', '.join(SELECTION_POLICIES)}")
    fallback = block.get("fallback_policy")
    if fallback not in FALLBACK_POLICIES:
        problems.append(f"content_identity_contract.fallback_policy must be one of {', '.join(FALLBACK_POLICIES)}")
    if fallback == "APPROVED_FALLBACK" and not str(block.get("fallback_authority", "")).strip():
        problems.append("APPROVED_FALLBACK requires fallback_authority")
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    if selection == "UNRESOLVED" or fallback == "UNRESOLVED":
        ref = str(block.get("open_question_ref", ""))
        if not ref or (oq_ids is not None and ref not in oq_ids):
            problems.append("unresolved identity/fallback policy requires a declared Open Question")
    migration = block.get("migration_behavior")
    if migration not in MIGRATION_BEHAVIORS:
        problems.append(f"content_identity_contract.migration_behavior must be one of {', '.join(MIGRATION_BEHAVIORS)}")
    if migration == "MIGRATE" and not str(block.get("migration_authority", "")).strip():
        problems.append("MIGRATE behavior requires explicit migration_authority")
    if migration == "UNRESOLVED":
        ref = str(block.get("migration_open_question_ref", ""))
        if not ref or (oq_ids is not None and ref not in oq_ids):
            problems.append("unresolved migration behavior requires a declared Open Question")

    states = block.get("lifecycle")
    if not isinstance(states, list):
        return problems + ["content_identity_contract.lifecycle must be a list"]
    by_operation = {}
    state_ids = set()
    for index, state in enumerate(states):
        tag = f"content_identity_contract.lifecycle[{index}]"
        if not isinstance(state, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        state_id = str(state.get("state_id", ""))
        if not re.fullmatch(r"CI-\d{2}", state_id):
            problems.append(f"{tag}.state_id must use CI-## form")
        elif state_id in state_ids:
            problems.append(f"{tag}.state_id duplicates {state_id}")
        state_ids.add(state_id)
        operation = state.get("operation")
        if operation not in OPERATIONS:
            problems.append(f"{tag}.operation must be one of {', '.join(OPERATIONS)}")
        elif operation in by_operation:
            problems.append(f"content identity operation {operation} is duplicated")
        by_operation[operation] = state
        applicability = state.get("applicability")
        status = state.get("status")
        if applicability not in APPLICABILITY:
            problems.append(f"{tag}.applicability must be one of {', '.join(APPLICABILITY)}")
        if status not in STATUSES:
            problems.append(f"{tag}.status must be one of {', '.join(STATUSES)}")
        if not str(state.get("expected_identity", "")).strip():
            problems.append(f"{tag}.expected_identity must be non-empty")
        if applicability == "APPLICABLE" and status != "COVERED":
            problems.append(f"{tag}: APPLICABLE operation must be COVERED")
        if applicability == "NOT_APPLICABLE" and status != "INVESTIGATED_AND_REJECTED":
            problems.append(f"{tag}: NOT_APPLICABLE operation must be INVESTIGATED_AND_REJECTED")
        if applicability == "UNRESOLVED" and status != "UNRESOLVED_AND_EXPOSED":
            problems.append(f"{tag}: UNRESOLVED operation must be UNRESOLVED_AND_EXPOSED")
        if status == "UNRESOLVED_AND_EXPOSED":
            ref = str(state.get("open_question_ref", ""))
            if not ref or (oq_ids is not None and ref not in oq_ids):
                problems.append(f"{tag}: unresolved operation requires a declared Open Question")
        elif not str(state.get("disposition_ref", "")).strip():
            problems.append(f"{tag}: terminal operation requires disposition_ref")
    for operation in OPERATIONS:
        if operation not in by_operation:
            problems.append(f"content identity contract silently omits lifecycle operation {operation}")
    return problems


def material_item_ids(block):
    if not isinstance(block, Mapping):
        return []
    return [
        str(x.get("state_id")) for x in block.get("lifecycle", [])
        if isinstance(x, Mapping) and x.get("state_id")
    ]


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("content_identity_contract"), Mapping)
