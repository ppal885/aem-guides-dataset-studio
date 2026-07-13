from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from app.core.auth import UserIdentity, CurrentUser
from app.core.structured_logging import get_structured_logger
from app.db.session import Session, db_session
from app.jobs import crud
from app.storage import get_storage
from app.services.dataset_job_service import resolve_dataset_storage_job_id
from app.utils.http_headers import content_disposition
import zipfile
from io import BytesIO
from typing import Optional

router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = get_structured_logger(__name__)


def _dataset_not_found_response(job) -> HTTPException:
    if job.status in ("pending", "running"):
        return HTTPException(
            status_code=409,
            detail="Job is still running. Wait for generation to complete before downloading.",
        )
    if job.status == "failed":
        message = (job.error_message or "Generation did not complete.").strip()
        return HTTPException(status_code=404, detail=f"Job failed: {message}")
    return HTTPException(
        status_code=404,
        detail="Dataset not found. Please ensure the job has completed successfully.",
    )


@router.get("/{job_id}/download")
def download_dataset(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Download dataset as ZIP file."""
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    storage = get_storage()
    storage_job_id = resolve_dataset_storage_job_id(job_id, job=job, storage=storage)
    storage_path = str(storage.get_job_path(storage_job_id or job_id))
    download_name = f"{job.name or job_id}.zip"
    disposition = content_disposition(download_name)

    if not storage_job_id:
        logger.warning_structured(
            "Download requested but dataset not found",
            extra_fields={"job_id": job_id, "storage_path": storage_path, "job_status": job.status},
        )
        raise _dataset_not_found_response(job)

    try:
        zip_buffer = storage.get_dataset_zip(storage_job_id)

        if zip_buffer:
            zip_buffer.seek(0)
            zip_content = zip_buffer.getvalue()
            zip_size = len(zip_content)

            if zip_size == 0:
                logger.warning_structured(
                    "Download requested but zip file is empty",
                    extra_fields={"job_id": job_id},
                )
                raise HTTPException(status_code=404, detail="Dataset zip file is empty")

            logger.info_structured(
                "Serving dataset download (in-memory)",
                extra_fields={
                    "job_id": job_id,
                    "zip_size": zip_size,
                    "filename": download_name,
                },
            )

            zip_buffer.seek(0)

            def generate():
                chunk_size = 8192 * 4
                while True:
                    chunk = zip_buffer.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

            return StreamingResponse(
                generate(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": disposition,
                    "Content-Length": str(zip_size),
                },
            )

        logger.info_structured(
            "Serving dataset download (streaming)",
            extra_fields={"job_id": job_id, "filename": download_name},
        )

        zip_generator = storage.get_dataset_zip_stream(storage_job_id)
        if not zip_generator:
            raise HTTPException(status_code=404, detail="Dataset zip file could not be created")

        return StreamingResponse(
            zip_generator,
            media_type="application/zip",
            headers={"Content-Disposition": disposition},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error_structured(
            "Error creating download response",
            extra_fields={
                "job_id": job_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to prepare download: {str(e)}")

@router.get("/{job_id}/structure")
def get_dataset_structure(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get the structure of a generated dataset."""
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check permissions
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get dataset file
    storage = get_storage()
    storage_job_id = resolve_dataset_storage_job_id(job_id, job=job, storage=storage)
    if not storage_job_id:
        raise _dataset_not_found_response(job)

    structure = storage.get_dataset_structure(storage_job_id)
    if not structure:
        raise HTTPException(status_code=404, detail="Dataset structure could not be loaded")
    
    return {
        "job_id": job_id,
        "job_name": job.name,
        "structure": structure,
        "manifest": job.result.get("manifest") if job.result and isinstance(job.result, dict) else None,
    }

@router.get("/{job_id}/file")
def get_dataset_file(
    job_id: str,
    file_path: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get a specific file from a dataset."""
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get dataset file
    storage = get_storage()
    storage_job_id = resolve_dataset_storage_job_id(job_id, job=job, storage=storage)
    if not storage_job_id:
        raise _dataset_not_found_response(job)

    file_content = storage.get_file(storage_job_id, file_path)
    if file_content is None:
        zip_bytes = storage.get_dataset_zip(storage_job_id)
        if not zip_bytes:
            raise HTTPException(status_code=404, detail="Dataset not found")
        file_content = _extract_file(
            zip_bytes.getvalue() if hasattr(zip_bytes, "getvalue") else zip_bytes,
            file_path,
        )
    if file_content is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine content type
    content_type = "text/plain"
    if file_path.endswith(".xml") or file_path.endswith(".dita") or file_path.endswith(".ditamap"):
        content_type = "application/xml"
    elif file_path.endswith(".json"):
        content_type = "application/json"
    
    return StreamingResponse(
        BytesIO(file_content),
        media_type=content_type,
        headers={
            "Content-Disposition": content_disposition(
                file_path.split("/")[-1],
                disposition="inline",
            )
        },
    )

@router.get("/{job_id}/search")
def search_dataset(
    job_id: str,
    query: str,
    file_type: Optional[str] = None,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Search within a dataset."""
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get dataset file
    storage = get_storage()
    storage_job_id = resolve_dataset_storage_job_id(job_id, job=job, storage=storage)
    if not storage_job_id:
        raise _dataset_not_found_response(job)

    results = _search_files_filesystem(storage, storage_job_id, query, file_type)
    
    return {
        "job_id": job_id,
        "query": query,
        "results": results,
        "count": len(results),
    }

def _extract_structure(zip_bytes: bytes) -> dict:
    """Extract directory structure from ZIP file."""
    structure = {
        "files": [],
        "directories": [],
    }
    
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_file:
        for name in zip_file.namelist():
            if name.endswith('/'):
                structure["directories"].append(name.rstrip('/'))
            else:
                info = zip_file.getinfo(name)
                structure["files"].append({
                    "path": name,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                })
    
    return structure

def _extract_file(zip_bytes: bytes, file_path: str) -> Optional[bytes]:
    """Extract a specific file from ZIP."""
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_file:
        if file_path in zip_file.namelist():
            return zip_file.read(file_path)
    return None

def _search_files_filesystem(storage, job_id: str, query: str, file_type: Optional[str] = None) -> list:
    """Search for query in files directly from filesystem - optimized for large datasets."""
    results = []
    query_lower = query.lower()
    job_path = storage.get_job_path(job_id)
    
    # Limit search to prevent excessive processing
    max_files_to_search = 10000
    files_searched = 0
    
    # Get list of files to search
    files_to_search = []
    for item in job_path.rglob('*'):
        if item.is_file():
            if file_type and not str(item).endswith(file_type):
                continue
            files_to_search.append(item)
            if len(files_to_search) >= max_files_to_search:
                break
    
    # Search files in chunks to avoid memory issues
    chunk_size = 100
    for i in range(0, len(files_to_search), chunk_size):
        chunk = files_to_search[i:i + chunk_size]
        for file_path in chunk:
            if files_searched >= max_files_to_search:
                break
            
            try:
                rel_path = file_path.relative_to(job_path)
                path_str = str(rel_path).replace('\\', '/')
                
                # Read file in chunks for large files
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        # For very large files, only read first 10MB
                        content = f.read(10 * 1024 * 1024)
                        if len(content) >= 10 * 1024 * 1024:
                            # File is too large, check if query appears in first part
                            if query_lower not in content.lower():
                                continue
                            # For large files, just count matches without line numbers
                            match_count = content.lower().count(query_lower)
                            results.append({
                                "file": path_str,
                                "matches": [],
                                "match_count": match_count,
                            })
                            files_searched += 1
                            continue
                        
                        if query_lower in content.lower():
                            # Find line numbers for smaller files
                            lines = content.split('\n')
                            matches = []
                            for line_num, line in enumerate(lines, 1):
                                if query_lower in line.lower():
                                    matches.append({
                                        "line": line_num,
                                        "content": line.strip()[:100],  # Preview
                                    })
                                    if len(matches) >= 50:  # Limit matches per file
                                        break
                            
                            results.append({
                                "file": path_str,
                                "matches": matches,
                                "match_count": len(matches) if len(matches) < 50 else content.lower().count(query_lower),
                            })
                            files_searched += 1
                except (UnicodeDecodeError, PermissionError, OSError):
                    # Skip binary files or files we can't read
                    continue
            except Exception:
                continue
    
    return results

def _search_files(zip_bytes: bytes, query: str, file_type: Optional[str] = None) -> list:
    """Search for query in files from ZIP (legacy method for small datasets)."""
    results = []
    query_lower = query.lower()
    
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_file:
        for name in zip_file.namelist():
            if file_type and not name.endswith(file_type):
                continue
            
            try:
                content = zip_file.read(name).decode('utf-8', errors='ignore')
                if query_lower in content.lower():
                    # Find line numbers
                    lines = content.split('\n')
                    matches = []
                    for i, line in enumerate(lines, 1):
                        if query_lower in line.lower():
                            matches.append({
                                "line": i,
                                "content": line.strip()[:100],  # Preview
                            })
                    
                    results.append({
                        "file": name,
                        "matches": matches,
                        "match_count": len(matches),
                    })
            except Exception:
                continue
    
    return results


@router.post("/{job_id}/upload-to-aem")
def upload_dataset_to_aem(job_id: str, user: UserIdentity = CurrentUser):
    """Legacy AEM dataset upload — removed from the product."""
    raise HTTPException(
        status_code=410,
        detail="AEM dataset upload is no longer available. Download the ZIP from Jobs or Explorer instead.",
    )
