"""Build RAG records from UI states/transitions/flows.

Each record is structured TEXT (for semantic search) + metadata. Raw screenshots
stay as referenced evidence, never as primary RAG content. Every record carries
an authority of UI_OBSERVATION or OBSERVED_UI_FLOW so the downstream Test Plan
system can distinguish it from OFFICIAL_PRODUCT_DOCUMENTATION / ACCEPTED_UAC /
SPECIFICATION and refuse to mint a formal AC from a UI observation alone.
"""

import hashlib
import json

from .surface_resolution import LEGACY_UI, is_current_product_contract

RECORD_TYPES = (
    "UI_SURFACE", "UI_CAPABILITY", "UI_STATE", "UI_TRANSITION", "UI_FLOW",
    "UI_CURRENTNESS", "UI_SURFACE_IDENTITY", "UI_SURFACE_RELATION", "UI_HIERARCHY",
    "UI_CONFIGURATION_DEPENDENCY",
)
AUTHORITY_STATE = "UI_OBSERVATION"
AUTHORITY_FLOW = "OBSERVED_UI_FLOW"


def _hash(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record(record_type, doc_text, metadata):
    rid = _hash(record_type + "|" + doc_text)
    md = {"record_type": record_type, "content_hash": rid}
    md.update(metadata)
    return {"id": rid, "document": doc_text, "metadata": md}


def state_record(state):
    """UI_STATE record: a human/semantic sentence + structured metadata."""
    caps = ", ".join(state.visible_capabilities) or "none observed"
    text = (
        f"UI state on the {state.product} {state.surface or 'UNKNOWN'} surface. "
        f"Route identity: {state.route_identity or 'UNKNOWN'}. "
        f"Region {state.region or 'UNKNOWN'}, container {state.container or 'UNKNOWN'}. "
        f"Left panel: {state.active_left_panel or 'none'}; right panel: {state.active_right_panel or 'none'}; "
        f"editor mode: {state.active_editor_mode or 'n/a'}; active tab: {state.active_tab or 'n/a'}. "
        f"Open dialog: {state.open_dialog or 'none'}; open menu: {state.open_menu or 'none'}. "
        f"Entity context: {state.active_entity_type or 'none'}; empty state: {state.empty_state or 'none'}. "
        f"Visible capabilities: {caps}."
    )
    md = {
        "product": state.product, "surface": state.surface, "region": state.region,
        "container": state.container, "editor_mode": state.active_editor_mode,
        "entity_context": state.active_entity_type, "empty_state": state.empty_state,
        "state_id": state.state_id, "capabilities": json.dumps(state.visible_capabilities),
        "disabled_capabilities": json.dumps(state.disabled_capabilities),
        "product_version": state.product_version, "currentness": state.currentness,
        "source_screenshot": state.screenshot_id, "authority": AUTHORITY_STATE,
        "url_normalized": state.url_normalized, "route_identity": state.route_identity,
    }
    return _record("UI_STATE", text, md)


def surface_identity_record(surface):
    """Route-scoped capability identity; legacy placement is never current truth."""
    lifecycle_note = (
        "This is a legacy UI placement and historical evidence only; it must not be used "
        "as the current product contract."
        if surface.lifecycle == LEGACY_UI
        else "This surface identity remains route-scoped and must not be merged by capability name."
    )
    text = (
        f"Capability {surface.capability} is observed on surface {surface.surface or 'UNKNOWN'} "
        f"at route {surface.route_identity or 'UNKNOWN'}, classified as {surface.lifecycle}. "
        f"{lifecycle_note}"
    )
    md = {
        "surface_id": surface.surface_id,
        "capability": surface.capability,
        "surface": surface.surface,
        "route_identity": surface.route_identity,
        "lifecycle": surface.lifecycle,
        "environment": surface.environment,
        "product_version": surface.product_version,
        "evidence_ids": json.dumps(list(surface.evidence_ids)),
        "is_current_product_contract": is_current_product_contract(surface),
        "authority": AUTHORITY_STATE,
    }
    return _record("UI_SURFACE_IDENTITY", text, md)


def surface_relation_record(relation):
    """Evidence-backed lifecycle relation between two route-scoped surfaces."""
    text = (
        f"UI surface {relation.source_surface_id} {relation.relation} "
        f"{relation.target_surface_id}. This lifecycle relation is supported by evidence "
        f"{', '.join(relation.evidence_ids)}."
    )
    md = {
        "from_surface_id": relation.source_surface_id,
        "to_surface_id": relation.target_surface_id,
        "relation": relation.relation,
        "evidence_ids": json.dumps(list(relation.evidence_ids)),
        "authority": AUTHORITY_STATE,
    }
    return _record("UI_SURFACE_RELATION", text, md)


def hierarchy_record(parent, relation, child, *, hierarchy_type="PRODUCT"):
    """Deterministic product/capability hierarchy edge for graph retrieval."""
    text = f"{hierarchy_type} hierarchy: {parent} {relation} {child}."
    md = {
        "parent": parent,
        "relation": relation,
        "child": child,
        "hierarchy_type": hierarchy_type,
        "authority": AUTHORITY_STATE,
    }
    return _record("UI_HIERARCHY", text, md)


def configuration_dependency_record(
    configuration,
    relation,
    target,
    *,
    surface="",
    capability="",
    observed_behavior=(),
):
    """Record an observed configuration dependency without fixing option values."""
    behavior = tuple(observed_behavior)
    observations = "; ".join(behavior) or "configuration dependency observed"
    text = (
        f"Observed UI configuration dependency on surface {surface or 'UNKNOWN'}: "
        f"{configuration} {relation} {target}. "
        f"Capability context: {capability or 'none'}. "
        f"Observed behavior: {observations}. "
        "The available values are environment or profile data and are not a fixed "
        "product option list. This is observed UI behavior, not a formal product contract."
    )
    metadata = {
        "configuration": configuration,
        "relation": relation,
        "target": target,
        "surface": surface,
        "capability": capability,
        "observed_behavior": json.dumps(list(behavior)),
        "authority": AUTHORITY_STATE,
        "formal_contract": False,
        "lifecycle_scope": "CURRENT_UI",
    }
    return _record("UI_CONFIGURATION_DEPENDENCY", text, metadata)


def transition_record(t, *, from_label="", to_label="", action_label=""):
    """UI_TRANSITION record: 'from --action--> to' as searchable prose."""
    action_label = action_label or (t.action or {}).get("capability") or (t.action or {}).get("type", "action")
    effect = ", ".join(t.observed_effects) or "state updated"
    text = (
        f"On surface {t.surface or 'UNKNOWN'}: from state {from_label or t.from_state_id} "
        f"the user action '{action_label}' ({(t.action or {}).get('control_pattern', 'UNKNOWN')}) "
        f"leads to state {to_label or t.to_state_id}. Relation: {t.relation}. "
        f"Observed effect: {effect}. This is an observed UI flow, not a formal product contract."
    )
    md = {
        "surface": t.surface, "from_state": t.from_state_id, "to_state": t.to_state_id,
        "action": action_label, "control_pattern": (t.action or {}).get("control_pattern", ""),
        "relation": t.relation, "observed_effect": effect,
        "product_version": t.product_version, "authority": AUTHORITY_FLOW,
        "before_screenshot": t.before_screenshot, "after_screenshot": t.after_screenshot,
    }
    return _record("UI_TRANSITION", text, md)


def flow_record(flow, *, action_labels=None):
    """UI_FLOW record: a multi-step observed workflow as prose."""
    action_labels = action_labels or {}
    lines = []
    for step in flow.get("steps", []):
        act = action_labels.get(step["action"], step["action"]) or "action"
        lines.append(f"{step['state']} --{act}--> {step['next_state']}")
    text = (
        f"Observed UI workflow on surface {flow.get('surface') or 'UNKNOWN'}: "
        + " ; ".join(lines)
        + ". Authority: OBSERVED_UI_FLOW (not a formal product contract)."
    )
    md = {
        "surface": flow.get("surface", ""), "steps": json.dumps(flow.get("steps", [])),
        "terminal_state": flow.get("terminal_state", ""), "authority": AUTHORITY_FLOW,
    }
    return _record("UI_FLOW", text, md)


def behavior_model_fact(t, *, action_label=""):
    """Expose a transition as a UI_FLOW BehaviorModel fact for the test-plan reasoner."""
    return {
        "fact_type": "UI_FLOW",
        "from_state": t.from_state_id,
        "action": action_label or (t.action or {}).get("capability", ""),
        "to_state": t.to_state_id,
        "preconditions": list(t.preconditions),
        "observed_effect": ", ".join(t.observed_effects),
        "surface": t.surface,
        "authority": AUTHORITY_FLOW,
        "evidence_id": t.transition_id,
    }
