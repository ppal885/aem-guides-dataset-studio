"""Crawl AEM Guides documentation from Experience League using LangChain or Playwright.

Crawls HTML pages, splits into chunks, embeds, and stores for RAG retrieval.
Stores in ChromaDB when available; falls back to JSON for backward compatibility.
Respects rate limits (1 req/sec) and uses existing embedding service.

When USE_PLAYWRIGHT_SCRAPER=true or config use_playwright=true, uses Playwright
to extract structured content (p, li, codeph, codeblocks) for richer, DITA-ready data.

URLs are loaded from config/aem_guides_crawl_urls.json (or storage/aem_guides_crawl_urls.json).
Add or remove URLs in the config file without code changes.
"""
import json
import os
import hashlib
from pathlib import Path
from typing import Optional

from app.storage import get_storage
from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    add_documents as chroma_add_documents,
    delete_collection,
    delete_documents,
    get_documents_where,
    is_chroma_available,
    CHROMA_COLLECTION_AEM_GUIDES,
)
from app.services.chunk_metadata_extractor import extract_metadata_from_crawled_page
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

AEM_GUIDES_BASE = "https://experienceleague.adobe.com/en/docs/experience-manager-guides"
CRAWL_URLS_CONFIG_FILENAME = "aem_guides_crawl_urls.json"

# Fallback when config file is missing or invalid
DEFAULT_CRAWL_URLS = [
    f"{AEM_GUIDES_BASE}",
    f"{AEM_GUIDES_BASE}/using/overview",
    f"{AEM_GUIDES_BASE}/using/user-guide/about-aem-guide/intro",
    f"{AEM_GUIDES_BASE}/using/install-guide/on-prem-ig/download-install-upgrade-aemg/download-install",
    f"{AEM_GUIDES_BASE}/using/release-info/release-notes/on-prem-release-notes/latest-release-info",
]

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
RATE_LIMIT_SEC = 1.0
DOC_CHUNKS_FILENAME = "aem_guides_doc_chunks.json"
STRUCTURED_BY_URL_FILENAME = "aem_guides_structured_by_url.json"
MAX_CONTENT_CHARS = 8000


def _get_crawl_config_path() -> Path:
    """Path for crawl URLs config. Prefer storage; fallback to bundled config."""
    storage = get_storage()
    storage_config = storage.base_path / CRAWL_URLS_CONFIG_FILENAME
    if storage_config.exists():
        return storage_config
    # Bundled config in backend/config/
    backend_dir = Path(__file__).resolve().parent.parent.parent
    bundled = backend_dir / "config" / CRAWL_URLS_CONFIG_FILENAME
    if bundled.exists():
        return bundled
    return storage_config


def _load_crawl_urls() -> list[str]:
    """
    Load crawl URLs from config file. Paths in config are relative to base_url.
    Returns resolved full URLs. Falls back to DEFAULT_CRAWL_URLS on error.
    """
    path = _get_crawl_config_path()
    if not path.exists():
        logger.info_structured(
            "Crawl config not found, using default URLs",
            extra_fields={"config_path": str(path)},
        )
        return DEFAULT_CRAWL_URLS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        base_url = (data.get("base_url") or AEM_GUIDES_BASE).rstrip("/")
        paths = data.get("urls") or []
        urls = []
        for p in paths:
            p = (p or "").strip()
            if p.startswith("http://") or p.startswith("https://"):
                urls.append(p)
            else:
                suffix = p.lstrip("/") if p else ""
                urls.append(f"{base_url}/{suffix}" if suffix else base_url)
        if urls:
            logger.info_structured(
                "Crawl URLs loaded from config",
                extra_fields={"config_path": str(path), "count": len(urls)},
            )
            return urls
    except (json.JSONDecodeError, OSError) as e:
        logger.warning_structured(
            "Failed to load crawl config, using default URLs",
            extra_fields={"config_path": str(path), "error": str(e)},
        )
    return DEFAULT_CRAWL_URLS


