"""Unit tests for the deterministic core of the UI Behavior Harvester.

Browser-free: every test drives the pure modules (state signature, url
normalization, DOM taxonomy, action safety, transitions, flows, dedup, records,
currentness). Run with: python -m pytest ui_harvester/tests -q
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ui_harvester import actions, currentness, dom_extract, rag_records, reports, taxonomy
from ui_harvester import surface_resolution as surface_mod
from ui_harvester import transitions as trans_mod
from ui_harvester.state import (
    UIState,
    compute_state_id,
    finalize_state,
    normalize_route_identity,
    normalize_url,
)
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
    assert entry["route_identity"] == st.route_identity
    assert entry["screenshot_path"].endswith("shot:abc.png")


def test_image_checksum_deterministic():
    assert image_checksum(b"abc") == image_checksum(b"abc")
    assert image_checksum(b"abc") != image_checksum(b"abd")


# --- route-scoped surface lifecycle -----------------------------------------
def _surface_pair():
    current_route = (
        "/libs/fmdita/clientlibs/xmleditor/page.html"
        "?appmode=author&leftpanel=repository_panel"
    )
    legacy_route = "/libs/fmdita/mapcollections"
    current = surface_mod.make_surface_identity(
        "OPEN_MAP_COLLECTIONS", "NEW_EDITOR_MAP_COLLECTIONS", current_route
    )
    legacy = surface_mod.make_surface_identity(
        "OPEN_MAP_COLLECTIONS", "LEGACY_MAP_COLLECTIONS", legacy_route
    )
    return current, legacy


def test_route_identity_preserves_current_surface_and_drops_asset_identity():
    route = normalize_route_identity(
        "http://host/libs/fmdita/clientlibs/xmleditor/page.html"
        "?leftPanel=repository_panel&appMode=author"
        "&src=%2Fcontent%2Fdam%2FGUID-abc.dita"
    )
    assert route == (
        "/libs/fmdita/clientlibs/xmleditor/page.html"
        "?appmode=author&leftpanel=repository_panel"
    )
    assert "src" not in route
    assert "GUID" not in route


def test_route_identity_canonicalizes_legacy_map_collections():
    route = normalize_route_identity(
        "http://host/libs/fmdita/mapcollections/details.html/content/dam/example"
    )
    assert route == "/libs/fmdita/mapcollections"


def test_same_capability_on_current_and_legacy_routes_never_merges():
    current, legacy = _surface_pair()
    assert current.surface_id != legacy.surface_id
    assert current.route_identity != legacy.route_identity


def test_route_hints_classify_known_current_and_legacy_surfaces():
    current, legacy = _surface_pair()
    assert current.lifecycle == surface_mod.CURRENT_UI
    assert legacy.lifecycle == surface_mod.LEGACY_UI


def test_conflicting_lifecycle_evidence_remains_version_unknown():
    evidence = (
        surface_mod.LifecycleEvidence(
            source_type="DOCUMENTATION",
            source_ref="docs/current",
            assertion="Current map collections surface",
            classification=surface_mod.CURRENT_UI,
        ),
        surface_mod.LifecycleEvidence(
            source_type="JIRA",
            source_ref="GUIDES-1",
            assertion="Legacy map collections surface",
            classification=surface_mod.LEGACY_UI,
        ),
    )
    identity = surface_mod.make_surface_identity(
        "OPEN_MAP_COLLECTIONS",
        "MAP_COLLECTIONS",
        "/libs/fmdita/mapcollections",
        evidence=evidence,
    )
    assert identity.lifecycle == surface_mod.VERSION_UNKNOWN


def test_replacement_relation_requires_explicit_lifecycle_evidence():
    current, legacy = _surface_pair()
    with pytest.raises(ValueError, match="requires explicit"):
        surface_mod.make_surface_relation(
            legacy, current, surface_mod.REPLACED_BY
        )

    evidence = surface_mod.LifecycleEvidence(
        source_type="DOCUMENTATION",
        source_ref="docs/map-collections-migration",
        assertion="The new editor map collections surface replaces the legacy route.",
        relation=surface_mod.REPLACED_BY,
    )
    relation = surface_mod.make_surface_relation(
        legacy, current, surface_mod.REPLACED_BY, evidence=(evidence,)
    )
    assert relation.source_surface_id == legacy.surface_id
    assert relation.target_surface_id == current.surface_id
    assert relation.evidence_ids == (evidence.evidence_id,)


def test_current_plan_retrieval_prefers_current_and_excludes_legacy():
    current, legacy = _surface_pair()
    selected = surface_mod.select_surfaces(
        (legacy, current), purpose=surface_mod.CURRENT_TEST_PLAN
    )
    assert selected == [current]

    legacy_requested = surface_mod.select_surfaces(
        (current, legacy),
        purpose=surface_mod.CURRENT_TEST_PLAN,
        requested_route=legacy.route_identity,
    )
    assert legacy_requested[0] == legacy


def test_historical_jira_retrieval_may_prefer_legacy():
    current, legacy = _surface_pair()
    selected = surface_mod.select_surfaces(
        (current, legacy), purpose=surface_mod.HISTORICAL_JIRA
    )
    assert selected[0] == legacy


def test_legacy_surface_is_never_a_current_product_contract():
    current, legacy = _surface_pair()
    assert surface_mod.is_current_product_contract(current)
    assert not surface_mod.is_current_product_contract(legacy)


def test_product_hierarchy_keeps_current_and_legacy_map_collections_separate():
    edges = set(taxonomy.PRODUCT_HIERARCHY_EDGES)
    assert (
        "MAP_COLLECTIONS", "HAS_CURRENT_SURFACE", "NEW_EDITOR_MAP_COLLECTIONS"
    ) in edges
    assert (
        "MAP_COLLECTIONS", "HAS_LEGACY_SURFACE", "LEGACY_MAP_COLLECTIONS"
    ) in edges
    assert (
        "USER_PREFERENCES", "HAS_SECTION", "GENERAL"
    ) in edges
    assert (
        "USER_PREFERENCES", "HAS_SECTION", "APPEARANCE"
    ) in edges
    assert not any(
        relation in (surface_mod.REPLACED_BY, surface_mod.SUPERSEDED_BY)
        for _, relation, _ in edges
    )
    serialized = json.dumps(sorted(edges))
    for environment_label in ("Draft", "Edits", "HR-Approved", "HR-Review"):
        assert environment_label not in serialized


def test_crawler_observes_workflows_but_blocks_business_mutations():
    assert actions.mutation_boundary(opens_container="NESTED_CONTEXT_MENU") == actions.OBSERVE
    assert actions.mutation_boundary(
        opens_container="MODAL_FORM", reversible=True
    ) == actions.CONFIGURE_EPHEMERAL
    assert actions.mutation_boundary(
        action="save as new version", commits_business_operation=True
    ) == actions.COMMIT_MUTATION
    assert actions.mutation_boundary(
        action="generate sites page", commits_business_operation=True
    ) == actions.COMMIT_MUTATION


def test_surface_rag_records_mark_legacy_non_current_and_serialize_relations():
    current, legacy = _surface_pair()
    legacy_record = rag_records.surface_identity_record(legacy)
    assert legacy_record["metadata"]["is_current_product_contract"] is False
    assert "legacy" in legacy_record["document"].lower()

    evidence = surface_mod.LifecycleEvidence(
        source_type="CODE",
        source_ref="route-registry",
        assertion="The current route supersedes the legacy map collections route.",
        relation=surface_mod.SUPERSEDED_BY,
    )
    relation = surface_mod.make_surface_relation(
        legacy, current, surface_mod.SUPERSEDED_BY, evidence=(evidence,)
    )
    record = rag_records.surface_relation_record(relation)
    assert record["metadata"]["from_surface_id"] == legacy.surface_id
    assert record["metadata"]["to_surface_id"] == current.surface_id
    assert json.loads(record["metadata"]["evidence_ids"]) == [evidence.evidence_id]


def test_surface_graph_preserves_route_scoped_records(tmp_path):
    current, legacy = _surface_pair()
    result = SimpleNamespace(
        capabilities={
            current.surface_id: {
                "capability": current.capability,
                "surface": current.surface,
                "route_identity": current.route_identity,
                "lifecycle": current.lifecycle,
            },
            legacy.surface_id: {
                "capability": legacy.capability,
                "surface": legacy.surface,
                "route_identity": legacy.route_identity,
                "lifecycle": legacy.lifecycle,
            },
        },
        states={},
        transitions=[],
    )
    reports.write_graphs(result, tmp_path, [])
    graph = json.loads(
        (tmp_path / "graph" / "ui_surface_graph.json").read_text(encoding="utf-8")
    )
    assert len(graph) == 2
    assert {entry["route_identity"] for entry in graph.values()} == {
        current.route_identity,
        legacy.route_identity,
    }


def test_rag_export_includes_requested_product_hierarchy():
    result = SimpleNamespace(capabilities={}, states={}, transitions=[])
    records = reports.build_rag_records(result, [])
    hierarchy = {
        (
            item["metadata"].get("parent"),
            item["metadata"].get("relation"),
            item["metadata"].get("child"),
        )
        for item in records
        if item["metadata"]["record_type"] == "UI_HIERARCHY"
    }
    assert (
        "MAP_COLLECTIONS", "HAS_CURRENT_SURFACE", "NEW_EDITOR_MAP_COLLECTIONS"
    ) in hierarchy
    assert (
        "MAP_COLLECTIONS", "HAS_LEGACY_SURFACE", "LEGACY_MAP_COLLECTIONS"
    ) in hierarchy


def test_overview_new_file_topic_creation_topology_is_modeled():
    product = set(taxonomy.PRODUCT_HIERARCHY_EDGES)
    capabilities = set(taxonomy.CAPABILITY_HIERARCHY_EDGES)
    assert ("AEM_GUIDES", "HAS_SURFACE", "OVERVIEW") in product
    assert ("AEM_GUIDES", "HAS_AREA", "USER_PREFERENCES") in product
    assert ("GENERAL", "HAS_PREFERENCE", "FOLDER_PROFILE") in product
    assert {
        ("OVERVIEW", "HAS_ACTION_FAMILY", "NEW_FILE"),
        ("NEW_FILE", "HAS_ACTION", "CREATE_TOPIC"),
        ("NEW_FILE", "HAS_ACTION", "CREATE_MAP"),
        ("CREATE_TOPIC", "OPENS", "NEW_TOPIC_DIALOG"),
        ("NEW_TOPIC_DIALOG", "HAS_CONTROL", "TOPIC_TEMPLATE_SELECTOR"),
    } <= capabilities


def test_configuration_relation_vocabulary_covers_all_dependency_classes():
    assert set(taxonomy.CONFIGURATION_RELATIONS) == {
        "CONFIGURATION_CONTROLS_OPTIONS",
        "CONFIGURATION_CONTROLS_UI_REPRESENTATION",
        "CONFIGURATION_CONTROLS_CAPABILITY",
    }


def test_folder_profile_controls_topic_templates_without_literal_options():
    dependency = next(
        item
        for item in taxonomy.CONFIGURATION_DEPENDENCIES
        if item["configuration"] == "FOLDER_PROFILE"
    )
    assert dependency["relation"] == "CONFIGURATION_CONTROLS_OPTIONS"
    assert dependency["target"] == "TOPIC_TEMPLATE_SELECTOR"
    assert dependency["surface"] == "OVERVIEW"
    assert dependency["capability"] == "CREATE_TOPIC"
    assert "options" not in dependency
    assert "template_options" not in dependency
    assert not any(
        parent == "TOPIC_TEMPLATE_SELECTOR" and relation == "HAS_OPTION"
        for parent, relation, _ in taxonomy.CAPABILITY_HIERARCHY_EDGES
    )


def test_configuration_dependency_rag_records_are_emitted_without_fixture_values():
    result = SimpleNamespace(capabilities={}, states={}, transitions=[])
    records = reports.build_rag_records(result, [])
    dependencies = [
        item
        for item in records
        if item["metadata"]["record_type"] == "UI_CONFIGURATION_DEPENDENCY"
    ]
    folder_profile = next(
        item
        for item in dependencies
        if item["metadata"]["configuration"] == "FOLDER_PROFILE"
    )
    assert folder_profile["metadata"]["relation"] == "CONFIGURATION_CONTROLS_OPTIONS"
    assert folder_profile["metadata"]["target"] == "TOPIC_TEMPLATE_SELECTOR"
    assert folder_profile["metadata"]["formal_contract"] is False
    document = folder_profile["document"].lower()
    assert "folder_profile" in document
    for literal_option in ("ditaval", "glossary", "markdown", "reference", "task"):
        assert literal_option not in document
