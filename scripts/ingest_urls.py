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
from urllib.parse import unquote, urljoin, urlsplit


def _text_from_html(html: str, url: str) -> tuple[str, str]:
    """The existing non-LangChain extraction, shared by the guarded replay."""
    import re
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = (match.group(1).strip() if match else "") or url.rsplit("/", 1)[-1]
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t\r\f]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip(), title


def validate_guides_url(url: str) -> str:
    """Allow only the reviewed public Guides documentation origin and path."""
    if not isinstance(url, str) or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise ValueError("UNEXPECTED_URL")
    parts = urlsplit(url)
    decoded_path = unquote(parts.path)
    if not (parts.scheme == "https" and parts.netloc == "experienceleague.adobe.com"
            and parts.path.startswith("/en/docs/experience-manager-guides/")
            and "\\" not in decoded_path and not any(part in {".", ".."} for part in decoded_path.split("/"))
            and not parts.query and not parts.fragment):
        raise ValueError("UNEXPECTED_URL")
    return url


def _reject_non_document_html(html: str, title: str) -> None:
    """Catch recognizable HTTP-200 error/login/landing responses before embedding.

    Check page identity, not prose: real troubleshooting articles can mention
    error messages in their body. This is not a general semantic page validator.
    """
    from html import unescape
    import re

    headings = re.findall(r"<h1\b[^>]*>(.*?)</h1\s*>", html, flags=re.I | re.S)[:3]
    labels = [unescape(re.sub(r"<[^>]*>", " ", item)).strip().lower() for item in [title, *headings]]
    errors = re.compile(
        r"^(?:(?:error\s*)?(?:401|403|404|500|502|503)(?:\b|\s)|"
        r"(?:page |document |resource )?not found\b|access denied\b|forbidden\b|"
        r"unauthorized\b|permission denied\b|service unavailable\b|temporarily unavailable\b|"
        r"internal server error\b|sign[ -]?in\b|log[ -]?in\b|authentication required\b|"
        r"verify (?:that )?you are human\b|just a moment\b)")
    generic = {"experience league", "adobe experience league", "experience manager guides",
               "adobe experience manager guides", "aem guides", "documentation", "welcome", "home"}
    for label in labels:
        normalized = re.sub(r"\s+", " ", label)
        if errors.search(normalized):
            raise ValueError("PAGE_ERROR_DOCUMENT")
    main_title = re.split(r"\s*[|\u2013\u2014]\s*", labels[0], maxsplit=1)[0].strip()
    if main_title in generic:
        raise ValueError("PAGE_GENERIC_LANDING")


def prepare_guides_page(url: str, *, cafile: str) -> dict:
    """Fetch ONCE and prepare existing ingest-format chunks without any index write.

    The optional missing-only replay uses this instead of the permissive legacy
    fetch. Every redirect is checked before it is followed; HTTP error responses,
    another origin, non-HTML, oversized bodies and empty text are rejected.
    The original URL remains the existing stable ingest-ID/provenance contract.
    """
    import httpx
    import ssl

    original = validate_guides_url(url)
    current = original
    maximum = 2 * 1024 * 1024
    context = ssl.create_default_context(cafile=cafile)
    with httpx.Client(timeout=30, follow_redirects=False, verify=context) as client:
        for _ in range(6):
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("PAGE_REDIRECT_INVALID")
                    current = validate_guides_url(urljoin(current, location))
                    continue
                if (response.status_code != 200 or response.headers.get("content-type", "")
                        .split(";", 1)[0].strip().lower() != "text/html"):
                    raise ValueError("PAGE_PREFLIGHT_FAILED")
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > maximum:
                        raise ValueError("PAGE_TOO_LARGE")
                html = bytes(body).decode(response.encoding or "utf-8", errors="strict")
                break
        else:
            raise ValueError("PAGE_REDIRECT_LIMIT")
    text, title = _text_from_html(html, current)
    if not text:
        raise ValueError("PAGE_TEXT_EMPTY")
    _reject_non_document_html(html, title)
    chunks = [chunk for chunk in _split(text, 1000, 200) if chunk.strip()]
    if not chunks or len(chunks) > 3000:
        raise ValueError("PAGE_CHUNKS_INVALID")
    key = hashlib.md5(original.encode()).hexdigest()[:10]  # Existing nonsecurity ingest-ID contract.
    return {
        "url": original, "final_url": current,
        "page_sha256": hashlib.sha256(body).hexdigest(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "ids": [f"aem_ingest_{key}_{index}" for index in range(len(chunks))],
        "documents": chunks,
        "metadatas": [{"url": original, "title": title} for _ in chunks],
    }


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
        import httpx
        html = httpx.get(url, timeout=30, follow_redirects=True).text
        return _text_from_html(html, url)


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