def _get_doc_chunks_path() -> Path:
    """Path for storing doc chunks JSON."""
    storage = get_storage()
    return storage.base_path / DOC_CHUNKS_FILENAME


def _load_existing_doc_chunks() -> list[dict]:
    path = _get_doc_chunks_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _get_structured_by_url_path() -> Path:
    """Path for storing per-URL structured content (Playwright only)."""
    storage = get_storage()
    return storage.base_path / STRUCTURED_BY_URL_FILENAME


def _stable_chunk_id(url: str, chunk_index: int) -> str:
    digest = hashlib.sha256(f"{url}|{chunk_index}".encode("utf-8")).hexdigest()[:24]
    return f"aem_url_{digest}"


def _fallback_embedding(text: str, *, dim: int = 384) -> list[float]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in str(text or ""))
    tokens = {token for token in cleaned.split() if len(token) >= 2}
    if not tokens:
        return [0.0] * dim
    vector = [0.0] * dim
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    magnitude = sum(value * value for value in vector) ** 0.5
    if magnitude <= 0:
        return vector
    return [round(value / magnitude, 8) for value in vector]


def _load_crawl_config() -> dict:
    """Load full crawl config (urls, recursive settings). Returns empty dict on error."""
    path = _get_crawl_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_crawl_urls() -> list[str]:
    """Return the resolved list of configured crawl URLs."""
    return _load_crawl_urls()


def save_urls_to_config(new_urls: list[str]) -> int:
    """
    Append new_urls to the config JSON file (deduplicating).
    Returns the number of URLs actually added.
    """
    path = _get_crawl_config_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {"base_url": AEM_GUIDES_BASE, "urls": []}

        existing = set(data.get("urls") or [])
        added = 0
        for url in new_urls:
            url = (url or "").strip()
            if url and url not in existing:
                data.setdefault("urls", []).append(url)
                existing.add(url)
                added += 1

        if added:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return added
    except (json.JSONDecodeError, OSError) as e:
        logger.warning_structured(
            "Failed to save URLs to crawl config",
            extra_fields={"error": str(e)},
        )
        return 0


