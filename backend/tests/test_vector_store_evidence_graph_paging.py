import pytest

from app.services import vector_store_service as vector_store


class FakeCollection:
    def __init__(self, records, *, count_values=None, failures=None, empty_offsets=None):
        self.records = list(records)
        self.count_values = list(count_values or [len(self.records), len(self.records)])
        self.failures = dict(failures or {})
        self.empty_offsets = set(empty_offsets or set())
        self.calls = []

    def count(self):
        if len(self.count_values) > 1:
            return self.count_values.pop(0)
        return self.count_values[0]

    def get(self, *, limit, offset, include):
        self.calls.append((limit, offset, tuple(include)))
        remaining_failures = self.failures.get(offset, 0)
        if remaining_failures:
            self.failures[offset] = remaining_failures - 1
            raise RuntimeError("transient Chroma failure")
        if offset in self.empty_offsets:
            return {"ids": [], "metadatas": [], "documents": []}
        page = self.records[offset : offset + limit]
        return {
            "ids": [item[0] for item in page],
            "metadatas": [item[1] for item in page],
            "documents": [item[2] for item in page],
        }


class FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, name):
        assert name == "aem_guides"
        return self.collection


def _install(monkeypatch, collection):
    monkeypatch.setattr(vector_store, "_get_client", lambda: FakeClient(collection))
    monkeypatch.setattr(vector_store, "_collection_exists", lambda client, name: True)


def test_paginated_scan_handles_empty_collection_without_get(monkeypatch):
    collection = FakeCollection([], count_values=[0, 0])
    _install(monkeypatch, collection)
    assert list(vector_store.iter_collection_records("aem_guides", batch_size=500)) == []
    assert collection.calls == []


def test_paginated_scan_uses_limit_offset_and_preserves_documents(monkeypatch):
    collection = FakeCollection(
        [(f"id-{index}", {"n": index}, f"doc-{index}") for index in range(5)]
    )
    _install(monkeypatch, collection)

    rows = list(
        vector_store.iter_collection_records(
            "aem_guides",
            include_documents=True,
            batch_size=2,
        )
    )

    assert [row["id"] for row in rows] == [f"id-{index}" for index in range(5)]
    assert rows[-1]["document"] == "doc-4"
    assert [call[:2] for call in collection.calls] == [(2, 0), (2, 2), (1, 4)]


def test_paginated_scan_retries_failed_page(monkeypatch):
    collection = FakeCollection(
        [("id-1", {}, "doc")],
        failures={0: 2},
    )
    _install(monkeypatch, collection)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    rows = list(vector_store.iter_collection_records("aem_guides", max_retries=3))

    assert [row["id"] for row in rows] == ["id-1"]
    assert len(collection.calls) == 3


def test_paginated_scan_rejects_empty_page_and_42k_failure_shape(monkeypatch):
    collection = FakeCollection([], count_values=[42198, 42198], empty_offsets={0})
    _install(monkeypatch, collection)

    with pytest.raises(RuntimeError, match=r"empty page.*offset 0.*42198"):
        list(vector_store.iter_collection_records("aem_guides", batch_size=500))


def test_paginated_scan_rejects_count_change(monkeypatch):
    collection = FakeCollection(
        [("id-1", {}, "doc-1"), ("id-2", {}, "doc-2")],
        count_values=[2, 3],
    )
    _install(monkeypatch, collection)

    with pytest.raises(RuntimeError, match=r"scanned=2, initial_count=2, final_count=3"):
        list(vector_store.iter_collection_records("aem_guides", batch_size=1))


def test_paginated_scan_raises_after_retry_exhaustion(monkeypatch):
    collection = FakeCollection(
        [("id-1", {}, "doc")],
        failures={0: 5},
    )
    _install(monkeypatch, collection)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match=r"page scan failed.*offset 0"):
        list(vector_store.iter_collection_records("aem_guides", max_retries=3))
