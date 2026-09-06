"""Provider/reset cache separation; no models, network or Chroma clients."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import embedding_service as embedding
from app.services import jira_qa_copilot_cache as cache


class CacheNamespaceTests(unittest.TestCase):
    def setUp(self):
        cache.clear_copilot_caches_for_tests()
        embedding.reset_embedding_runtime_state()
        self.addCleanup(cache.clear_copilot_caches_for_tests)
        self.addCleanup(embedding.reset_embedding_runtime_state)

    def test_same_provider_and_text_hits(self):
        cache.cache_set_embedding_vector("query", [0.1, 0.2])
        self.assertEqual(cache.cache_get_embedding_vector("query"), [0.1, 0.2])

    def test_provider_change_cannot_return_local_vector(self):
        with patch.object(embedding, "_USE_AZURE_EMBEDDING", False):
            cache.cache_set_embedding_vector("query", [0.1, 0.2])
        with patch.object(embedding, "_USE_AZURE_EMBEDDING", True):
            self.assertIsNone(cache.cache_get_embedding_vector("query"))

    def test_model_reset_invalidates_even_same_text(self):
        cache.cache_set_embedding_vector("query", [0.1, 0.2])
        embedding.reset_embedding_runtime_state()
        self.assertIsNone(cache.cache_get_embedding_vector("query"))

    def test_model_config_change_invalidates_even_same_dimension(self):
        cache.cache_set_embedding_vector("query", [0.1, 0.2])
        with patch.object(embedding, "DITA_EMBEDDING_MODEL_PATH", "different-model"):
            self.assertIsNone(cache.cache_get_embedding_vector("query"))

    def test_old_inflight_encode_cannot_write_into_new_namespace(self):
        old = embedding.embedding_cache_namespace()
        embedding.reset_embedding_runtime_state()
        cache.cache_set_embedding_vector("query", [0.1, 0.2], namespace=old)
        self.assertIsNone(cache.cache_get_embedding_vector("query"))
        self.assertEqual(cache._EMBEDDING_CACHE, {})

    def test_explicit_stale_namespace_cannot_read_old_vector(self):
        old = embedding.embedding_cache_namespace()
        cache.cache_set_embedding_vector("query", [0.1, 0.2], namespace=old)
        embedding.reset_embedding_runtime_state()
        self.assertIsNone(cache.cache_get_embedding_vector("query", namespace=old))

    def test_cached_vectors_are_not_mutated_by_caller(self):
        original = [0.1, 0.2]
        cache.cache_set_embedding_vector("query", original)
        original[0] = 9
        result = cache.cache_get_embedding_vector("query")
        result[0] = 8
        self.assertEqual(cache.cache_get_embedding_vector("query"), [0.1, 0.2])

    def test_ttl_expiry_is_unchanged(self):
        with patch.object(cache.time, "monotonic", return_value=10):
            cache.cache_set_embedding_vector("query", [0.1, 0.2])
        with patch.object(cache.time, "monotonic", return_value=10 + cache._TTL_EMB):
            self.assertIsNone(cache.cache_get_embedding_vector("query"))

    def test_context_cache_is_unchanged_by_embedding_reset(self):
        cache.cache_set_context("case", "signature", "context")
        embedding.reset_embedding_runtime_state()
        self.assertEqual(cache.cache_get_context("case", "signature"), "context")


if __name__ == "__main__":
    unittest.main(verbosity=2)
