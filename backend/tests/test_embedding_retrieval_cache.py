"""Real retrieval/cache callsites with fake encoders and vector-store calls.

No backend app startup, model loading, Chroma access, network or storage writes.
Run directly with the backend interpreter; does not load pytest conftest.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


_backend = str(Path(__file__).resolve().parents[1])
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.services import embedding_service as embeddings
from app.services import jira_qa_copilot_cache as cache
from app.services import jira_qa_retrieval_service as semantic
from app.services import jira_retrieval_service as hybrid


QUERY = "fixture content retrieval query"


class RetrievalEmbeddingCacheTests(unittest.TestCase):
    def start_patch(self, item):
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def setUp(self):
        self.start_patch(patch.multiple(
            embeddings, _USE_AZURE_EMBEDDING=False,
            DITA_EMBEDDING_MODEL="fixture-model", DITA_EMBEDDING_MODEL_PATH="",
        ))
        for module in (hybrid, semantic):
            self.start_patch(patch.object(module, "is_embedding_available", return_value=True))
            self.start_patch(patch.object(module, "is_chroma_available", return_value=True))
        self.query_collection = self.start_patch(patch.object(hybrid, "query_collection", return_value=[]))
        self.hybrid_encode = self.start_patch(patch.object(hybrid, "embed_query", side_effect=self.fake_encode))
        self.semantic_encode = self.start_patch(patch.object(semantic, "embed_query", side_effect=self.fake_encode))
        self.start_patch(patch.object(hybrid, "logger"))
        embeddings.reset_embedding_runtime_state()
        cache.clear_copilot_caches_for_tests()
        self.addCleanup(embeddings.reset_embedding_runtime_state)
        self.addCleanup(cache.clear_copilot_caches_for_tests)

    @staticmethod
    def fake_encode(_text):
        return [0.3, 0.4, 0.5] if embeddings._USE_AZURE_EMBEDDING else [0.1, 0.2]

    @staticmethod
    def retrieve_hybrid():
        return hybrid.retrieve_similar_jiras(
            QUERY, domain=None, dita_entities=[], affected_outputs=[], customer_names=[],
        )

    def assert_queried_vector(self, expected):
        self.assertTrue(self.query_collection.called)
        for query in self.query_collection.call_args_list:
            self.assertEqual(query.args[1], expected)

    def test_resolve_reuses_cached_embedding_only_in_same_namespace(self):
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.1, 0.2])
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.1, 0.2])
        self.hybrid_encode.assert_called_once_with(QUERY)
        self.semantic_encode.assert_not_called()
        self.query_collection.assert_not_called()

    def test_resolve_provider_change_reencodes_same_query(self):
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.1, 0.2])
        embeddings._USE_AZURE_EMBEDDING = True
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.3, 0.4, 0.5])
        self.assertEqual(self.hybrid_encode.call_count, 2)
        self.assertEqual(cache.cache_get_embedding_vector(QUERY), [0.3, 0.4, 0.5])

    def test_resolve_reset_reencodes_same_query(self):
        hybrid._resolve_embedding(QUERY, None)
        embeddings.reset_embedding_runtime_state()
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.1, 0.2])
        self.assertEqual(self.hybrid_encode.call_count, 2)

    def test_resolve_mid_encode_reset_or_configuration_change_discards_result(self):
        for change in ("reset", "provider", "model"):
            with self.subTest(change=change):
                embeddings._USE_AZURE_EMBEDDING = False
                embeddings.reset_embedding_runtime_state()
                cache.clear_copilot_caches_for_tests()
                def encode(_text):
                    if change == "reset":
                        embeddings.reset_embedding_runtime_state()
                    elif change == "provider":
                        embeddings._USE_AZURE_EMBEDDING = not embeddings._USE_AZURE_EMBEDDING
                    else:
                        embeddings.DITA_EMBEDDING_MODEL += "-changed"
                    return [0.1, 0.2]
                self.hybrid_encode.side_effect = encode
                self.assertIsNone(hybrid._resolve_embedding(QUERY, None))
                self.assertIsNone(cache.cache_get_embedding_vector(QUERY))
                self.query_collection.assert_not_called()

    def test_hybrid_retrieval_does_not_query_after_namespace_changes_during_encode(self):
        for change in ("reset", "provider"):
            with self.subTest(change=change):
                embeddings.reset_embedding_runtime_state()
                cache.clear_copilot_caches_for_tests()
                def encode(_text):
                    if change == "reset":
                        embeddings.reset_embedding_runtime_state()
                    else:
                        embeddings._USE_AZURE_EMBEDDING = not embeddings._USE_AZURE_EMBEDDING
                    return [0.1, 0.2]
                self.hybrid_encode.side_effect = encode
                self.assertEqual(self.retrieve_hybrid(), [])
                self.query_collection.assert_not_called()

    def test_semantic_retrieval_does_not_query_after_namespace_changes_during_encode(self):
        for change in ("reset", "provider", "model"):
            with self.subTest(change=change):
                embeddings._USE_AZURE_EMBEDDING = False
                embeddings.reset_embedding_runtime_state()
                cache.clear_copilot_caches_for_tests()
                def encode(_text):
                    if change == "reset":
                        embeddings.reset_embedding_runtime_state()
                    elif change == "provider":
                        embeddings._USE_AZURE_EMBEDDING = not embeddings._USE_AZURE_EMBEDDING
                    else:
                        embeddings.DITA_EMBEDDING_MODEL += "-changed"
                    return [0.1, 0.2]
                self.semantic_encode.side_effect = encode
                self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
                self.assertIsNone(cache.cache_get_embedding_vector(QUERY))
                self.query_collection.assert_not_called()
                self.hybrid_encode.assert_not_called()

    def test_semantic_retrieval_reuses_same_namespace_and_reencodes_new_provider(self):
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.assert_queried_vector([0.1, 0.2])
        self.query_collection.reset_mock()
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.semantic_encode.assert_called_once_with(QUERY)
        self.assert_queried_vector([0.1, 0.2])

        self.query_collection.reset_mock()
        embeddings._USE_AZURE_EMBEDDING = True
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.assertEqual(self.semantic_encode.call_count, 2)
        self.assert_queried_vector([0.3, 0.4, 0.5])
        self.hybrid_encode.assert_not_called()

    def test_semantic_and_hybrid_share_only_same_namespace_cached_vectors(self):
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.1, 0.2])
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.semantic_encode.assert_not_called()
        self.assert_queried_vector([0.1, 0.2])
        self.query_collection.reset_mock()

        embeddings._USE_AZURE_EMBEDDING = True
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.semantic_encode.assert_called_once_with(QUERY)
        self.assert_queried_vector([0.3, 0.4, 0.5])
        self.assertEqual(hybrid._resolve_embedding(QUERY, None), [0.3, 0.4, 0.5])
        self.hybrid_encode.assert_called_once_with(QUERY)

    def test_failed_encode_never_populates_cache_or_queries_chroma(self):
        self.hybrid_encode.side_effect = None
        self.hybrid_encode.return_value = None
        self.semantic_encode.side_effect = None
        self.semantic_encode.return_value = None
        self.assertIsNone(hybrid._resolve_embedding(QUERY, None))
        self.assertEqual(self.retrieve_hybrid(), [])
        self.assertEqual(semantic.semantic_search_jira_qa(QUERY), [])
        self.assertIsNone(cache.cache_get_embedding_vector(QUERY))
        self.query_collection.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
