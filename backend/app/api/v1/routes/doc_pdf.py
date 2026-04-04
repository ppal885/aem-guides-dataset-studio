import os
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.api.v1.routes._api_errors import raise_api_error
from app.core.auth import CurrentUser, UserIdentity
from app.storage import get_storage

router = APIRouter()

UPLOAD_DIR = get_storage().base_path / "pdf_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str, fallback: str = "upload.pdf") -> str:
    candidate = Path(filename or fallback).name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    if not sanitized.lower().endswith(".pdf"):
        sanitized = f"{sanitized or Path(fallback).stem}.pdf"
    return sanitized


def _allowed_index_directories() -> list[Path]:
    configured = [
        Path(item.strip()).expanduser().resolve()
        for item in (os.getenv("PDF_INDEX_ALLOWED_DIRECTORIES") or "").split(os.pathsep)
        if item.strip()
    ]
    return [UPLOAD_DIR.resolve(), *configured]


def _validate_index_directory(directory: str) -> Path:
    candidate = Path(directory).expanduser().resolve()
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError("directory does not exist or is not a directory")
    for allowed_dir in _allowed_index_directories():
        try:
            candidate.relative_to(allowed_dir)
            return candidate
        except ValueError:
            continue
    raise ValueError("directory is outside the configured PDF indexing allowlist")


@router.post("/index-pdf")
async def upload_and_index_pdf(
    request: Request,
    user: UserIdentity = CurrentUser,
    file: UploadFile = File(...),
    doc_type: str = Form("product_doc"),
    label: str = Form(""),
    force: bool = Form(False),
    use_ocr: bool = Form(False),
):
    try:
        from app.services.doc_pdf_index_service import DOC_TYPES, index_pdf
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are accepted")
        if doc_type not in DOC_TYPES:
            raise ValueError(f"Invalid doc_type '{doc_type}'")

        tenant_upload_dir = UPLOAD_DIR / tenant_id
        tenant_upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = tenant_upload_dir / _safe_filename(file.filename)
        with save_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        file_size_mb = save_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 100:
            save_path.unlink(missing_ok=True)
            raise ValueError(f"File too large ({file_size_mb:.1f}MB). Max 100MB")

        result = await index_pdf(
            pdf_path=save_path,
            tenant_id=tenant_id,
            doc_type=doc_type,
            label=label or file.filename.replace(".pdf", "").replace("-", " ").replace("_", " ").title(),
            force=force,
            use_ocr=use_ocr,
        )
        return result.to_dict()
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to upload and index PDF")


@router.get("/indexed")
async def list_indexed_docs_route(request: Request, user: UserIdentity = CurrentUser):
    try:
        from app.services.doc_pdf_index_service import list_indexed_docs
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        docs = list_indexed_docs(tenant_id)
        return {"tenant_id": tenant_id, "docs": docs, "count": len(docs)}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to list indexed PDFs")


@router.delete("/indexed/{file_hash}")
async def remove_indexed_doc_route(request: Request, file_hash: str, user: UserIdentity = CurrentUser):
    try:
        from app.services.doc_pdf_index_service import remove_from_index
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        success = remove_from_index(tenant_id, file_hash)
        return {"removed": success, "file_hash": file_hash}
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to remove indexed PDF")


@router.post("/index-directory")
async def index_directory_route(request: Request, body: dict, user: UserIdentity = CurrentUser):
    try:
        from app.services.doc_pdf_index_service import index_pdf_directory
        from app.services.tenant_service import get_authorized_tenant_id

        tenant_id = get_authorized_tenant_id(request, user)
        directory = body.get("directory", "")
        if not directory:
            raise ValueError("directory is required")
        safe_directory = _validate_index_directory(directory)
        results = await index_pdf_directory(
            directory=safe_directory,
            tenant_id=tenant_id,
            doc_type=body.get("doc_type", "product_doc"),
            force=body.get("force", False),
            use_ocr=body.get("use_ocr", False),
        )
        return {
            "results": [result.to_dict() for result in results],
            "indexed": sum(1 for result in results if result.chunks_stored > 0),
            "skipped": sum(1 for result in results if result.skipped),
            "errors": sum(1 for result in results if result.errors and not result.skipped),
        }
    except Exception as exc:
        raise_api_error(exc, default_detail="Failed to index PDF directory")
