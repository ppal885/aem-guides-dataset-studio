"""Unit tests for the deterministic core of the UI Behavior Harvester.

Browser-free: every test drives the pure modules (state signature, url
normalization, DOM taxonomy, action safety, transitions, flows, dedup, records,
currentness). Run with: python -m pytest ui_harvester/tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ui_harvester import actions, currentness, dom_extract, rag_records, taxonomy
from ui_harvester import transitions as trans_mod
from ui_harvester.state import UIState, compute_state_id, finalize_state, normalize_url
from ui_harvester.screenshot import ScreenshotStore, image_checksum


# --- state signature + url normalization + volatile removal -------------------
def _state(**over):
    base = dict(surface="NEW_EDITOR", active_left_panel="MAP", open_dialog="",
                visible_capabilities=["OPEN_MAP", "SWITCH_SOURCE"], url="https://a/editor.html/x")
    base.update(over)
    return finalize_state(UIState(**base))


def test_state_signature_is_stable_and_order_independent():
    a = _state(visible_capabilities=["OPEN_MAP", "SWITCH_SOURCE"])
    b = _state(visible_capabilities=["SWITCH_SOURCE", "OPEN_MAP"])  # reordered
    assert a.state_id == b.state_id
    assert a.state_id.startswith("sha256:")


def test_semantic_state_change_changes_id():
    a = _state(open_dialog="")
    b = _state(open_dialog="CREATE_BASELINE")
    assert a.state_id != b.state_id


def test_volatile_fields_do_not_affect_identity():
    a = _state(captured_at="2026-01-01T00:00:00Z", screenshot_id="shot:aaa", product_version="1.2")
    b = _state(captured_at="2026-08-20T12:00:00Z", screenshot_id="shot:zzz", product_version="9.9")
    assert a.state_id == b.state_id  # timestamps/screenshot/version are excluded


def test_url_normalization_strips_volatile_query_and_fragment():
    u = normalize_url("https://HOST/assets.html/content?timestamp=99&wcmmode=x&folder=dam#frag/")
    assert "timestamp" not in u and "wcmmode" not in u and "#frag" not in u
    assert u == "https://host/assets.html/content?folder=dam"


def test_url_normalization_masks_uuid_and_guid_segments():
    u = normalize_url("https://h/x/4314237f-544f-4acd-a7a9-1a13ed1f8640/GUID-abc123-en.dita")
    assert "4314237f" not in u and "GUID-abc123" not in u and "*" in u


# --- DOM taxonomy mapping -----------------------------------------------------
def test_role_maps_to_control_pattern():
    assert taxonomy.map_role_to_control("button") == "ACTION_BUTTON"
    assert taxonomy.map_role_to_control("tab") == "TAB"
    assert taxonomy.map_role_to_control("treeitem") == "TREE_ITEM"


def test_aria_expanded_makes_disclosure_toggle_not_chevron():
    node = {"role": "button", "name": "Conditions", "attributes": {"aria-expanded": "false"}}
    c = dom_extract.classify_node(node)
    assert c["control_pattern"] == "DISCLOSURE_TOGGLE"
    assert "COLLAPSED" in c["states"]
    assert c.get("visual_primitive") == "CHEVRON"  # chevron kept only as a visual hint


def test_capability_differs_from_control_type():
    node = {"role": "button", "name": "Create Baseline"}
    c = dom_extract.classify_node(node)
    assert c["control_pattern"] == "ACTION_BUTTON"     # HOW
    assert c["capability"] == "CREATE_BASELINE"        # WHAT


def test_disabled_capabilities_split_out():
    nodes = [{"role": "button", "name": "Open Map"},
             {"role": "button", "name": "Publish", "disabled": True}]
    visible, disabled = dom_extract.extract_capabilities(nodes)
    assert "OPEN_MAP" in visible and "PUBLISH" in disabled


def test_shared_component_is_only_a_candidate():
    a = {"role": "dialog", "name": "File Picker"}
    b = {"role": "dialog", "name": "File Picker"}
    assert dom_extract.shared_component_candidate(a, b) == "POTENTIAL_SHARED_COMPONENT"
    c = {"role": "dialog", "name": "Other"}
    assert dom_extract.shared_component_candidate(a, c) == "SAME_UI_PATTERN_CANDIDATE"


# --- action safety ------------------------------------------------------------
def test_destructive_action_is_blocked_even_with_safe_word():
    # 'save' is destructive; presence of a safe token must not un-block it.
    v = actions.classify_action(capability="SAVE_AND_CLOSE", name="Save", control_pattern="ACTION_BUTTON")
    assert v == actions.BLOCKED


def test_navigation_action_is_safe():
    v = actions.classify_action(capability="OPEN_CONDITIONS", name="Conditions", control_pattern="DISCLOSURE_TOGGLE")
    assert v == actions.SAFE


def test_unnamed_generic_action_is_unknown_not_clicked():
    v = actions.classify_action(capability="FROBNICATE", name="Frobnicate", control_pattern="ACTION_BUTTON")
    assert v == actions.UNKNOWN
    assert actions.is_clickable(v) is False


def test_blocked_selector_overrides_safe_text():
    v = actions.classify_action(capability="OPEN", name="Open", control_pattern="ACTION_BUTTON",
                                selector='role=button[name="Open"]', blocked_selectors=['name="Open"'])
    assert v == actions.BLOCKED


# --- transitions + flows ------------------------------------------------------
def test_transition_serialization_is_observed_flow():
    a, b = _state(open_dialog=""), _state(open_dialog="CREATE_BASELINE")
    t = trans_mod.make_transition(a, b, {"type": "click", "capability": "CREATE_BASELINE"}, relation="OPENS")
    d = t.to_dict()
    assert d["authority"] == "OBSERVED_UI_FLOW"
    assert d["from_state_id"] == a.state_id and d["to_state_id"] == b.state_id
    assert d["transition_id"].startswith("sha256:")


def test_flow_path_extraction_stitches_chain():
    s0, s1, s2 = _state(active_tab="0"), _state(active_tab="1"), _state(active_tab="2")
    t1 = trans_mod.make_transition(s0, s1, {"capability": "OPEN_BASELINE"})
    t2 = trans_mod.make_transition(s1, s2, {"capability": "CREATE_BASELINE"})
    flows = trans_mod.extract_flow_paths([t1, t2])
    assert len(flows) == 1
    assert [s["action"] for s in flows[0]["steps"]] == ["OPEN_BASELINE", "CREATE_BASELINE"]
    assert flows[0]["authority"] == "OBSERVED_UI_FLOW"


def test_flow_extraction_breaks_cycles():
    s0, s1 = _state(active_tab="0"), _state(active_tab="1")
    t1 = trans_mod.make_transition(s0, s1, {"capability": "OPEN"})
    t2 = trans_mod.make_transition(s1, s0, {"capability": "CLOSE"})  # cycle
    flows = trans_mod.extract_flow_paths([t1, t2])
    # a visited state is not revisited within one path -> no infinite loop
    for f in flows:
        seen = [step["state"] for step in f["steps"]]
        assert len(seen) == len(set(seen))


# --- dedup (states + screenshots) --------------------------------------------
def test_menu_open_close_open_does_not_multiply_states():
    # opening then closing a menu returns to the same semantic state (same id).
    closed1 = _state(open_menu="")
    opened = _state(open_menu="EDITOR_INSERT_OVERFLOW")
    closed2 = _state(open_menu="")
    assert closed1.state_id == closed2.state_id != opened.state_id


def test_distinct_menu_contexts_are_distinct_states():
    left = _state(open_menu="LEFT_NAV_MORE_MENU")
    editor = _state(open_menu="EDITOR_INSERT_OVERFLOW")
    assert left.state_id != editor.state_id  # menu identity is not normalized to MORE_MENU


def test_screenshot_dedup_by_checksum_and_state(tmp_path):
    store = ScreenshotStore(str(tmp_path))
    data = b"\x89PNG-bytes"
    sid1, new1 = store.store(data, "sha256:state1")
    sid2, new2 = store.store(data, "sha256:state1")  # same bytes + same state -> dedup
    sid3, new3 = store.store(data, "sha256:state2")  # same bytes, different state -> kept
    assert new1 is True and new2 is False and sid1 == sid2
    assert new3 is True and sid3 != sid1


# --- rag records + authority --------------------------------------------------
def test_state_record_carries_observation_authority():
    r = rag_records.state_record(_state())
    assert r["metadata"]["record_type"] == "UI_STATE"
    assert r["metadata"]["authority"] == "UI_OBSERVATION"
    assert r["id"].startswith("sha256:")


def test_transition_record_carries_observed_flow_authority():
    a, b = _state(active_tab="0"), _state(active_tab="1")
    t = trans_mod.make_transition(a, b, {"type": "click", "capability": "SWITCH_SOURCE", "control_pattern": "TAB"})
    r = rag_records.transition_record(t)
    assert r["metadata"]["authority"] == "OBSERVED_UI_FLOW"
    assert "observed ui flow" in r["document"].lower()


# --- currentness resolution ---------------------------------------------------
def test_current_query_prefers_matching_version():
    ev = {"product": "AEM_GUIDES", "product_version": "2026.4.0", "currentness": "CURRENT_UI_REFERENCE"}
    assert currentness.resolve(target_product="AEM_GUIDES", target_version="2026.4.0",
                               intent="current", evidence=ev) == currentness.APPLICABLE_CURRENT


def test_unknown_version_yields_uncertainty_not_merge():
    ev = {"product": "AEM_GUIDES", "product_version": "UNKNOWN", "currentness": "VERSION_UNKNOWN"}
    v = currentness.resolve(target_product="AEM_GUIDES", target_version="2026.4.0", intent="current", evidence=ev)
    assert v in (currentness.POSSIBLY_APPLICABLE, currentness.UNKNOWN)


def test_superseded_not_offered_to_current_query():
    ev = {"product": "AEM_GUIDES", "product_version": "2025.1.0",
          "currentness": "SUPERSEDED_UI_REFERENCE", "superseded_by": "sha256:new"}
    assert currentness.resolve(target_product="AEM_GUIDES", target_version="2026.4.0",
                               intent="current", evidence=ev) == currentness.SUPERSEDED


def test_newer_evidence_does_not_win_a_historical_query():
    ev = {"product": "AEM_GUIDES", "product_version": "2026.9.0", "currentness": "CURRENT_UI_REFERENCE"}
    # asking about an older release must not accept newer-than-target evidence
    assert currentness.resolve(target_product="AEM_GUIDES", target_version="2025.1.0",
                               intent="historical", evidence=ev) == currentness.VERSION_MISMATCH


# --- manifest serialization ---------------------------------------------------
def test_screenshot_manifest_entry_shape():
    st = _state(screenshot_id="shot:abc")
    store = ScreenshotStore
    entry = store.manifest_entry(store.__new__(store), st)  # manifest_entry is pure
    assert entry["state_id"] == st.state_id
    assert entry["authority"] == "UI_OBSERVATION"
    assert entry["screenshot_path"].endswith("shot:abc.png")


def test_image_checksum_deterministic():
    assert image_checksum(b"abc") == image_checksum(b"abc")
    assert image_checksum(b"abc") != image_checksum(b"abd")
