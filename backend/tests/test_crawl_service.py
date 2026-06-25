from __future__ import annotations

import json

from langchain_core.documents import Document

from app.services import crawl_service


class _FakeWebBaseLoader:
    def __init__(self, urls, **_kwargs):
        self.urls = urls

    def load(self):
        return [
            Document(
                page_content=(
                    "Authoring file management explains how writers manage files, folders, "
                    "and related AEM Guides content from the authoring workspace."
                ),
                metadata={"source": url, "title": "Authoring file management"},
            )
            for url in self.urls
        ]


def test_explicit_url_crawl_merges_json_chunks_without_replacing_existing(monkeypatch, tmp_path):
    chunks_path = tmp_path / "aem_guides_doc_chunks.json"
    old_url = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/overview"
    new_url = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/manage-content/authoring-file-management"
    chunks_path.write_text(
        json.dumps(
            [
                {
                    "url": old_url,
                    "title": "Existing overview",
                    "content": "Existing AEM Guides overview chunk.",
                    "chunk_index": 0,
                },
                {
                    "url": new_url,
                    "title": "Stale file management",
                    "content": "Old stale chunk for the same URL.",
                    "chunk_index": 0,
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(crawl_service, "_get_doc_chunks_path", lambda: chunks_path)
    monkeypatch.setattr(crawl_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(crawl_service, "is_embedding_available", lambda: False)

    import langchain_community.document_loaders

    monkeypatch.setattr(langchain_community.document_loaders, "WebBaseLoader", _FakeWebBaseLoader)

    stats = crawl_service.crawl_and_index(urls=[new_url], chunk_size=500, chunk_overlap=0)

    assert stats["pages_crawled"] == 1
    assert stats["chunks_stored"] == 1
    merged = json.loads(chunks_path.read_text(encoding="utf-8"))
    assert any(item["url"] == old_url for item in merged)
    new_chunks = [item for item in merged if item["url"] == new_url]
    assert len(new_chunks) == 1
    assert new_chunks[0]["title"] == "Authoring file management"
    assert "Old stale chunk" not in new_chunks[0]["content"]
