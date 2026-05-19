"""Peer-scope xrefs and flat multi-map wiring on flat_hierarchical_dita recipe."""

from __future__ import annotations

from app.tasks.generate_dataset import run_generate_dataset


def test_flat_hierarchical_peer_xrefs_in_body():
    cfg = {
        "name": "peer-xref-test",
        "seed": "seed-peer",
        "root_folder": "dataset",
        "recipes": [
            {
                "type": "flat_hierarchical_dita",
                "topic_count": 5,
                "topics_per_section": 2,
                "include_xrefs": True,
                "xref_scope": "peer",
                "pretty_print": False,
            }
        ],
    }
    files = run_generate_dataset(cfg, "job-peer-xref")
    flat_keys = [k for k in files if "/flat_5/topics/topic_00001.dita" in k.replace("\\", "/")]
    assert flat_keys, "expected flat topic path"
    xml = files[flat_keys[0]]
    assert b'scope="peer"' in xml
    assert b'format="dita"' in xml
    assert b"topic_00002.dita" in xml


def test_flat_hierarchical_local_xrefs_omit_peer_attributes():
    cfg = {
        "name": "local-xref-test",
        "seed": "seed-local",
        "root_folder": "dataset",
        "recipes": [
            {
                "type": "flat_hierarchical_dita",
                "topic_count": 3,
                "topics_per_section": 2,
                "include_xrefs": True,
                "xref_scope": "local",
                "pretty_print": False,
            }
        ],
    }
    files = run_generate_dataset(cfg, "job-local-xref")
    flat_keys = [k for k in files if "/flat_3/topics/topic_00001.dita" in k.replace("\\", "/")]
    assert flat_keys
    xml = files[flat_keys[0]]
    assert b'scope="peer"' not in xml


def test_flat_multiple_guide_maps_root_uses_mapref():
    cfg = {
        "name": "multi-flat-map-test",
        "seed": "seed-mmaps",
        "root_folder": "dataset",
        "recipes": [
            {
                "type": "flat_hierarchical_dita",
                "topic_count": 10,
                "topics_per_section": 5,
                "flat_submap_count": 4,
                "include_xrefs": False,
                "pretty_print": False,
            }
        ],
    }
    files = run_generate_dataset(cfg, "job-multi-flat")
    root_keys = [k for k in files if k.replace("\\", "/").endswith("/flat_10/rootmap_10.ditamap")]
    assert root_keys
    root_xml = files[root_keys[0]]
    assert b"<mapref" in root_xml
    assert b"maps/flat_guide_01.ditamap" in root_xml
    assert b"maps/flat_guide_04.ditamap" in root_xml
    guide_keys = [k for k in files if "/flat_10/maps/flat_guide_" in k.replace("\\", "/")]
    assert len(guide_keys) == 4


def test_customer_style_product_in_title():
    cfg = {
        "name": "cust-style-test",
        "seed": "seed-cust",
        "root_folder": "dataset",
        "recipes": [
            {
                "type": "flat_hierarchical_dita",
                "topic_count": 2,
                "topics_per_section": 2,
                "customer_style": True,
                "content_subject": "Northwind Analytics",
                "pretty_print": False,
            }
        ],
    }
    files = run_generate_dataset(cfg, "job-cust-style")
    t1 = [k for k in files if "/flat_2/topics/topic_00001.dita" in k.replace("\\", "/")][0]
    xml = files[t1]
    assert b"Northwind Analytics" in xml
    assert b"Customer-facing help topic" in xml
