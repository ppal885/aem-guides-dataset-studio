"""Adversarial tests for exact discovery-to-disposition binding (stdlib only)."""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from discovery_disposition import review_reason


def terminal_fixture(directory, *, verdict="REJECTED"):
    """Small reusable, evidence-bound fixture; test decisions are not production ACs."""
    source = Path(directory) / "consumer.py"
    source.write_text("# synthetic inspected consumer\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    candidate = {
        "hypothesis_id": "DS-example", "dimension": "CONSUMER",
        "candidate": "Investigate the adjacent consumer", "reason": "Recorded shared flow",
        "technical_basis": ["recorded source: sibling consumer"], "current_evidence": ["E-CODE"],
        "generator": "FEATURE_MAP", "equivalence_key": "FEATURE_MAP:EXAMPLE:sibling",
        "status": "INVESTIGATION_CANDIDATE", "requires_more_evidence": True, "confidence": 0.0,
    }
    hypothesis = dict(candidate, status=verdict, requires_more_evidence=verdict == "UNRESOLVED")
    verification = {
        "hypothesis_id": candidate["hypothesis_id"], "verdict": verdict,
        "subject": "ACTUAL_IMPLEMENTATION", "supporting_authorities": [],
        "supporting_evidence": [], "disproving_evidence": [],
        "disposition": "EXCLUDED", "note": "The inspected branch excludes this consumer.",
    }
    disposition = {"finding_id": "DIS-01", "source_refs": [candidate["hypothesis_id"]],
                   "statement": "The adjacent consumer has a different execution path.",
                   "disposition": "OUT_OF_SCOPE", "reason": "The inspected branch excludes this consumer."}
    manifest = {
        "coverage_hypotheses": [hypothesis], "verifications": [verification],
        "dispositions": [disposition], "open_questions": [],
        "evidence_catalog": [{"id": "E-CODE", "source_type": "code", "source_ref": source.as_posix(),
                              "source_hash": digest, "content_inspected": True}],
        "evidence_lifecycle": [{"evidence_id": "E-CODE", "source": "current repository",
            "query": "Inspect the adjacent consumer and shared execution branch", "pass": "second",
            "status": "USED", "hypothesis_id": candidate["hypothesis_id"],
            "subject": "ACTUAL_IMPLEMENTATION", "authority": "CURRENT_IMPLEMENTATION",
            "source_ref": source.as_posix(), "source_hash": digest}],
    }
    if verdict == "REJECTED":
        verification["disproving_evidence"] = ["E-CODE"]
    elif verdict == "UNRESOLVED":
        verification.update(disposition="OPEN_QUESTION", insufficient=True, open_question_ref="OQ-01")
        disposition.update(disposition="OPEN_QUESTION", open_question_ref="OQ-01")
        manifest["open_questions"] = [{"id": "OQ-01", "question": "Does the adjacent consumer use this execution path?"}]
        manifest["evidence_lifecycle"] = []
    else:
        verification.update(disposition="REGRESSION", supporting_evidence=["E-CODE"],
                            supporting_authorities=["CURRENT_IMPLEMENTATION"])
        disposition.update(disposition="REGRESSION_COVERAGE")
    return candidate, manifest


class DiscoveryDispositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.candidate, self.manifest = terminal_fixture(self.temp.name)

    def test_valid_rejected_and_out_of_scope(self):
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_valid_investigated_rejected(self):
        self.manifest["dispositions"][0]["disposition"] = "INVESTIGATED_AND_REJECTED"
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_valid_confirmed_regression_does_not_require_ac(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="CONFIRMED")
        self.assertEqual("", review_reason(candidate, manifest))
        self.assertNotIn("acceptance_promotions", manifest)

    def test_unresolved_with_declared_question(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        self.assertEqual("", review_reason(candidate, manifest))

    def test_unresolved_without_catalog_does_not_fabricate_evidence(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        manifest["evidence_catalog"] = []
        candidate.update(current_evidence=[], discovered_source="/missing/consumer.py:1")
        manifest["coverage_hypotheses"][0].update(current_evidence=[], discovered_source=candidate["discovered_source"])
        self.assertEqual("", review_reason(candidate, manifest))
        self.assertEqual([], manifest["evidence_lifecycle"])

    def test_unavailable_source_can_be_honest_open_question(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        manifest["evidence_catalog"][0].update(availability="unavailable", source_hash="")
        self.assertEqual("", review_reason(candidate, manifest))

    def test_unresolved_still_requires_raw_source_identity(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        candidate["discovered_source"] = "/missing/consumer.py:1"
        self.assertIn("discovered_source", review_reason(candidate, manifest))

    def test_broad_axis_does_not_cover_candidate(self):
        self.manifest["coverage_hypotheses"] = [{"dimension": "CONSUMER"}]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_exact_key_tag_without_pipeline_is_not_enough(self):
        self.manifest["coverage_hypotheses"] = [{"equivalence_key": self.candidate["equivalence_key"],
                                                "generator": "FEATURE_MAP"}]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_feature_surface_tags_do_not_count(self):
        self.manifest["coverage_hypotheses"] = [{"surface": "EXAMPLE", "feature": "sibling"}]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_a_sibling_chain_cannot_clear_another(self):
        other = dict(self.candidate, equivalence_key="FEATURE_MAP:EXAMPLE:other")
        self.assertTrue(review_reason(other, self.manifest))

    def test_original_evidence_identity_cannot_be_substituted(self):
        self.manifest["coverage_hypotheses"][0]["current_evidence"] = ["E-OTHER"]
        self.assertIn("current_evidence", review_reason(self.candidate, self.manifest))

    def test_original_technical_basis_cannot_be_deleted(self):
        self.manifest["coverage_hypotheses"][0]["technical_basis"] = ["different feature"]
        self.assertIn("technical_basis", review_reason(self.candidate, self.manifest))

    def test_not_applicable_is_not_a_terminal_verdict(self):
        self.manifest["verifications"][0]["verdict"] = "NOT_APPLICABLE"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_empty_rejection_reason_does_not_count(self):
        self.manifest["dispositions"][0]["reason"] = ""
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_wrong_hypothesis_evidence_binding(self):
        self.manifest["evidence_lifecycle"][0]["hypothesis_id"] = "DS-other"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_retrieved_is_not_used(self):
        self.manifest["evidence_lifecycle"][0]["status"] = "RETRIEVED"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_missing_inspection_query(self):
        self.manifest["evidence_lifecycle"][0]["query"] = ""
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_author_review_placeholder_not_disposition(self):
        self.manifest["dispositions"][0]["reason"] = "AUTHOR MUST CONFIRM"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_retrieved_file_hash_not_semantic_inspection(self):
        self.manifest["evidence_catalog"][0]["content_inspected"] = False
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_rejection_requires_real_subject_authority(self):
        self.manifest["evidence_lifecycle"][0]["authority"] = "UNRECOGNIZED"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_catalog_authority_cannot_be_promoted_by_use(self):
        self.manifest["evidence_catalog"][0]["authority"] = "HISTORICAL_IMPLEMENTATION"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_wrong_disposition_link_does_not_count(self):
        self.manifest["dispositions"][0]["source_refs"] = ["DS-other"]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_duplicate_disposition_fails(self):
        self.manifest["dispositions"].append(copy.deepcopy(self.manifest["dispositions"][0]))
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_duplicate_hypothesis_fails(self):
        self.manifest["coverage_hypotheses"].append(copy.deepcopy(self.manifest["coverage_hypotheses"][0]))
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_duplicate_verification_fails(self):
        self.manifest["verifications"].append(copy.deepcopy(self.manifest["verifications"][0]))
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_missing_question_cannot_be_invented(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        manifest["open_questions"] = []
        self.assertTrue(review_reason(candidate, manifest))

    def test_question_destinations_must_agree(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="UNRESOLVED")
        manifest["dispositions"][0]["open_question_ref"] = "OQ-02"
        self.assertTrue(review_reason(candidate, manifest))

    def test_source_must_exist_in_catalog(self):
        self.manifest["evidence_catalog"] = []
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_stale_source_hash(self):
        Path(self.manifest["evidence_catalog"][0]["source_ref"]).write_text("# changed\n", encoding="utf-8")
        self.assertIn("hash", review_reason(self.candidate, self.manifest))

    def test_used_locator_must_match_catalog(self):
        self.manifest["evidence_lifecycle"][0]["source_ref"] = "different.py"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_discovery_synthesis_cannot_be_relabelled_as_authoritative(self):
        self.manifest["evidence_catalog"][0]["authority_class"] = "SUPPORTING_DISCOVERY"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_regression_cannot_silently_become_ac(self):
        candidate, manifest = terminal_fixture(self.temp.name, verdict="CONFIRMED")
        manifest["dispositions"][0]["disposition"] = "ACCEPTANCE_CONTRACT"
        self.assertTrue(review_reason(candidate, manifest))

    def test_unrelated_used_source_does_not_clear_code_neighbor(self):
        entry = dict(self.manifest["evidence_catalog"][0], id="E-OTHER")
        self.manifest["evidence_catalog"].append(entry)
        self.manifest["evidence_lifecycle"][0]["evidence_id"] = "E-OTHER"
        self.manifest["verifications"][0]["disproving_evidence"] = ["E-OTHER"]
        self.assertIn("unrelated", review_reason(self.candidate, self.manifest))

    def test_recorded_code_locator_can_bind_catalog(self):
        source = self.manifest["evidence_catalog"][0]["source_ref"]
        self.candidate.update(current_evidence=[source + ":1"], source_ref=source + ":1")
        self.manifest["coverage_hypotheses"][0].update(current_evidence=[source + ":1"], source_ref=source + ":1")
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_discovered_source_can_bind_catalog(self):
        source = self.manifest["evidence_catalog"][0]["source_ref"] + ":1"
        self.candidate.update(current_evidence=[source], discovered_source=source)
        self.manifest["coverage_hypotheses"][0].update(current_evidence=[source], discovered_source=source)
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def _set_source_ranges(self, discovered_range, catalog_range, *, bound=True):
        source = self.manifest["evidence_catalog"][0]["source_ref"]
        fields = {"discovered_source": source + discovered_range,
                  "current_evidence": ["E-CODE"] if bound else []}
        self.candidate.update(fields)
        self.manifest["coverage_hypotheses"][0].update(fields)
        self.manifest["evidence_catalog"][0]["source_ref"] = source + catalog_range
        self.manifest["evidence_lifecycle"][0]["source_ref"] = source + catalog_range

    def test_nonoverlapping_catalog_citation_cannot_bind_discovered_source(self):
        self._set_source_ranges(":9-11", ":2-5", bound=False)
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_direct_evidence_id_cannot_override_nonoverlapping_source(self):
        self._set_source_ranges(":9-11", ":2-5")
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_direct_evidence_id_cannot_override_a_different_source(self):
        source = self.manifest["evidence_catalog"][0]["source_ref"] + ".different:1"
        self.candidate["discovered_source"] = source
        self.manifest["coverage_hypotheses"][0]["discovered_source"] = source
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_overlapping_catalog_citation_binds_discovered_source(self):
        self._set_source_ranges(":9-11", ":11-15", bound=False)
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_whole_file_catalog_entry_binds_discovered_range(self):
        self._set_source_ranges(":9-11", "", bound=False)
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_model_label_can_be_regrounded_with_exact_discovery_ref(self):
        self.candidate["current_evidence"] = ["behavior_model.trigger"]
        self.manifest["coverage_hypotheses"][0]["current_evidence"] = ["behavior_model.trigger", "E-CODE"]
        self.manifest["evidence_catalog"][0]["discovery_refs"] = [self.candidate["equivalence_key"]]
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_broad_discovery_ref_cannot_reground_model_label(self):
        self.candidate["current_evidence"] = ["behavior_model.trigger"]
        self.manifest["coverage_hypotheses"][0]["current_evidence"] = ["behavior_model.trigger", "E-CODE"]
        self.manifest["evidence_catalog"][0]["discovery_refs"] = ["CONSUMER"]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_discovery_alias_cannot_replace_recorded_concrete_source(self):
        self.candidate.update(current_evidence=[], discovered_source="/other/consumer.py:1")
        self.manifest["coverage_hypotheses"][0].update(current_evidence=[], discovered_source="/other/consumer.py:1")
        self.manifest["evidence_catalog"][0]["discovery_refs"] = [self.candidate["equivalence_key"]]
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_feature_document_can_ground_activating_model_label(self):
        ref = "https://example.invalid/documented-feature"
        self.candidate.update(current_evidence=["behavior_model.trigger"], reference_urls=[ref])
        self.manifest["coverage_hypotheses"][0].update(current_evidence=["behavior_model.trigger", "E-CODE"], reference_urls=[ref])
        self.manifest["evidence_catalog"][0].update(source_type="documentation", source_ref=ref, authority="DOCUMENTATION")
        self.manifest["evidence_lifecycle"][0].update(source_ref=ref, authority="DOCUMENTATION")
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_catalog_code_line_suffix_checks_whole_file_hash(self):
        source = self.manifest["evidence_catalog"][0]["source_ref"] + ":1"
        self.manifest["evidence_catalog"][0]["source_ref"] = source
        self.manifest["evidence_lifecycle"][0]["source_ref"] = source
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_offline_document_can_bind_exact_underlying_locator(self):
        ref = "https://example.invalid/documented-feature"
        self.candidate.update(current_evidence=["OFFLINE_CHROMA: feature"], retrieved_url=ref)
        self.manifest["coverage_hypotheses"][0].update(current_evidence=self.candidate["current_evidence"], retrieved_url=ref)
        self.manifest["evidence_catalog"][0].update(source_type="documentation", source_ref=ref)
        self.manifest["evidence_lifecycle"][0].update(source_ref=ref, authority="DOCUMENTATION")
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_document_url_with_source_suffix_is_not_local_code(self):
        self.manifest["evidence_catalog"][0].update(source_type="documentation", source_ref="https://example.invalid/reference.xml")
        self.manifest["evidence_lifecycle"][0].update(source_ref="https://example.invalid/reference.xml", authority="DOCUMENTATION")
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def _bind_current_human_scope_rejection(self):
        self.manifest["evidence_catalog"].append({"id": "E-SCOPE", "source_type": "jira",
            "source_ref": "current issue scope", "authority": "EXPLICIT_HUMAN_DECISION"})
        self.manifest["verifications"][0].update(subject="PRODUCT_CONTRACT", disproving_evidence=["E-SCOPE"])
        self.manifest["evidence_lifecycle"] = [{"evidence_id": "E-SCOPE", "source": "attachments",
            "query": "Read current explicit scope decision for this consumer", "pass": "second",
            "status": "USED", "hypothesis_id": self.candidate["hypothesis_id"],
            "subject": "PRODUCT_CONTRACT", "authority": "EXPLICIT_HUMAN_DECISION"}]

    def test_current_human_scope_decision_can_reject_historical_candidate(self):
        self._bind_current_human_scope_rejection()
        self.assertEqual("", review_reason(self.candidate, self.manifest))

    def test_current_human_scope_rejects_unavailable_historical_source(self):
        self._bind_current_human_scope_rejection()
        source = self.manifest["evidence_catalog"][0]["source_ref"]
        self.candidate.update(generator="CODE_NEIGHBORHOOD", discovered_source=source)
        self.manifest["coverage_hypotheses"][0].update(generator="CODE_NEIGHBORHOOD", discovered_source=source)
        self.manifest["evidence_catalog"][0].update(availability="unavailable", source_hash="", content_inspected=False)
        before = copy.deepcopy(self.manifest["evidence_catalog"][0])
        self.assertEqual("", review_reason(self.candidate, self.manifest))
        self.assertEqual(before, self.manifest["evidence_catalog"][0])

    def test_unavailable_human_scope_source_cannot_override(self):
        self._bind_current_human_scope_rejection()
        self.manifest["evidence_catalog"][0]["availability"] = "unavailable"
        self.manifest["evidence_catalog"][1]["availability"] = "unavailable"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_fake_human_authority_cannot_skip_origin_check(self):
        self._bind_current_human_scope_rejection()
        self.manifest["evidence_catalog"][0]["availability"] = "unavailable"
        self.manifest["evidence_catalog"][1]["authority"] = "INFERENCE"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_unrelated_code_is_not_human_scope_override(self):
        self._bind_current_human_scope_rejection()
        self.manifest["evidence_catalog"][0]["availability"] = "unavailable"
        self.manifest["evidence_catalog"][1]["authority"] = "PR_IMPLEMENTATION"
        self.manifest["evidence_lifecycle"][0]["authority"] = "PR_IMPLEMENTATION"
        self.assertTrue(review_reason(self.candidate, self.manifest))

    def test_malformed_inputs_fail_as_review_not_exception(self):
        for bad in (None, [], "not an object", {"coverage_hypotheses": "wrong"}):
            with self.subTest(bad=bad):
                self.assertTrue(review_reason(self.candidate, bad))

    def test_input_is_not_mutated(self):
        before = copy.deepcopy(self.manifest)
        review_reason(self.candidate, self.manifest)
        self.assertEqual(before, self.manifest)


def run_self_tests():
    result = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiscoveryDispositionTests))
    if not result.wasSuccessful():
        raise AssertionError("discovery disposition self-tests failed")
    return True


if __name__ == "__main__":
    run_self_tests()
    print("PASS: discovery disposition self-tests")
