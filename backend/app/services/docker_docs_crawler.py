"""Crawl Docker documentation from docs.docker.com for RAG.

Fetches Docker get-started HTML pages, splits into chunks, embeds, and stores
in the 'docker_docs' ChromaDB collection for use during DITA generation.

URLs are loaded from config/docker_docs_crawl_urls.json. Add more sections
(Compose, Dockerfile reference, Engine) by extending that config file.

Pattern mirrors crawl_service.py (AEM Guides crawler).
"""
import json
import os
from pathlib import Path
from typing import Optional

from app.storage import get_storage
from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    add_documents as chroma_add_documents,
    delete_collection,
    is_chroma_available,
    query_collection,
    get_collection_count,
    CHROMA_COLLECTION_DOCKER_DOCS,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DOCKER_DOCS_BASE = "https://docs.docker.com"
DOCKER_CRAWL_CONFIG_FILENAME = "docker_docs_crawl_urls.json"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
RATE_LIMIT_SEC = 1.0
MAX_CONTENT_CHARS = 8000

DEFAULT_DOCKER_URLS = [
    "https://docs.docker.com/get-started/",
    "https://docs.docker.com/get-started/introduction/",
    "https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/",
    "https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/",
    "https://docs.docker.com/get-started/docker-concepts/building-images/",
    "https://docs.docker.com/get-started/docker-concepts/running-containers/",
    "https://docs.docker.com/get-started/workshop/",
]

# Retrieved at query time from chat_service
RAG_DOCKER_K = int(os.getenv("RAG_DOCKER_K", "3"))


def _get_config_path() -> Path:
    """Prefer storage copy; fall back to bundled config/docker_docs_crawl_urls.json."""
    storage = get_storage()
    storage_config = storage.base_path / DOCKER_CRAWL_CONFIG_FILENAME
    if storage_config.exists():
        return storage_config
    backend_dir = Path(__file__).resolve().parent.parent.parent
    bundled = backend_dir / "config" / DOCKER_CRAWL_CONFIG_FILENAME
    if bundled.exists():
        return bundled
    return storage_config


def _load_docker_urls() -> list[str]:
    path = _get_config_path()
    if not path.exists():
        return DEFAULT_DOCKER_URLS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        base = (data.get("base_url") or DOCKER_DOCS_BASE).rstrip("/")
        paths = data.get("urls") or []
        urls = []
        for p in paths:
            p = (p or "").strip()
            if p.startswith("http://") or p.startswith("https://"):
                urls.append(p)
            else:
                suffix = p.lstrip("/") if p else ""
                urls.append(f"{base}/{suffix}" if suffix else base)
        if urls:
            logger.info_structured(
                "Docker docs crawl URLs loaded",
                extra_fields={"config_path": str(path), "count": len(urls)},
            )
            return urls
    except (json.JSONDecodeError, OSError) as e:
        logger.warning_structured(
            "Failed to load Docker docs config, using defaults",
            extra_fields={"error": str(e)},
        )
    return DEFAULT_DOCKER_URLS


def crawl_docker_docs(
    urls: Optional[list[str]] = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    """Crawl Docker documentation, split into chunks, embed, and store in 'docker_docs' ChromaDB collection.

    URLs default to docker_docs_crawl_urls.json (get-started section).
    Returns stats: pages_crawled, chunks_stored, errors.
    """
    stats: dict = {"pages_crawled": 0, "chunks_stored": 0, "collection": CHROMA_COLLECTION_DOCKER_DOCS, "errors": []}

    try:
        from langchain_community.document_loaders import WebBaseLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as e:
        stats["errors"].append(
            f"LangChain not installed: {e}. Run: pip install langchain langchain-community langchain-text-splitters"
        )
        return stats

    resolved_urls = urls if urls else _load_docker_urls()

    loader = WebBaseLoader(
        resolved_urls,
        requests_per_second=1.0 / RATE_LIMIT_SEC if RATE_LIMIT_SEC > 0 else 0.5,
        header_template={"User-Agent": "AEM-Guides-Dataset-Studio/1.0 (docker-docs-indexer)"},
    )
    try:
        docs = loader.load()
    except Exception as e:
        stats["errors"].append(str(e))
        logger.warning_structured("Docker docs load failed", extra_fields={"error": str(e)})
        return stats

    stats["pages_crawled"] = len(docs)
    if not docs:
        return stats

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    records = []
    for i, chunk in enumerate(chunks):
        meta = chunk.metadata or {}
        content = chunk.page_content[:MAX_CONTENT_CHARS]
        records.append({
            "url": meta.get("source", ""),
            "title": meta.get("title", ""),
            "content": content,
            "chunk_index": i,
            "source": "docker_docs",
        })

    # Embed
    embeddings_list = None
    if is_embedding_available() and records:
        texts = [r["content"] for r in records]
        embeddings = embed_texts_batched(texts) if len(texts) > 64 else embed_texts(texts)
        if embeddings is not None:
            embeddings_list = [embeddings[i].tolist() for i in range(len(records))]

    # Store in ChromaDB (full replace)
    if is_chroma_available() and embeddings_list and records:
        delete_collection(CHROMA_COLLECTION_DOCKER_DOCS)
        ids = [f"docker_{i}" for i in range(len(records))]
        documents = [r["content"] for r in records]
        metadatas = [
            {"url": r.get("url", ""), "title": r.get("title", ""), "source": "docker_docs"}
            for r in records
        ]
        if chroma_add_documents(
            CHROMA_COLLECTION_DOCKER_DOCS,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings_list,
        ):
            logger.info_structured(
                "Docker docs chunks stored in ChromaDB",
                extra_fields={"count": len(records)},
            )

    stats["chunks_stored"] = len(records)
    logger.info_structured("Docker docs crawl completed", extra_fields=stats)
    return stats


def retrieve_docker_docs(query: str, k: int | None = None) -> list[dict]:
    """Query the 'docker_docs' ChromaDB collection and return matching chunks.

    Returns empty list when the collection is not indexed or embedding is unavailable.
    Each result: {title, url, content, score}.
    """
    resolved_k = k if k is not None else RAG_DOCKER_K
    try:
        from app.services.embedding_service import embed_query, is_embedding_available
        if not is_embedding_available():
            return []
        if not is_chroma_available():
            return []
        if get_collection_count(CHROMA_COLLECTION_DOCKER_DOCS) == 0:
            return []

        embedding = embed_query(query)
        if embedding is None:
            return []

        rows = query_collection(CHROMA_COLLECTION_DOCKER_DOCS, embedding, k=resolved_k)
        results = []
        for row in rows:
            meta = row.get("metadata") or {}
            content = (row.get("document") or "")
            results.append({
                "title": meta.get("title", "Docker Documentation"),
                "url": meta.get("url", ""),
                "content": content,
            })
        return results
    except Exception as e:
        logger.debug_structured("Docker docs retrieval failed", extra_fields={"error": str(e)})
        return []
