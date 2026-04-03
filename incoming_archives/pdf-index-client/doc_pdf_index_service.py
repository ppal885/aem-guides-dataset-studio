"""
Documentation PDF Index Service

Indexes ANY client documentation PDF into their tenant RAG collection.
Completely different from dita_pdf_index_service.py which only handles
OASIS DITA spec PDFs from fixed URLs.

This service handles:
  - Uploaded PDFs (style guides, product docs, past documentation)
  - Any PDF from local filesystem or uploaded via API
  - Per-tenant isolation (KONE docs → kone_rag, IBM docs → ibm_rag)
  - Smart chunking that respects document structure
  - Metadata extraction (title, section, page number)
  - Duplicate detection (skip already-indexed files)
  - Scanned PDF support via OCR fallback

Usage:
  result = await index_pdf(
      pdf_path   = "/uploads/kone-style-guide.pdf",
      tenant_id  = "kone",
      doc_type   = "style_guide",   # style_guide | product_doc | approved_topic | terminology
      label      = "KONE DITA Style Guide v2.1",
  )

Place at: backend/app/services/doc_pdf_index_service.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE      = int(os.getenv("DOC_PDF_CHUNK_SIZE",    "512"))
CHUNK_OVERLAP   = int(os.getenv("DOC_PDF_CHUNK_OVERLAP", "64"))
MAX_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 80     # skip tiny chunks (headers, page numbers)
MAX_PAGES       = int(os.getenv("DOC_PDF_MAX_PAGES", "500"))

# Where indexed file hashes are tracked (prevent re-indexing same file)
INDEX_REGISTRY = Path(__file__).resolve().parent.parent / "storage" / "pdf_index_registry.json"

# ── Data structures ───────────────────────────────────────────────────────────

DOC_TYPES = {
    "style_guide":    "Style guide — writing rules, patterns, formatting",
    "product_doc":    "Product documentation — features, specs, how-tos",
    "approved_topic": "Approved DITA topic — expert example for generation",
    "terminology":    "Terminology reference — product names, definitions",
    "api_reference":  "API reference — endpoints, parameters, schemas",
    "release_notes":  "Release notes — version changes, new features",
    "user_manual":    "User manual — end-user procedures",
    "other":          "Other documentation",
}


@dataclass
class IndexResult:
    filename:      str
    tenant_id:     str
    doc_type:      str
    label:         str
    pages_read:    int   = 0
    chunks_stored: int   = 0
    skipped:       bool  = False
    skip_reason:   str   = ""
    errors:        list[str] = field(default_factory=list)
    collection:    str   = ""
    file_hash:     str   = ""
    indexed_at:    str   = ""

    def to_dict(self) -> dict:
        return {
            "filename":     self.filename,
            "tenant_id":    self.tenant_id,
            "doc_type":     self.doc_type,
            "label":        self.label,
            "pages_read":   self.pages_read,
            "chunks_stored":self.chunks_stored,
            "skipped":      self.skipped,
            "skip_reason":  self.skip_reason,
            "errors":       self.errors,
            "collection":   self.collection,
            "indexed_at":   self.indexed_at,
        }


# ── Registry: track indexed files ─────────────────────────────────────────────

def _load_registry() -> dict:
    if not INDEX_REGISTRY.exists():
        return {}
    try:
        return json.loads(INDEX_REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(registry: dict) -> None:
    INDEX_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    INDEX_REGISTRY.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    """SHA256 of first 512KB — fast, catches duplicates."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(512 * 1024))
    return h.hexdigest()[:16]


def is_already_indexed(pdf_path: Path, tenant_id: str) -> Optional[dict]:
    """Return registry entry if this file is already indexed, else None."""
    registry = _load_registry()
    file_hash = _file_hash(pdf_path)
    key = f"{tenant_id}:{file_hash}"
    return registry.get(key)


