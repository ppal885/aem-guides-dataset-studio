"""Query logging regressions using fake clients; no Chroma, network, or storage."""
from copy import deepcopy
import io
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


# Support the isolated interpreter without consulting cwd or PYTHONPATH.
_backend = str(Path(__file__).resolve().parents[1])
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.core.structured_logging import StructuredJSONFormatter, StructuredLoggerAdapter
from app.services import vector_store_service as vectors


PREFIX = "ChromaDB query failed [CHROMA_QUERY_DIAGNOSTIC_V1] "
PRIVATE = "PRIVATE_DIAGNOSTIC_CONTENT"
UNSAFE = PRIVATE + "\nAuthorization: Bearer synthetic-token https://user:password@private.invalid/path?token=secret"
NAMES = ("aem_guides", "dita_spec", "jira_qa", "dita_ot_github", "learned_qa", "docker_docs")
STAGES = ("GET_COLLECTION", "COUNT", "QUERY_CALL", "RESULT_IDS", "RESULT_DOCUMENTS",
          "RESULT_METADATAS", "RESULT_DISTANCES")
FIELDS = {"schema_version", "stage", "collection", "query_vector_dimension", "error_type", "message_signal"}


def valid_result():
    return {"ids": [["id-1", "id-2"]], "documents": [["document-1", "document-2"]],
            "metadatas": [[{"source": "one"}, {"source": "two"}]], "distances": [[0.0, 0.25]]}


class AmbiguousTruth:
    def __bool__(self):
        raise ValueError("The truth value of an array with more than one element is ambiguous. " + UNSAFE)


class BrokenStringError(Exception):
    def __str__(self):
        raise RuntimeError(UNSAFE)


