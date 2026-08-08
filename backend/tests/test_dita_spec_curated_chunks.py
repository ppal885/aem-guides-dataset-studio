"""Tests for authoritative curated DITA specification evidence."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.services.dita_spec_curated_chunk_service import (
    curated_chunk_metadata,
    load_curated_dita_spec_chunks,
)


EXPECTED_CONSTRUCTS = {
    "@dir",
    "@domains",
    "sort-as",
    "DITA specialization",
    "Constraint behavior",
}


def test_curated_chunks_cover_known_dita_spec_gaps():
    records = load_curated_dita_spec_chunks()

    assert {record["construct"] for record in records} == EXPECTED_CONSTRUCTS
    assert len({record["id"] for record in records}) == len(records)
    assert all(record["source_url"].startswith("https://docs.oasis-open.org/dita/") for record in records)
    assert all("AEM Guides" not in record["content"] for record in records)


def test_curated_chunks_include_required_behavior_boundaries():
    by_construct = {record["construct"]: record["content"] for record in load_curated_dita_spec_chunks()}

    assert all(value in by_construct["@dir"] for value in ("ltr", "rtl", "lro", "rlo", "neutral characters"))
    assert "authors do not normally write" in by_construct["@domains"]
    assert "does not require a processor to sort" in by_construct["sort-as"]
    assert "inherits the semantics and default processing behavior" in by_construct["DITA specialization"]
    assert "cannot make required elements optional" in by_construct["Constraint behavior"]


def test_curated_metadata_is_chroma_compatible():
    for record in load_curated_dita_spec_chunks():
        metadata = curated_chunk_metadata(record)
        assert metadata["curated"] is True
        assert all(isinstance(value, (str, int, float, bool)) for value in metadata.values())


def test_full_pdf_reindex_preserves_curated_chunks(monkeypatch):
    from app.services import dita_pdf_index_service as service

    captured: dict = {}
    fake_httpx = SimpleNamespace(Client=object)
    fake_loaders = SimpleNamespace(PyPDFLoader=object)

    class FakeSplitter:
        def __init__(self, **_kwargs):
            pass

    class FakeVector(list):
        def tolist(self):
            return list(self)

    fake_splitters = SimpleNamespace(RecursiveCharacterTextSplitter=FakeSplitter)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setitem(sys.modules, "langchain_community.document_loaders", fake_loaders)
    monkeypatch.setitem(sys.modules, "langchain_text_splitters", fake_splitters)
    monkeypatch.setattr(service, "is_embedding_available", lambda: True)
    monkeypatch.setattr(service, "is_chroma_available", lambda: True)
    monkeypatch.setattr(service, "embed_texts", lambda texts: [FakeVector([0.1, 0.2]) for _ in texts])
    monkeypatch.setattr(service, "delete_collection", lambda collection: captured.setdefault("deleted", collection))

    def capture_add(collection, ids, documents, metadatas, embeddings):
        captured.update({
            "collection": collection,
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "embeddings": embeddings,
        })
        return True

    monkeypatch.setattr(service, "chroma_add_documents", capture_add)

    stats = service.index_dita_pdf(pdf_urls=["not-a-url"])

    assert stats["curated_chunks_stored"] == 5
    assert stats["chunks_stored"] == 5
    assert captured["deleted"] == "dita_spec"
    assert set(captured["ids"]) == {record["id"] for record in load_curated_dita_spec_chunks()}
    assert all(metadata["curated"] is True for metadata in captured["metadatas"])
