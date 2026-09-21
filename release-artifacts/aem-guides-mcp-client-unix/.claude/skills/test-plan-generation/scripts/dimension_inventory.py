"""Enumerate-first dimension inventory (G2), fail-closed.

WHY THIS EXISTS
---------------
The recurring failure is authoring ACs from the ticket text plus a couple of greps,
then having a reviewer add the dimension that was missed (an entry point, a sibling
surface, a state/config partition, an output-preset variant, an error path). The fix
is to force enumeration of the WHOLE dimension space BEFORE the ACs are written, and
make every dimension carry an explicit disposition.

This gate requires a behavioural plan to declare a manifest `dimension_inventory`
block that dispositions each canonical dimension. It is fail-closed: a behavioural
plan (one that has acceptance criteria) with no inventory block - and no concrete
opt-out - does not pass. When the block is present, every canonical dimension must be
dispositioned. The point is discovery discipline, not paperwork: a dimension that does
not apply is dispositioned NOT_APPLICABLE with a one-line reason, which still proves it
was considered rather than forgotten.

Trace code (consumers, siblings, entry points) in the BACKGROUND to fill this in; the
ACs themselves stay plain QE English (see coverage_forcing plain-language rule).

Generic only. Standard library only.
"""
from __future__ import annotations

import re

# The canonical dimension space every behavioural UAC must consider.
CANONICAL_DIMENSIONS = {
    "entry_points": "every way the behaviour can be triggered (UI action, API, service, scheduler)",
    "consumers_and_siblings": "code consumers and adjacent/sibling surfaces that share the touched path",
    "state_config_partitions": "on/off settings, profiles, baselines, locales and other state axes (both values)",
    "output_scope": "which output presets/types are affected; DITA-OT processing on/off where relevant",
    "error_and_negative_paths": "failure, invalid-input, empty and boundary conditions",
    "performance_scale": "behaviour at volume/scale/timeout when any workload signal exists",
    "security": "input parsing, injection, permission/tenant surfaces when relevant",
    "localization": "language/locale/translation surfaces when relevant",
    "upgrade_migration": "versioned or persisted state, upgrade/downgrade, older data",
    "regression_surface": "existing behaviour that must not break",
}
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE", "NOT_APPLICABLE")
VISUAL_REFERENCE_EVIDENCE_BLOCK = "visual_reference_evidence"
VISUAL_REFERENCE_COVERAGE_BLOCK = "visual_reference_coverage"
VISUAL_REFERENCE_SCHEMA = "aem-guides-visual-reference-coverage-v1"
WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK = "write_read_consumer_parity_evidence"
WRITE_READ_CONSUMER_PARITY_BLOCK = "write_read_consumer_parity"
WRITE_READ_CONSUMER_PARITY_SCHEMA = "aem-guides-write-read-consumer-parity-v1"
UI_ACTION_SURFACE_EVIDENCE_BLOCK = "ui_action_surface_evidence"
UI_ACTION_SURFACE_COVERAGE_BLOCK = "ui_action_surface_coverage"
UI_ACTION_SURFACE_SCHEMA = "aem-guides-ui-action-surface-coverage-v1"
UI_ACTION_PROOF_KIND = "SELECTABLE_UI_ACTION_ON_SURFACE"
UI_ACTION_CLAIM_STATUSES = ("PROVEN", "UNVERIFIED")
UI_ACTION_EVIDENCE_KINDS = (
    "INSPECTED_UI",
    "INSPECTED_IMPLEMENTATION",
    "APPLICABLE_PRODUCT_DOCUMENTATION",
    "INSPECTED_DESIGN",
)
WRITE_READ_CONSUMER_FIELDS = (
    "value_name",
    "write_surface",
    "write_control",
    "read_surface",
    "read_artifact",
)
VISUAL_SOURCE_KINDS = ("ATTACHMENT", "USER_PROVIDED")
VISUAL_REFERENCE_CONTEXTS = ("CURRENT_PRODUCT", "COMPARISON_PRODUCT")
VISUAL_OBSERVATION_AUTHORITY = "OBSERVATION_ONLY"
VISUAL_PROMOTION_AUTHORITIES = ("JIRA", "USER", "ACCEPTED_PRODUCT_SOURCE")
VISUAL_STATE_DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")
_NON_CONCRETE_SCOPE_REASON_RE = re.compile(
    r"^\s*(?:out\s+of\s+scope|not\s+applicable|unrelated|not\s+needed)\s*\.?\s*$",
    re.I,
)


