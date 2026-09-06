"""Synthetic cutover control-flow/diagnostic tests; no VM, model, or network access."""
import json
import unittest
from unittest.mock import Mock, patch

import switch_vm_backend_candidate as cutover


class TransitionTests(unittest.TestCase):
    def callbacks(self, failing=None, error=None):
        calls = []
        result = {"status": "synthetic"}

        def callback(name):
            def run():
                calls.append(name)
                if name == failing:
                    raise error
                return result if name == "verify_live" else None
            return run

        names = ("install", "reload_units", "verify_units", "restart", "verify_live", "rollback")
        return calls, result, [callback(name) for name in names]

    def test_success_returns_live_result_without_rollback(self):
        calls, result, callbacks = self.callbacks()
        self.assertIs(cutover.transition(*callbacks), result)
        self.assertEqual(calls, ["install", "reload_units", "verify_units", "restart", "verify_live"])

    def test_each_failure_stops_forward_execution_and_calls_rollback(self):
        stages = ("install", "reload_units", "verify_units", "restart", "verify_live")
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                error = RuntimeError("SYNTHETIC_FAILURE")
                calls, _, callbacks = self.callbacks(stage, error)
                with self.assertRaises(RuntimeError) as caught:
                    cutover.transition(*callbacks)
                self.assertIs(caught.exception, error)
                self.assertEqual(calls, list(stages[:index + 1]) + ["rollback"])

    def test_interrupt_also_runs_rollback(self):
        calls, _, callbacks = self.callbacks("restart", KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            cutover.transition(*callbacks)
        self.assertEqual(calls[-1], "rollback")
        self.assertNotIn("verify_live", calls)

    def test_publication_conflict_does_not_reach_restart(self):
        calls, _, callbacks = self.callbacks("install", FileExistsError("SYNTHETIC_RACE"))
        with self.assertRaises(FileExistsError):
            cutover.transition(*callbacks)
        # Ownership-aware rollback itself is responsible for leaving a foreign file
        # alone; this test covers the transition's ordering, not that file guard.
        self.assertEqual(calls, ["install", "rollback"])

    def test_rollback_failure_is_not_reported_as_success(self):
        callbacks = [Mock() for _ in range(6)]
        callbacks[1].side_effect = RuntimeError("INITIAL_FAILURE")
        callbacks[-1].side_effect = RuntimeError("ROLLBACK_FAILURE")
        with self.assertRaisesRegex(RuntimeError, "ROLLBACK_FAILURE"):
            cutover.transition(*callbacks)
        callbacks[3].assert_not_called()
        callbacks[4].assert_not_called()


class UnitShapeTests(unittest.TestCase):
    def test_normalizes_exec_and_ignores_only_runtime_state(self):
        parser = Mock(return_value=("/python", ["/python", "-m", "uvicorn"]))
        source = {
            "MainPID": "123", "ActiveState": "active", "SubState": "running",
            "ExecStart": "serialized command", "Environment": "PRIVATE=retained",
            "WorkingDirectory": "/backend", "ReadOnlyPaths": "/original",
            "DropInPaths": "/etc/example.conf", "User": "root",
        }
        original = dict(source)
        actual = cutover.unit_shape(source, parser)
        self.assertEqual(actual, {
            "ExecStart": parser.return_value, "Environment": "PRIVATE=retained",
            "WorkingDirectory": "/backend", "ReadOnlyPaths": "/original",
            "DropInPaths": ["/etc/example.conf"], "User": "root",
        })
        parser.assert_called_once_with("serialized command")
        self.assertEqual(source, original)

    def test_parser_failure_is_not_hidden(self):
        with self.assertRaisesRegex(ValueError, "BAD_EXEC"):
            cutover.unit_shape({"ExecStart": "bad"}, Mock(side_effect=ValueError("BAD_EXEC")))

    def test_dropin_order_normalized_but_paths_not_discarded(self):
        parser = Mock()
        self.assertEqual(cutover.unit_shape({"DropInPaths": "/etc/z.conf /etc/a.conf"}, parser),
                         {"DropInPaths": ["/etc/a.conf", "/etc/z.conf"]})
        parser.assert_not_called()


class EmbeddingStatusTests(unittest.TestCase):
    def setUp(self):
        self.factory = patch.object(cutover.http.client, "HTTPConnection").start()
        self.addCleanup(patch.stopall)
        self.connection = self.factory.return_value
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.getheader.side_effect = lambda name, default=None: default
        self.good = {
            "provider": "LOCAL", "ready": True, "available": True,
            "availability_verified": True, "last_request_status": "SUCCESS",
            "last_vector_dimension": 384, "error": "",
        }

    def packet(self, value):
        self.response.read.return_value = json.dumps(value).encode()

    def diagnostic(self, **changes):
        self.packet({"rag": {"embedding": {**self.good, **changes}}})

    def test_valid_live_diagnostic_passes_and_uses_only_fixed_loopback_read(self):
        self.diagnostic()
        self.assertEqual(cutover.embedding_status(8001), {"status": "PASS"})
        self.factory.assert_called_once_with("127.0.0.1", 8001, timeout=15)
        self.connection.request.assert_called_once_with(
            "GET", "/api/v1/mcp/health", headers={"Accept": "application/json"})
        self.response.read.assert_called_once_with(1024**2 + 1)
        self.connection.close.assert_called_once_with()

    def test_gateway_port_allowed_without_substituting_credentials(self):
        self.diagnostic()
        self.assertEqual(cutover.embedding_status(4502), {"status": "PASS"})
        self.factory.assert_called_once_with("127.0.0.1", 4502, timeout=15)
        self.assertNotIn("Authorization", self.connection.request.call_args.kwargs["headers"])

    def test_other_port_rejected_before_network(self):
        for port in (8000, 443, 0, "8001", None):
            with self.subTest(port=port), self.assertRaisesRegex(ValueError, "INVALID_PORT"):
                cutover.embedding_status(port)
        self.factory.assert_not_called()

    def test_auth_failure_or_redirect_is_not_followed_or_bypassed(self):
        for code in (401, 403, 302, 404, 500):
            with self.subTest(code=code):
                self.response.status = code
                self.assertEqual(cutover.embedding_status(8001), {
                    "status": "NOT_VERIFIED", "http_status": code})
        self.response.read.assert_not_called()
        self.assertEqual(self.connection.request.call_count, 5)
        self.assertEqual(self.connection.close.call_count, 5)

    def test_explicit_wrong_provider_dimension_or_failed_encoding_fails(self):
        changes = (
            {"provider": "AZURE"}, {"last_vector_dimension": 1536},
            {"last_vector_dimension": "384"}, {"last_vector_dimension": True},
            {"ready": False}, {"available": False}, {"availability_verified": False},
            {"ready": 1}, {"last_request_status": "FAILED"},
            {"last_request_status": "NOT_REQUESTED"}, {"error": "private failure text"},
        )
        for change in changes:
            with self.subTest(change=change):
                self.diagnostic(**change)
                self.assertEqual(cutover.embedding_status(8001), {"status": "FAILED"})

    def test_missing_diagnostic_is_not_verified(self):
        for packet in ({}, {"rag": {}}, {"rag": {"embedding": {}}},
                       {"rag": {"embedding": []}}, {"rag": None}, []):
            with self.subTest(packet=packet):
                self.packet(packet)
                self.assertEqual(cutover.embedding_status(8001), {"status": "NOT_VERIFIED"})

    def test_malformed_json_is_not_verified(self):
        self.response.read.return_value = b"not json"
        self.assertEqual(cutover.embedding_status(8001), {"status": "NOT_VERIFIED"})
        self.connection.close.assert_called_once_with()

    def test_oversized_or_compressed_response_is_not_verified(self):
        self.response.read.return_value = b"x" * (1024**2 + 1)
        self.assertEqual(cutover.embedding_status(8001), {"status": "NOT_VERIFIED"})
        self.diagnostic()
        self.response.getheader.return_value = "gzip"
        self.response.getheader.side_effect = None
        self.assertEqual(cutover.embedding_status(8001), {"status": "NOT_VERIFIED"})

    def test_timeout_is_not_verified_and_connection_closes(self):
        self.connection.getresponse.side_effect = TimeoutError("PRIVATE_NETWORK_DETAIL")
        self.assertEqual(cutover.embedding_status(8001), {"status": "NOT_VERIFIED"})
        self.connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
