"""Embedding provider safety tests; fake models/HTTP, no network or Chroma.

Uses unittest plus the backend's existing NumPy dependency. The tests never
instantiate a real model or import sentence-transformers/torch.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np


_backend = str(Path(__file__).resolve().parents[1])
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.services import embedding_service as embeddings


class ContextTestCase(unittest.TestCase):
    """Context cleanup compatible with both Python 3.10 and 3.11."""

    def enterContext(self, context):
        value = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return value


class EmbeddingProviderPinningTests(ContextTestCase):
    def setUp(self):
        self.enterContext(patch.multiple(
            embeddings,
            _USE_AZURE_EMBEDDING=False,
            _AZURE_EMBED_ENDPOINT="https://embedding.invalid",
            _AZURE_EMBED_KEY="nonfunctional-unit-test-placeholder",
            _AZURE_EMBED_MODEL="test-deployment",
            _AZURE_EMBED_VERSION="test-version",
            DITA_EMBEDDING_MODEL="test-local-model",
            DITA_EMBEDDING_MODEL_PATH="",
        ))
        self.model = Mock(spec=["encode"])
        self.model.encode.side_effect = lambda texts, **kwargs: np.array(
            [[0.1, 0.2, 0.3] for _ in texts])
        self.constructor = Mock(return_value=self.model)
        self.enterContext(patch.dict(sys.modules, {
            "sentence_transformers": SimpleNamespace(SentenceTransformer=self.constructor),
        }))
        self.enterContext(patch.object(embeddings, "_resolve_embedding_source",
                                      return_value=("test-local-model", "model_name")))
        self.azure = self.enterContext(patch.object(
            embeddings, "_try_azure_embedding",
            side_effect=lambda texts: [[0.4, 0.5] for _ in texts],
        ))
        self.logger = self.enterContext(patch.object(embeddings, "logger"))
        embeddings.reset_embedding_runtime_state()
        self.addCleanup(embeddings.reset_embedding_runtime_state)

    def run_embedding(self, texts, *, batched=False, batch_size=2):
        if batched:
            return embeddings.embed_texts_batched(texts, batch_size=batch_size)
        return embeddings.embed_texts(texts)

    def test_local_success_preserves_vectors_and_never_calls_azure(self):
        for batched in (False, True):
            with self.subTest(batched=batched):
                result = self.run_embedding(["one", "two", "three"], batched=batched)
                np.testing.assert_array_equal(result, [[0.1, 0.2, 0.3]] * 3)
                self.azure.assert_not_called()

    def test_local_import_failure_does_not_fallback_even_with_azure_credentials(self):
        self.constructor.side_effect = ImportError("model fixture import failure")
        for batched in (False, True):
            with self.subTest(batched=batched):
                embeddings.reset_embedding_runtime_state()
                self.assertIsNone(self.run_embedding(["one"], batched=batched))
                self.azure.assert_not_called()
                self.assertFalse(embeddings.get_embedding_diagnostics()["available"])

    def test_local_encode_failure_does_not_fallback(self):
        self.model.encode.side_effect = RuntimeError("model fixture encode failure")
        for batched in (False, True):
            with self.subTest(batched=batched):
                embeddings.reset_embedding_runtime_state()
                self.assertIsNone(self.run_embedding(["one"], batched=batched))
                self.azure.assert_not_called()
                self.assertFalse(embeddings.get_embedding_diagnostics()["available"])

    def test_prerelease_python_is_rejected_before_model_import_or_provider_fallback(self):
        for releaselevel in ("alpha", "beta", "candidate"):
            with self.subTest(releaselevel=releaselevel), patch.object(
                embeddings, "sys", SimpleNamespace(version_info=SimpleNamespace(releaselevel=releaselevel))
            ):
                embeddings.reset_embedding_runtime_state()
                diagnostics = embeddings.get_embedding_diagnostics()
                self.assertFalse(diagnostics["available"])
                self.assertFalse(diagnostics["availability_verified"])
                self.assertEqual(diagnostics["error"], "PYTHON_PRERELEASE_UNSUPPORTED")
                self.assertEqual(diagnostics["provider"], "LOCAL")
                self.assertIsNone(embeddings.embed_query("one"))
                self.constructor.assert_not_called()
                self.azure.assert_not_called()

    def test_azure_selection_does_not_inspect_local_python_prerelease_guard(self):
        embeddings._USE_AZURE_EMBEDDING = True
        with patch.object(embeddings, "sys", SimpleNamespace(version_info=SimpleNamespace(releaselevel="candidate"))):
            np.testing.assert_array_equal(embeddings.embed_query("one"), [0.4, 0.5])
            self.assertEqual(embeddings.get_embedding_diagnostics()["provider"], "AZURE")
            self.constructor.assert_not_called()

    def test_direct_diagnostics_of_local_import_failure_do_not_claim_azure_availability(self):
        private = "PRIVATE_MODEL_EXCEPTION Authorization: not-a-real-credential"
        self.constructor.side_effect = ImportError(private)
        diagnostics = embeddings.get_embedding_diagnostics()
        self.assertFalse(diagnostics["available"])
        self.assertFalse(diagnostics["ready"])
        self.assertFalse(diagnostics["availability_verified"])
        self.assertEqual(diagnostics["provider"], "LOCAL")
        self.assertEqual(diagnostics["error"], "LOCAL_MODEL_LOAD_FAILED")
        self.assertFalse(embeddings.is_embedding_available())
        self.azure.assert_not_called()
        emitted = json.dumps([diagnostics, self.logger.mock_calls], default=str)
        self.assertNotIn(private, emitted)

    def test_invalid_batch_sizes_do_not_attempt_provider_calls(self):
        for azure in (False, True):
            for size in (0, -1, False, True, "2", 1.5, None):
                with self.subTest(azure=azure, batch_size=size):
                    embeddings._USE_AZURE_EMBEDDING = azure
                    self.assertIsNone(embeddings.embed_texts_batched(["one"], batch_size=size))
                    self.constructor.assert_not_called()
                    self.azure.assert_not_called()

    def test_explicit_azure_success_never_loads_local_model(self):
        embeddings._USE_AZURE_EMBEDDING = True
        for batched in (False, True):
            with self.subTest(batched=batched):
                result = self.run_embedding(["one", "two", "three"], batched=batched)
                np.testing.assert_array_equal(result, [[0.4, 0.5]] * 3)
                self.constructor.assert_not_called()
                self.model.encode.assert_not_called()

    def test_azure_failure_never_falls_back_to_local(self):
        embeddings._USE_AZURE_EMBEDDING = True
        self.azure.side_effect = None
        self.azure.return_value = None
        for batched in (False, True):
            with self.subTest(batched=batched):
                embeddings.reset_embedding_runtime_state()
                self.assertIsNone(self.run_embedding(["one"], batched=batched))
                self.constructor.assert_not_called()
                self.assertFalse(embeddings.get_embedding_diagnostics()["available"])

    def test_azure_missing_credentials_never_falls_back_to_local(self):
        embeddings._USE_AZURE_EMBEDDING = True
        for missing in ("_AZURE_EMBED_ENDPOINT", "_AZURE_EMBED_KEY"):
            with patch.object(embeddings, missing, ""):
                for batched in (False, True):
                    with self.subTest(missing=missing, batched=batched):
                        embeddings.reset_embedding_runtime_state()
                        self.assertIsNone(self.run_embedding(["one"], batched=batched))
                        self.constructor.assert_not_called()

    def test_azure_available_does_not_load_the_unselected_local_model(self):
        embeddings._USE_AZURE_EMBEDDING = True
        self.assertTrue(embeddings.is_embedding_available())
        diagnostics = embeddings.get_embedding_diagnostics()
        self.assertFalse(diagnostics["availability_verified"])
        self.constructor.assert_not_called()
        self.azure.assert_not_called()

    def test_successful_request_is_reported_as_verified_availability(self):
        for azure in (False, True):
            with self.subTest(azure=azure):
                embeddings.reset_embedding_runtime_state()
                embeddings._USE_AZURE_EMBEDDING = azure
                self.assertIsNotNone(embeddings.embed_texts(["one"]))
                diagnostics = embeddings.get_embedding_diagnostics()
                self.assertTrue(diagnostics["available"])
                self.assertTrue(diagnostics["availability_verified"])

    def test_ready_provider_after_encode_failure_is_not_reported_as_verified_success(self):
        for azure in (False, True):
            with self.subTest(azure=azure):
                embeddings.reset_embedding_runtime_state()
                embeddings._USE_AZURE_EMBEDDING = azure
                target = self.azure if azure else self.model.encode
                target.side_effect = None
                target.return_value = None
                self.assertIsNone(embeddings.embed_texts(["one"]))
                # Readiness allows recovery on the next request; it is not a
                # claim that the failed query produced a compatible embedding.
                self.assertTrue(embeddings.is_embedding_available())
                diagnostics = embeddings.get_embedding_diagnostics()
                self.assertFalse(diagnostics["available"])
                self.assertFalse(diagnostics["availability_verified"])
                self.assertEqual(diagnostics["last_request_status"], "FAILED")
                self.assertIsNone(diagnostics["last_vector_dimension"])

    def test_query_uses_the_pinned_provider_and_returns_one_vector(self):
        for azure in (False, True):
            with self.subTest(azure=azure):
                embeddings.reset_embedding_runtime_state()
                embeddings._USE_AZURE_EMBEDDING = azure
                expected = [0.4, 0.5] if azure else [0.1, 0.2, 0.3]
                np.testing.assert_array_equal(embeddings.embed_query("one"), expected)

    def test_empty_input_does_not_attempt_any_provider(self):
        for azure in (False, True):
            for batched in (False, True):
                with self.subTest(azure=azure, batched=batched):
                    embeddings._USE_AZURE_EMBEDDING = azure
                    self.assertIsNone(self.run_embedding([], batched=batched))
        for value in (None, "", "  "):
            self.assertIsNone(embeddings.embed_query(value))
        self.constructor.assert_not_called()
        self.azure.assert_not_called()

    def test_malformed_vectors_are_rejected_for_both_providers_and_entrypoints(self):
        malformed = {
            "empty": [],
            "too_few_rows": [[0.1, 0.2]],
            "too_many_rows": [[0.1, 0.2]] * 3,
            "flat": [0.1, 0.2],
            "ragged": [[0.1, 0.2], [0.1]],
            "empty_dimensions": [[], []],
            "text": [["not-numeric"], ["not-numeric"]],
            "numeric_text": [["0.1"], ["0.2"]],
            "boolean": [[True], [False]],
            "nan": [[float("nan")], [0.2]],
            "infinity": [[float("inf")], [0.2]],
            "negative_infinity": [[float("-inf")], [0.2]],
            "complex": [[1 + 2j], [2 + 3j]],
        }
        for azure in (False, True):
            for batched in (False, True):
                for label, vectors in malformed.items():
                    with self.subTest(azure=azure, batched=batched, shape=label):
                        embeddings.reset_embedding_runtime_state()
                        embeddings._USE_AZURE_EMBEDDING = azure
                        self.model.encode.side_effect = None
                        self.model.encode.return_value = deepcopy(vectors)
                        self.azure.side_effect = None
                        self.azure.return_value = deepcopy(vectors)
                        self.assertIsNone(self.run_embedding(["one", "two"], batched=batched))

    def test_batched_local_partial_failure_discards_earlier_vectors(self):
        self.model.encode.side_effect = [np.array([[0.1, 0.2]] * 2), RuntimeError("second batch")]
        self.assertIsNone(embeddings.embed_texts_batched(["one", "two", "three"], batch_size=2))
        self.assertEqual(self.model.encode.call_count, 2)
        self.azure.assert_not_called()

    def test_batched_local_dimension_change_discards_whole_batch(self):
        self.model.encode.side_effect = [np.array([[0.1, 0.2]] * 2), np.array([[0.1, 0.2, 0.3]])]
        self.assertIsNone(embeddings.embed_texts_batched(["one", "two", "three"], batch_size=2))
        self.azure.assert_not_called()

    def test_batched_azure_partial_failure_discards_earlier_vectors(self):
        embeddings._USE_AZURE_EMBEDDING = True
        self.azure.side_effect = [np.array([[0.1, 0.2]] * 16), None]
        self.assertIsNone(embeddings.embed_texts_batched(["one"] * 17))
        self.constructor.assert_not_called()

    def test_selected_provider_failure_can_recover_without_using_other_provider(self):
        for azure in (False, True):
            with self.subTest(azure=azure):
                embeddings.reset_embedding_runtime_state()
                embeddings._USE_AZURE_EMBEDDING = azure
                target = self.azure if azure else self.model.encode
                target.side_effect = [None, np.array([[0.1, 0.2]])]
                self.assertIsNone(embeddings.embed_texts(["one"]))
                np.testing.assert_array_equal(embeddings.embed_texts(["one"]), [[0.1, 0.2]])
                self.assertTrue(embeddings.get_embedding_diagnostics()["available"])

    def test_blank_batched_entries_keep_input_output_alignment(self):
        result = embeddings.embed_texts_batched(["one", None, ""], batch_size=3)
        self.assertEqual(result.shape, (3, 3))
        self.model.encode.assert_called_once_with(["one", " ", " "], convert_to_numpy=True)

    def test_reset_invalidates_cache_namespace(self):
        before = embeddings.embedding_cache_namespace()
        embeddings.reset_embedding_runtime_state()
        self.assertNotEqual(before, embeddings.embedding_cache_namespace())

    def test_cache_namespace_stable_across_successful_model_load(self):
        before = embeddings.embedding_cache_namespace()
        self.assertIsNotNone(embeddings.embed_texts(["one"]))
        self.assertEqual(before, embeddings.embedding_cache_namespace())

    def test_cache_namespace_changes_for_provider_and_model_configuration(self):
        initial = embeddings.embedding_cache_namespace()
        for name, changed in (
            ("_USE_AZURE_EMBEDDING", True),
            ("DITA_EMBEDDING_MODEL", "another-local-model"),
            ("DITA_EMBEDDING_MODEL_PATH", "/test/another-local-model"),
        ):
            with self.subTest(configuration=name), patch.object(embeddings, name, changed):
                self.assertNotEqual(initial, embeddings.embedding_cache_namespace())

    def test_azure_cache_namespace_tracks_deployment_but_does_not_expose_configuration(self):
        embeddings._USE_AZURE_EMBEDDING = True
        initial = embeddings.embedding_cache_namespace()
        for name, changed in (
            ("_AZURE_EMBED_MODEL", "another-deployment"),
            ("_AZURE_EMBED_ENDPOINT", "https://another.invalid"),
            ("_AZURE_EMBED_VERSION", "another-version"),
        ):
            with self.subTest(configuration=name), patch.object(embeddings, name, changed):
                value = embeddings.embedding_cache_namespace()
                self.assertNotEqual(initial, value)
                self.assertNotIn(changed, value)
                self.assertNotIn(embeddings._AZURE_EMBED_KEY, value)


class AzureResponseValidationTests(ContextTestCase):
    def setUp(self):
        self.enterContext(patch.multiple(
            embeddings,
            _USE_AZURE_EMBEDDING=True,
            _AZURE_EMBED_ENDPOINT="https://embedding.invalid",
            _AZURE_EMBED_KEY="nonfunctional-unit-test-placeholder",
            _AZURE_EMBED_MODEL="test-deployment",
            _AZURE_EMBED_VERSION="test-version",
        ))
        self.response = Mock(ok=True)
        self.response.json.return_value = {
            "data": [{"index": 1, "embedding": [0.3, 0.4]},
                     {"index": 0, "embedding": [0.1, 0.2]}],
        }
        self.post = Mock(return_value=self.response)
        self.enterContext(patch.dict(sys.modules, {"requests": SimpleNamespace(post=self.post)}))
        self.logger = self.enterContext(patch.object(embeddings, "logger"))
        embeddings.reset_embedding_runtime_state()
        self.addCleanup(embeddings.reset_embedding_runtime_state)

    def test_actual_adapter_preserves_request_order_using_response_indices(self):
        result = embeddings._try_azure_embedding(["one", "two"])
        self.assertEqual(result, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(self.post.call_args.kwargs["timeout"], 30)
        self.assertEqual(self.post.call_args.kwargs["json"], {"input": ["one", "two"]})
        self.assertFalse(self.post.call_args.kwargs["allow_redirects"])

    def test_direct_azure_adapter_does_not_call_http_when_local_selected(self):
        embeddings._USE_AZURE_EMBEDDING = False
        self.assertIsNone(embeddings._try_azure_embedding(["one"]))
        self.post.assert_not_called()

    def test_partial_duplicate_and_invalid_response_indices_are_rejected(self):
        for data in (
            [{"index": 0, "embedding": [0.1]}],
            [{"index": 0, "embedding": [0.1]}, {"index": 0, "embedding": [0.2]}],
            [{"index": 0, "embedding": [0.1]}, {"index": 2, "embedding": [0.2]}],
            [{"index": -1, "embedding": [0.1]}, {"index": 0, "embedding": [0.2]}],
            [{"index": False, "embedding": [0.1]}, {"index": True, "embedding": [0.2]}],
            [{"index": "0", "embedding": [0.1]}, {"index": "1", "embedding": [0.2]}],
        ):
            with self.subTest(data=data):
                self.response.json.return_value = {"data": data}
                self.assertIsNone(embeddings._try_azure_embedding(["one", "two"]))

    def test_http_failure_and_malformed_json_do_not_raise(self):
        self.response.ok = False
        self.assertIsNone(embeddings._try_azure_embedding(["one"]))
        self.response.ok = True
        self.response.json.side_effect = ValueError("invalid fixture JSON")
        self.assertIsNone(embeddings._try_azure_embedding(["one"]))

    def test_adapter_partial_http_batch_failure_discards_all_vectors(self):
        first = Mock(ok=True)
        first.json.return_value = {"data": [{"index": i, "embedding": [0.1, 0.2]} for i in range(16)]}
        second = Mock(ok=False)
        self.post.side_effect = [first, second]
        self.assertIsNone(embeddings._try_azure_embedding(["one"] * 17))
        self.assertEqual(self.post.call_count, 2)

    def test_error_logging_does_not_expose_remote_payload_or_credentials(self):
        private = "PRIVATE_TEST_RESPONSE Authorization: Bearer not-a-real-token"
        self.post.side_effect = RuntimeError(private)
        self.assertIsNone(embeddings._try_azure_embedding(["one"]))
        emitted = json.dumps(self.logger.mock_calls, default=str)
        self.assertNotIn(private, emitted)
        self.assertNotIn(embeddings._AZURE_EMBED_KEY, emitted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