def _acceptance_block(plan_text: str) -> str:
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def _has_acceptance_criteria(plan_text: str) -> bool:
    for raw in _acceptance_block(plan_text).splitlines():
        if re.match(r"^\s*(?:[-*]\s*)?AC[-\s]?\d", raw, re.I):
            return True
    return False


def _opt_out_reason(manifest) -> str:
    if not isinstance(manifest, dict):
        return ""
    na = manifest.get("dimension_inventory_not_applicable")
    if isinstance(na, dict):
        return str(na.get("reason", "")).strip()
    if isinstance(na, str):
        return na.strip()
    return ""


def _dispositioned(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    disp = str(entry.get("disposition", "")).strip()
    reason = str(entry.get("reason", "")).strip()
    return disp in DISPOSITIONS and len(reason) >= 8


def _nonempty_strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _meaningful(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _concrete_scope_reason(value) -> bool:
    return _meaningful(value) and not _NON_CONCRETE_SCOPE_REASON_RE.match(str(value))


def _normalise(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _acceptance_text_by_id(plan_text: str) -> dict[str, str]:
    """Return acceptance lines keyed by their normalized AC identifier."""
    acceptance_lines: dict[str, str] = {}
    for raw in _acceptance_block(plan_text).splitlines():
        match = re.match(r"^\s*(?:[-*]\s*)?(AC[-\s]?\d+)\b", raw, re.I)
        if match:
            acceptance_lines[_normalise(match.group(1))] = raw
    return acceptance_lines


def _validate_visual_disposition(
    entry,
    *,
    tag: str,
    visual_source_ref: str,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{tag} must be an object with a disposition and reason."]
    problems: list[str] = []
    disposition = str(entry.get("disposition", "")).strip().upper()
    if disposition not in VISUAL_STATE_DISPOSITIONS:
        problems.append(
            f"{tag}.disposition must be one of {', '.join(VISUAL_STATE_DISPOSITIONS)}."
        )
    if not _meaningful(entry.get("reason")):
        problems.append(f"{tag}.reason must explain the disposition.")
    if disposition == "COVERED_BY_AC":
        if not _nonempty_strings(entry.get("ac_refs")):
            problems.append(f"{tag} COVERED_BY_AC requires one or more ac_refs.")
        authority = str(entry.get("desired_behavior_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}; a visual observation "
                "cannot establish desired product behavior."
            )
        evidence_refs = _nonempty_strings(entry.get("desired_behavior_evidence_refs"))
        if not evidence_refs:
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_evidence_refs."
            )
        elif visual_source_ref in evidence_refs:
            problems.append(
                f"{tag} cannot use visual source {visual_source_ref} as desired-behavior "
                "authority; cite Jira, the user, or an accepted product source."
            )
    elif disposition == "OPEN_QUESTION":
        if not _meaningful(entry.get("open_question_ref")):
            problems.append(f"{tag} OPEN_QUESTION requires open_question_ref.")
    elif disposition == "OUT_OF_SCOPE":
        if not _concrete_scope_reason(entry.get("reason")):
            problems.append(
                f"{tag} OUT_OF_SCOPE requires a concrete scope reason, not a placeholder."
            )
        authority = str(entry.get("scope_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} OUT_OF_SCOPE requires scope_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}."
            )
        evidence_refs = _nonempty_strings(entry.get("scope_evidence_refs"))
        if not evidence_refs:
            problems.append(f"{tag} OUT_OF_SCOPE requires scope_evidence_refs.")
        elif visual_source_ref in evidence_refs:
            problems.append(
                f"{tag} cannot use visual source {visual_source_ref} alone to set product scope."
            )
    return problems


def _visual_reference_evidence(manifest) -> tuple[list[dict], list[str]]:
    if not isinstance(manifest, dict) or VISUAL_REFERENCE_EVIDENCE_BLOCK not in manifest:
        return [], []
    records = manifest.get(VISUAL_REFERENCE_EVIDENCE_BLOCK)
    if not isinstance(records, list):
        return [], [f"{VISUAL_REFERENCE_EVIDENCE_BLOCK} must be a list."]

    problems: list[str] = []
    valid_records: list[dict] = []
    seen_refs: set[str] = set()
    for index, record in enumerate(records):
        tag = f"{VISUAL_REFERENCE_EVIDENCE_BLOCK}[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        source_ref = str(record.get("source_ref", "")).strip()
        if not source_ref:
            problems.append(f"{tag}.source_ref must identify the inspected visual source.")
            continue
        if source_ref in seen_refs:
            problems.append(f"{tag}.source_ref duplicates {source_ref}.")
            continue
        seen_refs.add(source_ref)
        source_kind = str(record.get("source_kind", "")).strip().upper()
        if source_kind not in VISUAL_SOURCE_KINDS:
            problems.append(
                f"{tag}.source_kind must be one of {', '.join(VISUAL_SOURCE_KINDS)}."
            )
        reference_context = str(record.get("reference_context", "")).strip().upper()
        if reference_context not in VISUAL_REFERENCE_CONTEXTS:
            problems.append(
                f"{tag}.reference_context must be one of "
                f"{', '.join(VISUAL_REFERENCE_CONTEXTS)}."
            )
        if record.get("inspected") is not True:
            problems.append(
                f"{tag}.inspected must be true; do not infer UI facts from an attachment filename."
            )
        if record.get("observation_authority") != VISUAL_OBSERVATION_AUTHORITY:
            problems.append(
                f"{tag}.observation_authority must be {VISUAL_OBSERVATION_AUTHORITY}; "
                "visual evidence records visible facts, not desired behavior."
            )
        if not _meaningful(record.get("surface")):
            problems.append(f"{tag}.surface must name the observed UI surface.")
        if not _meaningful(record.get("visible_artifact")):
            problems.append(f"{tag}.visible_artifact must name the observed artifact or control.")
        states = record.get("state_variants")
        if not isinstance(states, list) or len(states) < 2:
            problems.append(
                f"{tag}.state_variants must list at least two observed state variants."
            )
        else:
            state_ids: set[str] = set()
            for state_index, state in enumerate(states):
                state_tag = f"{tag}.state_variants[{state_index}]"
                if not isinstance(state, dict):
                    problems.append(f"{state_tag} must be an object.")
                    continue
                state_id = str(state.get("state_id", "")).strip()
                if not state_id:
                    problems.append(f"{state_tag}.state_id must be non-empty.")
                elif state_id in state_ids:
                    problems.append(f"{state_tag}.state_id duplicates {state_id}.")
                else:
                    state_ids.add(state_id)
                if not _meaningful(state.get("observation")):
                    problems.append(
                        f"{state_tag}.observation must record the visible state fact."
                    )
                if not isinstance(state.get("material"), bool):
                    problems.append(
                        f"{state_tag}.material must explicitly be true or false."
                    )
                elif state.get("material") is False and not _concrete_scope_reason(
                    state.get("materiality_reason")
                ):
                    problems.append(
                        f"{state_tag}.materiality_reason must concretely explain why the "
                        "observed state is not material."
                    )
        valid_records.append(record)
    return valid_records, problems


def _write_read_consumer_parity_evidence(manifest) -> tuple[list[dict], list[str]]:
    if (
        not isinstance(manifest, dict)
        or WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK not in manifest
    ):
        return [], []
    records = manifest.get(WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK)
    if not isinstance(records, list):
        return [], [f"{WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK} must be a list."]

    problems: list[str] = []
    valid_records: list[dict] = []
    seen_pair_ids: set[str] = set()
    for index, record in enumerate(records):
        tag = f"{WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK}[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        pair_id = str(record.get("pair_id", "")).strip()
        if not pair_id:
            problems.append(f"{tag}.pair_id must identify the named write/read pair.")
            continue
        if pair_id in seen_pair_ids:
            problems.append(f"{tag}.pair_id duplicates {pair_id}.")
            continue
        seen_pair_ids.add(pair_id)
        for field in WRITE_READ_CONSUMER_FIELDS:
            if not _meaningful(record.get(field)):
                problems.append(f"{tag}.{field} must name the observed value relationship.")
        if (
            _meaningful(record.get("write_surface"))
            and _meaningful(record.get("read_surface"))
            and _normalise(record.get("write_surface"))
            == _normalise(record.get("read_surface"))
        ):
            problems.append(
                f"{tag}.read_surface must be a distinct named consumer surface."
            )
        if not _nonempty_strings(record.get("source_refs")):
            problems.append(
                f"{tag}.source_refs must identify the current evidence naming the pair."
            )
        valid_records.append(record)
    return valid_records, problems


def _ui_action_surface_evidence(manifest) -> tuple[list[dict], list[str]]:
    if (
        not isinstance(manifest, dict)
        or UI_ACTION_SURFACE_EVIDENCE_BLOCK not in manifest
    ):
        return [], []
    records = manifest.get(UI_ACTION_SURFACE_EVIDENCE_BLOCK)
    if not isinstance(records, list):
        return [], [f"{UI_ACTION_SURFACE_EVIDENCE_BLOCK} must be a list."]

    problems: list[str] = []
    valid_records: list[dict] = []
    seen_action_ids: set[str] = set()
    for index, record in enumerate(records):
        tag = f"{UI_ACTION_SURFACE_EVIDENCE_BLOCK}[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        action_id = str(record.get("action_id", "")).strip()
        if not action_id:
            problems.append(f"{tag}.action_id must identify the named UI action.")
            continue
        if action_id in seen_action_ids:
            problems.append(f"{tag}.action_id duplicates {action_id}.")
            continue
        seen_action_ids.add(action_id)
        if not _meaningful(record.get("action_name")):
            problems.append(f"{tag}.action_name must name the UI option or action.")
        if not _meaningful(record.get("surface")):
            problems.append(f"{tag}.surface must name the applicable UI surface.")
        claim_status = str(record.get("claim_status", "PROVEN")).strip().upper()
        if claim_status not in UI_ACTION_CLAIM_STATUSES:
            problems.append(
                f"{tag}.claim_status must be one of {', '.join(UI_ACTION_CLAIM_STATUSES)}."
            )
        if claim_status == "UNVERIFIED":
            if not _concrete_scope_reason(record.get("unverified_reason")):
                problems.append(
                    f"{tag}.unverified_reason must explain why current evidence does "
                    "not prove the existing UI action."
                )
            open_question_ref = str(record.get("open_question_ref", ""))
            if not re.fullmatch(r"OQ-\d{2}", open_question_ref):
                problems.append(
                    f"{tag}.open_question_ref must expose the unverified existing "
                    "action as a canonical Open Question."
                )
            if record.get("proof_kind") not in (None, "", "UNVERIFIED"):
                problems.append(
                    f"{tag}.proof_kind is an unsupported existing UI action claim; "
                    "a configured or documented outcome does not prove a selectable "
                    "action. Preserve the requested outcome separately and expose "
                    "this implementation claim as an Open Question."
                )
            if not _nonempty_strings(record.get("claim_evidence_refs")):
                problems.append(
                    f"{tag}.claim_evidence_refs must identify the source that named "
                    "the unverified action claim."
                )
            valid_records.append(record)
            continue
        evidence_surface = record.get("evidence_surface")
        if not _meaningful(evidence_surface):
            problems.append(
                f"{tag}.evidence_surface must name the surface on which the action is proven."
            )
        elif (
            _meaningful(record.get("surface"))
            and _normalise(evidence_surface) != _normalise(record.get("surface"))
        ):
            problems.append(
                f"{tag}.evidence_surface must match the applicable surface; evidence "
                "from another surface cannot prove this UI action."
            )
        if record.get("proof_kind") != UI_ACTION_PROOF_KIND:
            problems.append(
                f"{tag}.proof_kind is an unsupported existing UI action claim and "
                f"must be {UI_ACTION_PROOF_KIND}; a configured or documented outcome "
                "does not prove a selectable UI action. Preserve the requested outcome "
                "separately and expose the unsupported implementation claim."
            )
        evidence_kind = str(record.get("evidence_kind", "")).strip().upper()
        if evidence_kind not in UI_ACTION_EVIDENCE_KINDS:
            problems.append(
                f"{tag}.evidence_kind must be one of "
                f"{', '.join(UI_ACTION_EVIDENCE_KINDS)}."
            )
        if not _nonempty_strings(record.get("evidence_refs")):
            problems.append(
                f"{tag}.evidence_refs must cite current surface-specific action proof."
            )
        valid_records.append(record)
    return valid_records, problems


def _validate_write_read_consumer_disposition(
    entry,
    *,
    tag: str,
    pair: dict,
    plan_text: str,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{tag} must be an object with a disposition and reason."]
    problems: list[str] = []
    disposition = str(entry.get("disposition", "")).strip().upper()
    if disposition not in VISUAL_STATE_DISPOSITIONS:
        problems.append(
            f"{tag}.disposition must be one of {', '.join(VISUAL_STATE_DISPOSITIONS)}."
        )
    if not _meaningful(entry.get("reason")):
        problems.append(f"{tag}.reason must explain the disposition.")
    if disposition == "COVERED_BY_AC":
        ac_refs = _nonempty_strings(entry.get("ac_refs"))
        if not ac_refs:
            problems.append(f"{tag} COVERED_BY_AC requires one or more ac_refs.")
        authority = str(entry.get("desired_behavior_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}."
            )
        if not _nonempty_strings(entry.get("desired_behavior_evidence_refs")):
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_evidence_refs."
            )
        acceptance_lines = _acceptance_text_by_id(plan_text)
        normalized_names = [
            _normalise(pair.get(field)) for field in WRITE_READ_CONSUMER_FIELDS
        ]
        mapped_lines = [
            acceptance_lines.get(_normalise(ac_ref), "") for ac_ref in ac_refs
        ]
        if ac_refs and not any(
            all(name and name in _normalise(line) for name in normalized_names)
            for line in mapped_lines
        ):
            problems.append(
                f"{tag} COVERED_BY_AC must map one AC that names the value, write "
                "surface/control, and read surface/artifact."
            )
    elif disposition == "OPEN_QUESTION":
        if not _meaningful(entry.get("open_question_ref")):
            problems.append(f"{tag} OPEN_QUESTION requires open_question_ref.")
    elif disposition == "OUT_OF_SCOPE":
        if not _concrete_scope_reason(entry.get("reason")):
            problems.append(
                f"{tag} OUT_OF_SCOPE requires a concrete scope reason, not a placeholder."
            )
        authority = str(entry.get("scope_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} OUT_OF_SCOPE requires scope_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}."
            )
        if not _nonempty_strings(entry.get("scope_evidence_refs")):
            problems.append(f"{tag} OUT_OF_SCOPE requires scope_evidence_refs.")
    return problems


def _validate_write_read_consumer_parity(
    manifest,
    inv,
    plan_text: str,
) -> list[str]:
    pairs, problems = _write_read_consumer_parity_evidence(manifest)
    if not pairs:
        return problems
    coverage = (
        inv.get(WRITE_READ_CONSUMER_PARITY_BLOCK) if isinstance(inv, dict) else None
    )
    if not isinstance(coverage, dict):
        return problems + [
            f"dimension_inventory.{WRITE_READ_CONSUMER_PARITY_BLOCK} is required when "
            f"{WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK} names a write/read pair."
        ]
    if coverage.get("schema_version") != WRITE_READ_CONSUMER_PARITY_SCHEMA:
        problems.append(
            f"dimension_inventory.{WRITE_READ_CONSUMER_PARITY_BLOCK}.schema_version "
            f"must be {WRITE_READ_CONSUMER_PARITY_SCHEMA}."
        )
    records = coverage.get("pairs")
    if not isinstance(records, list):
        return problems + [
            f"dimension_inventory.{WRITE_READ_CONSUMER_PARITY_BLOCK}.pairs must be a list."
        ]
    coverage_by_pair: dict[str, dict] = {}
    for index, record in enumerate(records):
        tag = f"dimension_inventory.{WRITE_READ_CONSUMER_PARITY_BLOCK}.pairs[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        pair_id = str(record.get("pair_id", "")).strip()
        if not pair_id:
            problems.append(f"{tag}.pair_id must be non-empty.")
        elif pair_id in coverage_by_pair:
            problems.append(f"{tag}.pair_id duplicates {pair_id}.")
        else:
            coverage_by_pair[pair_id] = record

    for pair in pairs:
        pair_id = str(pair.get("pair_id", "")).strip()
        tag = f"dimension_inventory.{WRITE_READ_CONSUMER_PARITY_BLOCK}[{pair_id}]"
        record = coverage_by_pair.get(pair_id)
        if not record:
            problems.append(
                f"{tag} has no coverage record; disposition the named write/read "
                "consumer parity."
            )
            continue
        problems.extend(
            _validate_write_read_consumer_disposition(
                record,
                tag=tag,
                pair=pair,
                plan_text=plan_text,
            )
        )
    return problems


def _validate_ui_action_surface_disposition(
    entry,
    *,
    tag: str,
    action: dict,
    plan_text: str,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{tag} must be an object with a disposition and reason."]
    problems: list[str] = []
    disposition = str(entry.get("disposition", "")).strip().upper()
    if disposition not in VISUAL_STATE_DISPOSITIONS:
        problems.append(
            f"{tag}.disposition must be one of {', '.join(VISUAL_STATE_DISPOSITIONS)}."
        )
    if not _meaningful(entry.get("reason")):
        problems.append(f"{tag}.reason must explain the disposition.")
    if str(action.get("claim_status", "PROVEN")).strip().upper() == "UNVERIFIED":
        expected_oq = str(action.get("open_question_ref", ""))
        if disposition != "OPEN_QUESTION":
            problems.append(
                f"{tag} must use OPEN_QUESTION for an unverified existing UI action; "
                "this action claim cannot select or remove the requested outcome."
            )
        elif str(entry.get("open_question_ref", "")) != expected_oq:
            problems.append(
                f"{tag}.open_question_ref must match the unverified action claim's "
                f"Open Question {expected_oq!r}."
            )
        return problems
    if disposition == "COVERED_BY_AC":
        ac_refs = _nonempty_strings(entry.get("ac_refs"))
        if not ac_refs:
            problems.append(f"{tag} COVERED_BY_AC requires one or more ac_refs.")
        authority = str(entry.get("desired_behavior_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}."
            )
        if not _nonempty_strings(entry.get("desired_behavior_evidence_refs")):
            problems.append(
                f"{tag} COVERED_BY_AC requires desired_behavior_evidence_refs."
            )
        acceptance_lines = _acceptance_text_by_id(plan_text)
        action_name = _normalise(action.get("action_name"))
        surface = _normalise(action.get("surface"))
        mapped_lines = [
            acceptance_lines.get(_normalise(ac_ref), "") for ac_ref in ac_refs
        ]
        if ac_refs and not any(
            action_name
            and surface
            and action_name in _normalise(line)
            and surface in _normalise(line)
            for line in mapped_lines
        ):
            problems.append(
                f"{tag} COVERED_BY_AC must map one AC that names the UI action and "
                "its surface."
            )
    elif disposition == "OPEN_QUESTION":
        if not _meaningful(entry.get("open_question_ref")):
            problems.append(f"{tag} OPEN_QUESTION requires open_question_ref.")
    elif disposition == "OUT_OF_SCOPE":
        if not _concrete_scope_reason(entry.get("reason")):
            problems.append(
                f"{tag} OUT_OF_SCOPE requires a concrete scope reason, not a placeholder."
            )
        authority = str(entry.get("scope_authority", "")).strip().upper()
        if authority not in VISUAL_PROMOTION_AUTHORITIES:
            problems.append(
                f"{tag} OUT_OF_SCOPE requires scope_authority from "
                f"{', '.join(VISUAL_PROMOTION_AUTHORITIES)}."
            )
        if not _nonempty_strings(entry.get("scope_evidence_refs")):
            problems.append(f"{tag} OUT_OF_SCOPE requires scope_evidence_refs.")
    return problems


def _validate_ui_action_surface_coverage(
    manifest,
    inv,
    plan_text: str,
) -> list[str]:
    actions, problems = _ui_action_surface_evidence(manifest)
    if not actions:
        return problems
    coverage = (
        inv.get(UI_ACTION_SURFACE_COVERAGE_BLOCK) if isinstance(inv, dict) else None
    )
    if not isinstance(coverage, dict):
        return problems + [
            f"dimension_inventory.{UI_ACTION_SURFACE_COVERAGE_BLOCK} is required when "
            f"{UI_ACTION_SURFACE_EVIDENCE_BLOCK} names a UI action."
        ]
    if coverage.get("schema_version") != UI_ACTION_SURFACE_SCHEMA:
        problems.append(
            f"dimension_inventory.{UI_ACTION_SURFACE_COVERAGE_BLOCK}.schema_version "
            f"must be {UI_ACTION_SURFACE_SCHEMA}."
        )
    records = coverage.get("actions")
    if not isinstance(records, list):
        return problems + [
            f"dimension_inventory.{UI_ACTION_SURFACE_COVERAGE_BLOCK}.actions must be a list."
        ]
    coverage_by_action: dict[str, dict] = {}
    for index, record in enumerate(records):
        tag = f"dimension_inventory.{UI_ACTION_SURFACE_COVERAGE_BLOCK}.actions[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        action_id = str(record.get("action_id", "")).strip()
        if not action_id:
            problems.append(f"{tag}.action_id must be non-empty.")
        elif action_id in coverage_by_action:
            problems.append(f"{tag}.action_id duplicates {action_id}.")
        else:
            coverage_by_action[action_id] = record

    for action in actions:
        action_id = str(action.get("action_id", "")).strip()
        tag = f"dimension_inventory.{UI_ACTION_SURFACE_COVERAGE_BLOCK}[{action_id}]"
        record = coverage_by_action.get(action_id)
        if not record:
            problems.append(
                f"{tag} has no coverage record; disposition the named UI action on "
                "its applicable surface."
            )
            continue
        problems.extend(
            _validate_ui_action_surface_disposition(
                record,
                tag=tag,
                action=action,
                plan_text=plan_text,
            )
        )
    return problems


def _validate_visual_reference_coverage(manifest, inv) -> list[str]:
    observations, problems = _visual_reference_evidence(manifest)
    if not observations:
        return problems
    coverage = inv.get(VISUAL_REFERENCE_COVERAGE_BLOCK) if isinstance(inv, dict) else None
    if not isinstance(coverage, dict):
        return problems + [
            f"dimension_inventory.{VISUAL_REFERENCE_COVERAGE_BLOCK} is required when "
            f"{VISUAL_REFERENCE_EVIDENCE_BLOCK} records an inspected visual reference."
        ]
    if coverage.get("schema_version") != VISUAL_REFERENCE_SCHEMA:
        problems.append(
            f"dimension_inventory.{VISUAL_REFERENCE_COVERAGE_BLOCK}.schema_version "
            f"must be {VISUAL_REFERENCE_SCHEMA}."
        )
    records = coverage.get("references")
    if not isinstance(records, list):
        return problems + [
            f"dimension_inventory.{VISUAL_REFERENCE_COVERAGE_BLOCK}.references must be a list."
        ]
    coverage_by_source: dict[str, dict] = {}
    for index, record in enumerate(records):
        tag = f"dimension_inventory.{VISUAL_REFERENCE_COVERAGE_BLOCK}.references[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{tag} must be an object.")
            continue
        source_ref = str(record.get("source_ref", "")).strip()
        if not source_ref:
            problems.append(f"{tag}.source_ref must be non-empty.")
        elif source_ref in coverage_by_source:
            problems.append(f"{tag}.source_ref duplicates {source_ref}.")
        else:
            coverage_by_source[source_ref] = record

    for observation in observations:
        source_ref = str(observation.get("source_ref", "")).strip()
        record = coverage_by_source.get(source_ref)
        base_tag = (
            f"dimension_inventory.{VISUAL_REFERENCE_COVERAGE_BLOCK}"
            f"[{source_ref}]"
        )
        if not record:
            problems.append(
                f"{base_tag} has no coverage record; disposition the observed surface "
                "and every material state variant."
            )
            continue
        surface = record.get("surface")
        if not isinstance(surface, dict):
            problems.append(f"{base_tag}.surface must disposition the observed UI surface.")
        else:
            if _normalise(surface.get("name")) != _normalise(observation.get("surface")):
                problems.append(
                    f"{base_tag}.surface.name must match the observed surface "
                    f"{observation.get('surface')!r}."
                )
            problems.extend(
                _validate_visual_disposition(
                    surface,
                    tag=f"{base_tag}.surface",
                    visual_source_ref=source_ref,
                )
            )

        state_records = record.get("state_variants")
        if not isinstance(state_records, list):
            problems.append(
                f"{base_tag}.state_variants must disposition every observed material state."
            )
            continue
        state_coverage: dict[str, dict] = {}
        for state_index, state in enumerate(state_records):
            state_tag = f"{base_tag}.state_variants[{state_index}]"
            if not isinstance(state, dict):
                problems.append(f"{state_tag} must be an object.")
                continue
            state_id = str(state.get("state_id", "")).strip()
            if not state_id:
                problems.append(f"{state_tag}.state_id must be non-empty.")
            elif state_id in state_coverage:
                problems.append(f"{state_tag}.state_id duplicates {state_id}.")
            else:
                state_coverage[state_id] = state

        for observed_state in observation.get("state_variants") or []:
            if not isinstance(observed_state, dict) or observed_state.get("material") is not True:
                continue
            state_id = str(observed_state.get("state_id", "")).strip()
            state = state_coverage.get(state_id)
            if not state:
                problems.append(
                    f"{base_tag}.state_variants omits observed material state {state_id}."
                )
                continue
            problems.extend(
                _validate_visual_disposition(
                    state,
                    tag=f"{base_tag}.state_variants[{state_id}]",
                    visual_source_ref=source_ref,
                )
            )
    return problems


def validate(manifest, plan_text: str = "") -> list[str]:
    # Only behavioural plans (those that actually assert acceptance criteria) are gated.
    if not _has_acceptance_criteria(plan_text):
        return []
    visual_reference_declared = (
        isinstance(manifest, dict)
        and bool(manifest.get(VISUAL_REFERENCE_EVIDENCE_BLOCK))
    )
    write_read_consumer_parity_declared = (
        isinstance(manifest, dict)
        and bool(manifest.get(WRITE_READ_CONSUMER_PARITY_EVIDENCE_BLOCK))
    )
    ui_action_surface_declared = (
        isinstance(manifest, dict)
        and bool(manifest.get(UI_ACTION_SURFACE_EVIDENCE_BLOCK))
    )
    if (
        len(_opt_out_reason(manifest)) >= 12
        and not visual_reference_declared
        and not write_read_consumer_parity_declared
        and not ui_action_surface_declared
    ):
        return []
    inv = manifest.get("dimension_inventory") if isinstance(manifest, dict) else None
    if not isinstance(inv, dict) or not inv:
        return [
            "This UAC has acceptance criteria but declares no dimension_inventory. "
            "Enumerate the dimension space FIRST and disposition each of: "
            + ", ".join(CANONICAL_DIMENSIONS)
            + " (each COVERED_BY_AC / OPEN_QUESTION / OUT_OF_SCOPE / NOT_APPLICABLE with a "
            "reason), or set dimension_inventory_not_applicable with a concrete reason."
        ]
    problems: list[str] = []
    if visual_reference_declared and len(_opt_out_reason(manifest)) >= 12:
        problems.append(
            "dimension_inventory_not_applicable cannot bypass an inspected visual "
            "reference; disposition its observed surface and material states."
        )
    if write_read_consumer_parity_declared and len(_opt_out_reason(manifest)) >= 12:
        problems.append(
            "dimension_inventory_not_applicable cannot bypass named write/read "
            "consumer parity evidence."
        )
    if ui_action_surface_declared and len(_opt_out_reason(manifest)) >= 12:
        problems.append(
            "dimension_inventory_not_applicable cannot bypass named UI action "
            "surface evidence."
        )
    for dim, desc in CANONICAL_DIMENSIONS.items():
        if not _dispositioned(inv.get(dim)):
            problems.append(
                f"dimension_inventory.{dim} is not dispositioned ({desc}). "
                "Set disposition (COVERED_BY_AC/OPEN_QUESTION/OUT_OF_SCOPE/NOT_APPLICABLE) "
                "and a reason of at least 8 characters."
            )
    problems.extend(_validate_visual_reference_coverage(manifest, inv))
    problems.extend(_validate_write_read_consumer_parity(manifest, inv, plan_text))
    problems.extend(_validate_ui_action_surface_coverage(manifest, inv, plan_text))
    return problems


def summarize(manifest, plan_text: str = "") -> str:
    problems = validate(manifest, plan_text)
    lines = [f"DimensionInventory: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.extend(f"  {p}" for p in problems)
    return "\n".join(lines)


def _full_inventory(**overrides) -> dict:
    inv = {d: {"disposition": "NOT_APPLICABLE", "reason": "not relevant to this change"} for d in CANONICAL_DIMENSIONS}
    inv.update(overrides)
    return inv


def run_self_tests() -> None:
    nl = chr(10)
    non_behavioural = nl.join(["**Understanding**", "Some context.", ""])
    assert validate({}, non_behavioural) == [], "no ACs -> not gated"

    behavioural = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: the selected topic publishes.",
        ""])
    # Missing block -> fail closed.
    assert any("no dimension_inventory" in p for p in validate({}, behavioural)), "behavioural plan without inventory must fail"

    # Incomplete block -> fail on the missing dimension.
    partial = {"dimension_inventory": {"entry_points": {"disposition": "COVERED_BY_AC", "reason": "map dashboard + api + service"}}}
    probs = validate(partial, behavioural)
    assert any("regression_surface" in p for p in probs), "missing dimension must be flagged"

    # Complete block -> pass.
    complete = {"dimension_inventory": _full_inventory(
        entry_points={"disposition": "COVERED_BY_AC", "reason": "map dashboard, api, service all covered"},
        regression_surface={"disposition": "COVERED_BY_AC", "reason": "baseline path and full publish covered"},
    )}
    assert validate(complete, behavioural) == [], f"complete inventory must pass: {validate(complete, behavioural)}"

    # Opt-out -> pass.
    assert validate({"dimension_inventory_not_applicable": {"reason": "pure typo fix in a doc string, no behaviour"}}, behavioural) == [], "opt-out must pass"

    print("dimension_inventory self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
