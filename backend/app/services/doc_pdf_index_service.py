from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.structured_logging import get_structured_logger
from app.storage import get_storage

logger = get_structured_logger(__name__)

CHUNK_SIZE = int(os.getenv("DOC_PDF_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("DOC_PDF_CHUNK_OVERLAP", "64"))
MIN_CHUNK_CHARS = 80
MAX_PAGES = int(os.getenv("DOC_PDF_MAX_PAGES", "500"))

DOC_TYPES = {
    "style_guide": "Style guide and writing rules",
    "product_doc": "Product documentation",
    "approved_topic": "Approved DITA topic",
    "terminology": "Terminology reference",
    "api_reference": "API reference",
    "release_notes": "Release notes",
    "user_manual": "User manual",
    "other": "Other documentation",
}


def _registry_path() -> Path:
    path = get_storage().base_path / "pdf_index_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class IndexResult:
    filename: str
    tenant_id: str
    doc_type: str
    label: str
    pages_read: int = 0
    chunks_stored: int = 0
    skipped: bool = False
    skip_reason: str = ""
    errors: list[str] = field(default_factory=list)
    collection: str = ""
    file_hash: str = ""
    indexed_at: str = ""
    chunk_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "tenant_id": self.tenant_id,
            "doc_type": self.doc_type,
            "label": self.label,
            "pages_read": self.pages_read,
            "chunks_stored": self.chunks_stored,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "errors": self.errors,
            "collection": self.collection,
            "file_hash": self.file_hash,
            "indexed_at": self.indexed_at,
        }


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(payload: dict) -> None:
    _registry_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(512 * 1024))
    return digest.hexdigest()[:16]


def list_indexed_docs(tenant_id: str) -> list[dict]:
    registry = _load_registry()
    docs = [value for key, value in registry.items() if key.startswith(f"{tenant_id}:")]
    return sorted(docs, key=lambda item: item.get("indexed_at", ""), reverse=True)


def is_already_indexed(pdf_path: Path, tenant_id: str) -> dict | None:
    registry = _load_registry()
    return registry.get(f"{tenant_id}:{_file_hash(pdf_path)}")


def remove_from_index(tenant_id: str, file_hash: str) -> bool:
    from app.services.tenant_service import get_tenant
    from app.services.vector_store_service import delete_documents

    registry = _load_registry()
    key = f"{tenant_id}:{file_hash}"
    record = registry.pop(key, None)
    if not record:
        return False
    _save_registry(registry)

    chunk_ids = record.get("chunk_ids") or []
    if chunk_ids:
        try:
            delete_documents(get_tenant(tenant_id).rag_collection, chunk_ids)
        except Exception as exc:
            logger.warning_structured(
                "Failed to delete indexed PDF chunks",
                extra_fields={"tenant_id": tenant_id, "error": str(exc)},
            )
    return True


def _mark_indexed(result: IndexResult) -> None:
    registry = _load_registry()
    registry[f"{result.tenant_id}:{result.file_hash}"] = {
        "tenant_id": result.tenant_id,
        "filename": result.filename,
        "label": result.label,
        "doc_type": result.doc_type,
        "chunks": result.chunks_stored,
        "indexed_at": result.indexed_at,
        "collection": result.collection,
        "file_hash": result.file_hash,
        "chunk_ids": result.chunk_ids,
    }
    _save_registry(registry)


def _extract_text_pypdf(pdf_path: Path) -> tuple[list[dict], int]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise ValueError(f"Unable to read PDF '{pdf_path.name}': {exc}") from exc
    pages: list[dict] = []
    for index, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        pages.append({"page_num": index, "text": text, "has_text": len(text) > 30})
    return pages, len(reader.pages)


def _extract_text_pdfplumber(pdf_path: Path) -> tuple[list[dict], int]:
    import pdfplumber

    pages: list[dict] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for index, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                text = (page.extract_text() or "").strip()
                tables = page.extract_tables() or []
                table_lines: list[str] = []
                for table in tables:
                    for row in table or []:
                        row_text = " | ".join(str(cell or "") for cell in row or [])
                        if row_text.strip():
                            table_lines.append(row_text.strip())
                joined = "\n".join([text, *table_lines]).strip()
                pages.append({"page_num": index, "text": joined, "has_text": len(joined) > 30})
            return pages, len(pdf.pages)
    except Exception as exc:
        raise ValueError(f"Unable to extract text with pdfplumber from '{pdf_path.name}': {exc}") from exc


