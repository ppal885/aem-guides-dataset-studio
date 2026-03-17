from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, db_session
from app.jobs import crud
from app.storage import get_storage
from app.services.aem_upload_service import get_upload_service
import zipfile
import os
import tempfile
import shutil
from io import BytesIO
from typing import Optional
from pathlib import Path

router = APIRouter(prefix="/datasets", tags=["datasets"])


class AemUploadRequest(BaseModel):
    """Request model for AEM upload."""
    aem_base_url: str = Field(..., description="AEM instance base URL")
    target_path: str = Field(..., description="Target path in AEM (e.g., 'content/dam/Priyanka_Perf/')")
    username: str = Field(..., description="AEM username")
    password: str = Field(..., description="AEM password")
    max_concurrent: int = Field(default=20, ge=1, le=100, description="Maximum concurrent uploads")
    max_upload_files: int = Field(default=70000, ge=1, description="Maximum files to upload")

@router.get("/{job_id}/download")
def download_dataset(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Download dataset as ZIP file."""
    # #region agent log
    import json
    import os
    with open(r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"dataset_explorer.py:15","message":"Download endpoint entry","data":{"job_id":job_id,"user_id":user.id if user else None}})+'\n')
    # #endregion
    
    from app.core.structured_logging import get_structured_logger
    logger = get_structured_logger(__name__)
    
    job = crud.get_job(session, job_id)
    if not job:
        # #region agent log
        with open(r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"dataset_explorer.py:25","message":"Job not found in DB","data":{"job_id":job_id}})+'\n')
        # #endregion
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check permissions
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get dataset file
    storage = get_storage()
    storage_path = str(storage.get_job_path(job_id))
    
    # #region agent log
    with open(r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"dataset_explorer.py:35","message":"Before storage.exists check","data":{"job_id":job_id,"storage_path":storage_path,"job_db_id":str(job.id),"job_db_user_id":job.user_id}})+'\n')
    # #endregion
    
    # Check if dataset exists in storage
    exists_result = storage.exists(job_id)
    
    # #region agent log
    path_exists = os.path.exists(storage_path)
    files_in_dir = list(Path(storage_path).iterdir()) if path_exists else []
    with open(r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"dataset_explorer.py:40","message":"After storage.exists check","data":{"job_id":job_id,"exists_result":exists_result,"path_exists":path_exists,"files_count":len(files_in_dir),"files":[str(f.name) for f in files_in_dir[:10]]}})+'\n')
    # #endregion
    
    if not exists_result:
        logger.warning_structured(
            "Download requested but dataset not found",
            extra_fields={"job_id": job_id, "storage_path": storage_path}
        )
        raise HTTPException(status_code=404, detail="Dataset not found. Please ensure the job has completed successfully.")
    
    try:
        # Try to get ZIP buffer for small datasets
        zip_buffer = storage.get_dataset_zip(job_id)
        
        if zip_buffer:
            # Small dataset - use in-memory buffer
            zip_buffer.seek(0)
            zip_content = zip_buffer.getvalue()
            zip_size = len(zip_content)
            
            if zip_size == 0:
                logger.warning_structured(
                    "Download requested but zip file is empty",
                    extra_fields={"job_id": job_id}
                )
                raise HTTPException(status_code=404, detail="Dataset zip file is empty")
            
            logger.info_structured(
                "Serving dataset download (in-memory)",
                extra_fields={
                    "job_id": job_id,
                    "zip_size": zip_size,
                    "filename": f"{job.name or job_id}.zip"
                }
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
                    "Content-Disposition": f'attachment; filename="{job.name or job_id}.zip"',
                    "Content-Length": str(zip_size),
                }
            )
        else:
            # Large dataset - use streaming ZIP creation
            logger.info_structured(
                "Serving dataset download (streaming)",
                extra_fields={
                    "job_id": job_id,
                    "filename": f"{job.name or job_id}.zip"
                }
            )
            
            zip_generator = storage.get_dataset_zip_stream(job_id)
            if not zip_generator:
                raise HTTPException(status_code=404, detail="Dataset zip file could not be created")
            
            return StreamingResponse(
                zip_generator,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{job.name or job_id}.zip"',
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error_structured(
            "Error creating download response",
            extra_fields={
                "job_id": job_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
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
    
    # Check if dataset exists in storage
    if not storage.exists(job_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Use optimized filesystem-based structure loading
    structure = storage.get_dataset_structure(job_id)
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
    
    if not storage.exists(job_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    zip_bytes = storage.get_dataset_zip(job_id)
    if not zip_bytes:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Extract file
    file_content = _extract_file(zip_bytes.getvalue() if hasattr(zip_bytes, 'getvalue') else zip_bytes, file_path)
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
        headers={"Content-Disposition": f'inline; filename="{file_path.split("/")[-1]}"'}
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
    
    if not storage.exists(job_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Search files directly from filesystem
    results = _search_files_filesystem(storage, job_id, query, file_type)
    
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
def upload_dataset_to_aem(
    job_id: str,
    upload_request: AemUploadRequest,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Upload dataset to AEM instance."""
    from app.core.structured_logging import get_structured_logger
    logger = get_structured_logger(__name__)
    
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    storage = get_storage()
    
    if not storage.exists(job_id):
        logger.warning_structured(
            "Upload requested but dataset not found",
            extra_fields={"job_id": job_id}
        )
        raise HTTPException(
            status_code=404,
            detail="Dataset not found. Please ensure the job has completed successfully."
        )
    
    source_path = str(storage.get_job_path(job_id))
    temp_extract_dir = None
    
    # Ensure we're uploading a directory, not a zip file
    # If source_path is a zip file, extract it first
    if os.path.isfile(source_path) and source_path.endswith('.zip'):
        logger.info_structured(
            "Zip file detected, extracting before upload",
            extra_fields={"job_id": job_id, "zip_path": source_path}
        )
        try:
            temp_extract_dir = tempfile.mkdtemp(prefix=f"aem_upload_{job_id}_")
            with zipfile.ZipFile(source_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            source_path = temp_extract_dir
            logger.info_structured(
                "Zip file extracted successfully",
                extra_fields={"job_id": job_id, "extract_dir": temp_extract_dir}
            )
        except Exception as e:
            logger.error_structured(
                "Failed to extract zip file",
                extra_fields={
                    "job_id": job_id,
                    "zip_path": source_path,
                    "error": str(e)
                },
                exc_info=True
            )
            if temp_extract_dir and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract zip file: {str(e)}"
            )
    
    # Validate that source_path is a directory
    if not os.path.isdir(source_path):
        logger.error_structured(
            "Source path is not a directory",
            extra_fields={"job_id": job_id, "source_path": source_path}
        )
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Source path must be a directory. Only folder contents are uploaded, not zip files."
        )
    
    try:
        try:
            upload_service = get_upload_service()
        except FileNotFoundError as e:
            # Clean up temp directory before re-raising
            if temp_extract_dir and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
            logger.error_structured(
                "AEM upload service initialization failed",
                extra_fields={
                    "job_id": job_id,
                    "error": str(e)
                }
            )
            raise HTTPException(
                status_code=500,
                detail=f"Upload service not available: {str(e)}"
            )
        
        result = upload_service.upload_dataset(
            source_path=source_path,
            aem_base_url=upload_request.aem_base_url,
            target_path=upload_request.target_path,
            username=upload_request.username,
            password=upload_request.password,
            max_concurrent=upload_request.max_concurrent,
            max_upload_files=upload_request.max_upload_files
        )
        
        # Clean up temporary extraction directory if it was created
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            try:
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
                logger.info_structured(
                    "Cleaned up temporary extraction directory",
                    extra_fields={"job_id": job_id, "temp_dir": temp_extract_dir}
                )
            except Exception as cleanup_error:
                logger.warning_structured(
                    "Failed to clean up temporary directory",
                    extra_fields={
                        "job_id": job_id,
                        "temp_dir": temp_extract_dir,
                        "error": str(cleanup_error)
                    }
                )
        
        if result.get("success"):
            logger.info_structured(
                "AEM upload completed successfully",
                extra_fields={
                    "job_id": job_id,
                    "duration": result.get("duration"),
                    "aem_base_url": upload_request.aem_base_url,
                    "target_path": upload_request.target_path
                }
            )
            return {
                "success": True,
                "job_id": job_id,
                "message": result.get("message", "Upload completed successfully"),
                "duration": result.get("duration")
            }
        else:
            # Clean up temporary extraction directory before returning error
            if temp_extract_dir and os.path.exists(temp_extract_dir):
                try:
                    shutil.rmtree(temp_extract_dir, ignore_errors=True)
                except Exception:
                    pass
            error_message = result.get("error", "Unknown error")
            logger.error_structured(
                "AEM upload failed",
                extra_fields={
                    "job_id": job_id,
                    "error": error_message,
                    "aem_base_url": upload_request.aem_base_url
                }
            )
            raise HTTPException(
                status_code=500,
                detail=f"Upload failed: {error_message}"
            )
    
    except HTTPException:
        # Clean up temp directory before re-raising
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        raise
    except FileNotFoundError as e:
        # Clean up temp directory before re-raising
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        logger.error_structured(
            "AEM upload service error - file not found",
            extra_fields={
                "job_id": job_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Upload service error: {str(e)}"
        )
    except Exception as e:
        # Clean up temp directory before re-raising
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        logger.error_structured(
            "AEM upload endpoint error",
            extra_fields={
                "job_id": job_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload dataset: {str(e)}"
        )
