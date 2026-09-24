"""Probe-coverage enforcement gate (UACGAP-01).

The miss-probe library (data/miss_probes.json) encodes recurring discovery misses
(output-generation entry points, attribute-value derivation, shared-platform
features, ...). Until now those probes were ADVISORY: the dimension synthesizer
surfaced the raised dimension as a REVIEW note, but nothing FAILED a plan that
ignored it - so the same class of miss could recur ticket after ticket.

This gate closes that loop. When an ACTIVE probe's signal matches the current
evidence (issue text + plan), its implied dimension MUST be dispositioned: either
covered by a clarification dimension of that axis, or explicitly handled in a
manifest `probe_dispositions` block. Otherwise the plan fails.

The asset-upload conflict probe is the exception to the generic one-axis shape:
its material dimensions are recorded in the gate's structured contract so a broad
coverage axis cannot collapse content, conflict, routing, deployment, or document scope.

SHADOW probes stay advisory (never hard-fail). Plans whose evidence matches no
probe are unaffected (backward-compatible).

Generic only. Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "PROBE COVERAGE GATE:"
DISPOSITION_BLOCK = "probe_dispositions"
VALID_DISPOSITIONS = {"COVERED", "REJECTED", "NOT_APPLICABLE", "DEFERRED_OPEN_QUESTION"}
_PROBE_ID_RE = re.compile(r"\bMP-\d+\b")

# MP-011 is deliberately implemented inside the existing miss-probe gate rather
# than as a second asset-specific pipeline.  Its contract is activated only after
# the probe library matches asset-upload/conflict evidence.
ASSET_UPLOAD_CONFLICT_AXIS = "ASSET_UPLOAD_CONFLICT"
ASSET_UPLOAD_CONFLICT_BLOCK = "asset_upload_conflict"
ASSET_UPLOAD_CONFLICT_SCHEMA = "aem-guides-asset-upload-conflict-v1"
ASSET_DISPOSITIONS = {
    "COVERED",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
    "NOT_APPLICABLE",
    "PRESERVED",
}
ASSET_INVESTIGATION_ONLY_DISPOSITIONS = {
    "OUT_OF_SCOPE",
    "NOT_APPLICABLE",
    "PRESERVED",
}
ASSET_SURFACE_OWNERS = {"NATIVE_AEM_ASSETS", "AEM_GUIDES", "UNRESOLVED"}
NATIVE_AEM_ASSETS_ACTIONS = {
    "createversion": "Create Version",
    "overwritefiles": "Overwrite Files",
}
ASSET_DIMENSIONS = (
    "content_identity_duplicate_detection",
    "name_path_conflict",
    "request_handler_route",
)
ASSET_DOCUMENTATION_TARGETS = (*ASSET_DIMENSIONS, "affected_behavior", "baseline_action")
_UNRESOLVED_VALUES = {"", "unknown", "unresolved", "tbd", "n/a", "not applicable"}
_CONFIG_PROVIDER_SIGNAL_RE = re.compile(
    r"\b(?:config(?:uration)?\s+(?:provider|class)|osgi)\b|"
    r"\b(?:[A-Za-z_]\w*\.){2,}[A-Za-z_]\w*\b",
    re.I,
)
_HANDLER_ROUTE_SIGNAL_RE = re.compile(
    r"\b(?:servlet|handler|upload\s+route|request\s+route|endpoint|create\s+asset)\b",
    re.I,
)
_URL_RE = re.compile(r"\bhttps?://\S+", re.I)
_DEPLOYMENT_PATTERNS = (
    (
        "CLOUD_SERVICE",
        re.compile(
            r"\b(?:aem\s+as\s+a\s+cloud\s+service|aem\s+cloud\s+service|"
            r"cloud\s+service|cloud)\b",
            re.I,
        ),
    ),
    (
        "ON_PREMISE",
        re.compile(r"\b(?:on[-\s]?premise|aem\s+6\.?5(?:\s+lts)?)\b", re.I),
    ),
)
_PARITY_RELATION_FIELDS = ("parity_with", "difference_from")
_GENERIC_SCOPE_SURFACE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:dialog|upload\s+dialog|generic\s+(?:dialog|screen|ui)|ui|screen)\s*$",
    re.I,
)
_BROAD_PATH_CATEGORY_RE = re.compile(
    r"^\s*(?:non[-\s]?guides(?:\s+(?:path|flow|behavior))?|"
    r"other\s+products?(?:\s+(?:path|flow|behavior))?|generic\s+(?:upload\s+)?"
    r"(?:path|flow|behavior)|(?:upload\s+)?dialog\s+behavior)\s*$",
    re.I,
)
_GENERIC_BASELINE_ACTION_RE = re.compile(
    r"^\s*(?:the\s+)?(?:dialog|upload\s+dialog|all\s+dialog\s+actions?|all\s+actions?)\s*$",
    re.I,
)
_GENERIC_SCOPE_REASON_RE = re.compile(
    r"^\s*(?:out\s+of\s+scope|not\s+applicable|unaffected|not\s+changed|"
    r"separate\s+feature)\s*\.?\s*$",
    re.I,
)
_NATIVE_AEM_ASSETS_SURFACE_RE = re.compile(r"\baem\s+assets\b", re.I)
_GUIDES_SURFACE_RE = re.compile(r"\b(?:aem\s+)?guides\b", re.I)
_REPLACE_ACTION_RE = re.compile(r"\breplace\b", re.I)
_OVERWRITE_ACTION_RE = re.compile(r"\b(?:overwrite|replace)\b", re.I)
_CREATE_VERSION_ACTION_RE = re.compile(r"\bcreate\s+version\b", re.I)


def _load_miss_probe_library():
    path = Path(__file__).with_name("miss_probe_library.py")
    spec = importlib.util.spec_from_file_location("miss_probe_library", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _asset_problem(message: str) -> str:
    return _problem(f"asset-upload conflict contract: {message}")


def _issue_text(manifest: dict[str, Any]) -> str:
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if not isinstance(issue, dict):
        return ""
    parts = [str(issue.get("summary", "")), str(issue.get("description", ""))]
    labels = issue.get("labels")
    if isinstance(labels, list):
        parts.append(" ".join(str(x) for x in labels))
    comps = issue.get("components")
    if isinstance(comps, list):
        parts.append(" ".join(str(x) for x in comps))
    return "\n".join(parts)


def _text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for nested in value.values():
            values.extend(_text_values(nested))
        return values
    if isinstance(value, (list, tuple)):
        values = []
        for nested in value:
            values.extend(_text_values(nested))
        return values
    return []


def _asset_scope_text(plan_body: str, manifest: dict[str, Any]) -> str:
    """Use product-facing scope/evidence, not gate output, to find deployments."""
    parts = [plan_body, _issue_text(manifest)]
    for key in (
        "accepted_uac",
        "contract_facts",
        "behavior_model",
        "scope_applicability",
    ):
        parts.extend(_text_values(manifest.get(key)))
    return "\n".join(part for part in parts if part)


def _nonempty_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _meaningful(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in _UNRESOLVED_VALUES


def _concrete_scope_reason(value: object) -> bool:
    return _meaningful(value) and not _GENERIC_SCOPE_REASON_RE.match(str(value))


def _normalise_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _deployment_key(value: object) -> str:
    normalized = _normalise_key(value)
    if normalized in {
        "cloud",
        "cloudservice",
        "aemcloudservice",
        "aemasacloudservice",
        "aemcs",
    }:
        return "CLOUD_SERVICE"
    if normalized in {
        "onpremise",
        "onprem",
        "aem65",
        "aem65lts",
    }:
        return "ON_PREMISE"
    return normalized.upper()


def _detected_deployments(plan_body: str, manifest: dict[str, Any]) -> set[str]:
    scope_text = _asset_scope_text(plan_body, manifest)
    return {
        deployment
        for deployment, pattern in _DEPLOYMENT_PATTERNS
        if pattern.search(scope_text)
    }


def _validate_asset_dimension(
    name: str,
    value: object,
    *,
    requires_handler_evidence: bool,
    requires_config_separation: bool,
) -> list[str]:
    tag = f"{ASSET_UPLOAD_CONFLICT_BLOCK}.dimensions.{name}"
    if not isinstance(value, dict):
        return [_asset_problem(f"{tag} must be an object with a disposition and reason")]

    problems: list[str] = []
    disposition = str(value.get("disposition", "")).strip().upper()
    if disposition not in ASSET_DISPOSITIONS:
        problems.append(
            _asset_problem(
                f"{tag}.disposition must be one of {', '.join(sorted(ASSET_DISPOSITIONS))}"
            )
        )
    if not _meaningful(value.get("reason")):
        problems.append(_asset_problem(f"{tag}.reason must explain the disposition"))
    if disposition == "COVERED" and not _nonempty_strings(value.get("ac_refs")):
        problems.append(_asset_problem(f"{tag} COVERED requires one or more ac_refs"))
    if disposition == "OPEN_QUESTION" and not _meaningful(value.get("open_question_ref")):
        problems.append(_asset_problem(f"{tag} OPEN_QUESTION requires open_question_ref"))
    if disposition in ASSET_INVESTIGATION_ONLY_DISPOSITIONS:
        if not _concrete_scope_reason(value.get("reason")):
            problems.append(
                _asset_problem(
                    f"{tag} {disposition} requires a concrete, evidence-based reason"
                )
            )
        if not _nonempty_strings(value.get("evidence_refs")):
            problems.append(
                _asset_problem(
                    f"{tag} {disposition} requires evidence_refs; investigation "
                    "disposition is not automatic acceptance coverage"
                )
            )

    if name != "request_handler_route":
        return problems

    if requires_handler_evidence and disposition not in {"COVERED", "OPEN_QUESTION"}:
        problems.append(
            _asset_problem(
                f"{tag} names request-routing evidence and must be COVERED with dispatch "
                "evidence or OPEN_QUESTION; a configuration/class label cannot be scoped out "
                "as handler proof"
            )
        )
    if requires_config_separation and not _nonempty_strings(value.get("configuration_artifacts")):
        problems.append(
            _asset_problem(
                f"{tag} must record configuration_artifacts separately when a configuration "
                "provider or class is named"
            )
        )
    if disposition != "COVERED":
        return problems

    actual = value.get("actual_handler")
    if not isinstance(actual, dict):
        return problems + [
            _asset_problem(
                f"{tag} COVERED requires actual_handler with handler, route, source_ref, "
                "and evidence_kind REQUEST_DISPATCH"
            )
        ]
    for field in ("handler", "route", "source_ref"):
        if not _meaningful(actual.get(field)):
            problems.append(
                _asset_problem(
                    f"{tag}.actual_handler.{field} must identify inspected request-dispatch evidence"
                )
            )
    if actual.get("evidence_kind") != "REQUEST_DISPATCH":
        problems.append(
            _asset_problem(
                f"{tag}.actual_handler.evidence_kind must be REQUEST_DISPATCH; "
                "configuration evidence is not request-handler proof"
            )
        )
    return problems


def _validate_deployments(
    block: dict[str, Any],
    *,
    detected: set[str],
) -> tuple[list[str], set[str]]:
    rows = block.get("deployments")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        return [
            _asset_problem(f"{ASSET_UPLOAD_CONFLICT_BLOCK}.deployments must be a list")
        ], set()

    problems: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        tag = f"{ASSET_UPLOAD_CONFLICT_BLOCK}.deployments[{index}]"
        if not isinstance(row, dict):
            problems.append(_asset_problem(f"{tag} must be an object"))
            continue
        deployment = _deployment_key(row.get("deployment"))
        if not deployment or deployment.casefold() in _UNRESOLVED_VALUES:
            problems.append(_asset_problem(f"{tag}.deployment must name a deployment model"))
            continue
        if deployment in seen:
            problems.append(_asset_problem(f"{tag}.deployment duplicates {deployment}"))
        seen.add(deployment)
        disposition = str(row.get("disposition", "")).strip().upper()
        if disposition not in ASSET_DISPOSITIONS:
            problems.append(
                _asset_problem(
                    f"{tag}.disposition must be one of {', '.join(sorted(ASSET_DISPOSITIONS))}"
                )
            )
        if not _meaningful(row.get("reason")):
            problems.append(_asset_problem(f"{tag}.reason must explain the disposition"))
        if disposition == "COVERED":
            if not _nonempty_strings(row.get("ac_refs")):
                problems.append(_asset_problem(f"{tag} COVERED requires one or more ac_refs"))
            if not _nonempty_strings(row.get("evidence_refs")):
                problems.append(
                    _asset_problem(
                        f"{tag} COVERED requires evidence_refs; deployment parity cannot be inferred"
                    )
                )
        if disposition == "OPEN_QUESTION" and not _meaningful(row.get("open_question_ref")):
            problems.append(_asset_problem(f"{tag} OPEN_QUESTION requires open_question_ref"))
        if disposition in ASSET_INVESTIGATION_ONLY_DISPOSITIONS:
            if not _concrete_scope_reason(row.get("reason")):
                problems.append(
                    _asset_problem(
                        f"{tag} {disposition} requires a concrete, evidence-based reason"
                    )
                )
            if not _nonempty_strings(row.get("evidence_refs")):
                problems.append(
                    _asset_problem(
                        f"{tag} {disposition} requires evidence_refs; an independently "
                        "dispositioned deployment does not automatically need an AC"
                    )
                )
        for relationship in _PARITY_RELATION_FIELDS:
            if _meaningful(row.get(relationship)) and not _nonempty_strings(
                row.get("relationship_evidence_refs")
            ):
                problems.append(
                    _asset_problem(
                        f"{tag}.{relationship} requires relationship_evidence_refs; "
                        "do not infer deployment parity or a difference"
                    )
                )

    for deployment in sorted(detected - seen):
        problems.append(
            _asset_problem(
                f"named deployment {deployment} is not independently dispositioned in "
                f"{ASSET_UPLOAD_CONFLICT_BLOCK}.deployments"
            )
        )
    return problems, seen


def _validate_affected_behavior(
    block: dict[str, Any],
    *,
    deployments: set[str],
) -> list[str]:
    tag = f"{ASSET_UPLOAD_CONFLICT_BLOCK}.affected_behavior"
    behavior = block.get("affected_behavior")
    if not isinstance(behavior, dict):
        return [
            _asset_problem(
                f"{tag} must name the affected deployment, product surface, and exact behavior path"
            )
        ]

    problems: list[str] = []
    disposition = str(behavior.get("disposition", "")).strip().upper()
    if disposition not in ASSET_DISPOSITIONS:
        problems.append(
            _asset_problem(
                f"{tag}.disposition must be one of {', '.join(sorted(ASSET_DISPOSITIONS))}"
            )
        )
    deployment = _deployment_key(behavior.get("deployment"))
    if not deployment or deployment.casefold() in _UNRESOLVED_VALUES:
        problems.append(_asset_problem(f"{tag}.deployment must name the affected deployment"))
    elif deployment not in deployments:
        problems.append(
            _asset_problem(
                f"{tag}.deployment is not independently dispositioned in "
                f"{ASSET_UPLOAD_CONFLICT_BLOCK}.deployments"
            )
        )
    product_surface = behavior.get("product_surface")
    if not _meaningful(product_surface):
        problems.append(_asset_problem(f"{tag}.product_surface must be non-empty"))
    elif _GENERIC_SCOPE_SURFACE_RE.match(str(product_surface)):
        problems.append(
            _asset_problem(
                f"{tag}.product_surface must name the affected product surface, not a generic dialog"
            )
        )
    surface_owner = str(behavior.get("surface_owner", "")).strip().upper()
    if surface_owner not in ASSET_SURFACE_OWNERS:
        problems.append(
            _asset_problem(
                f"{tag}.surface_owner must be one of {', '.join(sorted(ASSET_SURFACE_OWNERS))}"
            )
        )
    ownership_evidence = _nonempty_strings(
        behavior.get("surface_ownership_evidence_refs")
    )
    if surface_owner == "NATIVE_AEM_ASSETS":
        if not _NATIVE_AEM_ASSETS_SURFACE_RE.search(str(product_surface or "")):
            problems.append(
                _asset_problem(
                    f"{tag}.product_surface must name AEM Assets when surface_owner is "
                    "NATIVE_AEM_ASSETS"
                )
            )
        if _GUIDES_SURFACE_RE.search(str(product_surface or "")):
            problems.append(
                _asset_problem(
                    f"{tag}.product_surface cannot credit a native AEM Assets action to Guides"
                )
            )
        product_action = behavior.get("product_action")
        if not _meaningful(product_action):
            problems.append(
                _asset_problem(
                    f"{tag}.product_action must name the native AEM Assets action"
                )
            )
        elif _REPLACE_ACTION_RE.search(str(product_action)):
            problems.append(
                _asset_problem(
                    f"{tag}.product_action must use the source-backed native AEM Assets "
                    "action name, not Replace"
                )
            )
        elif _CREATE_VERSION_ACTION_RE.search(
            f"{product_action or ''} {behavior.get('path') or ''}"
        ) and _normalise_key(product_action) != "createversion":
            problems.append(
                _asset_problem(
                    f"{tag}.product_action must name the native version flow "
                    "Create Version"
                )
            )
        elif _OVERWRITE_ACTION_RE.search(
            f"{product_action or ''} {behavior.get('path') or ''}"
        ) and _normalise_key(product_action) != "overwritefiles":
            problems.append(
                _asset_problem(
                    f"{tag}.product_action must name the native overwrite flow "
                    "Overwrite Files"
                )
            )
        if not ownership_evidence:
            problems.append(
                _asset_problem(
                    f"{tag}.surface_ownership_evidence_refs must source native AEM Assets ownership"
                )
            )
    elif surface_owner == "AEM_GUIDES":
        if _NATIVE_AEM_ASSETS_SURFACE_RE.search(str(product_surface or "")):
            problems.append(
                _asset_problem(
                    f"{tag}.product_surface names AEM Assets and cannot be credited to "
                    "AEM_GUIDES"
                )
            )
        if not ownership_evidence:
            action_key = _normalise_key(behavior.get("product_action"))
            native_action = NATIVE_AEM_ASSETS_ACTIONS.get(action_key)
            if native_action:
                problems.append(
                    _asset_problem(
                        f"{tag}.surface_ownership_evidence_refs must prove a Guides-owned "
                        f"surface before {native_action} can be credited to AEM_GUIDES"
                    )
                )
            else:
                problems.append(
                    _asset_problem(
                        f"{tag}.surface_ownership_evidence_refs must prove a Guides-owned surface"
                    )
                )
    elif surface_owner == "UNRESOLVED" and disposition != "OPEN_QUESTION":
        problems.append(
            _asset_problem(
                f"{tag}.surface_owner UNRESOLVED requires disposition OPEN_QUESTION"
            )
        )
    path = behavior.get("path")
    if not _meaningful(path):
        problems.append(_asset_problem(f"{tag}.path must name the affected behavior path"))
    elif _BROAD_PATH_CATEGORY_RE.match(str(path)):
        problems.append(
            _asset_problem(
                f"{tag}.path must name an exact behavior path, not an inferred broad category"
            )
        )
    if not _meaningful(behavior.get("reason")):
        problems.append(_asset_problem(f"{tag}.reason must explain the disposition"))
    if disposition == "COVERED":
        if not _nonempty_strings(behavior.get("ac_refs")):
            problems.append(_asset_problem(f"{tag} COVERED requires one or more ac_refs"))
        if not _nonempty_strings(behavior.get("evidence_refs")):
            problems.append(
                _asset_problem(
                    f"{tag} COVERED requires evidence_refs for the affected deployment/path"
                )
            )
    if disposition == "OPEN_QUESTION" and not _meaningful(
        behavior.get("open_question_ref")
    ):
        problems.append(_asset_problem(f"{tag} OPEN_QUESTION requires open_question_ref"))
    if disposition in ASSET_INVESTIGATION_ONLY_DISPOSITIONS:
        if not _concrete_scope_reason(behavior.get("reason")):
            problems.append(
                _asset_problem(
                    f"{tag} {disposition} requires a concrete, evidence-based reason"
                )
            )
        if not _nonempty_strings(behavior.get("evidence_refs")):
            problems.append(
                _asset_problem(
                    f"{tag} {disposition} requires evidence_refs; disposition does not "
                    "automatically require acceptance coverage"
                )
            )
    return problems


def _validate_baseline_actions(block: dict[str, Any]) -> list[str]:
    block_tag = f"{ASSET_UPLOAD_CONFLICT_BLOCK}.baseline_actions"
    if "baseline_actions" not in block:
        return [
            _asset_problem(
                f"{block_tag} must be declared to separate unaffected actions from the changed path"
            )
        ]
    actions = block.get("baseline_actions")
    if not isinstance(actions, list):
        return [_asset_problem(f"{block_tag} must be a list")]
    if not actions:
        problems: list[str] = []
        if not _concrete_scope_reason(block.get("baseline_actions_reason")):
            problems.append(
                _asset_problem(
                    f"{block_tag} empty list requires baseline_actions_reason grounded in current evidence"
                )
            )
        if not _nonempty_strings(block.get("baseline_actions_evidence_refs")):
            problems.append(
                _asset_problem(
                    f"{block_tag} empty list requires baseline_actions_evidence_refs"
                )
            )
        return problems

    problems = []
    for index, action in enumerate(actions):
        tag = f"{block_tag}[{index}]"
        if not isinstance(action, dict):
            problems.append(_asset_problem(f"{tag} must be an object"))
            continue
        action_name = action.get("action")
        if not _meaningful(action_name):
            problems.append(_asset_problem(f"{tag}.action must name a baseline action"))
        elif _GENERIC_BASELINE_ACTION_RE.match(str(action_name)):
            problems.append(
                _asset_problem(
                    f"{tag}.action must name a specific action, not a generic dialog"
                )
            )
        relation = str(action.get("relation_to_affected_path", "")).strip().upper()
        if relation not in {"UNAFFECTED", "AFFECTED", "UNRESOLVED"}:
            problems.append(
                _asset_problem(
                    f"{tag}.relation_to_affected_path must be UNAFFECTED, AFFECTED, or UNRESOLVED"
                )
            )
        disposition = str(action.get("disposition", "")).strip().upper()
        if disposition not in ASSET_DISPOSITIONS:
            problems.append(
                _asset_problem(
                    f"{tag}.disposition must be one of {', '.join(sorted(ASSET_DISPOSITIONS))}"
                )
            )
        if not _meaningful(action.get("reason")):
            problems.append(_asset_problem(f"{tag}.reason must explain the disposition"))
        if disposition == "COVERED":
            if not _nonempty_strings(action.get("ac_refs")):
                problems.append(_asset_problem(f"{tag} COVERED requires one or more ac_refs"))
            if not _nonempty_strings(action.get("evidence_refs")):
                problems.append(
                    _asset_problem(
                        f"{tag} COVERED requires evidence_refs for the named baseline action"
                    )
                )
        if disposition == "OPEN_QUESTION" and not _meaningful(
            action.get("open_question_ref")
        ):
            problems.append(_asset_problem(f"{tag} OPEN_QUESTION requires open_question_ref"))
        if disposition in ASSET_INVESTIGATION_ONLY_DISPOSITIONS:
            if not _concrete_scope_reason(action.get("reason")):
                problems.append(
                    _asset_problem(
                        f"{tag} {disposition} requires a concrete, evidence-based reason"
                    )
                )
            if not _nonempty_strings(action.get("evidence_refs")):
                problems.append(
                    _asset_problem(
                        f"{tag} {disposition} requires evidence_refs; a baseline action "
                        "does not automatically need acceptance coverage"
                    )
                )
    return problems


def _validate_documentation_sources(
    block: dict[str, Any],
    *,
    deployments: set[str],
) -> list[str]:
    if "documentation_sources" not in block:
        return [
            _asset_problem(
                f"{ASSET_UPLOAD_CONFLICT_BLOCK}.documentation_sources must be declared; "
                "use an empty list only when no documentation supports the contract"
            )
        ]
    sources = block.get("documentation_sources")
    if not isinstance(sources, list):
        return [
            _asset_problem(
                f"{ASSET_UPLOAD_CONFLICT_BLOCK}.documentation_sources must be a list"
            )
        ]

    problems: list[str] = []
    for index, source in enumerate(sources):
        tag = f"{ASSET_UPLOAD_CONFLICT_BLOCK}.documentation_sources[{index}]"
        if not isinstance(source, dict):
            problems.append(_asset_problem(f"{tag} must be an object"))
            continue
        if not _meaningful(source.get("source_ref")):
            problems.append(_asset_problem(f"{tag}.source_ref must be non-empty"))
        deployment_scope = {
            _deployment_key(value) for value in _nonempty_strings(source.get("deployment_scope"))
        }
        surface_scope = {
            _normalise_key(value) for value in _nonempty_strings(source.get("surface_scope"))
        }
        if not deployment_scope:
            problems.append(
                _asset_problem(
                    f"{tag}.deployment_scope must name every deployment the documentation covers"
                )
            )
        if not surface_scope:
            problems.append(
                _asset_problem(
                    f"{tag}.surface_scope must name every product surface the documentation covers"
                )
            )
        supports = source.get("supports")
        if supports is None:
            supports = []
        if not isinstance(supports, list):
            problems.append(_asset_problem(f"{tag}.supports must be a list"))
            continue
        for support_index, support in enumerate(supports):
            support_tag = f"{tag}.supports[{support_index}]"
            if not isinstance(support, dict):
                problems.append(_asset_problem(f"{support_tag} must be an object"))
                continue
            dimension = str(support.get("dimension", "")).strip()
            if dimension not in ASSET_DOCUMENTATION_TARGETS:
                problems.append(
                    _asset_problem(
                        f"{support_tag}.dimension must be one of "
                        f"{', '.join(ASSET_DOCUMENTATION_TARGETS)}"
                    )
                )
            deployment = _deployment_key(support.get("deployment"))
            surface = _normalise_key(support.get("surface"))
            if not deployment:
                problems.append(_asset_problem(f"{support_tag}.deployment must be non-empty"))
            elif deployment not in deployments:
                problems.append(
                    _asset_problem(
                        f"{support_tag}.deployment is not independently dispositioned"
                    )
                )
            elif deployment not in deployment_scope:
                problems.append(
                    _asset_problem(
                        f"{support_tag} maps documentation outside its deployment_scope; "
                        "deployment-specific documentation cannot establish another deployment"
                    )
                )
            if not surface:
                problems.append(_asset_problem(f"{support_tag}.surface must be non-empty"))
            elif surface not in surface_scope:
                problems.append(
                    _asset_problem(
                        f"{support_tag} maps documentation outside its surface_scope; "
                        "product-specific documentation cannot establish another surface"
                    )
                )
    return problems


def _validate_asset_upload_conflict_contract(
    plan_body: str,
    manifest: dict[str, Any],
) -> list[str]:
    block = manifest.get(ASSET_UPLOAD_CONFLICT_BLOCK)
    if not isinstance(block, dict):
        return [
            _asset_problem(
                f"active {ASSET_UPLOAD_CONFLICT_AXIS} evidence requires an "
                f"{ASSET_UPLOAD_CONFLICT_BLOCK} block"
            )
        ]
    problems: list[str] = []
    if block.get("schema_version") != ASSET_UPLOAD_CONFLICT_SCHEMA:
        problems.append(
            _asset_problem(
                f"{ASSET_UPLOAD_CONFLICT_BLOCK}.schema_version must be "
                f"{ASSET_UPLOAD_CONFLICT_SCHEMA}"
            )
        )
    dimensions = block.get("dimensions")
    if not isinstance(dimensions, dict):
        return problems + [
            _asset_problem(f"{ASSET_UPLOAD_CONFLICT_BLOCK}.dimensions must be an object")
        ]
    scope_text = _asset_scope_text(plan_body, manifest)
    handler_signal = bool(_HANDLER_ROUTE_SIGNAL_RE.search(scope_text))
    config_signal = bool(
        _CONFIG_PROVIDER_SIGNAL_RE.search(_URL_RE.sub("", scope_text))
    )
    for name in ASSET_DIMENSIONS:
        problems.extend(
            _validate_asset_dimension(
                name,
                dimensions.get(name),
                requires_handler_evidence=(
                    handler_signal or config_signal
                    if name == "request_handler_route"
                    else False
                ),
                requires_config_separation=config_signal if name == "request_handler_route" else False,
            )
        )
    deployment_problems, deployments = _validate_deployments(
        block,
        detected=_detected_deployments(plan_body, manifest),
    )
    problems.extend(deployment_problems)
    problems.extend(_validate_affected_behavior(block, deployments=deployments))
    problems.extend(_validate_baseline_actions(block))
    problems.extend(_validate_documentation_sources(block, deployments=deployments))
    return problems


def _evidence_pairs(plan_body: str, manifest: dict[str, Any]) -> list[tuple[str, str]]:
    return [("issue", _issue_text(manifest)), ("plan", plan_body or "")]


def activated_probes(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the ACTIVE probes whose signal matches the current evidence.

    Each item: {probe_id, axis, candidate, shadow}. SHADOW probes are included with
    shadow=True so callers can report them without hard-failing.
    """
    manifest_data = manifest if isinstance(manifest, dict) else {}
    try:
        mpl = _load_miss_probe_library()
        candidates = mpl.candidates_for(_evidence_pairs(plan_body, manifest_data))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        pid = str(c.get("probe_id") or "")
        if not pid:
            m = _PROBE_ID_RE.search(str(c.get("reason", "")))
            pid = m.group(0) if m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({
            "probe_id": pid,
            "axis": str(c.get("dimension") or "").upper(),
            "candidate": str(c.get("candidate") or ""),
            "shadow": bool(c.get("non_authoritative")),
        })
    return out


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return any(not p["shadow"] for p in activated_probes(plan_body, manifest))


