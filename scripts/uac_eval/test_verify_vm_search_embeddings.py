"""In-memory search diagnostic regressions; every HTTP request is mocked."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


_spec = importlib.util.spec_from_file_location(
    "vm_search_embeddings_test_subject",
    Path(__file__).resolve().with_name("verify_vm_search_embeddings.py"))
subject = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(subject)

PRIVATE = "PRIVATE_RESPONSE_MUST_NOT_APPEAR"
TOKEN = "synthetic-test-bearer"


def inventory(count=3):
    return {name: {"id": f"00000000-0000-0000-0000-{number:012d}", "count": count}
            for number, name in enumerate(subject.COLLECTIONS, 1)}


def status_data(expected=None, embedding_available=True):
    expected = inventory() if expected is None else expected
    return {
        "status": "ok", "chroma_available": True, "embedding_available": embedding_available,
        "collections": {name: row["count"] for name, row in expected.items()},
        "index_identity": {
            "schema_version": subject.routing.IDENTITY_SCHEMA, "status": "OK", "mode": "REMOTE",
            "target_fingerprint": subject.routing.TARGET_FINGERPRINT,
            "tenant": subject.routing.TENANT, "database": subject.routing.DATABASE,
            "collections": {name: {"status": "OK", **row, "private_metadata": PRIVATE}
                            for name, row in expected.items()},
            "private_path": PRIVATE},
        "unknown_details": PRIVATE,
    }


def packet(data, request_id=None):
    return {"jsonrpc": "2.0", "id": request_id or subject.routing._mcp_request()["id"],
            "result": {"content": [{"type": "text", "text": json.dumps(data)}]}}


def search_data(probe_id="table_editing", count=3, hits=2, searched=True):
    return {
        "schema_version": "jira-history-search-v2",
        "query_fingerprint": subject.fingerprint(dict(subject.PROBES)[probe_id]),
        "searched_jira_qa": searched, "indexed_chunks": count,
        "component_filter": None, "customer_filter": None,
        "match_count": hits, "rejected_candidate_count": 0,
        "results": [{"jira_key": f"GUIDES-{number}", "document": PRIVATE + str(number),
                     "retrieval": {"vector_score": 0.8, "keyword_score": 0.4,
                                   "metadata_score": 0.2, "final_score": 0.6},
                     "unknown_details": PRIVATE}
                    for number in range(1, hits + 1)],
        "backend_detail": PRIVATE,
    }


def search_packet(data, probe_id="table_editing"):
    return packet(data, "vm-search-" + probe_id)


def vector_data(count=3):
    return {"ids": [PRIVATE + str(number) for number in range(count)],
            "embeddings": [[0.5, -0.25, 0.75] for _ in range(count)],
            "documents": [PRIVATE] * count, "metadatas": [{"private": PRIVATE}] * count}


class ProbeTests(unittest.TestCase):
    def assert_failure(self, code, function, *args, **kwargs):
        with self.assertRaisesRegex(subject.ProbeError, "^" + code + "$") as raised:
            function(*args, **kwargs)
        self.assertNotIn(PRIVATE, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))

    def assert_redacted(self, report):
        serialized = json.dumps(report, allow_nan=False)
        for value in (PRIVATE, TOKEN, "GUIDES-1", "GUIDES-2"):
            self.assertNotIn(value, serialized)


class RequestTests(ProbeTests):
    def test_only_documented_status_history_and_collection_reads_are_constructed(self):
        self.assertEqual(subject.request_spec("status"),
                         ("POST", "/mcp", subject.routing._mcp_request()))
        for probe_id, query in subject.PROBES:
            method, path, body = subject.request_spec("history", probe_id)
            self.assertEqual((method, path), ("POST", "/mcp"))
            self.assertEqual(body["params"], {"name": "search_jira_history",
                                            "arguments": {"query": query, "top_k": 3}})
        for name, row in inventory().items():
            self.assertEqual(subject.request_spec("collection", name),
                             ("GET", subject.routing.CHROMA_PREFIX + name, None))
            self.assertEqual(subject.request_spec("count", row["id"]),
                             ("GET", subject.routing.CHROMA_PREFIX + row["id"] + "/count", None))
            self.assertEqual(subject.request_spec("vector_sample", row["id"]),
                             ("POST", subject.routing.CHROMA_PREFIX + row["id"] + "/get",
                              {"limit": 3, "include": ["embeddings"]}))

    def test_returned_request_mutation_cannot_extend_the_allowlist(self):
        body = subject.request_spec("status")[2]
        body["params"]["name"] = "reset_index"
        self.assertEqual(subject.request_spec("status")[2]["params"]["name"], "check_rag_status")
        body = subject.request_spec("history", "table_editing")[2]
        body["params"]["arguments"]["top_k"] = 10000
        self.assertEqual(subject.request_spec("history", "table_editing")[2]["params"]["arguments"]["top_k"], 3)

    def test_admin_writes_arbitrary_queries_paths_and_unknown_selectors_are_rejected(self):
        identifier = inventory()["jira_qa"]["id"]
        invalid = [(kind, identifier) for kind in ("reset", "add", "upsert", "delete", "query", "ingest", "synthesis")]
        invalid += [("status", "extra"), ("history", "arbitrary private query"),
                    ("collection", "../jira_qa"), ("collection", "jira_qa?limit=1"),
                    ("collection", "/api/v2/reset"), ("count", "jira_qa"),
                    ("vector_sample", identifier + "/delete"), ("history", "")]
        for kind, selector in invalid:
            with self.subTest(kind=kind, selector=selector):
                with patch.object(subject.http.client, "HTTPConnection") as connection:
                    self.assert_failure("REQUEST_NOT_ALLOWLISTED", subject.read_json, 8000, kind, selector)
                connection.assert_not_called()

    def test_other_ports_cross_route_operations_and_token_reuse_are_rejected(self):
        for port, kind, selector, token, code in (
                (443, "status", "", "", "PORT_NOT_ALLOWLISTED"),
                (True, "status", "", "", "PORT_NOT_ALLOWLISTED"),
                ("8001", "status", "", "", "PORT_NOT_ALLOWLISTED"),
                (8000, "status", "", "", "PORT_NOT_ALLOWLISTED"),
                (8001, "collection", "jira_qa", "", "PORT_NOT_ALLOWLISTED"),
                (4502, "collection", "jira_qa", "", "PORT_NOT_ALLOWLISTED"),
                (8000, "collection", "jira_qa", TOKEN, "BACKEND_TOKEN_NOT_ALLOWED_FOR_CHROMA")):
            with self.subTest(port=port, kind=kind):
                with patch.object(subject.http.client, "HTTPConnection") as connection:
                    self.assert_failure(code, subject.read_json, port, kind, selector, token=token)
                connection.assert_not_called()

    def test_invalid_tokens_are_rejected_before_connection(self):
        for token in (None, 1, "with space", "x\r\nInjected: value", "x\x00", "x\x7f", "x" * 8193):
            with self.subTest(token_type=type(token).__name__, length=len(token) if isinstance(token, str) else None):
                with patch.object(subject.http.client, "HTTPConnection") as connection:
                    self.assert_failure("INVALID_AUTH_TOKEN", subject.read_json, 8001, "status", token=token)
                connection.assert_not_called()


class TransportTests(ProbeTests):
    def connection(self, raw=b"{}", status=200, headers=None):
        values = {"Content-Type": "application/json"}
        values.update(headers or {})
        response = Mock(status=status)
        response.read.return_value = raw
        response.getheader.side_effect = lambda name, default=None: values.get(name, default)
        connection = Mock()
        connection.getresponse.return_value = response
        return connection, response

    def test_loopback_bounded_response_auth_scope_and_connection_close(self):
        for port, kind, selector, token in ((8001, "status", "", TOKEN),
                                             (4502, "history", "table_editing", TOKEN),
                                             (8000, "collection", "jira_qa", "")):
            with self.subTest(port=port):
                connection, response = self.connection(b'{"ok":true}')
                with patch.object(subject.http.client, "HTTPConnection", return_value=connection) as constructor:
                    self.assertEqual(subject.read_json(port, kind, selector, token=token), {"ok": True})
                constructor.assert_called_once_with("127.0.0.1", port, timeout=subject.SOCKET_TIMEOUT)
                method, path, body = subject.request_spec(kind, selector)
                args = connection.request.call_args
                self.assertEqual(args.args, (method, path))
                self.assertEqual(json.loads(args.kwargs["body"]) if body else args.kwargs["body"], body)
                if token:
                    self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer " + token)
                else:
                    self.assertNotIn("Authorization", args.kwargs["headers"])
                response.read.assert_called_once_with(subject.MAX_BYTES + 1)
                connection.close.assert_called_once()

    def test_auth_errors_redirects_and_other_statuses_never_read_response_bodies(self):
        for code in (301, 302, 303, 307, 308, 401, 403, 404, 500):
            with self.subTest(status=code):
                connection, response = self.connection(PRIVATE.encode(), status=code,
                                                       headers={"Location": "https://untrusted.invalid/"})
                failure = "AUTHENTICATION_OR_AUTHORIZATION_FAILED" if code in (401, 403) else "HTTP_STATUS_NOT_OK"
                with patch.object(subject.http.client, "HTTPConnection", return_value=connection) as constructor:
                    self.assert_failure(failure, subject.read_json, 8001, "status", token=TOKEN)
                constructor.assert_called_once()
                connection.request.assert_called_once()
                response.read.assert_not_called()
                connection.close.assert_called_once()

    def test_timeout_and_transport_errors_are_redacted_and_closed(self):
        for stage in ("constructor", "request", "response", "read"):
            for error, code in ((TimeoutError(PRIVATE), "HTTP_TIMEOUT"),
                                (OSError(PRIVATE), "HTTP_REQUEST_FAILED"),
                                (subject.http.client.HTTPException(PRIVATE), "HTTP_REQUEST_FAILED")):
                with self.subTest(stage=stage, code=code):
                    connection, response = self.connection()
                    if stage == "request":
                        connection.request.side_effect = error
                    elif stage == "response":
                        connection.getresponse.side_effect = error
                    elif stage == "read":
                        response.read.side_effect = error
                    with patch.object(subject.http.client, "HTTPConnection", return_value=connection,
                                      side_effect=error if stage == "constructor" else None):
                        self.assert_failure(code, subject.read_json, 8001, "status", token=TOKEN)
                    if stage != "constructor":
                        connection.close.assert_called_once()

    def test_bad_json_duplicate_keys_and_nonfinite_literals_are_rejected(self):
        for raw in (PRIVATE.encode(), b"\xff", b'{"a":1,"a":2}', b'{"nested":{"a":1,"a":2}}',
                    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}'):
            with self.subTest(raw=raw):
                connection, _ = self.connection(raw)
                with patch.object(subject.http.client, "HTTPConnection", return_value=connection):
                    self.assert_failure("INVALID_JSON_RESPONSE", subject.read_json, 8001, "status")
                connection.close.assert_called_once()

    def test_json_numeric_overflow_is_rejected_as_nonfinite(self):
        connection, _ = self.connection(b'{"nested":[{"score":1e999}]}')
        with patch.object(subject.http.client, "HTTPConnection", return_value=connection):
            self.assert_failure("INVALID_JSON_RESPONSE", subject.read_json, 8001, "status")

    def test_response_size_encoding_type_and_length_are_bounded(self):
        cases = [({"Content-Length": str(subject.MAX_BYTES + 1)}, b"{}", "RESPONSE_TOO_LARGE"),
                 ({}, b"x" * (subject.MAX_BYTES + 1), "RESPONSE_TOO_LARGE"),
                 ({"Content-Encoding": "gzip"}, b"{}", "UNSUPPORTED_RESPONSE_ENCODING"),
                 ({"Content-Type": "text/html"}, b"{}", "JSON_CONTENT_TYPE_REQUIRED"),
                 ({"Content-Type": ""}, b"{}", "JSON_CONTENT_TYPE_REQUIRED")]
        cases.extend(({"Content-Length": length}, b"{}", "INVALID_RESPONSE_LENGTH")
                     for length in ("-1", "+2", " 2", "2 ", "2.0", "99999999999", PRIVATE))
        for headers, raw, code in cases:
            with self.subTest(code=code, headers=headers):
                connection, _ = self.connection(raw, headers=headers)
                with patch.object(subject.http.client, "HTTPConnection", return_value=connection):
                    self.assert_failure(code, subject.read_json, 8001, "status")
                connection.close.assert_called_once()

    def test_deadline_limits_timeout_and_rejects_expired_reads(self):
        connection, _ = self.connection()
        with patch.object(subject.time, "monotonic", side_effect=[100, 102]), \
                patch.object(subject.http.client, "HTTPConnection", return_value=connection) as constructor:
            self.assertEqual(subject.read_json(8001, "status", deadline=110), {})
        constructor.assert_called_once_with("127.0.0.1", 8001, timeout=10)
        with patch.object(subject.time, "monotonic", return_value=100), \
                patch.object(subject.http.client, "HTTPConnection") as constructor:
            self.assert_failure("DIAGNOSTIC_BUDGET_EXHAUSTED", subject.read_json, 8001, "status", deadline=100)
        constructor.assert_not_called()
        connection, _ = self.connection()
        with patch.object(subject.time, "monotonic", side_effect=[100, 110]), \
                patch.object(subject.http.client, "HTTPConnection", return_value=connection):
            self.assert_failure("DIAGNOSTIC_BUDGET_EXHAUSTED", subject.read_json, 8001, "status", deadline=110)
        connection.close.assert_called_once()


class StatusTests(ProbeTests):
    def test_status_is_sanitized_without_mutating_identity_or_inventing_model_identity(self):
        data = status_data()
        original = deepcopy(data)
        result = subject.checked_status(packet(data))
        self.assertEqual(data, original)
        self.assertEqual(set(result), {"index_identity", "embedding_available_reported"})
        self.assertTrue(result["embedding_available_reported"])
        self.assertEqual(result["index_identity"]["collections"]["jira_qa"]["count"], 3)
        self.assert_redacted(result)
        self.assertNotIn("model", json.dumps(result))
        result["index_identity"]["collections"]["jira_qa"]["count"] = 999
        self.assertEqual(data, original)

    def test_embedding_unavailable_is_reported_false_and_unknown_model_fields_are_omitted(self):
        data = status_data(embedding_available=False)
        data.update(embedding_model=PRIVATE, fallback_model=PRIVATE, model_configuration={"token": TOKEN})
        result = subject.checked_status(packet(data))
        self.assertIs(result["embedding_available_reported"], False)
        self.assert_redacted(result)
        self.assertNotIn("model", json.dumps(result))

    def test_missing_or_nonboolean_embedding_availability_is_not_truthy_success(self):
        for value in (None, 0, 1, "true", "false", [], {}):
            with self.subTest(value=value):
                self.assert_failure("EMBEDDING_AVAILABILITY_NOT_REPORTED", subject.checked_status,
                                    packet(status_data(embedding_available=value)))
        data = status_data()
        data.pop("embedding_available")
        self.assert_failure("EMBEDDING_AVAILABILITY_NOT_REPORTED", subject.checked_status, packet(data))

    def test_missing_collection_invalid_uuid_and_noninteger_counts_fail(self):
        for field, value, code in (("id", PRIVATE, "COLLECTION_UUID_UNAVAILABLE"),
                                   ("count", True, "COLLECTION_COUNT_UNAVAILABLE"),
                                   ("count", "3", "COLLECTION_COUNT_UNAVAILABLE"),
                                   ("count", -1, "COLLECTION_COUNT_UNAVAILABLE")):
            with self.subTest(field=field, value=value):
                data = status_data()
                data["index_identity"]["collections"]["jira_qa"][field] = value
                self.assert_failure(code, subject.checked_status, packet(data))
        data = status_data()
        del data["index_identity"]["collections"]["jira_qa"]
        self.assert_failure("RUNTIME_COLLECTION_UNAVAILABLE", subject.checked_status, packet(data))

    def test_remote_scope_target_and_duplicate_collection_identity_are_checked(self):
        for field, value, code in (("mode", "LOCAL", "RUNTIME_NOT_REMOTE"),
                                   ("tenant", "other", "RUNTIME_SCOPE_MISMATCH"),
                                   ("database", "other", "RUNTIME_SCOPE_MISMATCH"),
                                   ("target_fingerprint", "0" * 64, "RUNTIME_TARGET_MISMATCH")):
            with self.subTest(field=field):
                data = status_data()
                data["index_identity"][field] = value
                self.assert_failure(code, subject.checked_status, packet(data))
        data = status_data()
        data["index_identity"]["collections"]["aem_guides"]["id"] = inventory()["jira_qa"]["id"]
        self.assert_failure("DUPLICATE_COLLECTION_UUID", subject.checked_status, packet(data))

    def test_public_counts_require_exact_integers_and_matching_values(self):
        for value in (True, "3", 3.0, 2, None):
            with self.subTest(value=value):
                data = status_data()
                data["collections"]["jira_qa"] = value
                self.assert_failure("MCP_COUNT_MISMATCH", subject.checked_status, packet(data))

    def test_invalid_ambiguous_and_error_mcp_envelopes_are_redacted(self):
        cases = []
        for field, value in (("jsonrpc", "1.0"), ("id", "wrong-id"), ("error", PRIVATE)):
            changed = packet(status_data())
            changed[field] = value
            cases.append((changed, "INVALID_MCP_RESPONSE"))
        changed = packet(status_data())
        changed["result"]["isError"] = True
        cases.append((changed, "MCP_TOOL_ERROR"))
        changed = packet(status_data())
        changed["result"]["content"] *= 2
        cases.append((changed, "AMBIGUOUS_MCP_CONTENT"))
        cases.append((packet({"error": PRIVATE}), "BACKEND_REPORTED_ERROR"))
        for changed, code in cases:
            with self.subTest(code=code):
                self.assert_failure(code, subject.checked_status, changed)


class VectorTests(ProbeTests):
    def test_sample_counts_and_dimension_do_not_claim_active_encoder(self):
        for count in (1, 2, 3, 10):
            with self.subTest(count=count):
                result = subject.vector_summary(vector_data(min(3, count)), count)
                self.assertEqual(result, {"status": "FINITE_STORED_VECTOR_SAMPLE", "samples": min(3, count),
                                          "dimension": 3, "current_query_dimension": None,
                                          "current_encoder_verified": False})
                self.assert_redacted(result)

    def test_sample_length_ids_and_vector_shapes_are_strict(self):
        for field, value in (("ids", []), ("ids", ["a", "a", "a"]), ("ids", ["a", "b", "bad\x00id"]),
                             ("ids", "abc"), ("embeddings", []), ("embeddings", [[], [], []]),
                             ("embeddings", [[True], [1], [1]]), ("embeddings", [["1"], [1], [1]]),
                             ("embeddings", [[float("nan")], [1], [1]]),
                             ("embeddings", [[float("inf")], [1], [1]])):
            with self.subTest(field=field, value_type=type(value).__name__):
                data = vector_data()
                data[field] = value
                self.assert_failure("VECTOR_SAMPLE_INVALID", subject.vector_summary, data, 3)

    def test_conflicting_dimensions_and_zero_vectors_are_rejected(self):
        data = vector_data()
        data["embeddings"][1] = [1, 2]
        self.assert_failure("STORED_SAMPLE_DIMENSIONS_CONFLICT", subject.vector_summary, data, 3)
        data = vector_data()
        data["embeddings"][1] = [0, -0.0, 0]
        self.assert_failure("ZERO_STORED_VECTOR", subject.vector_summary, data, 3)


class SearchTests(ProbeTests):
    def summary(self, data, probe_id="table_editing"):
        return subject.search_summary(search_packet(data, probe_id), probe_id, 3)

    def test_valid_v2_results_keep_finite_scores_but_hash_references_and_documents(self):
        data = search_data()
        result = self.summary(data)
        self.assertEqual(result["status"], "RETURNED_RESULTS")
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["results"][0]["reference_sha256"], subject.fingerprint("GUIDES-1"))
        self.assertEqual(result["results"][0]["document_sha256"], subject.fingerprint(PRIVATE + "1"))
        self.assertEqual(result["results"][0]["scores"], data["results"][0]["retrieval"])
        self.assertIs(result["fresh_embedding_verified"], False)
        self.assertIs(result["semantic_relevance_human_verified"], False)
        self.assert_redacted(result)

    def test_empty_search_and_unavailable_retrieval_are_distinct(self):
        self.assertEqual(self.summary(search_data(hits=0))["status"], "INCONCLUSIVE_EMPTY_RESULTS")
        self.assertEqual(self.summary(search_data(hits=0, searched=False))["status"], "RETRIEVAL_UNAVAILABLE")
        self.assert_failure("SEARCH_STATE_CONTRADICTS_RESULTS", self.summary, search_data(searched=False))

    def test_schema_current_query_fingerprint_and_unfiltered_request_must_match(self):
        for field, value, code in (("schema_version", "v1", "SEARCH_SCHEMA_NOT_SUPPORTED"),
                                   ("query_fingerprint", "0" * 64, "QUERY_FINGERPRINT_MISMATCH"),
                                   ("component_filter", "Editor", "UNEXPECTED_SEARCH_FILTER"),
                                   ("customer_filter", "private", "UNEXPECTED_SEARCH_FILTER")):
            with self.subTest(field=field):
                data = search_data()
                data[field] = value
                self.assert_failure(code, self.summary, data)

    def test_booleans_strings_and_missing_search_counters_are_not_accepted_as_numbers(self):
        for field, code in (("indexed_chunks", "SEARCH_INDEX_COUNT_MISMATCH"),
                            ("match_count", "SEARCH_RESULTS_INVALID"),
                            ("rejected_candidate_count", "SEARCH_REJECTION_COUNT_INVALID")):
            for value in (True, False, "0", "3", 3.0, -1, None):
                with self.subTest(field=field, value=value):
                    data = search_data()
                    data[field] = value
                    self.assert_failure(code, self.summary, data)
        for value in (None, 0, 1, "true", "false"):
            with self.subTest(searched=value):
                data = search_data()
                data["searched_jira_qa"] = value
                self.assert_failure("SEARCH_STATE_NOT_REPORTED", self.summary, data)

    def test_bad_result_count_duplicates_and_untrusted_references_are_rejected(self):
        data = search_data()
        data["match_count"] = 1
        self.assert_failure("SEARCH_RESULTS_INVALID", self.summary, data)
        data = search_data(hits=4)
        self.assert_failure("SEARCH_RESULTS_INVALID", self.summary, data)
        data = search_data()
        data["results"][1]["jira_key"] = data["results"][0]["jira_key"]
        self.assert_failure("DUPLICATE_SEARCH_RESULT", self.summary, data)
        for value in (None, "lower-1", "../GUIDES-1", PRIVATE):
            with self.subTest(reference=value):
                data = search_data()
                data["results"][0]["jira_key"] = value
                self.assert_failure("SEARCH_RESULT_REFERENCE_INVALID", self.summary, data)

    def test_missing_empty_and_oversize_documents_are_rejected(self):
        for value in (None, "", PRIVATE * 300):
            with self.subTest(length=len(value) if isinstance(value, str) else None):
                data = search_data()
                data["results"][0]["document"] = value
                self.assert_failure("SEARCH_RESULT_DOCUMENT_INVALID", self.summary, data)

    def test_all_retrieval_scores_require_finite_numbers_between_zero_and_one(self):
        for field in ("vector_score", "keyword_score", "metadata_score", "final_score"):
            for value in (True, False, "0.5", None, -0.1, 1.1):
                with self.subTest(field=field, value=value):
                    data = search_data()
                    data["results"][0]["retrieval"][field] = value
                    self.assert_failure("RETRIEVAL_SCORE_INVALID", self.summary, data)
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, nonfinite=value):
                    data = search_data()
                    data["results"][0]["retrieval"][field] = value
                    self.assert_failure("INVALID_JSON_RESPONSE", self.summary, data)
        data = search_data()
        del data["results"][0]["retrieval"]
        self.assert_failure("RETRIEVAL_EVIDENCE_NOT_REPORTED", self.summary, data)


class FakeReader:
    def __init__(self, expected=None):
        self.expected = inventory() if expected is None else expected
        self.calls = []
        self.status_calls = {8001: 0, 4502: 0}
        self.change = None

    def __call__(self, port, kind, selector="", *, token="", deadline=None):
        self.calls.append((port, kind, selector, token, deadline))
        if port not in (8000, 8001, 4502) or (port == 8000 and token):
            raise AssertionError("Unexpected transport target or token exposure")
        if kind == "status":
            self.status_calls[port] += 1
            value = status_data(self.expected)
        elif kind == "collection":
            value = {"name": selector, "id": self.expected[selector]["id"], "metadata": PRIVATE}
        elif kind in ("count", "vector_sample"):
            row = next(row for row in self.expected.values() if row["id"] == selector)
            value = row["count"] if kind == "count" else vector_data(min(3, row["count"]))
        elif kind == "history":
            value = search_data(selector, count=self.expected["jira_qa"]["count"])
            if port == 4502:
                value["results"].reverse()
                value["results"][0]["retrieval"]["final_score"] = 0.7
        else:
            raise AssertionError("Unexpected operation")
        if self.change is not None:
            value = self.change(port, kind, selector, value)
        if kind == "status":
            return packet(value)
        if kind == "history":
            return search_packet(value, selector)
        return deepcopy(value)


class DiagnosticTests(ProbeTests):
    def run_reader(self, reader):
        with patch.object(subject.http.client, "HTTPConnection") as connection:
            report = subject.run_diagnostic(token=TOKEN, reader=reader)
        connection.assert_not_called()
        self.assert_redacted(report)
        return report

    def assert_proof_boundaries(self, report):
        self.assertTrue(all(value is False for value in report["actions"].values()))
        for field in ("model_parity_proven", "fresh_embedding_verified"):
            self.assertIs(report["embedding_verification"][field], False)
        for field in ("full_live_payload_equality_verified", "ranking_parity_proven",
                      "team_client_authentication_verified", "import_authorized", "resume_writers_authorized"):
            self.assertIs(report[field], False)

    def test_all_hits_pass_smoke_only_despite_route_score_order_differences(self):
        reader = FakeReader()
        report = self.run_reader(reader)
        self.assertEqual(report["status"], "PASS_QUERY_SMOKE_ONLY")
        self.assertEqual(report["phase"], "COMPLETE")
        self.assertTrue(report["routing_identity_and_counts_stable"])
        self.assertEqual(len(report["queries"]), 3)
        self.assertEqual(reader.status_calls, {8001: 2, 4502: 2})
        self.assert_proof_boundaries(report)
        for query in report["queries"]:
            self.assertEqual(query["returned_reference_overlap_count"], 2)
            self.assertIn("INFORMATIONAL_ONLY", query["ranking_comparison"])
            self.assertNotEqual(query["routes"]["backend_8001"]["results"],
                                query["routes"]["gateway_4502"]["results"])
        for port, kind, selector, token, deadline in reader.calls:
            self.assertEqual(token, "" if port == 8000 else TOKEN)
            self.assertIsInstance(deadline, (int, float))
            self.assertIn(kind, {"status", "collection", "count", "vector_sample", "history"})

    def test_empty_or_unavailable_search_returns_partial_without_inventing_success(self):
        for searched, expected_status in ((True, "INCONCLUSIVE_EMPTY_RESULTS"), (False, "RETRIEVAL_UNAVAILABLE")):
            with self.subTest(searched=searched):
                reader = FakeReader()
                def change(port, kind, selector, value):
                    if kind == "history" and port == 4502 and selector == "table_editing":
                        return search_data(selector, hits=0, searched=searched)
                    return value
                reader.change = change
                report = self.run_reader(reader)
                self.assertEqual(report["status"], "PARTIAL_QUERY_SMOKE")
                self.assertEqual(report["queries"][0]["routes"]["gateway_4502"]["status"], expected_status)
                self.assert_proof_boundaries(report)

    def test_embedding_unavailable_with_hits_remains_partial(self):
        reader = FakeReader()
        def change(port, kind, selector, value):
            if kind == "status":
                value["embedding_available"] = False
            return value
        reader.change = change
        report = self.run_reader(reader)
        self.assertEqual(report["status"], "PARTIAL_QUERY_SMOKE")
        self.assert_proof_boundaries(report)

    def test_empty_stored_collection_skips_vector_sampling(self):
        expected = inventory()
        expected["dita_spec"]["count"] = 0
        reader = FakeReader(expected)
        report = self.run_reader(reader)
        self.assertEqual(report["stored_vector_samples"]["dita_spec"], {"status": "EMPTY_COLLECTION", "samples": 0})
        self.assertFalse(any(kind == "vector_sample" and selector == expected["dita_spec"]["id"]
                             for _, kind, selector, _, _ in reader.calls))
        self.assert_proof_boundaries(report)

    def test_route_identity_mismatch_and_identity_drift_block(self):
        for stage, code in (("initial", "BACKEND_GATEWAY_ROUTING_MISMATCH"),
                            ("after", "INDEX_CHANGED_DURING_PROBE")):
            with self.subTest(stage=stage):
                reader = FakeReader()
                def change(port, kind, selector, value):
                    if kind == "status" and ((stage == "initial" and port == 4502)
                                              or (stage == "after" and reader.status_calls[port] == 2)):
                        value["index_identity"]["collections"]["jira_qa"]["id"] = "99999999-0000-0000-0000-000000000001"
                    return value
                reader.change = change
                report = self.run_reader(reader)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["reason"], code)
                self.assert_proof_boundaries(report)

    def test_direct_inventory_id_or_count_mismatch_blocks(self):
        for kind, replacement, code in (("collection", {"name": "jira_qa", "id": "99999999-0000-0000-0000-000000000001"},
                                         "DIRECT_COLLECTION_MISMATCH"),
                                        ("count", True, "DIRECT_COUNT_MISMATCH"),
                                        ("count", "3", "DIRECT_COUNT_MISMATCH"),
                                        ("count", 4, "DIRECT_COUNT_MISMATCH")):
            with self.subTest(kind=kind, code=code):
                reader = FakeReader()
                reader.change = lambda port, operation, selector, value: replacement if operation == kind else value
                report = self.run_reader(reader)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["reason"], code)

    def test_auth_timeout_and_unexpected_errors_block_with_redacted_reason(self):
        for failure, code in ((subject.ProbeError("AUTHENTICATION_OR_AUTHORIZATION_FAILED"),
                               "AUTHENTICATION_OR_AUTHORIZATION_FAILED"),
                              (subject.ProbeError("HTTP_TIMEOUT"), "HTTP_TIMEOUT"),
                              (RuntimeError(PRIVATE + TOKEN), "UNEXPECTED_DIAGNOSTIC_FAILURE")):
            for operation in ("status", "history"):
                with self.subTest(operation=operation, code=code):
                    reader = FakeReader()
                    def change(port, kind, selector, value):
                        if kind == operation:
                            raise failure
                        return value
                    reader.change = change
                    report = self.run_reader(reader)
                    self.assertEqual(report["status"], "BLOCKED")
                    self.assertEqual(report["reason"], code)
                    self.assert_proof_boundaries(report)


class CliTests(ProbeTests):
    def test_self_test_cli_dispatches_only_to_test_entry_point(self):
        runner = Mock(return_value=0)
        with patch.object(subject, "_sibling", return_value=SimpleNamespace(run_self_tests=runner)) as sibling, \
                patch.object(subject, "run_diagnostic") as diagnostic:
            self.assertEqual(subject.main(["--self-test"]), 0)
        sibling.assert_called_once_with("test_verify_vm_search_embeddings")
        runner.assert_called_once_with()
        diagnostic.assert_not_called()

    def test_non_linux_cli_stops_before_diagnostic(self):
        error = io.StringIO()
        with patch.object(subject.sys, "platform", "win32"), patch.object(subject, "run_diagnostic") as diagnostic, \
                redirect_stderr(error):
            self.assertEqual(subject.main([]), 1)
        diagnostic.assert_not_called()
        self.assertIn("RUN_ON_VM_LINUX_LOOPBACK_REQUIRED", error.getvalue())

    def test_cli_status_exit_codes_and_allowlisted_report_printing(self):
        for status, code in (("PASS_QUERY_SMOKE_ONLY", 0), ("PARTIAL_QUERY_SMOKE", 2), ("BLOCKED", 1)):
            with self.subTest(status=status):
                output = io.StringIO()
                with patch.object(subject.sys, "platform", "linux"), \
                        patch.dict(subject.os.environ, {"AEM_STUDIO_TOKEN": TOKEN}), \
                        patch.object(subject, "run_diagnostic", return_value={"status": status}) as diagnostic, \
                        redirect_stdout(output):
                    self.assertEqual(subject.main([]), code)
                diagnostic.assert_called_once_with(token=TOKEN)
                self.assertEqual(json.loads(output.getvalue()), {"status": status})
                self.assertNotIn(TOKEN, output.getvalue())


def run_self_tests():
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                               for case in (RequestTests, TransportTests, StatusTests,
                                            VectorTests, SearchTests, DiagnosticTests, CliTests))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_self_tests())
