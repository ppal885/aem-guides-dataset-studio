"""Tests for complete Chroma record scans used by corpus audits."""

from __future__ import annotations

from app.services import vector_store_service


def test_collection_records_optionally_includes_documents_and_handles_sparse_results(monkeypatch):
    class FakeCollection:
        def get(self, *, include):
            assert include == ["metadatas", "documents"]
            return {
                "ids": ["DXML-1::summary::0", "DXML-2::summary::0"],
                "metadatas": [{"jira_key": "DXML-1"}],
                "documents": ["first document"],
            }

    class FakeClient:
        def get_collection(self, *, name):
            assert name == "jira_qa"
            return FakeCollection()

    monkeypatch.setattr(vector_store_service, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(vector_store_service, "_collection_exists", lambda client, name: True)

    records = vector_store_service.get_collection_records("jira_qa", include_documents=True)

    assert records == [
        {
            "id": "DXML-1::summary::0",
            "metadata": {"jira_key": "DXML-1"},
            "document": "first document",
        },
        {"id": "DXML-2::summary::0", "metadata": {}, "document": ""},
    ]


def test_collection_records_default_remains_metadata_only(monkeypatch):
    class FakeCollection:
        def get(self, *, include):
            assert include == ["metadatas"]
            return {"ids": ["DXML-1::summary::0"], "metadatas": [{"jira_key": "DXML-1"}]}

    class FakeClient:
        def get_collection(self, *, name):
            return FakeCollection()

    monkeypatch.setattr(vector_store_service, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(vector_store_service, "_collection_exists", lambda client, name: True)

    assert vector_store_service.get_collection_records("jira_qa") == [
        {"id": "DXML-1::summary::0", "metadata": {"jira_key": "DXML-1"}}
    ]
