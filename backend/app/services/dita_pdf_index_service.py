"""DITA specification PDF index service using LangChain.

Downloads OASIS DITA spec PDFs (1.2, 1.3 Part 1 Base), loads with PyPDFLoader,
splits, embeds, and stores in ChromaDB for RAG retrieval.

PDF URLs configurable via DITA_PDF_URLS env (comma-separated) or dita_pdf.urls in config.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional

from app.storage import get_storage
from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    add_documents as chroma_add_documents,
    delete_collection,
    is_chroma_available,
    CHROMA_COLLECTION_DITA_SPEC,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DITA_12_PDF_URL = "https://docs.oasis-open.org/dita/v1.2/spec/DITA1.2-spec.pdf"
DITA_13_PART1_BASE_PDF_URL = "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/dita-v1.3-os-part1-base.pdf"
DITA_SPEC_DIR = "dita_spec"
CRAWL_CONFIG_FILENAME = "aem_guides_crawl_urls.json"
CHUNK_SIZE = int(os.getenv("DITA_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("DITA_CHUNK_OVERLAP", "200"))
MAX_CONTENT_CHARS = 8000

DEFAULT_PDF_URLS = [DITA_12_PDF_URL, DITA_13_PART1_BASE_PDF_URL]


def _get_pdf_urls() -> list[str]:
    """Get DITA PDF URLs from DITA_PDF_URLS env (comma-separated) or config dita_pdf.urls."""
    urls_env = os.getenv("DITA_PDF_URLS", "").strip()
    if urls_env:
        urls = [u.strip() for u in urls_env.split(",") if u.strip() and u.strip().startswith(("http://", "https://"))]
        if urls:
            return urls
    storage = get_storage()
    for config_path in [
        storage.base_path / CRAWL_CONFIG_FILENAME,
        Path(__file__).resolve().parent.parent.parent / "config" / CRAWL_CONFIG_FILENAME,
    ]:
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                dita = data.get("dita_pdf") or {}
                urls = dita.get("urls")
                if isinstance(urls, list) and urls:
                    valid = [u.strip() for u in urls if isinstance(u, str) and u.strip().startswith(("http://", "https://"))]
                    if valid:
                        return valid
                url = (dita.get("url") or "").strip()
                if url and url.startswith(("http://", "https://")):
                    return [url]
            except (json.JSONDecodeError, OSError):
                pass
    return DEFAULT_PDF_URLS


def _get_pdf_path_for_url(url: str) -> Path:
    """Path for storing a DITA PDF. Derive filename from URL."""
    storage = get_storage()
    base = storage.base_path / DITA_SPEC_DIR
    base.mkdir(parents=True, exist_ok=True)
    match = re.search(r"/([^/]+\.pdf)(?:\?|$)", url)
    filename = match.group(1) if match else url.split("/")[-1] or "dita-spec.pdf"
    return base / filename


def _id_prefix_for_url(url: str) -> str:
    """Short id prefix for ChromaDB ids (e.g. dita12, dita13)."""
    if "v1.2" in url or "DITA1.2" in url:
        return "dita12"
    if "v1.3" in url or "part1-base" in url:
        return "dita13"
    return "dita"


def index_dita_pdf(
    pdf_urls: Optional[list[str]] = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    """
    Download DITA spec PDFs, load with LangChain, split, embed, and store in ChromaDB.
    Returns stats: pages_loaded, chunks_stored, sources_indexed, errors.
    """
    urls = pdf_urls or _get_pdf_urls()
    stats = {"pages_loaded": 0, "chunks_stored": 0, "sources_indexed": [], "errors": []}

    try:
        import httpx
    except ImportError:
        stats["errors"].append("httpx not installed. Run: pip install httpx")
        return stats

    try:
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as e:
        stats["errors"].append(
            f"LangChain not installed: {e}. Run: pip install langchain-community langchain-text-splitters pypdf"
        )
        return stats

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    all_records = []
    id_offset = 0

    for pdf_url in urls:
        if not pdf_url or not pdf_url.strip().startswith(("http://", "https://")):
            continue
        pdf_url = pdf_url.strip()
        pdf_path = _get_pdf_path_for_url(pdf_url)

        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                resp = client.get(pdf_url)
                resp.raise_for_status()
                pdf_path.write_bytes(resp.content)
        except Exception as e:
            stats["errors"].append(f"PDF download failed ({pdf_url}): {e}")
            logger.warning_structured(
                "DITA PDF download failed",
                extra_fields={"url": pdf_url, "error": str(e)},
            )
            continue

        try:
            loader = PyPDFLoader(str(pdf_path))
            docs = loader.load()
        except Exception as e:
            stats["errors"].append(f"PDF load failed ({pdf_url}): {e}")
            logger.warning_structured(
                "DITA PDF load failed",
                extra_fields={"path": str(pdf_path), "url": pdf_url, "error": str(e)},
            )
            continue

        stats["pages_loaded"] += len(docs)
        if not docs:
            continue

        chunks = splitter.split_documents(docs)
        prefix = _id_prefix_for_url(pdf_url)
        for i, chunk in enumerate(chunks):
            metadata = chunk.metadata or {}
            page = metadata.get("page", "")
            all_records.append({
                "id": f"{prefix}_{id_offset + i}",
                "content": chunk.page_content[:MAX_CONTENT_CHARS],
                "source_url": pdf_url,
                "page": str(page) if page else "",
            })
        id_offset += len(chunks)
        stats["sources_indexed"].append(pdf_url)

    if not all_records:
        logger.info_structured(
            "DITA PDF index completed (no chunks)",
            extra_fields=stats,
        )
        return stats

    embeddings_list = None
    if is_embedding_available() and all_records:
        texts = [r["content"] for r in all_records]
        embeddings = (
            embed_texts_batched(texts)
            if len(texts) > 64
            else embed_texts(texts)
        )
        if embeddings is not None:
            embeddings_list = [embeddings[i].tolist() for i in range(len(all_records))]

    if is_chroma_available() and embeddings_list and all_records:
        delete_collection(CHROMA_COLLECTION_DITA_SPEC)
        ids = [r["id"] for r in all_records]
        documents = [r["content"] for r in all_records]
        metadatas = [
            {"source_url": r.get("source_url", ""), "page": r.get("page", "")}
            for r in all_records
        ]
        if chroma_add_documents(
            CHROMA_COLLECTION_DITA_SPEC,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings_list,
        ):
            logger.info_structured(
                "DITA spec chunks stored in ChromaDB",
                extra_fields={"count": len(all_records), "sources": stats["sources_indexed"]},
            )

    stats["chunks_stored"] = len(all_records)

    logger.info_structured(
        "DITA PDF index completed",
        extra_fields=stats,
    )
    return stats
