"""
PDF Documentation Index Routes

Endpoints for uploading and indexing client documentation PDFs.
Register in router.py:
  from app.api.v1.routes import doc_pdf
  api_router.include_router(doc_pdf.router, prefix="/docs", tags=["docs"])
"""
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "pdf_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/index-pdf")
async def upload_and_index_pdf(
    request:  Request,
    file:     UploadFile = File(...),
    doc_type: str        = Form("product_doc"),
    label:    str        = Form(""),
    force:    bool       = Form(False),
    use_ocr:  bool       = Form(False),
):
    """
    Upload a PDF and index it into the tenant's RAG collection.

    Form fields:
      file      — the PDF file
      doc_type  — style_guide | product_doc | approved_topic |
                  terminology | api_reference | release_notes | user_manual
      label     — human-readable name (defaults to filename)
      force     — re-index even if already indexed (default False)
      use_ocr   — try OCR for scanned pages (default False)

    Returns IndexResult dict.
    """
    try:
        from app.services.doc_pdf_index_service import index_pdf, DOC_TYPES
        from app.services.tenant_service import get_tenant_id_from_request

        tenant_id = get_tenant_id_from_request(request)

        # Validate file type
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            return {"error": "Only PDF files are accepted", "filename": file.filename}

        # Validate doc_type
        if doc_type not in DOC_TYPES:
            return {
                "error": f"Invalid doc_type '{doc_type}'",
                "valid_types": list(DOC_TYPES.keys()),
            }

        # Save upload to temp path
        tenant_upload_dir = UPLOAD_DIR / tenant_id
        tenant_upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = tenant_upload_dir / file.filename

        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        file_size_mb = save_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 100:
            save_path.unlink()
            return {"error": f"File too large ({file_size_mb:.1f}MB). Max 100MB."}

        # Index
        result = await index_pdf(
            pdf_path  = save_path,
            tenant_id = tenant_id,
            doc_type  = doc_type,
            label     = label or file.filename.replace(".pdf", "").replace("-", " ").replace("_", " ").title(),
            force     = force,
            use_ocr   = use_ocr,
        )

        return result.to_dict()

    except Exception as e:
        return {"error": str(e)}


@router.get("/indexed")
async def list_indexed(request: Request):
    """
    List all PDFs indexed for this tenant.
    Shows filename, doc_type, label, chunk count, indexed date.
    """
    try:
        from app.services.doc_pdf_index_service import list_indexed_docs
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        docs = list_indexed_docs(tenant_id)
        return {"tenant_id": tenant_id, "docs": docs, "count": len(docs)}
    except Exception as e:
        return {"error": str(e), "docs": []}


@router.delete("/indexed/{file_hash}")
async def remove_indexed(request: Request, file_hash: str):
    """Remove a document from the index by file hash."""
    try:
        from app.services.doc_pdf_index_service import remove_from_index
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        success   = remove_from_index(tenant_id, file_hash)
        return {"removed": success, "file_hash": file_hash}
    except Exception as e:
        return {"error": str(e)}


@router.post("/index-directory")
async def index_directory(request: Request, body: dict):
    """
    Index all PDFs in a server-side directory.
    Used for bulk onboarding — admin only.

    Body: { "directory": "/path/to/docs", "doc_type": "product_doc", "force": false }
    """
    try:
        from app.services.doc_pdf_index_service import index_pdf_directory
        from app.services.tenant_service import get_tenant_id_from_request
        tenant_id = get_tenant_id_from_request(request)
        directory = body.get("directory", "")
        if not directory:
            return {"error": "directory is required"}

        results = await index_pdf_directory(
            directory = directory,
            tenant_id = tenant_id,
            doc_type  = body.get("doc_type", "product_doc"),
            force     = body.get("force", False),
            use_ocr   = body.get("use_ocr", False),
        )
        return {
            "results":  [r.to_dict() for r in results],
            "indexed":  sum(1 for r in results if r.chunks_stored > 0),
            "skipped":  sum(1 for r in results if r.skipped),
            "errors":   sum(1 for r in results if r.errors and not r.skipped),
        }
    except Exception as e:
        return {"error": str(e)}
