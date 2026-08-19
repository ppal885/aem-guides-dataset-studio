"""Build RAG records from UI states/transitions/flows.

Each record is structured TEXT (for semantic search) + metadata. Raw screenshots
stay as referenced evidence, never as primary RAG content. Every record carries
an authority of UI_OBSERVATION or OBSERVED_UI_FLOW so the downstream Test Plan
system can distinguish it from OFFICIAL_PRODUCT_DOCUMENTATION / ACCEPTED_UAC /
SPECIFICATION and refuse to mint a formal AC from a UI observation alone.
"""

import hashlib
import json

RECORD_TYPES = (
    "UI_SURFACE", "UI_CAPABILITY", "UI_STATE", "UI_TRANSITION", "UI_FLOW",
    "UI_CURRENTNESS",
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
        "url_normalized": state.url_normalized,
    }
    return _record("UI_STATE", text, md)


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
