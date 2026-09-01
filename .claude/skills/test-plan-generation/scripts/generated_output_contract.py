"""Structured generated-output oracles for publishing and export workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping


SCHEMA_VERSION = "aem-guides-generated-output-contract-v2"
LEGACY_SCHEMA_VERSION = "aem-guides-generated-output-contract-v1"
ORACLE_TYPES = (
    "ARTIFACT_EXISTS", "CONTENT_CORRECT", "TITLE_CORRECT", "HIERARCHY_CORRECT",
    "ORDER_CORRECT", "NAVIGATION_CORRECT", "LINKS_CORRECT", "METADATA_CORRECT",
    "REPOSITORY_STATE_CORRECT", "OUTPUT_PATH_CORRECT", "LOCALE_CORRECT", "NO_DUPLICATES",
    "NO_ORPHANS", "NO_STALE_OUTPUT", "UNCHANGED_CONTENT_NOT_REWRITTEN",
    "ACTIVATION_STATE_CORRECT", "STATUS_MATCHES_REAL_OUTPUT", "DELIVERY_AVAILABLE",
)
APPLICABILITY = ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED")
STATUSES = ("COVERED", "INVESTIGATED_AND_REJECTED", "UNRESOLVED_AND_EXPOSED")
ARTIFACT_KINDS = ("ARCHIVE", "SITE", "DOCUMENT", "REPOSITORY_TREE", "API_PAYLOAD", "OTHER")
PAYLOAD_ROLES = ("PRIMARY_CONTENT", "SUPPORTING", "DIAGNOSTIC")
ITEM_DISPOSITIONS = ("INCLUDED", "EXCLUDED", "UNRESOLVED")


def _strings(value, *, nonempty=False):
    return isinstance(value, list) and (not nonempty or bool(value)) and all(
        isinstance(x, str) and x.strip() for x in value
    )


def validate_generated_output_contract(block, *, open_question_ids=None, **_kwargs):
    problems = []
    if not isinstance(block, Mapping):
        return ["generated_output_contract must be an object"]
    schema_version = block.get("schema_version")
    if schema_version not in (SCHEMA_VERSION, LEGACY_SCHEMA_VERSION):
        problems.append(
            "generated_output_contract.schema_version must be "
            f"{SCHEMA_VERSION} (or legacy {LEGACY_SCHEMA_VERSION})"
        )
    artifact_kind = block.get("artifact_kind")
    if artifact_kind not in ARTIFACT_KINDS:
        problems.append(f"generated_output_contract.artifact_kind must be one of {', '.join(ARTIFACT_KINDS)}")
    for field in ("entry_surface", "output_identity"):
        if not str(block.get(field, "")).strip():
            problems.append(f"generated_output_contract.{field} must be non-empty")
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    strict_delivery = schema_version == SCHEMA_VERSION or "delivery_in_scope" in block
    delivery_scope = block.get("delivery_in_scope")
    if strict_delivery and delivery_scope not in (True, False, "UNRESOLVED"):
        problems.append(
            "generated_output_contract.delivery_in_scope must be true, false, or UNRESOLVED"
        )
    if delivery_scope is True and not str(block.get("download_surface", "")).strip():
        problems.append("in-scope artifact delivery requires a download_surface")
    if delivery_scope == "UNRESOLVED":
        ref = str(block.get("delivery_scope_open_question_ref", ""))
        if not ref or (oq_ids is not None and ref not in oq_ids):
            problems.append(
                "UNRESOLVED delivery scope requires a declared delivery_scope_open_question_ref"
            )
    if not strict_delivery and artifact_kind == "ARCHIVE" and not str(
        block.get("download_surface", "")
    ).strip():
        problems.append("legacy ARCHIVE output requires a download_surface")
    inventory = block.get("payload_inventory")
    if not isinstance(inventory, list) or not inventory:
        problems.append("generated_output_contract.payload_inventory must be a non-empty list")
        inventory = []
    included_primary = False
    inventory_ids = set()
    for index, item in enumerate(inventory):
        tag = f"generated_output_contract.payload_inventory[{index}]"
        if not isinstance(item, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        item_id = str(item.get("item_id", ""))
        if not re.fullmatch(r"GOI-\d{2}", item_id):
            problems.append(f"{tag}.item_id must use GOI-## form")
        elif item_id in inventory_ids:
            problems.append(f"{tag}.item_id duplicates {item_id}")
        inventory_ids.add(item_id)
        if not str(item.get("item", "")).strip():
            problems.append(f"{tag}.item must be non-empty")
        role = item.get("role")
        if role not in PAYLOAD_ROLES:
            problems.append(f"{tag}.role must be one of {', '.join(PAYLOAD_ROLES)}")
        disposition = item.get("disposition")
        if disposition not in ITEM_DISPOSITIONS:
            problems.append(f"{tag}.disposition must be one of {', '.join(ITEM_DISPOSITIONS)}")
        if role == "PRIMARY_CONTENT" and disposition == "INCLUDED":
            included_primary = True
        if disposition == "UNRESOLVED":
            ref = str(item.get("open_question_ref", ""))
            if not ref or (oq_ids is not None and ref not in oq_ids):
                problems.append(f"{tag}: UNRESOLVED inventory item requires a declared Open Question")
    if artifact_kind == "ARCHIVE" and not included_primary:
        problems.append(
            "ARCHIVE payload must include at least one PRIMARY_CONTENT item; a logs/diagnostics-only archive "
            "does not validate the requested generated artifact"
        )

    layout = block.get("structure")
    if not isinstance(layout, Mapping):
        problems.append("generated_output_contract.structure must be an object")
    else:
        for field in ("root", "hierarchy", "relative_path_policy"):
            value = str(layout.get(field, "")).strip()
            if not value:
                problems.append(f"generated_output_contract.structure.{field} must be resolved or UNRESOLVED")
            elif value.upper() == "UNRESOLVED":
                ref = str(layout.get(f"{field}_open_question_ref", ""))
                if not ref or (oq_ids is not None and ref not in oq_ids):
                    problems.append(f"output structure {field} is UNRESOLVED but has no declared Open Question")

    oracles = block.get("oracles")
    if not isinstance(oracles, list):
        return problems + ["generated_output_contract.oracles must be a list"]
    by_type = {}
    oracle_ids = set()
    for index, oracle in enumerate(oracles):
        tag = f"generated_output_contract.oracles[{index}]"
        if not isinstance(oracle, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        oracle_id = str(oracle.get("oracle_id", ""))
        if not re.fullmatch(r"GO-\d{2}", oracle_id):
            problems.append(f"{tag}.oracle_id must use GO-## form")
        elif oracle_id in oracle_ids:
            problems.append(f"{tag}.oracle_id duplicates {oracle_id}")
        oracle_ids.add(oracle_id)
        oracle_type = oracle.get("oracle_type")
        if oracle_type not in ORACLE_TYPES:
            problems.append(f"{tag}.oracle_type must be a canonical generated-output oracle")
        elif oracle_type in by_type:
            problems.append(f"generated output oracle {oracle_type} is duplicated")
        by_type[oracle_type] = oracle
        applicability = oracle.get("applicability")
        status = oracle.get("status")
        if applicability not in APPLICABILITY:
            problems.append(f"{tag}.applicability must be one of {', '.join(APPLICABILITY)}")
        if status not in STATUSES:
            problems.append(f"{tag}.status must be one of {', '.join(STATUSES)}")
        if not str(oracle.get("expected", "")).strip():
            problems.append(f"{tag}.expected must state the observable oracle or rejection reason")
        if applicability == "APPLICABLE" and status != "COVERED":
            problems.append(f"{tag}: APPLICABLE oracle must be COVERED")
        if applicability == "NOT_APPLICABLE" and status != "INVESTIGATED_AND_REJECTED":
            problems.append(f"{tag}: NOT_APPLICABLE oracle must be INVESTIGATED_AND_REJECTED")
        if applicability == "UNRESOLVED" and status != "UNRESOLVED_AND_EXPOSED":
            problems.append(f"{tag}: UNRESOLVED oracle must be UNRESOLVED_AND_EXPOSED")
        if status == "UNRESOLVED_AND_EXPOSED":
            ref = str(oracle.get("open_question_ref", ""))
            if not ref or (oq_ids is not None and ref not in oq_ids):
                problems.append(f"{tag}: unresolved oracle requires a declared Open Question")
        else:
            if not str(oracle.get("disposition_ref", "")).strip():
                problems.append(f"{tag}: terminal oracle requires disposition_ref")
    required_oracle_types = ORACLE_TYPES if strict_delivery else tuple(
        oracle_type for oracle_type in ORACLE_TYPES if oracle_type != "DELIVERY_AVAILABLE"
    )
    for oracle_type in required_oracle_types:
        if oracle_type not in by_type:
            problems.append(f"generated output contract silently omits oracle {oracle_type}")
    delivery_oracle = by_type.get("DELIVERY_AVAILABLE")
    if delivery_oracle:
        expected_delivery_state = {
            True: ("APPLICABLE", "COVERED"),
            False: ("NOT_APPLICABLE", "INVESTIGATED_AND_REJECTED"),
            "UNRESOLVED": ("UNRESOLVED", "UNRESOLVED_AND_EXPOSED"),
        }.get(delivery_scope)
        if expected_delivery_state and (
            delivery_oracle.get("applicability"), delivery_oracle.get("status")
        ) != expected_delivery_state:
            problems.append(
                "DELIVERY_AVAILABLE must follow delivery_in_scope: true -> APPLICABLE/COVERED, "
                "false -> NOT_APPLICABLE/INVESTIGATED_AND_REJECTED, and UNRESOLVED -> "
                "UNRESOLVED/UNRESOLVED_AND_EXPOSED"
            )
        if (
            delivery_scope == "UNRESOLVED"
            and delivery_oracle.get("open_question_ref")
            != block.get("delivery_scope_open_question_ref")
        ):
            problems.append(
                "DELIVERY_AVAILABLE and delivery scope must reference the same Open Question"
            )
    # These two protect the central distinction: success is not output correctness.
    for required in ("CONTENT_CORRECT", "STATUS_MATCHES_REAL_OUTPUT"):
        record = by_type.get(required)
        if record and record.get("applicability") == "NOT_APPLICABLE":
            problems.append(f"{required} cannot be NOT_APPLICABLE for a generated product artifact")
    return problems


def material_item_ids(block):
    if not isinstance(block, Mapping):
        return []
    result = [
        str(x.get("item_id")) for x in block.get("payload_inventory", [])
        if isinstance(x, Mapping) and x.get("item_id")
    ]
    result.extend(
        str(x.get("oracle_id")) for x in block.get("oracles", [])
        if isinstance(x, Mapping) and x.get("oracle_id")
    )
    return result


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("generated_output_contract"), Mapping)
