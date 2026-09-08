"""Regression tests for individually retained, advisory relationship candidates."""

from __future__ import annotations

import copy
import unittest

from recorded_neighbor_discovery import candidates_for


def manifest(findings=None, edges=None, catalog=None):
    return {
        "evidence_catalog": catalog or [],
        "construct_relationships": {
            "edges": edges or [],
            "discovery": {"code_neighborhood_sweep": {
                "sibling_config_keys": {"searched": True, "findings": findings or []},
            }},
        },
    }


class RecordedNeighborDiscoveryTests(unittest.TestCase):
    def test_same_axis_siblings_remain_independent(self):
        result = candidates_for(manifest([
            {"neighbor": "first option", "source": "/repo/config.xml:8"},
            {"neighbor": "second option", "source": "/repo/config.xml:9"},
        ]))
        self.assertEqual(len(result), 2)
        self.assertEqual({item["dimension"] for item in result}, {"CONFIGURATION"})
        self.assertEqual(len({item["equivalence_key"] for item in result}), 2)

    def test_missing_catalog_is_not_fabricated(self):
        item = candidates_for(manifest([
            {"neighbor": "alternate output", "source": "/repo/options.xml:9"},
        ]))[0]
        self.assertEqual(item["current_evidence"], [])
        self.assertEqual(item["discovered_source"], "/repo/options.xml:9")
        self.assertEqual(item["evidence_binding_status"], "MISSING_CATALOG_BINDING")
        self.assertEqual(item["relation_type"], "")

    def test_windows_drive_colon_and_slashes_bind(self):
        item = candidates_for(manifest([
            {"neighbor": "alternate option", "source": r"C:\repo\Config.xml:9"},
        ], catalog=[{"id": "E-1", "source_ref": "c:/REPO/config.xml"}]))[0]
        self.assertEqual(item["current_evidence"], ["E-1"])

    def test_posix_case_stays_distinct(self):
        item = candidates_for(manifest([
            {"neighbor": "alternate option", "source": "/repo/Config.xml:9"},
        ], catalog=[{"id": "E-1", "source_ref": "/repo/config.xml"}]))[0]
        self.assertEqual(item["current_evidence"], [])

    def test_bounded_source_requires_line_overlap(self):
        data = manifest([
            {"neighbor": "alternate option", "source": "/repo/config.xml:9-11"},
        ], catalog=[
            {"id": "WRONG", "source_ref": "/repo/config.xml:2-5"},
            {"source_id": "MATCH", "source_ref": "/repo/config.xml:10-15"},
        ])
        self.assertEqual(candidates_for(data)[0]["current_evidence"], ["MATCH"])

    def test_chunk_identity_binds_declared_catalog_only(self):
        data = manifest(edges=[{
            "relation_type": "CONSUMER", "neighbor": "another surface", "source": "chunk_id:known-chunk",
        }])
        data["evidence_catalog"] = {"sources": [{"id": "E-2", "source_ref": "chunk_id:known-chunk"}]}
        self.assertEqual(candidates_for(data)[0]["current_evidence"], ["E-2"])

    def test_matching_edge_deduplicates_and_oos_stays_advisory(self):
        data = manifest([
            {"neighbor": "alternate option", "source": "/repo/config.xml:9"},
        ], edges=[{
            "relation_type": "SIBLING_CONFIG", "neighbor": "alternate option", "source": "/repo/config.xml:9",
            "disposition": "OUT_OF_SCOPE", "reason": "Current accepted scope excludes this option.",
        }])
        items = candidates_for(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["recorded_disposition"]["disposition"], "OUT_OF_SCOPE")
        self.assertEqual(items[0]["status"], "INVESTIGATION_CANDIDATE")
        self.assertEqual(items[0]["confidence"], 0.0)
        self.assertFalse(items[0]["authoritative"])
        self.assertEqual(items[0]["authority_class"], "SUPPORTING_DISCOVERY")

    def test_unmatched_edge_and_distinct_relation_retained(self):
        edges = [
            {"relation_type": "CALLER", "neighbor": "shared service", "source": "/repo/service.py:12"},
            {"relation_type": "CONSUMER", "neighbor": "shared service", "source": "/repo/service.py:12"},
        ]
        self.assertEqual(len(candidates_for(manifest(edges=edges))), 2)

    def test_duplicate_records_collapsed_without_mutating_manifest(self):
        finding = {"neighbor": "alternate option", "source": "/repo/config.xml:9"}
        data = manifest([finding, copy.deepcopy(finding)])
        before = copy.deepcopy(data)
        self.assertEqual(len(candidates_for(data)), 1)
        self.assertEqual(data, before)

    def test_malformed_records_produce_nothing(self):
        for malformed in (None, [], "text", {"construct_relationships": []}, manifest([
            None, {}, {"neighbor": [], "source": "/repo/file.py:9"},
            {"neighbor": "thing", "source": "not a citation"},
            {"neighbor": "thing", "source": "/repo/file.py:0"},
            {"neighbor": "thing", "source": "/repo/file.py:9-1"},
        ], edges=[{"neighbor": "thing", "source": "/repo/file.py:8", "relation_type": "INVENTED"}])):
            with self.subTest(malformed=malformed):
                self.assertEqual(candidates_for(malformed), [])

    def test_empty_findings_are_noop(self):
        self.assertEqual(candidates_for({"behavior_model": {"trigger": "change label"}}), [])
        self.assertEqual(candidates_for(manifest()), [])

    def test_oversized_numeric_citation_cannot_crash_discovery(self):
        self.assertEqual(candidates_for(manifest([
            {"neighbor": "option", "source": "/repo/file.py:" + "9" * 5000},
        ])), [])

    def test_key_stable_across_input_order(self):
        findings = [
            {"neighbor": "first option", "source": "/repo/config.xml:8"},
            {"neighbor": "second option", "source": "/repo/config.xml:9"},
        ]
        left = {item["equivalence_key"] for item in candidates_for(manifest(findings))}
        right = {item["equivalence_key"] for item in candidates_for(manifest(list(reversed(findings))))}
        self.assertEqual(left, right)


def run_self_tests() -> bool:
    return unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RecordedNeighborDiscoveryTests)
    ).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_self_tests() else 1)
