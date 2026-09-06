"""Synthetic routing checks: every HTTP request is mocked; no VM or store I/O."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


_spec = importlib.util.spec_from_file_location(
    "vm_chroma_routing_checks", Path(__file__).resolve().with_name("vm_chroma_routing_checks.py")
)
checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checks)


def inventory():
    names = (*checks.COLLECTIONS, "dita_ot_github", "learned_qa", "docker_docs", "other_index")
    return {name: {"id": f"00000000-0000-0000-0000-{number:012d}", "count": number - 1}
            for number, name in enumerate(names, 1)}


def identity(expected):
    return {"schema_version": checks.IDENTITY_SCHEMA, "status": "OK", "mode": "REMOTE",
            "target_fingerprint": checks.TARGET_FINGERPRINT,
            "tenant": checks.TENANT, "database": checks.DATABASE,
            "collections": {name: {"status": "OK", **expected[name]}
                            for name in checks.COLLECTIONS}}


def packet(expected, current=None):
    data = {"status": "ok", "chroma_available": True,
            "collections": {name: expected[name]["count"] for name in checks.COLLECTIONS},
            "index_identity": current if current is not None else identity(expected),
            "untrusted_extra": "SECRET_RAW_DOCUMENT"}
    return {"jsonrpc": "2.0", "id": checks.MCP_REQUEST["id"],
            "result": {"content": [{"type": "text", "text": json.dumps(data)}]}}


class TransportTests(unittest.TestCase):
    def connection(self, data=None, status=200, raw=None, headers=None):
        response = Mock(status=status)
        response.read.return_value = raw if raw is not None else json.dumps(data).encode()
        response.getheader.side_effect = lambda name, default=None: (headers or {}).get(name, default)
        connection = Mock()
        connection.getresponse.return_value = response
        return connection, response

    def test_fixed_loopback_bounded_read_and_close(self):
        connection, response = self.connection({"nanosecond heartbeat": 1})
        with patch.object(checks.http.client, "HTTPConnection", return_value=connection) as constructor:
            self.assertEqual(checks.http_json(8000, "GET", "/api/v2/heartbeat"),
                             {"nanosecond heartbeat": 1})
        constructor.assert_called_once_with("127.0.0.1", 8000, timeout=8)
        response.read.assert_called_once_with(checks.MAX_BYTES + 1)
        connection.close.assert_called_once()

    def test_no_redirects_and_no_error_body_read(self):
        for code in (301, 302, 307, 308, 401, 500):
            with self.subTest(status=code):
                connection, response = self.connection(raw=b"SECRET_ERROR", status=code)
                with patch.object(checks.http.client, "HTTPConnection", return_value=connection):
                    with self.assertRaisesRegex(checks.RoutingCheckError, "^HTTP_STATUS_NOT_OK$"):
                        checks.http_json(8000, "GET", "/api/v2/heartbeat")
                response.read.assert_not_called()
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_transport_and_parser_errors_are_redacted(self):
        for exception in (OSError("SECRET_TOKEN"), checks.http.client.HTTPException("SECRET_TOKEN")):
            with patch.object(checks.http.client, "HTTPConnection", side_effect=exception):
                with self.assertRaisesRegex(checks.RoutingCheckError, "^HTTP_REQUEST_FAILED$"):
                    checks.http_json(8000, "GET", "/api/v2/heartbeat")
        for raw in (b'SECRET_DOCUMENT', b'{"count": NaN}', b'{"id":1,"id":2}', b'\xff'):
            with self.subTest(raw=raw):
                connection, _ = self.connection(raw=raw)
                with patch.object(checks.http.client, "HTTPConnection", return_value=connection):
                    with self.assertRaisesRegex(checks.RoutingCheckError, "^INVALID_JSON_RESPONSE$"):
                        checks.http_json(8000, "GET", "/api/v2/heartbeat")
                connection.close.assert_called_once()

    def test_response_size_headers_and_body_are_bounded(self):
        for headers, raw, reason in (
            ({"Content-Length": str(checks.MAX_BYTES + 1)}, b"{}", "RESPONSE_TOO_LARGE"),
            ({}, b"x" * (checks.MAX_BYTES + 1), "RESPONSE_TOO_LARGE"),
            ({"Content-Length": "invalid SECRET"}, b"{}", "INVALID_RESPONSE_LENGTH"),
            ({"Content-Encoding": "gzip"}, b"{}", "UNSUPPORTED_RESPONSE_ENCODING"),
        ):
            with self.subTest(reason=reason, headers=headers):
                connection, _ = self.connection(raw=raw, headers=headers)
                with patch.object(checks.http.client, "HTTPConnection", return_value=connection):
                    with self.assertRaisesRegex(checks.RoutingCheckError, "^" + reason + "$"):
                        checks.http_json(8000, "GET", "/api/v2/heartbeat")

    def test_reject_writes_paths_ports_and_token_reuse_before_connection(self):
        invalid = [
            (443, "GET", "/health", None, ""),
            (True, "GET", "/health", None, ""),
            (8001, "GET", checks.CHROMA_COLLECTIONS, None, ""),
            (8000, "POST", "/mcp", checks.MCP_REQUEST, ""),
            (8000, "POST", checks.CHROMA_COLLECTIONS, {"name": "new"}, ""),
            (8000, "DELETE", checks.CHROMA_PREFIX + "jira_qa", None, ""),
            (8000, "POST", "/api/v2/reset", None, ""),
            (8000, "GET", checks.CHROMA_PREFIX + "../jira_qa", None, ""),
            (8000, "GET", checks.CHROMA_PREFIX + "jira_qa?limit=1", None, ""),
            (8000, "GET", "/api/v2/heartbeat", {}, ""),
            (4502, "GET", "/api/v2/heartbeat", None, "backend-secret"),
            (8001, "GET", "/mcp/health", None, "secret\r\nInjected: x"),
            (4502, "POST", "/mcp", {**checks.MCP_REQUEST, "method": "tools/list"}, ""),
        ]
        for args in invalid:
            with self.subTest(args=args):
                with patch.object(checks.http.client, "HTTPConnection") as constructor:
                    with self.assertRaises(checks.RoutingCheckError):
                        checks.http_json(*args)
                constructor.assert_not_called()

    def test_only_exact_status_tool_payload_and_backend_token(self):
        connection, _ = self.connection({})
        with patch.object(checks.http.client, "HTTPConnection", return_value=connection):
            checks.http_json(8001, "POST", "/mcp", checks.MCP_REQUEST, "private-token")
        arguments = connection.request.call_args
        self.assertEqual(json.loads(arguments.kwargs["body"]), checks.MCP_REQUEST)
        self.assertEqual(arguments.kwargs["headers"]["Authorization"], "Bearer private-token")
        mutated = deepcopy(checks.MCP_REQUEST)
        mutated["params"]["name"] = "reindex"
        with patch.object(checks, "MCP_REQUEST", mutated):
            with patch.object(checks.http.client, "HTTPConnection") as constructor:
                with self.assertRaises(checks.RoutingCheckError):
                    checks.http_json(8001, "POST", "/mcp", mutated)
                constructor.assert_not_called()


class InventoryTests(unittest.TestCase):
    def route(self, expected, changes=None):
        routes = {"/api/v2/heartbeat": {"nanosecond heartbeat": 1},
                  checks.CHROMA_COLLECTIONS: [dict(name=name, metadata={"secret": "RAW_METADATA"}, **row)
                                               for name, row in expected.items()]}
        for name, row in expected.items():
            routes[checks.CHROMA_PREFIX + name] = {"name": name, "id": row["id"],
                                                  "metadata": {"secret": "RAW_METADATA"}}
            routes[checks.CHROMA_PREFIX + row["id"] + "/count"] = row["count"]
        routes.update(changes or {})
        return lambda port, method, path: deepcopy(routes[path])

    def test_all_seven_collections_and_real_zero_are_verified(self):
        expected = inventory()
        with patch.object(checks, "http_json", side_effect=self.route(expected)) as request:
            report = checks.inspect_inventory(8000, expected)
        self.assertEqual(report["collections"], expected)
        self.assertEqual(request.call_count, 16)
        self.assertFalse(report["full_content_validation"])
        self.assertNotIn("RAW_METADATA", json.dumps(report))
        self.assertEqual(report["collections"]["jira_qa"]["count"], 0)

    def test_inventory_missing_extra_duplicate_and_changed_uuid_fail(self):
        expected = inventory()
        listed = [{"name": name, **row} for name, row in expected.items()]
        variants = [listed[:-1], listed + [{"name": "extra"}], listed[:-1] + [listed[0]],
                    [{**listed[0], "id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}] + listed[1:]]
        for value in variants:
            with self.subTest(value=value):
                with patch.object(checks, "http_json", side_effect=self.route(
                        expected, {checks.CHROMA_COLLECTIONS: value})):
                    with self.assertRaises(checks.RoutingCheckError):
                        checks.inspect_inventory(8000, expected)

    def test_missing_count_never_becomes_zero_and_last_collection_is_checked(self):
        expected = inventory()
        for name in ("jira_qa", "other_index"):
            for value in (None, True, -1, "0", expected[name]["count"] + 1):
                with self.subTest(name=name, value=value):
                    changes = {checks.CHROMA_PREFIX + expected[name]["id"] + "/count": value}
                    with patch.object(checks, "http_json", side_effect=self.route(expected, changes)):
                        with self.assertRaises(checks.RoutingCheckError):
                            checks.inspect_inventory(4502, expected)

    def test_lookup_drift_is_not_hidden_by_matching_collection_list(self):
        expected = inventory()
        for collection in ({"name": "jira_qa"}, {"name": "wrong", **expected["jira_qa"]},
                           {"name": "jira_qa", "id": expected["aem_guides"]["id"]}):
            with patch.object(checks, "http_json", side_effect=self.route(
                    expected, {checks.CHROMA_PREFIX + "jira_qa": collection})):
                with self.assertRaises(checks.RoutingCheckError):
                    checks.inspect_inventory(8000, expected)

    def test_invalid_expectations_fail_before_network(self):
        expected = inventory()
        variants = [{}, {key: row for key, row in expected.items() if key != "jira_qa"},
                    {**expected, "jira_qa": {"id": "bad", "count": 0}},
                    {**expected, "jira_qa": {"id": expected["jira_qa"]["id"], "count": None}},
                    {**expected, "jira_qa": expected["aem_guides"]}]
        for value in variants:
            with patch.object(checks, "http_json") as request:
                with self.assertRaises(checks.RoutingCheckError):
                    checks.inspect_inventory(8000, value)
            request.assert_not_called()


class BackendTests(unittest.TestCase):
    def route(self, expected, backend=None, gateway=None):
        def respond(port, method, path, body=None, token=""):
            if path == "/mcp/health":
                return {"status": "alive"}
            return deepcopy((backend if port == 8001 else gateway) or packet(expected))
        return respond

    def test_fingerprint_matches_exact_backend_schema(self):
        canonical = (b'{"database":"default_database","mode":"REMOTE",'
                     b'"target":{"host":"127.0.0.1","port":8000,"ssl":false},'
                     b'"tenant":"default_tenant"}')
        self.assertEqual(checks.TARGET_FINGERPRINT, hashlib.sha256(canonical).hexdigest())

    def test_live_backend_and_gateway_match_redacted_identity(self):
        expected = inventory()
        current = identity(expected)
        current["untrusted_secret"] = "SECRET_RAW_DOCUMENT"
        with patch.object(checks, "http_json", side_effect=self.route(
                expected, packet(expected, current), packet(expected, current))) as request:
            report = checks.verify_backend(expected, "backend-secret")
        self.assertEqual(report["status"], "MATCH")
        self.assertEqual(report["backend"], report["gateway"])
        self.assertFalse(report["full_content_validation"])
        self.assertNotIn("SECRET_RAW_DOCUMENT", json.dumps(report))
        self.assertNotIn("backend-secret", json.dumps(report))
        self.assertEqual([call.args[0] for call in request.call_args_list], [8001, 8001, 4502, 4502])

    def test_shared_wrong_target_and_gateway_drift_both_fail(self):
        expected = inventory()
        mutations = [("mode", "EMBEDDED"), ("tenant", "another_tenant"),
                     ("database", "another_database"), ("target_fingerprint", "a" * 64),
                     ("status", "PARTIAL"), ("schema_version", "unknown")]
        for field, value in mutations:
            for both_wrong in (True, False):
                with self.subTest(field=field, both_wrong=both_wrong):
                    current = identity(expected)
                    current[field] = value
                    bad = packet(expected, current)
                    with patch.object(checks, "http_json", side_effect=self.route(
                            expected, bad if both_wrong else None, bad)):
                        with self.assertRaises(checks.RoutingCheckError):
                            checks.verify_backend(expected)

    def test_runtime_missing_collection_uuid_count_and_false_zero_fail(self):
        expected = inventory()
        variants = []
        for name in checks.COLLECTIONS:
            current = identity(expected)
            del current["collections"][name]
            variants.append(current)
            for field, value in (("id", None), ("id", "f" * 36), ("count", None),
                                 ("count", True), ("count", -1), ("status", "UNAVAILABLE"),
                                 ("count", expected[name]["count"] + 1)):
                current = identity(expected)
                current["collections"][name][field] = value
                variants.append(current)
        for current in variants:
            with patch.object(checks, "http_json", side_effect=self.route(expected, packet(expected, current))):
                with self.assertRaises(checks.RoutingCheckError):
                    checks.verify_backend(expected)

    def test_mcp_protocol_failures_and_top_level_count_drift_fail(self):
        expected = inventory()
        valid = packet(expected)
        error_tool = deepcopy(valid)
        error_tool["result"]["isError"] = True
        count_drift = deepcopy(valid)
        data = json.loads(count_drift["result"]["content"][0]["text"])
        data["collections"]["jira_qa"] = None
        count_drift["result"]["content"][0]["text"] = json.dumps(data)
        ambiguous = deepcopy(valid)
        ambiguous["result"]["content"] *= 2
        invalid_unicode = deepcopy(valid)
        invalid_unicode["result"]["content"][0]["text"] = "SECRET\ud800"
        values = [{"error": {"message": "SECRET"}}, {**valid, "id": "wrong"}, error_tool,
                  {**valid, "result": {"content": []}}, count_drift, ambiguous, invalid_unicode]
        for value in values:
            with patch.object(checks, "http_json", side_effect=self.route(expected, value)):
                with self.assertRaises(checks.RoutingCheckError) as caught:
                    checks.verify_backend(expected)
                self.assertNotIn("SECRET", str(caught.exception))


class VectorSmokeTests(unittest.TestCase):
    def route(self, sample=None, result=None):
        def respond(port, method, path, body):
            if path.endswith("/get"):
                return deepcopy(sample if sample is not None else
                                {"ids": ["PRIVATE_RECORD_ID"], "embeddings": [[0.25, -0.5, 1.0]]})
            return deepcopy(result if result is not None else
                            {"ids": [["PRIVATE_RECORD_ID"]], "distances": [[0.0]]})
        return respond

    def test_queries_every_nonempty_collection_without_fixed_dimension(self):
        expected = inventory()
        with patch.object(checks, "http_json", side_effect=self.route()) as request:
            report = checks.smoke_vector_queries(expected)
        self.assertEqual(request.call_count, 12)
        self.assertEqual(report["collections"]["jira_qa"]["status"], "SKIPPED_EMPTY")
        for name in tuple(expected)[1:]:
            self.assertEqual(report["collections"][name]["dimension"], 3)
            self.assertEqual(report["collections"][name]["status"], "QUERY_SUCCEEDED")
        for call in request.call_args_list:
            self.assertEqual(call.args[:2], (8000, "POST"))
            if call.args[2].endswith("/query"):
                self.assertEqual(call.args[3]["include"], ["distances"])
                self.assertEqual(len(call.args[3]["query_embeddings"]), 1)
                self.assertIn(call.args[3]["n_results"], (1, 2, 3))
        self.assertFalse(report["full_content_validation"])
        self.assertTrue(report["query_smoke_only"])
        self.assertNotIn("PRIVATE_RECORD_ID", json.dumps(report))
        self.assertNotIn("0.25", json.dumps(report))

    def test_invalid_scalar_empty_nonfinite_and_boolean_vectors_fail(self):
        for vector in (None, 1, [], [True], [float("nan")], [float("inf")], [[1.0]], ["0.1"]):
            with self.subTest(vector=vector):
                sample = {"ids": ["id"], "embeddings": [vector]}
                with patch.object(checks, "http_json", side_effect=self.route(sample=sample)) as request:
                    with self.assertRaisesRegex(checks.RoutingCheckError, "^VECTOR_SAMPLE_INVALID$"):
                        checks.smoke_vector_queries(inventory())
                self.assertEqual(request.call_count, 1)

    def test_missing_sample_and_invalid_query_results_fail(self):
        for sample in ({}, {"ids": [], "embeddings": []},
                       {"ids": [None], "embeddings": [[1.0]]}):
            with patch.object(checks, "http_json", side_effect=self.route(sample=sample)):
                with self.assertRaises(checks.RoutingCheckError):
                    checks.smoke_vector_queries(inventory())
        for result in ({}, {"ids": [[]], "distances": [[]]},
                       {"ids": [[None]], "distances": [[0.0]]},
                       {"ids": [["id"]], "distances": [[None]]},
                       {"ids": [["id"]], "distances": [[True]]},
                       {"ids": [["id"]], "distances": [[float("inf")]]},
                       {"ids": [["id"]], "distances": [[]]},
                       {"ids": [["id", "id"]], "distances": [[0, 0]]}):
            with patch.object(checks, "http_json", side_effect=self.route(result=result)):
                with self.assertRaises(checks.RoutingCheckError):
                    checks.smoke_vector_queries(inventory())

    def test_transport_permits_only_constrained_vector_read_payloads(self):
        prefix = checks.CHROMA_PREFIX + inventory()["aem_guides"]["id"]
        valid_get = {"limit": 1, "include": ["embeddings"]}
        valid_query = {"query_embeddings": [[0.2, 0.1]], "n_results": 3, "include": ["distances"]}
        for suffix, body in (("/get", valid_get), ("/query", valid_query)):
            connection, _ = TransportTests().connection({})
            with patch.object(checks.http.client, "HTTPConnection", return_value=connection):
                checks.http_json(8000, "POST", prefix + suffix, body)
            self.assertEqual(json.loads(connection.request.call_args.kwargs["body"]), body)
        invalid = [
            (8000, "/get", {**valid_get, "limit": True}, ""),
            (8000, "/get", {**valid_get, "limit": 2}, ""),
            (8000, "/get", {**valid_get, "include": ["documents"]}, ""),
            (8000, "/query", {**valid_query, "include": ["metadatas"]}, ""),
            (8000, "/query", {**valid_query, "query_texts": ["private"]}, ""),
            (8000, "/query", {**valid_query, "n_results": 4}, ""),
            (8000, "/query", {**valid_query, "query_embeddings": [[float("nan")]]}, ""),
            (8000, "/query", {**valid_query, "query_embeddings": [[1], [2]]}, ""),
            (4502, "/query", valid_query, ""),
            (8000, "/query", valid_query, "backend-secret"),
            (8000, "/add", valid_query, ""),
        ]
        for port, suffix, body, token in invalid:
            with patch.object(checks.http.client, "HTTPConnection") as constructor:
                with self.assertRaises(checks.RoutingCheckError):
                    checks.http_json(port, "POST", prefix + suffix, body, token)
                constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
