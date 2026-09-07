"""Synthetic filtered-search/retry checks; no VM, network, models or systemd."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import switch_vm_backend_candidate as cutover


def route_fixture(filtered=False):
    rejected = {"reference_sha256": "b" * 64, "historical_match": {
        "qualified": False, "strength": "unproven", "mechanism_score": 0.2,
        "evidence_types": ["area_or_semantic_overlap_only"]}}
    return {
        "status": "CANDIDATES_REJECTED_BY_POLICY" if filtered else "RETURNED_RESULTS",
        "searched_jira_qa_reported": True,
        "result_count": 0 if filtered else 1,
        "results": [] if filtered else [{"reference_sha256": "a" * 64}],
        "rejected_candidate_count": 1 if filtered else 0,
        "rejected_candidates": [rejected] if filtered else [],
        "qualified_history_match_returned": not filtered,
    }


def search_fixture(filtered=False):
    return {
        "status": "PASS_FILTERED_QUERY_SMOKE_ONLY" if filtered else "PASS_QUERY_SMOKE_ONLY",
        "qualified_history_search_smoke_passed": not filtered,
        "routing_identity_and_counts_stable": True,
        "queries": [{"probe_id": probe, "routes": {
            route: route_fixture(filtered) for route in ("backend_8001", "gateway_4502")}}
            for probe in ("table_editing", "map_title", "publishing")],
    }


class FilteredSearchTests(unittest.TestCase):
    def assert_rejected(self, result):
        with self.assertRaisesRegex(ValueError, "LIVE_SEARCH_SMOKE_FAILED"):
            cutover.checked_search_outcome(result)

    def test_qualified_success_retains_qualified_label(self):
        result = search_fixture()
        original = copy.deepcopy(result)
        self.assertEqual(cutover.checked_search_outcome(result), "QUALIFIED_MATCHES_RETURNED")
        self.assertEqual(result, original)

    def test_all_rejected_candidates_do_not_claim_qualified_matches(self):
        result = search_fixture(True)
        original = copy.deepcopy(result)
        self.assertEqual(cutover.checked_search_outcome(result), "CANDIDATES_RETRIEVED_SOME_FILTERED")
        self.assertEqual(result, original)
        self.assertTrue(all(route["result_count"] == 0 for query in result["queries"]
                            for route in query["routes"].values()))

    def test_mixed_qualified_and_filtered_routes_remain_scoped(self):
        result = search_fixture()
        result["status"] = "PASS_FILTERED_QUERY_SMOKE_ONLY"
        result["qualified_history_search_smoke_passed"] = False
        result["queries"][0]["routes"]["backend_8001"] = route_fixture(True)
        self.assertEqual(cutover.checked_search_outcome(result), "CANDIDATES_RETRIEVED_SOME_FILTERED")

    def test_partial_blocked_unknown_and_missing_top_status_reject(self):
        for status in ("PARTIAL_QUERY_SMOKE", "BLOCKED", "PASS", None, False):
            with self.subTest(status=status):
                result = search_fixture()
                result["status"] = status
                self.assert_rejected(result)

    def test_routing_stability_must_be_literal_true(self):
        for value in (False, None, 1, "true"):
            with self.subTest(value=value):
                result = search_fixture()
                result["routing_identity_and_counts_stable"] = value
                self.assert_rejected(result)

    def test_empty_unavailable_and_failed_routes_always_reject(self):
        for status in ("INCONCLUSIVE_EMPTY_RESULTS", "RETRIEVAL_UNAVAILABLE", "FAILED", "TIMEOUT", None):
            for route in ("backend_8001", "gateway_4502"):
                with self.subTest(status=status, route=route):
                    result = search_fixture(True)
                    result["queries"][1]["routes"][route]["status"] = status
                    self.assert_rejected(result)

    def test_global_and_route_filter_status_must_agree(self):
        for filtered in (True, False):
            result = search_fixture(filtered)
            result["status"] = "PASS_QUERY_SMOKE_ONLY" if filtered else "PASS_FILTERED_QUERY_SMOKE_ONLY"
            self.assert_rejected(result)

    def test_exact_probe_set_required(self):
        for alteration in ("missing", "extra", "duplicate", "unknown"):
            with self.subTest(alteration=alteration):
                result = search_fixture()
                if alteration == "missing":
                    result["queries"].pop()
                elif alteration == "extra":
                    result["queries"].append(copy.deepcopy(result["queries"][0]))
                else:
                    result["queries"][0]["probe_id"] = "map_title" if alteration == "duplicate" else "unknown"
                self.assert_rejected(result)

    def test_exact_two_routes_required(self):
        for alteration in ("missing", "extra"):
            result = search_fixture()
            routes = result["queries"][0]["routes"]
            if alteration == "missing":
                del routes["backend_8001"]
            else:
                routes["unreviewed_endpoint"] = route_fixture()
            self.assert_rejected(result)

    def test_malformed_container_types_fail_with_safe_reason(self):
        invalid = [None, [], "report", 1]
        for path in ("queries", "query", "routes", "route"):
            for value in (None, "bad", 7, []):
                result = search_fixture()
                if path == "queries":
                    result["queries"] = value
                elif path == "query":
                    result["queries"][0] = value
                elif path == "routes":
                    result["queries"][0]["routes"] = value
                else:
                    result["queries"][0]["routes"]["backend_8001"] = value
                invalid.append(result)
        for result in invalid:
            with self.subTest(result=result):
                self.assert_rejected(result)

    def test_result_and_rejection_counts_cannot_be_fabricated(self):
        for filtered in (True, False):
            for key, value in (("result_count", -1), ("result_count", True),
                               ("results", None), ("rejected_candidate_count", -1),
                               ("rejected_candidate_count", True), ("rejected_candidates", None),
                               ("searched_jira_qa_reported", False)):
                with self.subTest(filtered=filtered, key=key, value=value):
                    result = search_fixture(filtered)
                    result["queries"][0]["routes"]["backend_8001"][key] = value
                    self.assert_rejected(result)

    def test_route_status_requires_consistent_results_and_rejections(self):
        cases = [(False, "result_count", 0), (False, "results", []),
                 (True, "rejected_candidate_count", 0), (True, "rejected_candidates", []),
                 (True, "result_count", 1), (True, "results", [{"reference_sha256": "a" * 64}])]
        for filtered, key, value in cases:
            with self.subTest(filtered=filtered, key=key):
                result = search_fixture(filtered)
                result["queries"][0]["routes"]["backend_8001"][key] = value
                self.assert_rejected(result)

    def test_qualified_booleans_must_match_outcome_without_coercion(self):
        for filtered in (True, False):
            for value in (filtered, None, 1, "true"):
                for level in ("report", "route"):
                    with self.subTest(filtered=filtered, value=value, level=level):
                        result = search_fixture(filtered)
                        if level == "report":
                            result["qualified_history_search_smoke_passed"] = value
                        else:
                            result["queries"][0]["routes"]["backend_8001"]["qualified_history_match_returned"] = value
                        self.assert_rejected(result)

    def test_reference_fingerprints_are_required_and_not_arbitrary_text(self):
        for filtered in (True, False):
            for value in (None, "a" * 63, "A" * 64, "g" * 64, 7):
                with self.subTest(filtered=filtered, value=value):
                    result = search_fixture(filtered)
                    row_name = "rejected_candidates" if filtered else "results"
                    result["queries"][0]["routes"]["backend_8001"][row_name][0]["reference_sha256"] = value
                    self.assert_rejected(result)

    def test_duplicate_or_conflicting_references_reject(self):
        for filtered in (True, False):
            result = search_fixture(filtered)
            route = result["queries"][0]["routes"]["backend_8001"]
            row_name = "rejected_candidates" if filtered else "results"
            count_name = "rejected_candidate_count" if filtered else "result_count"
            route[row_name].append(copy.deepcopy(route[row_name][0]))
            route[count_name] = 2
            self.assert_rejected(result)
        result = search_fixture()
        route = result["queries"][0]["routes"]["backend_8001"]
        rejected = route_fixture(True)["rejected_candidates"][0]
        rejected["reference_sha256"] = route["results"][0]["reference_sha256"]
        route.update(rejected_candidate_count=1, rejected_candidates=[rejected])
        self.assert_rejected(result)

    def test_rejected_candidates_cannot_claim_qualified_or_proven(self):
        for match in (None, [], {}, {"qualified": True, "strength": "unproven"},
                      {"qualified": 0, "strength": "unproven"},
                      {"qualified": False, "strength": "proven"}):
            with self.subTest(match=match):
                result = search_fixture(True)
                result["queries"][0]["routes"]["backend_8001"]["rejected_candidates"][0]["historical_match"] = match
                self.assert_rejected(result)

    def test_counts_are_bounded_even_when_row_lengths_match(self):
        for filtered, count in ((False, 4), (True, 10)):
            result = search_fixture(filtered)
            route = result["queries"][0]["routes"]["backend_8001"]
            row_name = "rejected_candidates" if filtered else "results"
            count_name = "rejected_candidate_count" if filtered else "result_count"
            row = copy.deepcopy(route[row_name][0])
            route[row_name] = [{**row, "reference_sha256": f"{index:064x}"} for index in range(count)]
            route[count_name] = count
            self.assert_rejected(result)

    def test_malformed_result_and_rejection_rows_reject(self):
        for filtered in (True, False):
            for row in (None, [], "bad", 7):
                with self.subTest(filtered=filtered, row=row):
                    result = search_fixture(filtered)
                    row_name = "rejected_candidates" if filtered else "results"
                    result["queries"][0]["routes"]["backend_8001"][row_name] = [row]
                    self.assert_rejected(result)

    def test_actual_diagnostic_normalization_and_cutover_contract_integrate(self):
        # Reuse the existing read-contract fake, not a second approximation of
        # raw MCP/Chroma responses. Both production helpers execute unchanged.
        import test_verify_vm_search_embeddings as search_tests

        counts = dict(zip(dict(search_tests.subject.PROBES), (2, 9, 9)))
        expected = {
            "hits": "QUALIFIED_MATCHES_RETURNED",
            "filtered": "CANDIDATES_RETRIEVED_SOME_FILTERED",
            "mixed": "CANDIDATES_RETRIEVED_SOME_FILTERED",
            "empty": None,
        }
        for scenario, outcome in expected.items():
            with self.subTest(scenario=scenario):
                reader = search_tests.FakeReader()

                def change(port, kind, selector, value):
                    if kind != "history":
                        return value
                    if scenario == "filtered" or (scenario == "mixed" and selector == "table_editing"):
                        return search_tests.rejected_search_data(selector, rejected=counts[selector])
                    if scenario == "empty" and port == 4502 and selector == "table_editing":
                        return search_tests.search_data(selector, hits=0)
                    return value

                reader.change = change
                with patch.object(search_tests.subject.http.client, "HTTPConnection") as network:
                    report = search_tests.subject.run_diagnostic(reader=reader)
                    if outcome is None:
                        self.assertEqual(report["status"], "PARTIAL_QUERY_SMOKE")
                        self.assert_rejected(report)
                    else:
                        self.assertEqual(cutover.checked_search_outcome(report), outcome)
                network.assert_not_called()
                self.assertEqual(reader.status_calls, {8001: 2, 4502: 2})
                self.assertEqual(sum(call[1] == "history" for call in reader.calls), 6)
                self.assertTrue(all(value is False for value in report["actions"].values()))
                self.assertIs(report["resume_writers_authorized"], False)
                self.assertIs(report["embedding_verification"]["fresh_embedding_verified"], False)
                self.assertNotIn(search_tests.PRIVATE, json.dumps(report))
                if scenario == "filtered":
                    self.assertEqual([query["routes"]["backend_8001"]["rejected_candidate_count"]
                                      for query in report["queries"]], [2, 9, 9])
                    self.assertIs(report["qualified_history_search_smoke_passed"], False)


class RolledBackBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-rollback-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.previous = self.candidate / "cutover-abcdefgh"
        self.previous.mkdir()
        self.target = self.root / "95-uac-python311.conf"
        self.payload = b"[Service]\nExecStart=synthetic-candidate\n"
        self.witness = self.previous / "override.conf"
        self.witness.write_bytes(self.payload)
        self.config = self.root / "reviewed.conf"
        self.config.write_bytes(b"paused synthetic configuration")
        self.absent = self.root / "absent.env"
        self.ids = {
            cutover.BACKEND: {"pid": "101", "invocation": "1" * 32},
            cutover.CHROMA: {"pid": "102", "invocation": "2" * 32},
        }
        self.units = {service: {
            "MainPID": identity["pid"], "ActiveState": "active", "SubState": "running",
            "ExecStart": "old-" + service, "DropInPaths": "", "Environment": "PAUSED=true",
            "WorkingDirectory": "/synthetic/backend"} for service, identity in self.ids.items()}
        self.base = {"services": copy.deepcopy(self.units),
                     "inspected_file_hashes": {str(self.config): self.file_hash(self.config),
                                               str(self.absent): None}}
        self.receipt = {"services": copy.deepcopy(self.ids)}
        self.snapshot = {"units": copy.deepcopy(self.units), "identities": copy.deepcopy(self.ids),
                         "files": dict(self.base["inspected_file_hashes"])}
        self.current = copy.deepcopy(self.units)
        self.ids[cutover.BACKEND] = {"pid": "103", "invocation": "3" * 32}
        self.current[cutover.BACKEND]["MainPID"] = "103"
        self.state = {"state": "ROLLED_BACK_BACKEND_ONLY", "target": str(self.target)}
        self.report = {"status": "STOP", "phase": "CUTOVER", "reason": "LIVE_SEARCH_SMOKE_FAILED",
                       "last_completed_state": "ROLLED_BACK_BACKEND_ONLY", "cutover_dir": str(self.previous)}
        self.write_json("state.json", self.state)
        self.write_json("report.json", self.report)
        self.write_json("private-before.json", self.snapshot)
        self.original_receipt = copy.deepcopy(self.receipt)
        self.original_base = copy.deepcopy(self.base)
        self.original_files = self.capture_files()

        def require(condition, reason):
            if not condition:
                raise RuntimeError(reason)

        def safe_path(path, exists=True):
            path = Path(path)
            require(path.is_relative_to(self.root) and not path.is_symlink(), "UNSAFE_TEST_PATH")
            require(not exists or path.exists(), "MISSING_TEST_PATH")
            return path

        self.r = SimpleNamespace(
            require=require, safe_path=safe_path, SERVICES=tuple(self.units),
            bounded=lambda path: Path(path).read_bytes(), digest=lambda raw: hashlib.sha256(raw).hexdigest(),
            file_hash=self.file_hash, exec_start=lambda value: (value, [value]),
            command=Mock(side_effect=AssertionError("NO_SYSTEMD_COMMAND_ALLOWED")),
            atomic_write=Mock(side_effect=AssertionError("NO_REPORT_WRITE_ALLOWED")),
        )
        self.process_check = Mock()
        self.addCleanup(patch.stopall)
        patch.object(cutover, "CANDIDATE", self.candidate).start()
        patch.object(cutover, "TARGET", self.target).start()

    @staticmethod
    def file_hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def capture_files(self):
        return {str(path): path.read_bytes() for path in self.previous.iterdir() if path.is_file()}

    def write_json(self, name, value):
        (self.previous / name).write_text(json.dumps(value), encoding="utf-8")

    def retry(self, previous=None):
        return cutover.rolled_back_baseline(self.r, previous or self.previous, self.base, self.receipt,
                                           self.current, self.ids, self.payload, self.process_check)

    def assert_no_mutation(self):
        self.assertEqual(self.receipt, self.original_receipt)
        self.assertEqual(self.base, self.original_base)
        self.r.command.assert_not_called()
        self.r.atomic_write.assert_not_called()

    def assert_stops(self, reason):
        before = self.capture_files()
        with self.assertRaisesRegex(RuntimeError, reason):
            self.retry()
        self.process_check.assert_not_called()
        self.assertEqual(self.capture_files(), before)
        self.assert_no_mutation()

    def test_valid_rollback_binds_new_identity_without_editing_old_receipt(self):
        result = self.retry()
        self.assertEqual(result["retry_of"], str(self.previous))
        self.assertEqual(result["services"], self.ids)
        self.assertNotEqual(result["services"][cutover.BACKEND], self.receipt["services"][cutover.BACKEND])
        self.assertEqual(result["services"][cutover.CHROMA], self.receipt["services"][cutover.CHROMA])
        self.assertEqual(result["scope"], "NEW_CURRENT_IDENTITY_BASELINE_AFTER_VALIDATED_ROLLBACK")
        for path, raw in self.original_files.items():
            self.assertEqual(result["files"][path], hashlib.sha256(raw).hexdigest())
        self.assertIsNone(result["files"][str(self.absent)])
        self.process_check.assert_called_once_with(self.ids[cutover.BACKEND])
        self.assertEqual(self.capture_files(), self.original_files)
        self.assert_no_mutation()

    def test_only_exact_child_cutover_path_allowed(self):
        for path in (self.root, self.candidate / "cutover-short", self.candidate / "cutover-ABCDEFGH",
                     self.previous / "cutover-abcdefgh"):
            with self.subTest(path=str(path)):
                with self.assertRaisesRegex(RuntimeError, "RETRY_PATH_NOT_ALLOWLISTED"):
                    self.retry(path)
        self.process_check.assert_not_called()
        self.assert_no_mutation()

    def test_override_file_present_prevents_retry(self):
        self.target.write_bytes(self.payload)
        self.assert_stops("RETRY_OVERRIDE_STILL_PRESENT")
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_dangling_override_symlink_prevents_retry(self):
        try:
            self.target.symlink_to(self.root / "missing-target")
        except OSError as error:
            self.skipTest("Host does not support symlinks: " + type(error).__name__)
        self.assertFalse(self.target.exists())
        self.assert_stops("RETRY_OVERRIDE_STILL_PRESENT")
        self.assertTrue(self.target.is_symlink())

    def test_incomplete_or_other_state_rejects(self):
        for value in ("OVERRIDE_INSTALLED", "BACKEND_ONLY_ROLLBACK_REQUESTED", "PASS"):
            self.write_json("state.json", {**self.state, "state": value})
            self.assert_stops("RETRY_ROLLBACK_NOT_PROVEN")

    def test_rollback_state_target_and_extra_fields_must_match(self):
        for value in ({**self.state, "target": "/other"}, {**self.state, "extra": True}):
            self.write_json("state.json", value)
            self.assert_stops("RETRY_ROLLBACK_NOT_PROVEN")

    def test_report_must_prove_exact_successful_rollback_reason(self):
        for key, value in (("status", "PASS"), ("phase", "PREFLIGHT"), ("reason", "OTHER_FAILURE"),
                           ("last_completed_state", "BACKEND_RESTART_REQUESTED"), ("cutover_dir", "/other")):
            with self.subTest(key=key):
                self.write_json("report.json", {**self.report, key: value})
                self.assert_stops("RETRY_ROLLBACK_NOT_PROVEN")

    def test_snapshot_identity_cannot_bind_another_original_run(self):
        self.snapshot["identities"][cutover.BACKEND]["invocation"] = "f" * 32
        self.write_json("private-before.json", self.snapshot)
        self.assert_stops("RETRY_BASELINE_IDENTITY_MISMATCH")

    def test_chroma_pid_and_invocation_must_remain_exact(self):
        for key, value in (("pid", "999"), ("invocation", "f" * 32)):
            with self.subTest(key=key):
                self.ids[cutover.CHROMA] = {**self.receipt["services"][cutover.CHROMA], key: value}
                self.assert_stops("RETRY_SERVICE_IDENTITY_MISMATCH")

    def test_old_backend_invocation_cannot_claim_completed_restart(self):
        self.ids[cutover.BACKEND] = copy.deepcopy(self.receipt["services"][cutover.BACKEND])
        self.assert_stops("RETRY_SERVICE_IDENTITY_MISMATCH")

    def test_pid_reuse_with_new_invocation_is_permitted_and_process_checked(self):
        self.ids[cutover.BACKEND]["pid"] = self.receipt["services"][cutover.BACKEND]["pid"]
        self.retry()
        self.process_check.assert_called_once_with(self.ids[cutover.BACKEND])
        self.assert_no_mutation()

    def test_changed_current_or_snapshot_unit_rejects_for_both_services(self):
        for source in (self.current, self.snapshot["units"]):
            for service in self.units:
                with self.subTest(source="current" if source is self.current else "snapshot", service=service):
                    original = source[service]["WorkingDirectory"]
                    source[service]["WorkingDirectory"] = "/unreviewed"
                    self.write_json("private-before.json", self.snapshot)
                    self.assert_stops("RETRY_UNIT_DRIFT")
                    source[service]["WorkingDirectory"] = original

    def test_missing_or_different_baseline_file_binding_rejects(self):
        original = dict(self.snapshot["files"])
        for remove in (True, False):
            self.snapshot["files"] = dict(original)
            if remove:
                del self.snapshot["files"][str(self.config)]
            else:
                self.snapshot["files"][str(self.config)] = "f" * 64
            self.write_json("private-before.json", self.snapshot)
            self.assert_stops("RETRY_BASELINE_FILE_MISMATCH")

    def test_changed_config_payload_rejects(self):
        self.config.write_bytes(b"changed configuration")
        self.assert_stops("RETRY_CONFIG_DRIFT")

    def test_previously_absent_config_now_present_rejects(self):
        self.absent.write_bytes(b"new late override")
        self.assert_stops("RETRY_CONFIG_DRIFT")

    def test_changed_owned_payload_rejects(self):
        self.witness.write_bytes(b"changed override")
        self.assert_stops("RETRY_PAYLOAD_DRIFT")

    def test_extra_hardlink_on_witness_rejects(self):
        os.link(self.witness, self.root / "extra-link")
        self.assert_stops("RETRY_PAYLOAD_DRIFT")

    def test_witness_symlink_rejects(self):
        destination = self.root / "other-override"
        destination.write_bytes(self.payload)
        self.witness.unlink()
        try:
            self.witness.symlink_to(destination)
        except OSError as error:
            self.skipTest("Host does not support symlinks: " + type(error).__name__)
        self.assert_stops("UNSAFE_TEST_PATH")

    def test_process_check_failure_propagates_without_rebinding_or_mutation(self):
        self.process_check.side_effect = RuntimeError("OLD_RUNTIME_PROCESS_NOT_PROVEN")
        with self.assertRaisesRegex(RuntimeError, "OLD_RUNTIME_PROCESS_NOT_PROVEN"):
            self.retry()
        self.process_check.assert_called_once_with(self.ids[cutover.BACKEND])
        self.assertEqual(self.capture_files(), self.original_files)
        self.assert_no_mutation()


if __name__ == "__main__":
    unittest.main()
