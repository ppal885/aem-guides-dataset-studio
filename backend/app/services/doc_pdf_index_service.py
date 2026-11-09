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
    """Content hash of the whole file.

    Hashing only a prefix made two PDFs with the same front matter share one identity, so the
    second was reported as already indexed or overwrote the first one's chunks.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()[:24]


def list_indexed_docs(tenant_id: str) -> list[dict]:
    registry = _load_registry()
    docs = [value for key, value in registry.items() if key.startswith(f"{tenant_id}:")]
    return sorted(docs, key=lambda item: item.get("indexed_at", ""), reverse=True)


def _legacy_file_hash(path: Path) -> str:
    """The pre-change identity (first 512 KB, 16 hex chars), so existing registry entries still resolve."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(512 * 1024))
    return digest.hexdigest()[:16]


def is_already_indexed(pdf_path: Path, tenant_id: str) -> dict | None:
    registry = _load_registry()
    return registry.get(f"{tenant_id}:{_file_hash(pdf_path)}") or registry.get(
        f"{tenant_id}:{_legacy_file_hash(pdf_path)}"
    )


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


def _table_lines_missing_from_text(text: str, tables: list) -> list[str]:
    """Pipe-joined table rows that ``extract_text()`` did not already produce as a complete line.

    pdfplumber's page text usually renders a table row as one line with the cells in order, so
    appending every row again duplicated table content. A row is suppressed only when a line of
    the page text is exactly that row — the same cells, in the same order, with nothing else.
    Matching each cell as a substring anywhere on the page would drop real data, e.g. the row
    ``timeout | 10`` on a page that only says ``timeout 100``.
    """
    page_lines = {" ".join(line.split()).casefold() for line in text.splitlines() if line.strip()}
    lines: list[str] = []
    for table in tables:
        for row in table or []:
            cells = [" ".join(str(cell or "").split()) for cell in row or []]
            filled = [cell for cell in cells if cell]
            if not filled:
                continue
            if " ".join(filled).casefold() in page_lines:
                continue
            lines.append(" | ".join(cells).strip())
    return lines


def _extract_text_pdfplumber(pdf_path: Path) -> tuple[list[dict], int]:
    import pdfplumber

    pages: list[dict] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for index, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                text = (page.extract_text() or "").strip()
                table_lines = _table_lines_missing_from_text(text, page.extract_tables() or [])
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


_NUMBERED_HEADING_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)+\.?\s+\S|^[0-9]+\.?\s+[A-Z][^.!?]*$")


def _is_heading_line(line: str) -> bool:
    """Conservative heading test for a single line, usable anywhere on a page.

    Accepts numbered section titles ("2.3 Configure output", "4 Publishing"), "Chapter/Section/
    Appendix ..." and short all-caps lines. Rejects sentences (trailing punctuation) and long lines,
    so numbered steps such as "1. Click Save." or "10 items were found." do not open a section.
    """
    line = line.strip()
    if not line or len(line) > 80 or line.endswith((".", ",", ";", ":")):
        return False
    if len(line.split()) > 12:
        return False
    if _NUMBERED_HEADING_RE.match(line):
        return True
    if re.match(r"^(chapter|section|appendix)\s+\S", line, re.IGNORECASE):
        return True
    letters = [ch for ch in line if ch.isalpha()]
    return len(letters) >= 3 and line.isupper() and len(line.split()) < 10


def _detect_heading(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line if _is_heading_line(first_line) else ""


def _effective_overlap_chars(split_pos: int) -> int:
    """Overlap carried into the next chunk, clamped so every split shrinks the buffer.

    ``DOC_PDF_CHUNK_OVERLAP`` large relative to ``DOC_PDF_CHUNK_SIZE`` used to keep the whole
    buffer and loop forever.
    """
    return max(0, min(CHUNK_OVERLAP * 4, split_pos // 2))


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
    # The buffer is text plus spans [(start, end, page_num)] recording which page each character
    # came from, so every chunk carries exactly the pages its own text came from.
    buffer = ""
    spans: list[tuple[int, int, int]] = []
    current_section = ""

    def pages_in(lo: int, hi: int) -> list[int]:
        return sorted({page for start, end, page in spans if start < hi and end > lo})

    def emit(text: str, chunk_pages: list[int], section: str) -> None:
        chunks.append({"text": text, "pages": chunk_pages, "section": section, **doc_meta})

    def append_text(text: str, page_num: int) -> None:
        nonlocal buffer
        if buffer:
            buffer += "\n\n"
        spans.append((len(buffer), len(buffer) + len(text), page_num))
        buffer += text

    def flush_buffer(*, final: bool = False) -> None:
        nonlocal buffer, spans
        text = buffer.strip()
        if not text:
            buffer, spans = "", []
            return
        chunk_pages = pages_in(0, len(buffer))
        if len(text) >= MIN_CHUNK_CHARS:
            emit(text, chunk_pages, current_section)
        elif chunks and (final or chunks[-1]["section"] == current_section):
            # Too short to stand alone: keep it with the previous chunk instead of dropping it.
            previous = chunks[-1]
            previous["text"] = f"{previous['text']}\n\n{text}"
            previous["pages"] = sorted(set(previous["pages"]) | set(chunk_pages))
        elif final:
            emit(text, chunk_pages, current_section)
        else:
            return  # carry the short text into the next section's buffer
        buffer, spans = "", []

    def split_oversized() -> None:
        nonlocal buffer, spans
        while len(buffer) > CHUNK_SIZE * 4:
            split_pos = CHUNK_SIZE * 3
            found_separator = False
            for separator in [". ", ".\n", "\n\n", "\n"]:
                pos = buffer.find(separator, split_pos)
                if 0 < pos < CHUNK_SIZE * 5:
                    split_pos = pos + len(separator)
                    found_separator = True
                    break
            if not found_separator:
                # No sentence or line break near the target: cut at the last whitespace before it
                # rather than in the middle of a word.
                space = buffer.rfind(" ", CHUNK_SIZE * 2, split_pos)
                if space > 0:
                    split_pos = space + 1
            chunk_text = buffer[:split_pos].strip()
            if len(chunk_text) >= MIN_CHUNK_CHARS:
                emit(chunk_text, pages_in(0, split_pos), current_section)
            overlap_start = split_pos - _effective_overlap_chars(split_pos)
            rest = buffer[overlap_start:]
            lead = len(rest) - len(rest.lstrip())
            cut = overlap_start + lead
            buffer = buffer[cut:].rstrip()
            spans = [
                (max(start, cut) - cut, end - cut, page)
                for start, end, page in spans
                if end > cut
            ]

    for page in pages:
        if not page.get("has_text"):
            continue
        page_num = int(page.get("page_num", 0))
        clean_lines = [
            line.strip()
            for line in str(page.get("text", "")).splitlines()
            if line.strip() and not is_junk(line)
        ]
        if not clean_lines:
            continue
        # Headings are detected on every line, not only a page's first line, so a section that
        # starts mid-page is labelled correctly.
        block: list[str] = []
        for line in clean_lines:
            if _is_heading_line(line):
                if block:
                    append_text("\n".join(block), page_num)
                    split_oversized()
                    block = []
                flush_buffer()
                current_section = line
            block.append(line)
        if block:
            append_text("\n".join(block), page_num)
            split_oversized()

    flush_buffer(final=True)
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
                "pages": json.dumps(chunk.get("pages") or []),
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