class DiagnosticHelperTests(unittest.TestCase):
    def diagnostic(self, stage="QUERY_CALL", collection="jira_qa", dimension=3, error=None):
        return vectors._query_failure_diagnostic(stage, collection, dimension,
                                                ValueError(UNSAFE) if error is None else error)

    def assert_safe(self, result):
        self.assertEqual(set(result), FIELDS)
        self.assertEqual(result["schema_version"], "chroma-query-diagnostic-v1")
        serialized = json.dumps(result, allow_nan=False)
        for text in (PRIVATE, "Authorization:", "Bearer", "synthetic-token", "private.invalid",
                     "password", "?token=", "\n"):
            self.assertNotIn(text, serialized)

    def test_allowed_stage_and_collection_are_kept_without_extra_fields(self):
        for stage in STAGES:
            for collection in NAMES:
                with self.subTest(stage=stage, collection=collection):
                    result = self.diagnostic(stage=stage, collection=collection)
                    self.assertEqual(result["stage"], stage)
                    self.assertEqual(result["collection"], collection)
                    self.assertEqual(result["query_vector_dimension"], 3)
                    self.assertEqual(result["error_type"], "ValueError")
                    self.assert_safe(result)

    def test_unknown_stage_collection_and_dynamic_exception_name_are_redacted(self):
        error_type = type(UNSAFE, (Exception,), {})
        for value in (UNSAFE, "", None, [], {}, 1):
            with self.subTest(value_type=type(value).__name__):
                result = self.diagnostic(stage=value, collection=value, error=error_type(UNSAFE))
                self.assertEqual(result["stage"], "UNKNOWN")
                self.assertEqual(result["collection"], "OTHER")
                self.assertEqual(result["error_type"], "OTHER")
                self.assert_safe(result)

    def test_only_builtin_nonnegative_integer_dimensions_are_reported(self):
        class IntegerSubclass(int):
            pass
        for value in (0, 1, 384, 1536, -1, True, False, 3.0, "3", None, [], IntegerSubclass(3)):
            with self.subTest(dimension_type=type(value).__name__, value=value):
                result = self.diagnostic(dimension=value)
                self.assertEqual(result["query_vector_dimension"], value if type(value) is int and value >= 0 else None)
                self.assert_safe(result)

    def test_exception_message_signals_are_fixed_categories_not_raw_text(self):
        cases = (
            (ValueError("The truth value of an array with more than one element is ambiguous. " + UNSAFE),
             "AMBIGUOUS_TRUTH_VALUE"),
            (ValueError("Embedding dimension 384 does not match dimensionality 768. " + UNSAFE),
             "DIMENSION_MISMATCH"),
            (TimeoutError("Request timed out. " + UNSAFE), "TIMEOUT"),
            (ConnectionError("Connection refused. " + UNSAFE), "CONNECTION_FAILURE"),
            (RuntimeError("401 Unauthorized. " + UNSAFE), "AUTH_FAILURE"),
            (RuntimeError("429 Too Many Requests. " + UNSAFE), "RATE_LIMITED"),
            (ValueError("Invalid argument. " + UNSAFE), "INVALID_ARGUMENT"),
            (RuntimeError(UNSAFE), "UNKNOWN"),
        )
        for error, expected in cases:
            with self.subTest(signal=expected):
                result = self.diagnostic(error=error)
                self.assertEqual(result["message_signal"], expected)
                self.assert_safe(result)

    def test_error_with_failing_string_conversion_cannot_break_diagnostic(self):
        result = self.diagnostic(error=BrokenStringError())
        self.assertEqual(result["message_signal"], "UNKNOWN")
        self.assertEqual(result["error_type"], "OTHER")
        self.assert_safe(result)

    def test_allowlisted_chroma_and_http_exception_names_are_safe_without_library_imports(self):
        for name in ("InvalidArgumentError", "InvalidDimensionException", "InvalidDimensionError",
                     "NotFoundError", "AuthorizationError", "AuthenticationError", "HTTPStatusError",
                     "HTTPError", "ReadTimeout", "ConnectTimeout", "ConnectError", "RequestError",
                     "InternalError", "ChromaError"):
            with self.subTest(error_type=name):
                error_type = type(name, (Exception,), {})
                result = self.diagnostic(error=error_type(UNSAFE))
                self.assertEqual(result["error_type"], name)
                self.assert_safe(result)

    def test_message_signal_uses_only_the_bounded_error_prefix(self):
        in_prefix = self.diagnostic(error=RuntimeError("timed out " + "x" * 5000 + UNSAFE))
        self.assertEqual(in_prefix["message_signal"], "TIMEOUT")
        self.assert_safe(in_prefix)
        beyond_prefix = self.diagnostic(error=RuntimeError("x" * 4096 + " timed out " + UNSAFE))
        self.assertEqual(beyond_prefix["message_signal"], "UNKNOWN")
        self.assert_safe(beyond_prefix)


class QueryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.collection = Mock(spec=["count", "query"])
        self.collection.count.return_value = 7
        self.collection.query.return_value = valid_result()
        self.client = Mock(spec=["list_collections", "get_collection"])
        self.client.list_collections.return_value = [SimpleNamespace(name="jira_qa")]
        self.client.get_collection.return_value = self.collection
        self.client_patch = patch.object(vectors, "_get_client", return_value=self.client)
        self.get_client = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.logger_patch = patch.object(vectors, "logger")
        self.logger = self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)

    def query(self, embedding=None, *, k=5, where=None, collection="jira_qa"):
        return vectors.query_collection(collection, [0.5, 0.0, -0.5] if embedding is None else embedding,
                                        k=k, where=where)

    def assert_warning(self, stage, error_type=None, signal=None, dimension=3, collection="jira_qa"):
        self.logger.warning_structured.assert_called_once()
        args = self.logger.warning_structured.call_args
        self.assertEqual(len(args.args), 1)
        self.assertEqual(set(args.kwargs), {"extra_fields"})
        message = args.args[0]
        self.assertTrue(message.startswith(PREFIX))
        payload = json.loads(message[len(PREFIX):])
        self.assertEqual(payload, args.kwargs["extra_fields"])
        self.assertEqual(set(payload), FIELDS)
        self.assertEqual(payload["schema_version"], "chroma-query-diagnostic-v1")
        self.assertEqual(payload["stage"], stage)
        self.assertEqual(payload["collection"], collection)
        self.assertEqual(payload["query_vector_dimension"], dimension)
        if error_type is not None:
            self.assertEqual(payload["error_type"], error_type)
        if signal is not None:
            self.assertEqual(payload["message_signal"], signal)
        self.assertNotIn("\n", message)
        self.assertNotIn(": ", message[len(PREFIX):])
        self.assertNotIn(", ", message[len(PREFIX):])
        for raw in (PRIVATE, "synthetic-token", "private.invalid", "password", "Authorization"):
            self.assertNotIn(raw, message + json.dumps(args.kwargs))
        self.assertEqual(self.logger.mock_calls, [call.warning_structured(message, extra_fields=payload)])
        return payload

    def test_success_preserves_calls_arguments_order_and_result_parsing(self):
        embedding = [0.5, 0.0, -0.5]
        where = {"source": PRIVATE}
        original = valid_result()
        self.collection.query.return_value = deepcopy(original)
        rows = self.query(embedding, k=10, where=where)
        self.assertEqual(rows, [
            {"id": "id-1", "document": "document-1", "metadata": {"source": "one"}, "distance": 0.0},
            {"id": "id-2", "document": "document-2", "metadata": {"source": "two"}, "distance": 0.25}])
        self.get_client.assert_called_once_with()
        self.assertEqual(self.client.method_calls, [call.list_collections(), call.get_collection(name="jira_qa")])
        self.assertEqual(self.collection.method_calls, [call.count(), call.query(
            query_embeddings=[embedding], n_results=7, where=where,
            include=["documents", "metadatas", "distances"])])
        self.assertIs(self.collection.query.call_args.kwargs["where"], where)
        self.assertEqual(self.collection.query.return_value, original)
        self.logger.assert_not_called()
        self.assertEqual(self.logger.mock_calls, [])

    def test_embedding_tolist_conversion_and_k_limit_are_preserved(self):
        class Embedding:
            def tolist(self):
                return [0.1, 0.2]
        self.query(Embedding(), k=2)
        self.collection.query.assert_called_once_with(query_embeddings=[[0.1, 0.2]], n_results=2,
                                                     where=None, include=["documents", "metadatas", "distances"])
        self.assertEqual(self.logger.mock_calls, [])

    def test_api_failures_report_exact_stage_without_retry_or_extra_reads(self):
        for stage in ("GET_COLLECTION", "COUNT", "QUERY_CALL"):
            with self.subTest(stage=stage):
                self.client.reset_mock()
                self.collection.reset_mock()
                self.logger.reset_mock()
                self.client.get_collection.side_effect = None
                self.collection.count.side_effect = None
                self.collection.query.side_effect = None
                target = {"GET_COLLECTION": self.client.get_collection, "COUNT": self.collection.count,
                          "QUERY_CALL": self.collection.query}[stage]
                target.side_effect = ValueError(UNSAFE)
                self.assertEqual(self.query(), [])
                self.assert_warning(stage, error_type="ValueError")
                self.assertEqual(self.client.method_calls, [call.list_collections(), call.get_collection(name="jira_qa")])
                expected = [] if stage == "GET_COLLECTION" else [call.count()]
                if stage == "QUERY_CALL":
                    expected.append(call.query(query_embeddings=[[0.5, 0.0, -0.5]], n_results=5,
                                               where=None, include=["documents", "metadatas", "distances"]))
                self.assertEqual(self.collection.method_calls, expected)

    def test_malformed_result_fields_report_the_original_failing_stage(self):
        for key, stage in (("ids", "RESULT_IDS"), ("documents", "RESULT_DOCUMENTS"),
                            ("metadatas", "RESULT_METADATAS"), ("distances", "RESULT_DISTANCES")):
            with self.subTest(key=key):
                result = valid_result()
                if key == "ids":
                    del result[key]
                else:
                    result[key] = [[]]
                self.collection.query.return_value = result
                self.logger.reset_mock()
                self.assertEqual(self.query(), [])
                self.assert_warning(stage, error_type="KeyError" if key == "ids" else "IndexError")

    def test_arraylike_truth_failures_in_result_fields_are_observed_without_coercion(self):
        for key, stage in (("ids", "RESULT_IDS"), ("documents", "RESULT_DOCUMENTS"),
                            ("metadatas", "RESULT_METADATAS"), ("distances", "RESULT_DISTANCES")):
            for location in ("outer", "element"):
                with self.subTest(key=key, location=location):
                    result = valid_result()
                    result[key] = AmbiguousTruth() if location == "outer" else [[AmbiguousTruth()]]
                    if key == "ids" and location == "element":
                        result[key] = [AmbiguousTruth()]
                    self.collection.query.return_value = result
                    self.logger.reset_mock()
                    self.assertEqual(self.query(), [])
                    self.assert_warning(stage, error_type="ValueError", signal="AMBIGUOUS_TRUTH_VALUE")

    def test_ambiguous_result_object_truth_stays_inside_original_catch(self):
        self.collection.query.return_value = AmbiguousTruth()
        self.assertEqual(self.query(), [])
        self.assert_warning("RESULT_IDS", error_type="ValueError", signal="AMBIGUOUS_TRUTH_VALUE")

    def test_partial_rows_are_discarded_when_later_document_parsing_fails(self):
        result = valid_result()
        result["documents"][0][1] = AmbiguousTruth()
        self.collection.query.return_value = result
        self.assertEqual(self.query(), [])
        self.assert_warning("RESULT_DOCUMENTS", error_type="ValueError", signal="AMBIGUOUS_TRUTH_VALUE")

    def test_id_iterator_failure_after_one_row_reports_ids_and_discards_partial_rows(self):
        class FailingIds:
            def __iter__(self):
                yield "id-1"
                raise ValueError(UNSAFE)
        result = valid_result()
        result["ids"] = [FailingIds()]
        self.collection.query.return_value = result
        self.assertEqual(self.query(), [])
        self.assert_warning("RESULT_IDS", error_type="ValueError")

    def test_normal_empty_result_shapes_do_not_log(self):
        for result in (None, {}, {"ids": []}, {"ids": [[]]}):
            with self.subTest(result=result):
                self.collection.query.return_value = result
                self.assertEqual(self.query(), [])
        self.assertEqual(self.logger.mock_calls, [])

    def test_missing_client_empty_embedding_and_absent_collection_do_not_log(self):
        self.get_client.return_value = None
        self.assertEqual(self.query(), [])
        self.get_client.return_value = self.client
        self.assertEqual(self.query([]), [])
        self.client.list_collections.return_value = []
        self.assertEqual(self.query(), [])
        self.client.get_collection.assert_not_called()
        self.collection.count.assert_not_called()
        self.collection.query.assert_not_called()
        self.assertEqual(self.logger.mock_calls, [])

    def test_existing_collection_discovery_failure_remains_silent(self):
        self.client.list_collections.side_effect = ValueError(UNSAFE)
        self.assertEqual(self.query(), [])
        self.client.get_collection.assert_not_called()
        self.assertEqual(self.logger.mock_calls, [])

    def test_zero_count_does_not_query_or_log(self):
        self.collection.count.return_value = 0
        self.assertEqual(self.query(), [])
        self.collection.count.assert_called_once_with()
        self.collection.query.assert_not_called()
        self.assertEqual(self.logger.mock_calls, [])

    def test_zero_missing_and_null_distances_retain_original_defaults(self):
        for distances in (None, [], [[0, 0.0]], [[None, None]]):
            with self.subTest(distances=distances):
                result = valid_result()
                result["distances"] = distances
                self.collection.query.return_value = result
                self.assertEqual([row["distance"] for row in self.query()], [0.0, 0.0])
        result = valid_result()
        del result["distances"]
        self.collection.query.return_value = result
        self.assertEqual([row["distance"] for row in self.query()], [0.0, 0.0])
        self.assertEqual(self.logger.mock_calls, [])

    def test_empty_or_null_documents_and_metadata_retain_original_defaults(self):
        for documents, metadatas in ((None, None), ([], []), ([[None, ""]], [[None, {}]])):
            with self.subTest(documents=documents, metadatas=metadatas):
                result = valid_result()
                result.update(documents=documents, metadatas=metadatas)
                self.collection.query.return_value = result
                rows = self.query()
                self.assertEqual([row["document"] for row in rows], ["", ""])
                self.assertEqual([row["metadata"] for row in rows], [{}, {}])
        self.assertEqual(self.logger.mock_calls, [])

    def test_client_initialization_and_embedding_preparation_errors_still_propagate(self):
        error = ValueError(UNSAFE)
        self.get_client.side_effect = error
        with self.assertRaises(ValueError) as raised:
            self.query()
        self.assertIs(raised.exception, error)
        self.get_client.side_effect = None
        with self.assertRaisesRegex(ValueError, "truth value"):
            self.query(AmbiguousTruth())
        class BadConversion:
            def tolist(self):
                raise error
        with self.assertRaises(ValueError) as raised:
            self.query(BadConversion())
        self.assertIs(raised.exception, error)
        self.client.get_collection.assert_not_called()
        self.collection.query.assert_not_called()
        self.assertEqual(self.logger.mock_calls, [])

    def test_keyboard_interrupt_is_not_newly_swallowed_by_diagnostics(self):
        self.collection.query.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.query()
        self.assertEqual(self.logger.mock_calls, [])

    def test_dynamic_collection_error_class_and_message_are_never_logged_raw(self):
        error_type = type(UNSAFE, (Exception,), {})
        self.client.list_collections.return_value = [SimpleNamespace(name=UNSAFE)]
        self.collection.query.side_effect = error_type(UNSAFE)
        self.assertEqual(self.query(collection=UNSAFE), [])
        self.assert_warning("QUERY_CALL", error_type="OTHER", collection="OTHER")

    def test_broken_exception_string_cannot_escape_retrieval_fallback(self):
        self.collection.query.side_effect = BrokenStringError()
        self.assertEqual(self.query(), [])
        self.assert_warning("QUERY_CALL", error_type="OTHER", signal="UNKNOWN")

    def test_actual_plain_and_structured_formatters_keep_safe_diagnostic(self):
        self.logger_patch.stop()
        # Standalone Logger avoids global handler/configuration mutations.
        logger = logging.Logger("query_diagnostic_fixture", logging.WARNING)
        logger.propagate = False
        plain, structured = io.StringIO(), io.StringIO()
        plain_handler = logging.StreamHandler(plain)
        plain_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        json_handler = logging.StreamHandler(structured)
        json_handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(plain_handler)
        logger.addHandler(json_handler)
        self.addCleanup(plain_handler.close)
        self.addCleanup(json_handler.close)
        self.collection.query.side_effect = ValueError(
            "The truth value of an array with more than one element is ambiguous. " + UNSAFE)
        with patch.object(vectors, "logger", StructuredLoggerAdapter(logger)):
            self.assertEqual(self.query(), [])
        plain_value = plain.getvalue()
        json_value = structured.getvalue()
        self.assertEqual(len(plain_value.splitlines()), 1)
        self.assertEqual(len(json_value.splitlines()), 1)
        safe = json.loads(plain_value.split(PREFIX, 1)[1])
        structured_row = json.loads(json_value)
        self.assertEqual({field: structured_row[field] for field in FIELDS}, safe)
        self.assertEqual(structured_row["message"], plain_value.removeprefix("WARNING ").strip())
        self.assertEqual(safe["stage"], "QUERY_CALL")
        self.assertEqual(safe["message_signal"], "AMBIGUOUS_TRUTH_VALUE")
        self.assertNotIn("exception", structured_row)
        for raw in (PRIVATE, "Authorization", "synthetic-token", "private.invalid", "Traceback"):
            self.assertNotIn(raw, plain_value + json_value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
