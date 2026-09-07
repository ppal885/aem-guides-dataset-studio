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


def _fetch_text(url: str) -> tuple[str, str]:
    """Fetch page text. Prefer langchain WebBaseLoader if present; otherwise plain
    httpx + tag-strip (no langchain dependency needed on the VM)."""
    try:
        from langchain_community.document_loaders import WebBaseLoader  # noqa: PLC0415
        docs = WebBaseLoader(url).load()
        text = "\n".join(d.page_content for d in docs)
        title = (docs[0].metadata.get("title") if docs else "") or url.rsplit("/", 1)[-1]
        return text, title
    except Exception:  # noqa: BLE001 - langchain missing or load failed; fall back
        import re
        import httpx
        html = httpx.get(url, timeout=30, follow_redirects=True).text
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = (m.group(1).strip() if m else "") or url.rsplit("/", 1)[-1]
        # strip script/style then tags, collapse whitespace
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"[ \t\r\f]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip(), title


def _split(text: str, size: int, overlap: int) -> list[str]:
    """Character splitter. Prefer langchain's RecursiveCharacterTextSplitter; else a
    simple fixed-window splitter with overlap."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415
        return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap).split_text(text)
    except Exception:  # noqa: BLE001
        chunks, i, n = [], 0, len(text)
        step = max(1, size - overlap)
        while i < n:
            chunks.append(text[i:i + size])
            i += step
        return chunks


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
    from app.services.embedding_service import embed_texts, is_embedding_available
    from app.services.vector_store_service import (
        add_documents, is_chroma_available, CHROMA_COLLECTION_AEM_GUIDES,
    )

    if not is_chroma_available() or not is_embedding_available():
        print("Chroma or embeddings unavailable.", file=sys.stderr)
        return 2

    total = 0
    for url in argv:
        try:
            text, title = _fetch_text(url)
            chunks = [c for c in _split(text, 1000, 200) if c.strip()]
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