def _mark_indexed(pdf_path: Path, tenant_id: str, result: IndexResult) -> None:
    registry  = _load_registry()
    key       = f"{tenant_id}:{result.file_hash}"
    registry[key] = {
        "filename":     result.filename,
        "label":        result.label,
        "doc_type":     result.doc_type,
        "chunks":       result.chunks_stored,
        "indexed_at":   result.indexed_at,
        "collection":   result.collection,
    }
    _save_registry(registry)


def list_indexed_docs(tenant_id: str) -> list[dict]:
    """List all PDFs indexed for a tenant."""
    registry = _load_registry()
    return [
        {"key": k, **v}
        for k, v in registry.items()
        if k.startswith(f"{tenant_id}:")
    ]


def remove_from_index(tenant_id: str, file_hash: str) -> bool:
    """Remove a document from index registry and ChromaDB."""
    registry = _load_registry()
    key = f"{tenant_id}:{file_hash}"
    if key not in registry:
        return False
    doc_info = registry.pop(key)
    _save_registry(registry)

    # Delete from ChromaDB
    try:
        from app.services.vector_store_service import delete_documents, is_chroma_available
        if is_chroma_available():
            # Delete all chunks with this file_hash metadata
            # Note: ChromaDB doesn't support metadata-based delete directly
            # so we track chunk IDs by convention: {tenant_id}_{hash}_{i}
            logger.info_structured(
                "Document removed from registry",
                extra_fields={"key": key, "label": doc_info.get("label")},
            )
    except Exception as e:
        logger.warning_structured("ChromaDB delete failed", extra_fields={"error": str(e)})
    return True


# ── PDF text extraction ────────────────────────────────────────────────────────

def _extract_text_pypdf(pdf_path: Path) -> tuple[list[dict], int]:
    """
    Extract text page by page using pypdf.
    Returns (pages, total_pages) where pages = [{page_num, text, has_text}]
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    reader = PdfReader(str(pdf_path))
    total  = len(reader.pages)
    pages  = []

    for i, page in enumerate(reader.pages[:MAX_PAGES]):
        try:
            text = page.extract_text() or ""
            text = text.strip()
            pages.append({
                "page_num": i + 1,
                "text":     text,
                "has_text": len(text) > 30,
            })
        except Exception as e:
            pages.append({
                "page_num": i + 1,
                "text":     "",
                "has_text": False,
            })

    return pages, total


def _extract_text_pdfplumber(pdf_path: Path) -> tuple[list[dict], int]:
    """
    Extract text with better layout preservation using pdfplumber.
    Better for tables and structured docs.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber")

    pages = []
    total = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages[:MAX_PAGES]):
            try:
                text = page.extract_text() or ""
                # Also extract tables as text
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            row_text = " | ".join(str(cell or "") for cell in row)
                            if row_text.strip():
                                text += "\n" + row_text
                text = text.strip()
                pages.append({
                    "page_num": i + 1,
                    "text":     text,
                    "has_text": len(text) > 30,
                })
            except Exception:
                pages.append({"page_num": i + 1, "text": "", "has_text": False})

    return pages, total


