"""Tests for tool_result_cache — LRU caching for tool results."""
import time
import pytest
from unittest.mock import patch
from app.services.tool_result_cache import ToolResultCache


class TestToolResultCache:
    def test_miss_returns_none(self):
        cache = ToolResultCache(ttl=60)
        assert cache.get("lookup_aem_guides", {"query": "test"}) is None

    def test_put_and_get(self):
        cache = ToolResultCache(ttl=60)
        result = {"results": [{"title": "Test"}]}
        cache.put("lookup_aem_guides", {"query": "test"}, result)
        assert cache.get("lookup_aem_guides", {"query": "test"}) == result

    def test_different_params_miss(self):
        cache = ToolResultCache(ttl=60)
        cache.put("lookup_aem_guides", {"query": "test"}, {"data": 1})
        assert cache.get("lookup_aem_guides", {"query": "other"}) is None

    def test_mutation_tools_never_cached(self):
        cache = ToolResultCache(ttl=60)
        cache.put("generate_dita", {"text": "hello"}, {"output": "xml"})
        assert cache.get("generate_dita", {"text": "hello"}) is None

    def test_create_job_never_cached(self):
        cache = ToolResultCache(ttl=60)
        cache.put("create_job", {"recipe": "task"}, {"job_id": "123"})
        assert cache.get("create_job", {"recipe": "task"}) is None

    def test_ttl_expiration(self):
        cache = ToolResultCache(ttl=1)
        cache.put("lookup_aem_guides", {"query": "test"}, {"data": 1})
        assert cache.get("lookup_aem_guides", {"query": "test"}) == {"data": 1}
        # Manually expire by patching the stored expire time
        key = list(cache._store.keys())[0]
        cache._store[key] = (cache._store[key][0], time.monotonic() - 1)
        assert cache.get("lookup_aem_guides", {"query": "test"}) is None

    def test_max_entries_eviction(self):
        cache = ToolResultCache(ttl=60, max_entries=3)
        for i in range(4):
            cache.put("tool", {"i": i}, {"result": i})
        assert cache.size == 3

    def test_clear(self):
        cache = ToolResultCache(ttl=60)
        cache.put("tool_a", {"q": "1"}, {"r": 1})
        cache.put("tool_b", {"q": "2"}, {"r": 2})
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_same_tool_different_params(self):
        cache = ToolResultCache(ttl=60)
        cache.put("lookup_aem_guides", {"query": "a", "k": 5}, {"r": 1})
        cache.put("lookup_aem_guides", {"query": "b", "k": 5}, {"r": 2})
        assert cache.get("lookup_aem_guides", {"query": "a", "k": 5}) == {"r": 1}
        assert cache.get("lookup_aem_guides", {"query": "b", "k": 5}) == {"r": 2}

    def test_param_order_independent(self):
        cache = ToolResultCache(ttl=60)
        cache.put("tool", {"a": 1, "b": 2}, {"r": 1})
        # Same params in different order should hit
        assert cache.get("tool", {"b": 2, "a": 1}) == {"r": 1}

    def test_fix_dita_xml_not_cached(self):
        cache = ToolResultCache(ttl=60)
        cache.put("fix_dita_xml", {"xml": "<topic/>"}, {"fixed": True})
        assert cache.get("fix_dita_xml", {"xml": "<topic/>"}) is None

    def test_hit_rate_info(self):
        cache = ToolResultCache(ttl=60)
        cache.put("tool", {"q": "1"}, {"r": 1})
        assert "cache_size=1" in cache.hit_rate_info