def _extract_text(pdf_path: Path) -> tuple[list[dict], int]:
    try:
        return _extract_text_pdfplumber(pdf_path)
    except ImportError:
        return _extract_text_pypdf(pdf_path)


def _detect_heading(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    if len(first_line) > 80:
        return ""
    if re.match(r"^[0-9]+(\.[0-9]+)*\s+\w", first_line):
        return first_line
    if re.match(r"^(chapter|section|appendix)\s+", first_line, re.IGNORECASE):
        return first_line
    if first_line.isupper() and len(first_line.split()) < 10:
        return first_line
    return ""


def _chunk_pages(pages: list[dict], doc_meta: dict) -> list[dict]:
    junk_patterns = [
        r"^\d+$",
        r"^page \d+ of \d+$",
        r"^confidential$",
        r"^_{3,}$",
        r"^www\.\S+$",
    ]

    def is_junk(line: str) -> bool:
        stripped = line.strip()
        return any(re.match(pattern, stripped, re.IGNORECASE) for pattern in junk_patterns)

    chunks: list[dict] = []
    buffer = ""
    buffer_pages: list[int] = []
    current_section = ""

    def flush_buffer() -> None:
        nonlocal buffer, buffer_pages
        text = buffer.strip()
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append(
                {
                    "text": text,
                    "pages": sorted(set(buffer_pages)),
                    "section": current_section,
                    **doc_meta,
                }
            )
        buffer = ""
        buffer_pages = []

    for page in pages:
        if not page.get("has_text"):
            continue
        clean_lines = []
        for line in str(page.get("text", "")).splitlines():
            stripped = line.strip()
            if not stripped or is_junk(stripped):
                continue
            clean_lines.append(stripped)
        clean_text = "\n".join(clean_lines).strip()
        if not clean_text:
            continue

        heading = _detect_heading(clean_text)
        if heading and buffer:
            flush_buffer()
            current_section = heading

        buffer = f"{buffer}\n\n{clean_text}".strip() if buffer else clean_text
        buffer_pages.append(int(page.get("page_num", 0)))

        while len(buffer) > CHUNK_SIZE * 4:
            split_pos = CHUNK_SIZE * 3
            for separator in [". ", ".\n", "\n\n", "\n"]:
                pos = buffer.find(separator, split_pos)
                if 0 < pos < CHUNK_SIZE * 5:
                    split_pos = pos + len(separator)
                    break
            chunk_text = buffer[:split_pos].strip()
            if len(chunk_text) >= MIN_CHUNK_CHARS:
                chunks.append(
                    {
                        "text": chunk_text,
                        "pages": sorted(set(buffer_pages)) or [int(page.get("page_num", 0))],
                        "section": current_section,
                        **doc_meta,
                    }
                )
            overlap_start = max(0, split_pos - CHUNK_OVERLAP * 4)
            buffer = buffer[overlap_start:].strip()
            buffer_pages = [int(page.get("page_num", 0))]

    flush_buffer()
    return chunks


def _credibility_score(doc_type: str) -> float:
    return {
        "approved_topic": 0.95,
        "style_guide": 0.9,
        "terminology": 0.9,
        "api_reference": 0.85,
        "product_doc": 0.8,
        "user_manual": 0.75,
        "release_notes": 0.7,
        "other": 0.6,
    }.get(doc_type, 0.7)


async def index_pdf(
    pdf_path: str | Path,
    tenant_id: str,
    doc_type: str = "product_doc",
    label: str = "",
    force: bool = False,
    use_ocr: bool = False,
) -> IndexResult:
    from app.services.embedding_service import embed_texts, is_embedding_available
    from app.services.tenant_service import get_tenant
    from app.services.vector_store_service import add_documents, is_chroma_available

    pdf_path = Path(pdf_path)
    result = IndexResult(
        filename=pdf_path.name,
        tenant_id=tenant_id,
        doc_type=doc_type,
        label=label or pdf_path.stem.replace("_", " ").replace("-", " ").title(),
        indexed_at=datetime.utcnow().isoformat(),
    )
    del use_ocr

    if not pdf_path.exists():
        result.errors.append(f"File not found: {pdf_path}")
        return result
    if pdf_path.suffix.lower() != ".pdf":
        result.errors.append("File must be a PDF.")
        return result
    if doc_type not in DOC_TYPES:
        result.errors.append(f"Unsupported doc_type '{doc_type}'.")
        return result

    result.file_hash = _file_hash(pdf_path)
    if not force:
        existing = is_already_indexed(pdf_path, tenant_id)
        if existing:
            result.skipped = True
            result.skip_reason = (
                f"Already indexed on {existing.get('indexed_at', 'unknown date')} "
                f"({existing.get('chunks', 0)} chunks). Use force to re-index."
            )
            return result

    if not is_chroma_available():
        result.errors.append("ChromaDB is not available.")
        return result
    if not is_embedding_available():
        result.errors.append("Embedding model is not available.")
        return result

    pages, total_pages = _extract_text(pdf_path)
    result.pages_read = total_pages
    text_pages = [page for page in pages if page.get("has_text")]
    if not text_pages:
        result.errors.append("No extractable text found in the PDF.")
        return result

    config = get_tenant(tenant_id)
    result.collection = config.rag_collection
    doc_meta = {
        "source": "pdf_upload",
        "tenant_id": tenant_id,
        "doc_type": doc_type,
        "label": result.label,
        "filename": result.filename,
        "file_hash": result.file_hash,
        "indexed_at": result.indexed_at,
        "credibility": _credibility_score(doc_type),
    }
    chunks = _chunk_pages(text_pages, doc_meta)
    if not chunks:
        result.errors.append("No usable chunks found after processing the PDF.")
        return result

    texts = [chunk["text"] for chunk in chunks]
    embeddings_raw = embed_texts(texts)
    if embeddings_raw is None:
        result.errors.append("Failed to embed PDF chunks.")
        return result
    embeddings = embeddings_raw.tolist() if hasattr(embeddings_raw, "tolist") else list(embeddings_raw)

    ids = [f"{tenant_id}_{result.file_hash}_{index}" for index in range(len(chunks))]
    metadatas = []
    for chunk in chunks:
        metadatas.append(
            {
                "source": chunk.get("source", "pdf_upload"),
                "tenant_id": tenant_id,
                "doc_type": doc_type,
                "label": result.label,
                "filename": result.filename,
                "section": chunk.get("section", ""),
                "page": str((chunk.get("pages") or [0])[0]),
                "file_hash": result.file_hash,
                "indexed_at": result.indexed_at,
                "credibility": str(chunk.get("credibility", _credibility_score(doc_type))),
            }
        )

    success = add_documents(
        config.rag_collection,
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    if not success:
        result.errors.append("Failed to store chunks in ChromaDB.")
        return result

    result.chunk_ids = ids
    result.chunks_stored = len(ids)
    _mark_indexed(result)
    logger.info_structured(
        "Indexed tenant PDF",
        extra_fields={"tenant_id": tenant_id, "filename": result.filename, "chunks": result.chunks_stored},
    )
    return result


async def index_pdf_directory(
    directory: str | Path,
    tenant_id: str,
    doc_type: str = "product_doc",
    force: bool = False,
    use_ocr: bool = False,
) -> list[IndexResult]:
    directory = Path(directory)
    if not directory.exists():
        return [
            IndexResult(
                filename=str(directory),
                tenant_id=tenant_id,
                doc_type=doc_type,
                label=str(directory),
                errors=[f"Directory not found: {directory}"],
                indexed_at=datetime.utcnow().isoformat(),
            )
        ]

    results: list[IndexResult] = []
    for pdf_file in sorted({*directory.glob("*.pdf"), *directory.glob("**/*.pdf")}):
        results.append(
            await index_pdf(
                pdf_path=pdf_file,
                tenant_id=tenant_id,
                doc_type=doc_type,
                label=pdf_file.stem.replace("_", " ").replace("-", " ").title(),
                force=force,
                use_ocr=use_ocr,
            )
        )
    return results