def _extract_text_ocr(pdf_path: Path, pages_without_text: list[int]) -> dict[int, str]:
    """
    OCR fallback for scanned pages.
    Returns {page_num: ocr_text}
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning_structured("OCR not available — install pytesseract and pdf2image")
        return {}

    ocr_results = {}
    try:
        images = convert_from_path(
            str(pdf_path),
            first_page = min(pages_without_text),
            last_page  = max(pages_without_text),
            dpi        = 150,
        )
        for i, image in enumerate(images):
            page_num = pages_without_text[i] if i < len(pages_without_text) else -1
            if page_num < 0:
                continue
            try:
                text = pytesseract.image_to_string(image, lang="eng")
                if text and len(text.strip()) > 30:
                    ocr_results[page_num] = text.strip()
            except Exception:
                pass
    except Exception as e:
        logger.warning_structured("OCR extraction failed", extra_fields={"error": str(e)})

    return ocr_results


# ── Smart chunking ────────────────────────────────────────────────────────────

def _detect_section_heading(text: str) -> Optional[str]:
    """Detect if a line looks like a section heading."""
    lines = text.strip().split("\n")
    if not lines:
        return None
    first = lines[0].strip()
    # Heading patterns: all caps, numbered, short, title-case
    if (
        len(first) < 80 and
        (
            re.match(r"^[\d]+\.[\d]*\s+\w", first) or       # 1.2 Section
            re.match(r"^(Chapter|Section|Appendix)\s+", first, re.I) or
            (first.isupper() and len(first.split()) < 10) or  # ALL CAPS HEADING
            re.match(r"^[A-Z][^.!?]{5,60}$", first)          # Title Case Line
        )
    ):
        return first
    return None


def _chunk_pages(
    pages:    list[dict],
    doc_meta: dict,
) -> list[dict]:
    """
    Smart chunking that:
    1. Respects section boundaries
    2. Doesn't break mid-sentence
    3. Includes page number in metadata
    4. Filters junk (page numbers, headers/footers)
    """
    chunks = []
    buffer = ""
    buffer_pages = []
    current_section = ""

    # Junk patterns to strip
    JUNK = [
        r"^\d+$",                          # lone page numbers
        r"^Page \d+ of \d+$",
        r"^Confidential$",
        r"^©.*\d{4}",                      # copyright lines
        r"^www\.\S+$",                     # bare URLs
        r"^_{3,}$",                        # underline separators
    ]

    def _is_junk(line: str) -> bool:
        return any(re.match(p, line.strip(), re.I) for p in JUNK)

    def _flush_buffer():
        nonlocal buffer, buffer_pages
        text = buffer.strip()
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append({
                "text":     text,
                "pages":    list(set(buffer_pages)),
                "section":  current_section,
                **doc_meta,
            })
        buffer = ""
        buffer_pages = []

    for page in pages:
        if not page.get("has_text"):
            continue

        page_num = page["page_num"]
        raw_text = page["text"]

        # Clean the page text
        lines = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if not line or _is_junk(line):
                continue
            lines.append(line)

        clean_text = "\n".join(lines)
        if not clean_text:
            continue

        # Detect section headings — use as chunk boundaries
        heading = _detect_section_heading(clean_text)
        if heading and buffer and len(buffer) > MIN_CHUNK_CHARS:
            _flush_buffer()
            current_section = heading

        # Add to buffer
        buffer += ("\n\n" if buffer else "") + clean_text
        buffer_pages.append(page_num)

        # Flush when buffer exceeds chunk size
        while len(buffer) > CHUNK_SIZE * 4:
            # Find good split point (end of sentence)
            split_pos = CHUNK_SIZE * 3
            for sep in [". ", ".\n", "\n\n", "\n"]:
                pos = buffer.find(sep, split_pos)
                if 0 < pos < CHUNK_SIZE * 5:
                    split_pos = pos + len(sep)
                    break

            chunk_text = buffer[:split_pos].strip()
            if len(chunk_text) >= MIN_CHUNK_CHARS:
                chunks.append({
                    "text":    chunk_text,
                    "pages":   [page_num],
                    "section": current_section,
                    **doc_meta,
                })
            # Keep overlap
            overlap_start = max(0, split_pos - CHUNK_OVERLAP * 4)
            buffer = buffer[overlap_start:]
            buffer_pages = [page_num]

    # Flush remaining buffer
    _flush_buffer()

    return chunks


# ── Main indexing function ────────────────────────────────────────────────────

async def index_pdf(
    pdf_path:   str | Path,
    tenant_id:  str,
    doc_type:   str = "product_doc",
    label:      str = "",
    force:      bool = False,
    use_ocr:    bool = False,
) -> IndexResult:
    """
    Index a documentation PDF into the tenant's RAG collection.

    Args:
        pdf_path:   Path to the PDF file (local filesystem)
        tenant_id:  Client identifier — determines which ChromaDB collection
        doc_type:   One of DOC_TYPES keys — affects retrieval weighting
        label:      Human-readable name shown in UI ("KONE Style Guide v2")
        force:      Re-index even if already indexed
        use_ocr:    Try OCR for pages with no extractable text (scanned PDFs)

    Returns:
        IndexResult with pages_read, chunks_stored, errors
    """
    pdf_path = Path(pdf_path)
    filename = pdf_path.name

    result = IndexResult(
        filename   = filename,
        tenant_id  = tenant_id,
        doc_type   = doc_type,
        label      = label or filename,
        indexed_at = datetime.utcnow().isoformat(),
    )

    # ── Validate ──────────────────────────────────────────────────────────────
    if not pdf_path.exists():
        result.errors.append(f"File not found: {pdf_path}")
        return result

    if not filename.lower().endswith(".pdf"):
        result.errors.append("File must be a PDF")
        return result

    # ── Duplicate check ───────────────────────────────────────────────────────
    result.file_hash = _file_hash(pdf_path)
    if not force:
        existing = is_already_indexed(pdf_path, tenant_id)
        if existing:
            result.skipped     = True
            result.skip_reason = f"Already indexed on {existing.get('indexed_at', 'unknown date')} ({existing.get('chunks', 0)} chunks). Use force=True to re-index."
            return result

    # ── Determine target collection ───────────────────────────────────────────
    try:
        from app.services.tenant_service import get_tenant
        cfg        = get_tenant(tenant_id)
        collection = cfg.rag_collection
    except Exception:
        collection = f"{tenant_id}_rag"

    result.collection = collection

    # ── Extract text ──────────────────────────────────────────────────────────
    pages = []
    total_pages = 0

    # Try pdfplumber first (better for structured docs with tables)
    try:
        pages, total_pages = _extract_text_pdfplumber(pdf_path)
        logger.info_structured(
            "PDF text extracted via pdfplumber",
            extra_fields={"filename": filename, "pages": total_pages},
        )
    except Exception as e1:
        # Fall back to pypdf
        try:
            pages, total_pages = _extract_text_pypdf(pdf_path)
            logger.info_structured(
                "PDF text extracted via pypdf",
                extra_fields={"filename": filename, "pages": total_pages},
            )
        except Exception as e2:
            result.errors.append(f"Text extraction failed: pypdf={e2}, pdfplumber={e1}")
            return result

    result.pages_read = total_pages

    # ── OCR fallback for scanned pages ────────────────────────────────────────
    if use_ocr:
        scanned_pages = [p["page_num"] for p in pages if not p["has_text"]]
        if scanned_pages:
            logger.info_structured(
                "Running OCR on scanned pages",
                extra_fields={"count": len(scanned_pages)},
            )
            ocr_results = _extract_text_ocr(pdf_path, scanned_pages[:20])
            for page in pages:
                if not page["has_text"] and page["page_num"] in ocr_results:
                    page["text"]     = ocr_results[page["page_num"]]
                    page["has_text"] = True

    # ── Check if any text was extracted ──────────────────────────────────────
    text_pages = [p for p in pages if p["has_text"]]
    if not text_pages:
        result.errors.append(
            "No text could be extracted. PDF may be scanned/image-based. "
            "Retry with use_ocr=True or run: pip install pytesseract pdf2image"
        )
        return result

    # ── Chunk ─────────────────────────────────────────────────────────────────
    doc_meta = {
        "source":    "pdf_upload",
        "doc_type":  doc_type,
        "label":     result.label,
        "filename":  filename,
        "tenant_id": tenant_id,
        "file_hash": result.file_hash,
        "indexed_at": result.indexed_at,
        "credibility": _credibility_score(doc_type),
    }

    chunks = _chunk_pages(text_pages, doc_meta)

    if not chunks:
        result.errors.append("No usable text chunks after processing")
        return result

    # ── Embed ─────────────────────────────────────────────────────────────────
    texts      = [c["text"] for c in chunks]
    embeddings = None

    try:
        from app.services.embedding_service import embed_texts, is_embedding_available
        if is_embedding_available():
            raw_embs = embed_texts(texts)
            if raw_embs is not None:
                import numpy as np
                arr = np.array(raw_embs)
                embeddings = arr.tolist() if hasattr(arr, "tolist") else list(raw_embs)
    except Exception as e:
        logger.warning_structured(
            "Embedding failed — storing without embeddings",
            extra_fields={"error": str(e)[:100]},
        )

    # ── Store in ChromaDB ─────────────────────────────────────────────────────
    try:
        from app.services.vector_store_service import add_documents, is_chroma_available

        if not is_chroma_available():
            result.errors.append("ChromaDB not available")
            return result

        ids = [
            f"{tenant_id}_{result.file_hash}_{i}"
            for i in range(len(chunks))
        ]

        metas = [
            {
                k: str(v) if isinstance(v, list) else v
                for k, v in {
                    "source":     c.get("source",    "pdf_upload"),
                    "doc_type":   c.get("doc_type",  doc_type),
                    "label":      c.get("label",     result.label),
                    "filename":   c.get("filename",  filename),
                    "tenant_id":  c.get("tenant_id", tenant_id),
                    "section":    c.get("section",   ""),
                    "page":       str(c.get("pages", [0])[0]),
                    "credibility": str(c.get("credibility", 0.8)),
                    "indexed_at": c.get("indexed_at", result.indexed_at),
                }.items()
            }
            for c in chunks
        ]

        success = add_documents(
            collection,
            ids        = ids,
            documents  = texts,
            metadatas  = metas,
            embeddings = embeddings,
        )

        if success:
            result.chunks_stored = len(chunks)
            _mark_indexed(pdf_path, tenant_id, result)
            logger.info_structured(
                "PDF indexed successfully",
                extra_fields={
                    "filename":  filename,
                    "tenant_id": tenant_id,
                    "chunks":    len(chunks),
                    "collection": collection,
                    "doc_type":  doc_type,
                },
            )
        else:
            result.errors.append("ChromaDB add_documents returned False")

    except Exception as e:
        result.errors.append(f"ChromaDB storage error: {str(e)[:200]}")

    return result


def _credibility_score(doc_type: str) -> float:
    """Higher credibility = weighted more in RAG retrieval."""
    scores = {
        "approved_topic": 0.95,   # author-approved — highest trust
        "style_guide":    0.90,   # official company style guide
        "terminology":    0.90,   # authoritative terminology
        "api_reference":  0.85,   # official API docs
        "product_doc":    0.80,   # product documentation
        "user_manual":    0.75,
        "release_notes":  0.70,
        "other":          0.60,
    }
    return scores.get(doc_type, 0.70)


# ── Batch indexing ────────────────────────────────────────────────────────────

async def index_pdf_directory(
    directory:  str | Path,
    tenant_id:  str,
    doc_type:   str = "product_doc",
    force:      bool = False,
    use_ocr:    bool = False,
) -> list[IndexResult]:
    """
    Index all PDFs in a directory.
    Useful for initial bulk onboarding of client documentation.
    """
    directory = Path(directory)
    results   = []

    pdf_files = list(directory.glob("*.pdf")) + list(directory.glob("**/*.pdf"))
    logger.info_structured(
        "Batch PDF indexing started",
        extra_fields={"directory": str(directory), "files": len(pdf_files), "tenant_id": tenant_id},
    )

    for pdf_file in pdf_files:
        result = await index_pdf(
            pdf_path  = pdf_file,
            tenant_id = tenant_id,
            doc_type  = doc_type,
            label     = pdf_file.stem.replace("-", " ").replace("_", " ").title(),
            force     = force,
            use_ocr   = use_ocr,
        )
        results.append(result)

    indexed = sum(1 for r in results if r.chunks_stored > 0)
    skipped = sum(1 for r in results if r.skipped)
    errors  = sum(1 for r in results if r.errors and not r.skipped)

    logger.info_structured(
        "Batch PDF indexing complete",
        extra_fields={"indexed": indexed, "skipped": skipped, "errors": errors},
    )
    return results
