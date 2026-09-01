"""Applicability-first semantic closure over every material behavior entity."""

from __future__ import annotations

import re
from collections.abc import Mapping


SCHEMA_VERSION = "aem-guides-semantic-closure-v1"

CLOSURE_DIMENSIONS = (
    "GOVERNING_SEMANTICS", "CONTROLLING_ATTRIBUTES", "GOVERNING_CONFIGURATION",
    "DIRECT_CONSUMERS", "SIBLING_CONSUMERS", "ALTERNATE_MECHANISMS", "PARENT_CONTEXT",
    "CHILD_CONTEXT", "HIERARCHY", "SPECIALIZATIONS", "REFERENCED_CONTENT",
    "NESTED_REFERENCED_CONTENT", "ALTERNATE_REPRESENTATION", "FALLBACK", "ABSENT_VALUE",
    "INVALID_VALUE", "POSITIVE_STATE", "NEGATIVE_STATE", "LIFECYCLE", "CROSS_SURFACE_SYNC",
    "DOWNSTREAM_PROCESSOR", "GENERATED_OUTPUT", "PERSISTED_STATE", "VERSION_APPLICABILITY",
    "DEPLOYMENT_APPLICABILITY", "ROLE_PROFILE_APPLICABILITY", "PUBLISHING_MODE",
    "BACKWARD_COMPATIBILITY", "LOCALE_APPLICABILITY", "CONTENT_IDENTITY", "NFR_RISK",
)

APPLICABILITY = ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED")
STATUSES = ("COVERED", "INVESTIGATED_AND_REJECTED", "UNRESOLVED_AND_EXPOSED")
SUBJECTS = ("PRODUCT_CONTRACT", "DITA_SEMANTICS", "ACTUAL_IMPLEMENTATION", "CURRENT_UI")


def validate_semantic_closure(
    block,
    *,
    material_entity_ids=None,
    required_dimensions=None,
    open_question_ids=None,
):
    problems = []
    if not isinstance(block, Mapping):
        return ["semantic_closure must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"semantic_closure.schema_version must be {SCHEMA_VERSION}")
    records = block.get("records")
    if not isinstance(records, list):
        return problems + ["semantic_closure.records must be a list"]
    entities = set(material_entity_ids or [])
    required = set(required_dimensions or [])
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    seen = set()
    covered_pairs = set()
    wildcard_dimensions = set()
    for index, record in enumerate(records):
        tag = f"semantic_closure.records[{index}]"
        if not isinstance(record, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        closure_id = str(record.get("closure_id", ""))
        if not re.fullmatch(r"SC-\d{2,3}", closure_id):
            problems.append(f"{tag}.closure_id must use stable SC-## form")
        elif closure_id in seen:
            problems.append(f"{tag}.closure_id duplicates {closure_id}")
        seen.add(closure_id)
        entity_ref = str(record.get("entity_ref", ""))
        if entity_ref != "*" and entity_ref not in entities:
            problems.append(f"{tag}.entity_ref must reference a material behavior node or '*' ")
        if entity_ref == "*":
            problems.append(
                f"{tag}.entity_ref '*' is not accepted; record applicability per evidence-bound "
                "material entity so one blanket decision cannot hide a gap"
            )
        dimension = record.get("dimension")
        if dimension not in CLOSURE_DIMENSIONS:
            problems.append(f"{tag}.dimension must be a canonical semantic-closure dimension")
        elif entity_ref == "*":
            wildcard_dimensions.add(dimension)
        else:
            covered_pairs.add((entity_ref, dimension))
        if record.get("subject") not in SUBJECTS:
            problems.append(f"{tag}.subject must be one of {', '.join(SUBJECTS)}")
        applicability = record.get("applicability")
        status = record.get("status")
        if applicability not in APPLICABILITY:
            problems.append(f"{tag}.applicability must be one of {', '.join(APPLICABILITY)}")
        if status not in STATUSES:
            problems.append(f"{tag}.status must be one of {', '.join(STATUSES)}")
        if not str(record.get("reason", "")).strip():
            problems.append(f"{tag}.reason must be non-empty")
        if applicability == "APPLICABLE" and status != "COVERED":
            problems.append(f"{tag}: APPLICABLE dimensions must be COVERED")
        if applicability == "NOT_APPLICABLE" and status != "INVESTIGATED_AND_REJECTED":
            problems.append(f"{tag}: NOT_APPLICABLE dimensions must be INVESTIGATED_AND_REJECTED")
        if applicability == "UNRESOLVED" and status != "UNRESOLVED_AND_EXPOSED":
            problems.append(f"{tag}: UNRESOLVED dimensions must be UNRESOLVED_AND_EXPOSED")
        if status in ("COVERED", "INVESTIGATED_AND_REJECTED"):
            if not str(record.get("disposition_ref", "")).strip():
                problems.append(f"{tag}.{status} requires disposition_ref")
        if status == "UNRESOLVED_AND_EXPOSED":
            ref = str(record.get("open_question_ref", ""))
            if not ref or (oq_ids is not None and ref not in oq_ids):
                problems.append(f"{tag}: unresolved closure requires a declared open_question_ref")

    # Every canonical dimension is considered for every material entity.  Wildcards
    # are rejected above because they cannot prove which discovered entity was reviewed.
    for entity in sorted(entities):
        for dimension in CLOSURE_DIMENSIONS:
            if dimension not in wildcard_dimensions and (entity, dimension) not in covered_pairs:
                problems.append(f"semantic closure silently omits {dimension} for {entity}")
    for dimension in sorted(required):
        if dimension not in CLOSURE_DIMENSIONS:
            problems.append(f"domain profile declares unknown closure dimension {dimension}")
        elif dimension not in wildcard_dimensions and not any(pair[1] == dimension for pair in covered_pairs):
            problems.append(f"active domain requires semantic-closure dimension {dimension}")
    return problems


def unresolved_records(block):
    if not isinstance(block, Mapping):
        return []
    return [
        record for record in block.get("records", [])
        if isinstance(record, Mapping) and record.get("status") == "UNRESOLVED_AND_EXPOSED"
    ]


def material_item_ids(block):
    if not isinstance(block, Mapping):
        return []
    return [
        str(record.get("closure_id")) for record in block.get("records", [])
        if isinstance(record, Mapping) and record.get("closure_id")
    ]


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("semantic_closure"), Mapping)
