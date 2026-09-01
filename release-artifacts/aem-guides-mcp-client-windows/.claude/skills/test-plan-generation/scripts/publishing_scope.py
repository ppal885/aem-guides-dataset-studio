"""Publishing-domain scope contract.

The gate prevents a primary preset from silently expanding to every output type
and forces DITA-OT, deployment, shared paths, and explicit exclusions to resolve.
"""

from __future__ import annotations

from collections.abc import Mapping


SCHEMA_VERSION = "aem-guides-publishing-scope-v1"
PUBLISHING_MODES = ("AEM_SITES", "NATIVE_PDF", "PDF2", "HTML5", "CUSTOM", "MULTIPLE", "UNRESOLVED")
DITA_OT_STATES = ("ON", "OFF", "BOTH", "NOT_APPLICABLE", "UNRESOLVED")
AEM_SITES_IMPLEMENTATIONS = ("NATIVE", "DITA_OT", "CUSTOM", "NOT_APPLICABLE", "UNRESOLVED")
DEPLOYMENT_MODES = ("CLOUD", "ON_PREM", "BOTH", "NOT_APPLICABLE", "UNRESOLVED")


def _nonempty_strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def validate_publishing_scope(block, *, open_question_ids=None, **_kwargs):
    problems = []
    if not isinstance(block, Mapping):
        return ["publishing_scope must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"publishing_scope.schema_version must be {SCHEMA_VERSION}")
    enums = (
        ("primary_publishing_mode", PUBLISHING_MODES),
        ("enable_dita_ot_processing", DITA_OT_STATES),
        ("aem_sites_implementation", AEM_SITES_IMPLEMENTATIONS),
        ("deployment_mode", DEPLOYMENT_MODES),
    )
    unresolved_fields = []
    for field, allowed in enums:
        value = block.get(field)
        if value not in allowed:
            problems.append(f"publishing_scope.{field} must be one of {', '.join(allowed)}")
        elif value == "UNRESOLVED":
            unresolved_fields.append(field)
    preset = str(block.get("primary_preset_type", "")).strip()
    if not preset:
        problems.append("publishing_scope.primary_preset_type must name the exact preset or UNRESOLVED")
    elif preset.upper() == "UNRESOLVED":
        unresolved_fields.append("primary_preset_type")
    for field in ("in_scope", "out_of_scope", "shared_path_outputs"):
        value = block.get(field)
        if not _nonempty_strings(value):
            problems.append(f"publishing_scope.{field} must be a string list")
    # Empty exclusions/shared outputs are meaningful only with an explicit reason.
    if block.get("out_of_scope") == [] and not str(block.get("out_of_scope_reason", "")).strip():
        problems.append("empty publishing_scope.out_of_scope requires out_of_scope_reason")
    if block.get("shared_path_outputs") == [] and not str(block.get("shared_path_reason", "")).strip():
        problems.append("empty publishing_scope.shared_path_outputs requires shared_path_reason")
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    refs = block.get("open_question_refs", [])
    if not _nonempty_strings(refs):
        problems.append("publishing_scope.open_question_refs must be a string list")
        refs = []
    if unresolved_fields and not refs:
        problems.append(
            "unresolved publishing scope fields require open_question_refs: " + ", ".join(unresolved_fields)
        )
    if oq_ids is not None and any(ref not in oq_ids for ref in refs):
        problems.append("publishing_scope.open_question_refs contains an undeclared Open Question")
    stages = block.get("transformation_stages")
    required_stages = (
        "SOURCE_CONTENT", "MAP_ROOT_CONTEXT", "PRESET", "PROFILE_CONFIG",
        "FILTER_KEY_REFERENCE_RESOLUTION", "SEMANTIC_PROCESSING", "INTERMEDIATE_REPRESENTATION",
        "TRANSFORMER", "OUTPUT_BUILDER", "POST_GENERATION", "GENERATED_ARTIFACT",
        "PERSISTED_REPOSITORY_STATE", "ACTIVATION_PUBLICATION", "STATUS_HISTORY_LOGGING",
    )
    if not isinstance(stages, list):
        problems.append("publishing_scope.transformation_stages must be a list")
    else:
        by_name = {x.get("stage"): x for x in stages if isinstance(x, Mapping)}
        for name in required_stages:
            entry = by_name.get(name)
            if not entry:
                problems.append(f"publishing_scope.transformation_stages is missing {name}")
                continue
            status = entry.get("applicability")
            if status not in ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED"):
                problems.append(f"publishing stage {name} has invalid applicability")
            if not str(entry.get("reason", "")).strip():
                problems.append(f"publishing stage {name} requires a reason")
            if status == "UNRESOLVED":
                ref = entry.get("open_question_ref")
                if not ref or (oq_ids is not None and ref not in oq_ids):
                    problems.append(f"publishing stage {name} UNRESOLVED requires a declared Open Question")
    return problems


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("publishing_scope"), Mapping)
