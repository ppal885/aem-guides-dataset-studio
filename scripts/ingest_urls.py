"""Surgically append one or more doc URLs to the AEM Guides RAG corpus (aem_guides
Chroma collection) WITHOUT wiping it.

Use this instead of crawl_service.crawl_and_index for adding a page: crawl_and_index
does a FULL delete+replace of the collection, so calling it with a single URL would
destroy the whole 1.5GB corpus. This helper fetches each URL, chunks, embeds, and
upserts with unique ids - non-destructive.

Run from the backend env (needs the local Chroma corpus + embeddings):
  cd backend && python ../scripts/ingest_urls.py <url1> [<url2> ...]

It also adds each URL to config/aem_guides_crawl_urls.json so future full crawls keep it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _add_to_crawl_config(backend: Path, urls: list[str]) -> None:
    cfg = backend / "config" / "aem_guides_crawl_urls.json"
    try:
        d = json.loads(cfg.read_text(encoding="utf-8"))
        existing = d.get("urls") or []
        added = 0
        for u in urls:
            if u not in existing:
                existing.append(u)
                added += 1
        d["urls"] = existing
        cfg.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"crawl config: +{added} url(s), now {len(existing)} total")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not update crawl config: {exc}", file=sys.stderr)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    from dotenv import load_dotenv
    load_dotenv(str(backend / ".env"))
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from app.services.embedding_service import embed_texts, is_embedding_available
    from app.services.vector_store_service import (
        add_documents, is_chroma_available, CHROMA_COLLECTION_AEM_GUIDES,
    )

    if not is_chroma_available() or not is_embedding_available():
        print("Chroma or embeddings unavailable.", file=sys.stderr)
        return 2

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    total = 0
    for url in argv:
        try:
            docs = WebBaseLoader(url).load()
            text = "\n".join(d.page_content for d in docs)
            title = (docs[0].metadata.get("title") if docs else "") or url.rsplit("/", 1)[-1]
            chunks = [c for c in splitter.split_text(text) if c.strip()]
            if not chunks:
                print(f"SKIP (no content): {url}", file=sys.stderr)
                continue
            embs = embed_texts(chunks)
            key = hashlib.md5(url.encode()).hexdigest()[:10]
            ids = [f"aem_ingest_{key}_{i}" for i in range(len(chunks))]
            metas = [{"url": url, "title": title} for _ in chunks]
            ok = add_documents(CHROMA_COLLECTION_AEM_GUIDES, ids=ids, documents=chunks,
                               metadatas=metas, embeddings=embs)
            print(f"{'OK ' if ok else 'FAIL'} {len(chunks):3d} chunks  {url}")
            total += len(chunks) if ok else 0
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {url}: {exc}", file=sys.stderr)

    _add_to_crawl_config(backend, list(argv))
    print(f"Appended {total} chunk(s) to {CHROMA_COLLECTION_AEM_GUIDES}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