def crawl_and_index(
    urls: Optional[list[str]] = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    """
    Crawl AEM Guides docs, split, embed, and store.
    URLs from config file when urls is None. Supports recursive mode via config.
    Returns stats: pages_crawled, chunks_stored, errors.
    """
    stats = {"pages_crawled": 0, "chunks_stored": 0, "errors": []}
    explicit_urls = urls is not None

    try:
        from langchain_community.document_loaders import WebBaseLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as e:
        stats["errors"].append(f"LangChain not installed: {e}. Run: pip install langchain langchain-community langchain-text-splitters")
        return stats

    use_recursive = False
    use_playwright = False
    if urls is None:
        config = _load_crawl_config()
        rec = config.get("recursive") or {}
        if rec.get("enabled"):
            use_recursive = True
            base_url = (config.get("base_url") or AEM_GUIDES_BASE).rstrip("/")
        else:
            urls = _load_crawl_urls()
    if urls is None:
        urls = DEFAULT_CRAWL_URLS

    docs = []
    if use_recursive:
        config = _load_crawl_config()
        base_url = (config.get("base_url") or AEM_GUIDES_BASE).rstrip("/")
        rec = config.get("recursive") or {}
        max_depth = rec.get("max_depth", 2)
        exclude_dirs = rec.get("exclude_dirs") or []
        try:
            from langchain_community.document_loaders import RecursiveUrlLoader
            loader = RecursiveUrlLoader(
                url=base_url,
                max_depth=max_depth,
                prevent_outside=True,
                exclude_dirs=exclude_dirs if exclude_dirs else None,
            )
            docs = loader.load()
        except ImportError:
            logger.warning_structured(
                "RecursiveUrlLoader not available, falling back to explicit URLs",
                extra_fields={},
            )
            urls = _load_crawl_urls()
            use_recursive = False

    if not use_recursive:
        config = _load_crawl_config()
        use_playwright = (
            config.get("use_playwright") is True
            or os.getenv("USE_PLAYWRIGHT_SCRAPER", "").lower() in ("true", "1", "yes")
        )

        if use_playwright:
            try:
                from app.services.playwright_scraper_service import scrape_experience_league_page
                from langchain_core.documents import Document

                docs = []
                for url in urls:
                    scraped = scrape_experience_league_page(url)
                    if scraped.get("error"):
                        stats["errors"].append(f"{url}: {scraped['error']}")
                        continue
                    parts = []
                    for p in scraped.get("paragraphs") or []:
                        parts.append(str(p))
                    for li in scraped.get("list_items") or []:
                        parts.append(f"• {li}")
                    for c in scraped.get("codeph") or []:
                        parts.append(f"`{c}`")
                    for cb in scraped.get("codeblocks") or []:
                        parts.append(cb)
                    for tbl in scraped.get("tables") or []:
                        if isinstance(tbl, list):
                            for row in tbl:
                                if isinstance(row, list):
                                    parts.append(" | ".join(str(c) for c in row))
                    page_content = "\n\n".join(parts) if parts else scraped.get("title", "")
                    meta = {
                        "source": url,
                        "title": scraped.get("title", ""),
                        "paragraphs": scraped.get("paragraphs", []),
                        "list_items": scraped.get("list_items", []),
                        "codeph": scraped.get("codeph", []),
                        "codeblocks": scraped.get("codeblocks", []),
                        "tables": scraped.get("tables", []),
                    }
                    docs.append(Document(page_content=page_content, metadata=meta))
                if not docs:
                    logger.warning_structured(
                        "Playwright scrape produced no docs, falling back to WebBaseLoader",
                        extra_fields={"errors": stats["errors"]},
                    )
                    use_playwright = False
            except ImportError as e:
                logger.warning_structured(
                    "Playwright not available, using WebBaseLoader",
                    extra_fields={"error": str(e)},
                )
                use_playwright = False

        if not use_playwright:
            loader = WebBaseLoader(
                urls,
                requests_per_second=1.0 / RATE_LIMIT_SEC if RATE_LIMIT_SEC > 0 else 0.5,
                header_template={"User-Agent": "AEM-Guides-Dataset-Studio/1.0 (documentation-indexer)"},
            )
            try:
                docs = loader.load()
            except Exception as e:
                stats["errors"].append(str(e))
                logger.warning_structured("Crawl load failed", extra_fields={"error": str(e)})
                return stats

    stats["pages_crawled"] = len(docs)
    if not docs:
        return stats

    # Per-URL structured content (Playwright only) for experience_league_to_dita
    structured_path = _get_structured_by_url_path()
    if use_playwright and docs:
        structured_by_url = []
        for doc in docs:
            meta = doc.metadata or {}
            structured_by_url.append({
                "url": meta.get("source", ""),
                "title": meta.get("title", ""),
                "paragraphs": meta.get("paragraphs", []),
                "list_items": meta.get("list_items", []),
                "codeph": meta.get("codeph", []),
                "codeblocks": meta.get("codeblocks", []),
                "tables": meta.get("tables", []),
            })
        structured_path.parent.mkdir(parents=True, exist_ok=True)
        structured_path.write_text(json.dumps(structured_by_url, indent=2), encoding="utf-8")
    elif structured_path.exists():
        structured_path.unlink()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    # Build chunk records: url, title, content, chunk_index
    # Use full chunk content (up to MAX_CONTENT_CHARS) for authenticity
    records = []
    for i, chunk in enumerate(chunks):
        metadata = chunk.metadata or {}
        content = chunk.page_content[:MAX_CONTENT_CHARS]
        records.append({
            "url": metadata.get("source", ""),
            "title": metadata.get("title", ""),
            "content": content,
            "chunk_index": i,
            "paragraphs": metadata.get("paragraphs", []),
            "list_items": metadata.get("list_items", []),
            "codeph": metadata.get("codeph", []),
            "codeblocks": metadata.get("codeblocks", []),
            "tables": metadata.get("tables", []),
        })

    # Embed if available
    embeddings_list = None
    if is_embedding_available() and records:
        texts = [r["content"] for r in records]
        embeddings = (
            embed_texts_batched(texts)
            if len(texts) > 64
            else embed_texts(texts)
        )
        if embeddings is not None:
            embeddings_list = [embeddings[i].tolist() for i in range(len(records))]
            for i, r in enumerate(records):
                r["embedding"] = embeddings_list[i]

    # Extract chunk metadata when feature flag is enabled
    chunk_metadata_enabled = os.getenv("CHUNK_METADATA_ENABLED", "false").lower() == "true"
    if chunk_metadata_enabled:
        for r in records:
            meta = extract_metadata_from_crawled_page(
                content=r["content"],
                url=r.get("url", ""),
                title=r.get("title", ""),
            )
            # Store full metadata as JSON on the record for JSON file fallback
            r["chunk_metadata"] = meta.model_dump(mode="json")

    embedding_mode = "semantic"
    if embeddings_list is None and records:
        embedding_mode = "lexical_fallback"
        embeddings_list = [_fallback_embedding(r["content"]) for r in records]
        for i, r in enumerate(records):
            r["embedding"] = embeddings_list[i]

    # Store to ChromaDB when available. Full crawls replace; explicit URL crawls upsert only those pages.
    if is_chroma_available() and embeddings_list and records:
        if explicit_urls:
            for url in {str(r.get("url") or "").strip() for r in records if str(r.get("url") or "").strip()}:
                existing_docs = get_documents_where(CHROMA_COLLECTION_AEM_GUIDES, {"url": url}, limit=1000)
                existing_ids = [str(item.get("id") or "").strip() for item in existing_docs if str(item.get("id") or "").strip()]
                if existing_ids:
                    delete_documents(CHROMA_COLLECTION_AEM_GUIDES, existing_ids)
            ids = [_stable_chunk_id(r.get("url", ""), int(r.get("chunk_index") or 0)) for r in records]
        else:
            delete_collection(CHROMA_COLLECTION_AEM_GUIDES)
            ids = [f"aem_{i}" for i in range(len(records))]
        documents = [r["content"] for r in records]
        if chunk_metadata_enabled:
            metadatas = []
            for r in records:
                md = {"url": r.get("url", ""), "title": r.get("title", ""), "embedding_mode": embedding_mode}
                cm = r.get("chunk_metadata", {})
                # Add only ChromaDB-compatible scalar fields (str/float/int/bool)
                for key in (
                    "doc_type", "element_name", "region_type", "source_type",
                    "chunk_priority", "content_hash", "is_standalone",
                ):
                    if key in cm:
                        md[key] = cm[key]
                metadatas.append(md)
        else:
            metadatas = [
                {"url": r.get("url", ""), "title": r.get("title", ""), "embedding_mode": embedding_mode}
                for r in records
            ]
        if chroma_add_documents(
            CHROMA_COLLECTION_AEM_GUIDES,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings_list,
        ):
            logger.info_structured(
                "AEM Guides chunks stored in ChromaDB",
                extra_fields={"count": len(records)},
            )

    # Store to JSON for backward compatibility and lexical fallback.
    path = _get_doc_chunks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if explicit_urls:
        new_urls = {str(r.get("url") or "").strip() for r in records if str(r.get("url") or "").strip()}
        merged_records = [
            item
            for item in _load_existing_doc_chunks()
            if str(item.get("url") or "").strip() not in new_urls
        ]
        merged_records.extend(records)
    else:
        merged_records = records
    path.write_text(json.dumps(merged_records, indent=2), encoding="utf-8")
    stats["chunks_stored"] = len(records)

    logger.info_structured(
        "AEM Guides crawl completed",
        extra_fields=stats,
    )
    return stats
