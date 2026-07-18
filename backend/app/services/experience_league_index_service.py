"""Crawl Experience League AEM Guides docs and upsert into RAG (Chroma + JSON).

Unlike ``crawl_and_index()`` in ``crawl_service``, this module **upserts** chunks
so existing indexed content (manual chunks, prior crawls) is preserved by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from app.core.structured_logging import get_structured_logger
from app.services.crawl_service import (
    AEM_GUIDES_BASE,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CRAWL_URLS_CONFIG_FILENAME,
    MAX_CONTENT_CHARS,
    _get_crawl_config_path,
    _get_doc_chunks_path,
    _load_crawl_urls,
)
from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    add_documents,
    delete_collection,
    get_collection_count,
    is_chroma_available,
)

logger = get_structured_logger(__name__)

DEFAULT_ALLOWED_HOSTS = frozenset({"experienceleague.adobe.com"})
DEFAULT_PATH_PREFIXES = (
    "/en/docs/experience-manager-guides",
    "/en/docs/experience-manager-guides-learn",
)
RATE_LIMIT_SEC = 1.0
USER_AGENT = "AEM-Guides-Dataset-Studio/1.0 (experience-league-indexer)"
SOURCE_TYPE = "official-experience-league"
CORPUS_NAME = "aem_guides"
PARSER_VERSION = "experience-league-index-service/2.0"


def _normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    path = parsed.path.rstrip("/") or "/"
    # Drop fragment; keep query (some EL pages use anchors only)
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def is_allowed_experience_league_url(
    url: str,
    *,
    allowed_hosts: frozenset[str] | None = None,
    path_prefixes: tuple[str, ...] | None = None,
) -> bool:
    """SSRF guard: only index approved Experience League AEM Guides paths."""
    allowed_hosts = allowed_hosts or DEFAULT_ALLOWED_HOSTS
    path_prefixes = path_prefixes or DEFAULT_PATH_PREFIXES
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host not in allowed_hosts:
        return False
    path = (parsed.path or "").lower()
    return any(path.startswith(prefix.lower()) for prefix in path_prefixes)


def filter_allowed_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        url = _normalize_url(raw)
        if not url or url in seen:
            continue
        if not is_allowed_experience_league_url(url):
            continue
        seen.add(url)
        out.append(url)
    return out


def stable_chunk_id(url: str, chunk_index: int) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"aem_el_{digest}_{chunk_index}"


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def discover_urls_recursive(
    base_url: str,
    *,
    max_depth: int = 3,
    exclude_dirs: list[str] | None = None,
) -> list[str]:
    """Discover Experience League pages under base_url using RecursiveUrlLoader."""
    base_url = _normalize_url(base_url)
    if not is_allowed_experience_league_url(base_url):
        raise ValueError(f"Base URL not allowed for Experience League crawl: {base_url}")

    try:
        from langchain_community.document_loaders import RecursiveUrlLoader
    except ImportError as exc:
        raise ImportError(
            "langchain-community required. Run: pip install langchain-community"
        ) from exc

    loader = RecursiveUrlLoader(
        url=base_url,
        max_depth=max(1, min(max_depth, 6)),
        prevent_outside=True,
        exclude_dirs=exclude_dirs or ["/communities/", "/t5/"],
        headers={"User-Agent": USER_AGENT},
    )
    docs = loader.load()
    urls = filter_allowed_urls(
        (doc.metadata or {}).get("source", "") for doc in docs
    )
    if base_url not in urls:
        urls.insert(0, base_url)
    return urls


def _scrape_with_playwright(urls: list[str]) -> tuple[list, list[str]]:
    from langchain_core.documents import Document

    from app.services.playwright_scraper_service import scrape_experience_league_page

    docs = []
    errors: list[str] = []
    for url in urls:
        scraped = scrape_experience_league_page(url)
        if scraped.get("error"):
            errors.append(f"{url}: {scraped['error']}")
            continue
        parts: list[str] = []
        for p in scraped.get("paragraphs") or []:
            parts.append(str(p))
        for li in scraped.get("list_items") or []:
            parts.append(f"• {li}")
        for c in scraped.get("codeph") or []:
            parts.append(f"`{c}`")
        for cb in scraped.get("codeblocks") or []:
            parts.append(str(cb))
        page_content = "\n\n".join(parts) if parts else str(scraped.get("title") or "")
        if not page_content.strip():
            errors.append(f"{url}: empty content")
            continue
        docs.append(
            Document(
                page_content=page_content,
                metadata={
                    "source": url,
                    "title": scraped.get("title", ""),
                    "paragraphs": scraped.get("paragraphs", []),
                    "list_items": scraped.get("list_items", []),
                    "codeph": scraped.get("codeph", []),
                    "codeblocks": scraped.get("codeblocks", []),
                    "tables": scraped.get("tables", []),
                },
            )
        )
    return docs, errors


def _scrape_with_web_loader(urls: list[str], *, rate_limit_sec: float = RATE_LIMIT_SEC) -> tuple[list, list[str]]:
    from langchain_community.document_loaders import WebBaseLoader

    errors: list[str] = []
    loader = WebBaseLoader(
        urls,
        requests_per_second=1.0 / rate_limit_sec if rate_limit_sec > 0 else 0.5,
        header_template={"User-Agent": USER_AGENT},
    )
    try:
        docs = loader.load()
    except Exception as exc:
        errors.append(str(exc))
        return [], errors
    return docs, errors


def scrape_urls_to_documents(
    urls: list[str],
    *,
    use_playwright: bool = False,
    rate_limit_sec: float = RATE_LIMIT_SEC,
) -> tuple[list, dict]:
    """Fetch pages and return LangChain Document list + stats."""
    urls = filter_allowed_urls(urls)
    stats = {"pages_requested": len(urls), "pages_crawled": 0, "errors": []}
    if not urls:
        return [], stats

    if use_playwright:
        docs, errors = _scrape_with_playwright(urls)
    else:
        docs, errors = _scrape_with_web_loader(urls, rate_limit_sec=rate_limit_sec)

    stats["errors"].extend(errors)
    # Keep only allowed sources
    filtered = []
    for doc in docs:
        source = _normalize_url((doc.metadata or {}).get("source", ""))
        if is_allowed_experience_league_url(source):
            meta = dict(doc.metadata or {})
            meta["source"] = source
            doc.metadata = meta
            filtered.append(doc)
    stats["pages_crawled"] = len(filtered)
    return filtered, stats


def documents_to_chunk_records(
    docs: list,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if not docs:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    records: list[dict] = []
    per_url_index: dict[str, int] = {}

    for chunk in chunks:
        metadata = chunk.metadata or {}
        url = _normalize_url(metadata.get("source", ""))
        chunk_index = per_url_index.get(url, 0)
        per_url_index[url] = chunk_index + 1
        content = (chunk.page_content or "")[:MAX_CONTENT_CHARS]
        page_hash = _content_hash(str(metadata.get("source", "")) + "\n" + str(chunk.page_content or ""))
        records.append(
            {
                "id": stable_chunk_id(url, chunk_index),
                "url": url,
                "source_url": url,
                "canonical_url": url,
                "source_type": SOURCE_TYPE,
                "corpus": CORPUS_NAME,
                "parser_version": PARSER_VERSION,
                "title": metadata.get("title", ""),
                "content": content,
                "content_hash": page_hash,
                "chunk_content_hash": _content_hash(content),
                "chunk_index": chunk_index,
                "paragraphs": metadata.get("paragraphs", []),
                "list_items": metadata.get("list_items", []),
                "codeph": metadata.get("codeph", []),
                "codeblocks": metadata.get("codeblocks", []),
                "tables": metadata.get("tables", []),
            }
        )
    return records


def _load_existing_json_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def merge_chunk_records(
    existing: list[dict],
    new_records: list[dict],
    *,
    crawled_urls: set[str],
) -> list[dict]:
    """Replace chunks for re-crawled URLs; keep unrelated existing chunks."""
    kept = []
    for row in existing:
        url = _normalize_url(str(row.get("url") or ""))
        if url in crawled_urls:
            continue
        kept.append(row)
    merged = [*kept, *new_records]
    merged.sort(key=lambda r: (str(r.get("url") or ""), int(r.get("chunk_index") or 0)))
    return merged


def upsert_records_to_chroma(records: list[dict], *, batch_size: int = 64) -> int:
    if not records or not is_chroma_available() or not is_embedding_available():
        return 0

    stored = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        texts = [r["content"] for r in batch]
        embeddings = embed_texts_batched(texts) if len(texts) > 32 else embed_texts(texts)
        if embeddings is None:
            continue
        ids = [r["id"] for r in batch]
        metadatas = [
            {
                "url": r.get("url", ""),
                "source_url": r.get("source_url", r.get("url", "")),
                "canonical_url": r.get("canonical_url", r.get("url", "")),
                "source_type": r.get("source_type", SOURCE_TYPE),
                "corpus": r.get("corpus", CORPUS_NAME),
                "title": r.get("title", ""),
                "chunk_index": int(r.get("chunk_index") or 0),
                "content_hash": r.get("content_hash", ""),
                "chunk_content_hash": r.get("chunk_content_hash", ""),
                "parser_version": r.get("parser_version", PARSER_VERSION),
            }
            for r in batch
        ]
        emb_list = [embeddings[i].tolist() for i in range(len(batch))]
        if add_documents(
            CHROMA_COLLECTION_AEM_GUIDES,
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=emb_list,
        ):
            stored += len(batch)
    return stored


def crawl_experience_league_rag(
    *,
    urls: list[str] | None = None,
    base_url: str | None = None,
    recursive: bool = False,
    max_depth: int = 3,
    from_config: bool = False,
    use_playwright: bool | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    wipe_collection: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Crawl Experience League AEM Guides pages and upsert into RAG.

    Returns stats dict with pages_crawled, chunks_stored, chroma_upserted, errors, urls_discovered.
    """
    stats: dict = {
        "pages_crawled": 0,
        "chunks_stored": 0,
        "chroma_upserted": 0,
        "urls_discovered": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    resolved_urls: list[str] = []
    if recursive:
        root = _normalize_url(base_url or AEM_GUIDES_BASE)
        config = {}
        cfg_path = _get_crawl_config_path()
        if cfg_path.exists():
            try:
                config = json.loads(cfg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                config = {}
        rec = config.get("recursive") or {}
        exclude_dirs = rec.get("exclude_dirs") or ["/communities/", "/t5/"]
        try:
            resolved_urls = discover_urls_recursive(
                root,
                max_depth=max_depth,
                exclude_dirs=exclude_dirs,
            )
        except Exception as exc:
            stats["errors"].append(str(exc))
            return stats
    elif from_config:
        resolved_urls = filter_allowed_urls(_load_crawl_urls())
    elif urls:
        resolved_urls = filter_allowed_urls(urls)
    else:
        resolved_urls = filter_allowed_urls(_load_crawl_urls())

    stats["urls_discovered"] = len(resolved_urls)
    if not resolved_urls:
        stats["errors"].append("No allowed Experience League URLs to crawl")
        return stats

    if dry_run:
        stats["sample_urls"] = resolved_urls[:20]
        return stats

    use_pw = (
        use_playwright
        if use_playwright is not None
        else os.getenv("USE_PLAYWRIGHT_SCRAPER", "").lower() in ("true", "1", "yes")
    )

    docs, scrape_stats = scrape_urls_to_documents(
        resolved_urls,
        use_playwright=use_pw,
    )
    stats["pages_crawled"] = scrape_stats.get("pages_crawled", 0)
    stats["errors"].extend(scrape_stats.get("errors") or [])

    records = documents_to_chunk_records(
        docs,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not records:
        return stats

    crawled_urls = {_normalize_url(r["url"]) for r in records}
    json_path = _get_doc_chunks_path()
    existing = _load_existing_json_chunks(json_path)
    merged = merge_chunk_records(existing, records, crawled_urls=crawled_urls)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    stats["chunks_stored"] = len(records)
    stats["json_total_chunks"] = len(merged)

    if wipe_collection and is_chroma_available():
        delete_collection(CHROMA_COLLECTION_AEM_GUIDES)
        stats["collection_wiped"] = True

    stats["chroma_upserted"] = upsert_records_to_chroma(records)
    stats["chroma_total_chunks"] = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)

    logger.info_structured(
        "Experience League RAG upsert completed",
        extra_fields={
            "urls": len(resolved_urls),
            "pages": stats["pages_crawled"],
            "new_chunks": stats["chunks_stored"],
            "chroma_upserted": stats["chroma_upserted"],
        },
    )
    return stats