def _covered_axes(manifest: dict[str, Any]) -> set[str]:
    """Axes the plan has already reasoned about: clarification dimensions and any
    coverage_hypotheses dimensions."""
    axes: set[str] = set()
    clar = manifest.get("clarification") if isinstance(manifest, dict) else None
    if isinstance(clar, dict):
        for dim in clar.get("dimension_space") or []:
            if isinstance(dim, dict) and dim.get("material", True) and dim.get("resolution"):
                axes.add(str(dim.get("axis", "")).upper())
    for hyp in (manifest.get("coverage_hypotheses") or []) if isinstance(manifest, dict) else []:
        if isinstance(hyp, dict) and hyp.get("dimension"):
            axes.add(str(hyp.get("dimension", "")).upper())
            if hyp.get("implied_dimension_axis"):
                axes.add(str(hyp["implied_dimension_axis"]).upper())
    # UACGAP-06: a populated entry_point_equivalence block is a first-class way to
    # disposition the ENTRY_POINT axis (its own gate validates the block's shape),
    # so it satisfies an ENTRY_POINT probe just like a clarification dimension.
    epe = manifest.get("entry_point_equivalence") if isinstance(manifest, dict) else None
    if isinstance(epe, dict) and isinstance(epe.get("candidates"), list) and epe["candidates"]:
        axes.update({"ENTRY_POINT", "SHARED_SERVICE_ENTRY_POINTS"})
    # The changed_service_neighbourhood block is the structured contract for the
    # shared-service probes; coverage_forcing validates its shape.
    csn = manifest.get("changed_service_neighbourhood") if isinstance(manifest, dict) else None
    if isinstance(csn, dict) and csn:
        axes.update({
            "SHARED_SERVICE_ENTRY_POINTS",
            "CONDITIONAL_SKIP_PRESERVED_OUTCOMES",
            "CALLER_SCOPED_LOOKUP_PERMISSIONS",
        })
    axes.discard("")
    return axes


def _dispositions(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in (manifest.get(DISPOSITION_BLOCK) or []) if isinstance(manifest, dict) else []:
        if isinstance(item, dict) and item.get("probe_id"):
            out[str(item["probe_id"])] = item
    return out


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    probes = [p for p in activated_probes(plan_body, manifest_data) if not p["shadow"]]
    if not probes:
        return []
    covered = _covered_axes(manifest_data)
    disp = _dispositions(manifest_data)
    problems: list[str] = []
    if any(p["axis"] == ASSET_UPLOAD_CONFLICT_AXIS for p in probes):
        problems.extend(_validate_asset_upload_conflict_contract(plan_body, manifest_data))
    for p in probes:
        pid, axis = p["probe_id"], p["axis"]
        if axis == ASSET_UPLOAD_CONFLICT_AXIS:
            # The structured contract above is this probe's required
            # disposition; a broad coverage-hypothesis axis cannot replace it.
            continue
        if axis in covered:
            continue
        d = disp.get(pid)
        if isinstance(d, dict):
            verdict = str(d.get("disposition", "")).strip().upper()
            if verdict in VALID_DISPOSITIONS and str(d.get("reason", "")).strip():
                continue
        problems.append(_problem(
            f"probe {pid} ({axis}) matched the evidence but its dimension is not covered - "
            f"record a coverage hypothesis with implied_dimension_axis {axis}, "
            f"a resolved clarification dimension, or a "
            f"{DISPOSITION_BLOCK} entry {{probe_id:{pid}, disposition, reason}} explicitly "
            f"rejecting or scoping it out"
        ))
    return problems


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    probes = activated_probes(plan_body, manifest)
    if not probes:
        return "probe coverage gate: no probe activated"
    active = [p["probe_id"] for p in probes if not p["shadow"]]
    shadow = [p["probe_id"] for p in probes if p["shadow"]]
    parts = [f"probe coverage gate: {len(active)} active probe(s) {active}"]
    if shadow:
        parts.append(f"shadow (advisory) {shadow}")
    problems = validate(plan_body, manifest)
    parts.append("CLEAN" if not problems else f"{len(problems)} uncovered")
    return " | ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe-coverage enforcement gate")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    plan_body = args.plan.read_text(encoding="utf-8") if args.plan.exists() else ""
    manifest_data = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    problems = validate(plan_body, manifest_data)
    if problems:
        for p in problems:
            print(p)
        return 1
    print(summarize(plan_body, manifest_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
