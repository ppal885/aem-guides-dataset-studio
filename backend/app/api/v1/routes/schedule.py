from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Request, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Union, Dict, Any, Optional
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, get_db
from app.jobs import crud
from app.jobs.schemas import DatasetConfig
from app.core.structured_logging import get_structured_logger
from app.tasks.generate_dataset import run_generate_dataset
from app.storage import get_storage

logger = get_structured_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

class ScheduleJobRequest(BaseModel):
    """Request model for scheduling a job."""
    config: dict  # Accept dict directly as frontend sends it
    scheduled_at: Union[datetime, str]  # Accept both datetime and ISO string
    timezone: str = "UTC"
    
    @field_validator('scheduled_at', mode='before')
    @classmethod
    def parse_scheduled_at(cls, v):
        """Parse scheduled_at from ISO string if needed."""
        if isinstance(v, str):
            # Handle ISO format strings (including Z suffix for UTC)
            v_clean = v.replace('Z', '+00:00')
            try:
                return datetime.fromisoformat(v_clean)
            except ValueError:
                # Try without timezone info
                try:
                    return datetime.fromisoformat(v.replace('Z', ''))
                except ValueError:
                    raise ValueError(f"Invalid datetime format: {v}. Expected ISO format (e.g., '2024-01-01T12:00:00Z')")
        return v
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        """Validate timezone is valid."""
        try:
            ZoneInfo(v)
            return v
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")

@router.get("")
def list_jobs(
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by job status"),
    limit: Optional[int] = Query(None, description="Maximum number of jobs to return (no limit if not specified)"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip for pagination"),
):
    """List all jobs for the current user. No default limit - returns all jobs if limit is not specified."""
    logger.info_structured(
        "Listing jobs",
        extra_fields={
            "user_id": user.id,
            "status_filter": status,
            "limit": limit,
            "offset": offset
        }
    )
    
    try:
        jobs, total_count = crud.get_user_jobs(
            session,
            user_id=user.id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Extract recipe type from config
        jobs_list = []
        for job in jobs:
            recipe_type = "unknown"
            if job.config and isinstance(job.config, dict):
                recipes = job.config.get("recipes", [])
                if recipes and isinstance(recipes, list) and len(recipes) > 0:
                    recipe_type = recipes[0].get("type", "unknown") if isinstance(recipes[0], dict) else "unknown"
            
            jobs_list.append({
                "id": str(job.id),
                "name": job.name,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "recipe_type": recipe_type,
                "result": job.result if job.result else None,
                "progress_percent": job.progress_percent,
                "files_generated": job.files_generated,
                "total_files_estimated": job.total_files_estimated,
                "current_stage": job.current_stage,
                "started_at": job.started_at.isoformat() if job.started_at else None,
            })
        
        return {
            "jobs": jobs_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error_structured(
            "Failed to list jobs",
            extra_fields={
                "user_id": user.id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to list jobs: {str(e)}"}
        )

@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Get a single job with progress information."""
    logger.info_structured(
        "Getting job details",
        extra_fields={
            "user_id": user.id,
            "job_id": job_id
        }
    )
    
    try:
        job = crud.get_job(session, job_id)
        if not job:
            return JSONResponse(
                status_code=404,
                content={"detail": "Job not found"}
            )
        
        if job.user_id != user.id:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )
        
        recipe_type = "unknown"
        if job.config and isinstance(job.config, dict):
            recipes = job.config.get("recipes", [])
            if recipes and isinstance(recipes, list) and len(recipes) > 0:
                recipe_type = recipes[0].get("type", "unknown") if isinstance(recipes[0], dict) else "unknown"
        
        # Calculate estimated time remaining
        estimated_time_remaining = None
        if job.status == "running" and job.started_at and job.progress_percent and job.progress_percent > 0:
            from datetime import datetime, timezone
            elapsed_seconds = (datetime.now(timezone.utc) - job.started_at).total_seconds()
            if elapsed_seconds > 0:
                estimated_total_seconds = (elapsed_seconds / job.progress_percent) * 100
                remaining_seconds = estimated_total_seconds - elapsed_seconds
                if remaining_seconds > 0:
                    if remaining_seconds < 60:
                        estimated_time_remaining = f"{int(remaining_seconds)} seconds"
                    elif remaining_seconds < 3600:
                        estimated_time_remaining = f"{int(remaining_seconds / 60)} minutes"
                    else:
                        estimated_time_remaining = f"{int(remaining_seconds / 3600)} hours"
        
        return {
            "id": str(job.id),
            "name": job.name,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "recipe_type": recipe_type,
            "result": job.result if job.result else None,
            "error_message": job.error_message,
            "progress_percent": job.progress_percent,
            "files_generated": job.files_generated,
            "total_files_estimated": job.total_files_estimated,
            "current_stage": job.current_stage,
            "estimated_time_remaining": estimated_time_remaining,
        }
    except Exception as e:
        logger.error_structured(
            "Failed to get job",
            extra_fields={
                "user_id": user.id,
                "job_id": job_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to get job: {str(e)}"}
        )

@router.post("")
async def create_job(
    request: Request,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Create an immediate job (not scheduled)."""
    # Read body once and store it to avoid re-reading issues
    body = None
    try:
        # Manually read body to avoid issues with Body() dependency
        try:
            body_bytes = await request.body()
            import json
            body = json.loads(body_bytes.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error_structured(
                "Failed to parse request body as JSON",
                extra_fields={
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            # Return proper error response without Content-Length issues
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid JSON in request body: {str(e)}"}
            )
        except Exception as e:
            logger.error_structured(
                "Failed to read request body",
                extra_fields={
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            # Return proper error response
            return JSONResponse(
                status_code=400,
                content={"detail": f"Failed to read request body: {str(e)}"}
            )
        
        logger.info_structured(
            "Creating job - received request",
            extra_fields={
                "user_id": user.id if user else "unknown",
                "body_type": type(body).__name__,
                "body_keys": list(body.keys()) if isinstance(body, dict) else None
            }
        )
        
        # Extract config from body
        if not isinstance(body, dict):
            logger.error_structured(
                "Invalid body type",
                extra_fields={"body_type": str(type(body))}
            )
            return JSONResponse(
                status_code=422,
                content={"detail": "Request body must be a JSON object"}
            )
        
        config_dict = body.get("config")
        if config_dict is None:
            logger.error_structured(
                "Missing config field",
                extra_fields={"body_keys": list(body.keys())}
            )
            return JSONResponse(
                status_code=422,
                content={"detail": "Missing 'config' field in request body"}
            )
        
        if not isinstance(config_dict, dict):
            logger.error_structured(
                "Config is not a dict",
                extra_fields={"config_type": str(type(config_dict))}
            )
            return JSONResponse(
                status_code=422,
                content={"detail": "'config' must be a dictionary"}
            )
        
        logger.debug_structured(
            "Received config",
            extra_fields={
                "config_type": type(config_dict).__name__,
                "config_keys": list(config_dict.keys()) if isinstance(config_dict, dict) else None
            }
        )
        
        # Extract name from config
        job_name = config_dict.get("name", "Dataset Generation")
        
        # Validate recipes if present
        recipes = config_dict.get("recipes", [])
        if recipes and not isinstance(recipes, list):
            return JSONResponse(
                status_code=400,
                content={"detail": "Recipes must be a list"}
            )
        
        logger.debug_structured(
            "Job creation details",
            extra_fields={
                "user_id": user.id,
                "job_name": job_name,
                "config_keys": list(config_dict.keys()),
                "recipe_count": len(recipes) if isinstance(recipes, list) else 0
            }
        )
        
        # Check concurrent job limit before creating new job
        try:
            running_jobs, _ = crud.get_user_jobs(
                session,
                user_id=user.id,
                status="running",
                limit=None
            )
            running_count = len(running_jobs)
            concurrent_limit = 20  # Match limit from limits endpoint
            
            if running_count >= concurrent_limit:
                logger.warning_structured(
                    "Concurrent job limit reached",
                    extra_fields={
                        "user_id": user.id,
                        "running_jobs": running_count,
                        "limit": concurrent_limit
                    }
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many concurrent jobs running ({running_count}/{concurrent_limit}). Please wait for some jobs to complete before creating new ones."
                    }
                )
        except Exception as limit_check_error:
            logger.warning_structured(
                "Failed to check concurrent job limit, proceeding anyway",
                extra_fields={
                    "error": str(limit_check_error),
                    "error_type": type(limit_check_error).__name__
                }
            )
            # Don't block job creation if limit check fails - graceful degradation
        
        try:
            job = crud.create_job(
                session,
                config=config_dict,
                name=job_name,
                user_id=user.id,
            )
            
            session.commit()
            job_id_str = str(job.id)
        except Exception as e:
            session.rollback()
            logger.error_structured(
                "Failed to create job in database",
                extra_fields={
                    "user_id": user.id,
                    "job_name": job_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                },
                exc_info=True
            )
            return JSONResponse(
                status_code=500,
                content={"detail": f"Failed to create job: {str(e)}"}
            )
        
        # #region agent log
        import json
        import os
        debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
        try:
            os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
            with open(debug_log_path, 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"schedule.py:140","message":"Job created, about to start generation","data":{"job_id":job_id_str,"job_name":str(job.name)}})+'\n')
        except Exception:
            pass  # Ignore debug log errors
        # #endregion
        
        logger.info(f"[NEW_CODE_v2] Job created successfully - ID: {job_id_str}, Name: {job.name}")
        
        # Validate config before starting generation to catch errors early
        try:
            from app.jobs.schemas import DatasetConfig
            from pydantic import ValidationError
            DatasetConfig.model_validate(config_dict)
            logger.debug(f"Config validation passed for job {job_id_str}")
        except ValidationError as ve:
            session.rollback()
            error_details = ve.errors()
            logger.error_structured(
                "Config validation failed",
                extra_fields={
                    "user_id": user.id,
                    "job_id": job_id_str,
                    "validation_errors": str(error_details)
                },
                exc_info=True
            )
            # Delete the job since validation failed
            try:
                session.delete(job)
                session.commit()
            except Exception:
                session.rollback()
            return JSONResponse(
                status_code=422,
                content={"detail": f"Invalid configuration: {error_details}"}
            )
        except Exception as ve:
            session.rollback()
            logger.error_structured(
                "Unexpected error during config validation",
                extra_fields={
                    "user_id": user.id,
                    "job_id": job_id_str,
                    "error_type": type(ve).__name__,
                    "error_message": str(ve)
                },
                exc_info=True
            )
            # Delete the job since validation failed
            try:
                session.delete(job)
                session.commit()
            except Exception:
                session.rollback()
            return JSONResponse(
                status_code=500,
                content={"detail": f"Failed to validate configuration: {str(ve)}"}
            )
        
        # Generate dataset after job creation - MUST run synchronously  
        logger.info(f"[NEW_CODE_v2] About to start dataset generation for job {job_id_str}")
        
        # CRITICAL: Ensure generation code executes
        try:
            # #region agent log
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                import os
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"schedule.py:147","message":"Entering generation try block","data":{"job_id":job_id_str}})+'\n')
            except Exception:
                pass  # Ignore debug log errors
            # #endregion
            
            logger.info(f"Starting dataset generation for job {job_id_str}")
            
            # Update job status to running - use a fresh session to avoid conflicts
            try:
                # Refresh job from database to ensure we have latest state
                session.refresh(job)
                job.status = "running"
                session.commit()
                logger.info(f"Job {job_id_str} status updated to running")
            except Exception as e:
                logger.error_structured(
                    "Failed to update job status to running",
                    extra_fields={
                        "job_id": job_id_str,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                session.rollback()
                # Continue anyway - job creation succeeded even if status update failed
            
            # Generate dataset files
            logger.info(f"Calling run_generate_dataset for job {job_id_str}")
            
            # #region agent log
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                import os
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"schedule.py:156","message":"Before run_generate_dataset call","data":{"job_id":job_id_str,"config_keys":list(config_dict.keys()) if isinstance(config_dict,dict) else None}})+'\n')
            except Exception:
                pass
            # #endregion
            
            # Check if this is a large dataset that should use streaming
            dataset_config = DatasetConfig.model_validate(config_dict)
            total_topic_count = sum(
                getattr(recipe, 'topic_count', 0) 
                for recipe in dataset_config.recipes 
                if hasattr(recipe, 'topic_count')
            )
            use_streaming = total_topic_count > 10000
            
            # Warn about very large datasets and check system resources
            if total_topic_count > 50000:
                logger.warning_structured(
                    "Very large dataset generation started",
                    extra_fields={
                        "job_id": job_id_str,
                        "topic_count": total_topic_count,
                        "estimated_time_minutes": total_topic_count / 1000,  # Rough estimate: 1000 topics per minute
                        "note": "This may take 30+ minutes. Monitor progress in Job History."
                    }
                )
            
            # Check available memory before starting very large datasets
            try:
                import psutil
                import os
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                available_memory_mb = psutil.virtual_memory().available / 1024 / 1024
                used_memory_mb = memory_info.rss / 1024 / 1024
                
                # Estimate memory needed (rough: 1MB per 1000 topics)
                estimated_memory_mb = total_topic_count / 1000
                
                if estimated_memory_mb > available_memory_mb * 0.8:  # Use max 80% of available
                    logger.warning_structured(
                        "Insufficient memory for dataset generation",
                        extra_fields={
                            "job_id": job_id_str,
                            "topic_count": total_topic_count,
                            "estimated_memory_mb": estimated_memory_mb,
                            "available_memory_mb": available_memory_mb,
                            "used_memory_mb": used_memory_mb
                        }
                    )
                    # Don't fail - let it try with streaming mode
            except Exception as mem_check_error:
                # If psutil not available or check fails, proceed anyway
                logger.debug(f"Memory check failed (non-critical): {mem_check_error}")
            
            storage = get_storage()
            storage_path = str(storage.get_job_path(job_id_str))
            
            # Estimate total files for progress tracking
            total_files_estimated = total_topic_count if total_topic_count > 0 else 100
            
            # Progress callback function
            def progress_callback(progress_percent: int, files_generated: int, current_stage: str):
                try:
                    from app.jobs import crud
                    crud.update_job_progress(
                        session,
                        job_id_str,
                        progress_percent=progress_percent,
                        files_generated=files_generated,
                        total_files_estimated=total_files_estimated,
                        current_stage=current_stage
                    )
                    session.commit()
                except Exception as progress_error:
                    logger.warning_structured(
                        "Failed to update job progress",
                        extra_fields={
                            "job_id": job_id_str,
                            "error": str(progress_error)
                        }
                    )
                    session.rollback()
            
            if use_streaming:
                logger.info(f"Using streaming mode for large dataset ({total_topic_count} topics) for job {job_id_str}")
                file_count = [0]
                sample_files = []
                batch_count = [0]
                
                def stream_batch(batch_files: dict):
                    try:
                        storage.save_dataset_batch(job_id_str, batch_files)
                        file_count[0] += len(batch_files)
                        batch_count[0] += 1
                        if len(sample_files) < 5:
                            sample_files.extend(list(batch_files.keys())[:5 - len(sample_files)])
                        
                        # Update progress every batch (for streaming mode)
                        if total_files_estimated > 0:
                            progress_percent = min(95, int((file_count[0] / total_files_estimated) * 95))
                            progress_callback(progress_percent, file_count[0], f"Generating topics ({file_count[0]}/{total_files_estimated})")
                        
                        # Log progress every 10 batches
                        if batch_count[0] % 10 == 0:
                            logger.info(f"Progress for job {job_id_str}: {file_count[0]} files generated in {batch_count[0]} batches")
                    except Exception as batch_error:
                        logger.error_structured(
                            "Error saving batch",
                            extra_fields={
                                "job_id": job_id_str,
                                "batch_size": len(batch_files),
                                "error": str(batch_error)
                            },
                            exc_info=True
                        )
                        raise
                
                # Initialize progress
                progress_callback(0, 0, "Starting generation")
                
                files = run_generate_dataset(config_dict, job_id_str, stream_callback=stream_batch, progress_callback=progress_callback)
                
                if files:
                    storage.save_dataset_batch(job_id_str, files)
                    file_count[0] += len(files)
                    if not sample_files:
                        sample_files = list(files.keys())[:5]
                
                total_files = file_count[0]
                progress_callback(100, total_files, "Generation complete")
                logger.info(f"Streaming completed for job {job_id_str}: {total_files} files in {batch_count[0]} batches")
            else:
                # Initialize progress
                progress_callback(0, 0, "Starting generation")
                
                files = run_generate_dataset(config_dict, job_id_str, progress_callback=progress_callback)
                total_files = len(files)
                sample_files = list(files.keys())[:5]
                
                # Final progress update
                progress_callback(100, total_files, "Generation complete")
            
            # #region agent log
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                import os
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"schedule.py:160","message":"After run_generate_dataset call","data":{"job_id":job_id_str,"file_count":total_files,"file_names":sample_files}})+'\n')
            except Exception:
                pass
            # #endregion
            
            logger.info(f"Dataset files generated for job {job_id_str}: {total_files} files - {sample_files}")
            
            # Save remaining files if any (for non-streaming or final batch)
            if files and not use_streaming:
                logger.debug(f"Getting storage instance for job {job_id_str}")
                
                # #region agent log
                debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
                try:
                    import os
                    os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                    with open(debug_log_path, 'a') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"schedule.py:167","message":"Before save_dataset call","data":{"job_id":job_id_str,"storage_path":storage_path,"file_count":len(files)}})+'\n')
                except Exception:
                    pass
                # #endregion
                
                logger.debug(f"Saving {len(files)} files to storage for job {job_id_str}")
                storage.save_dataset(job_id_str, files)
            
            # #region agent log
            import os
            path_exists = os.path.exists(storage_path)
            files_in_dir = list(Path(storage_path).iterdir()) if path_exists else []
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"schedule.py:172","message":"After save_dataset call","data":{"job_id":job_id_str,"storage_path":storage_path,"path_exists":path_exists,"files_count":len(files_in_dir),"files":[str(f.name) for f in files_in_dir[:10]]}})+'\n')
            except Exception:
                pass
            # #endregion
            
            logger.info(f"Dataset saved to storage for job {job_id_str} at {storage.get_job_path(job_id_str)}")
            
            # Verify storage
            exists_result = storage.exists(job_id_str)
            
            # #region agent log
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                import os
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"schedule.py:179","message":"Storage exists check","data":{"job_id":job_id_str,"storage_path":storage_path,"exists_result":exists_result,"path_exists":os.path.exists(storage_path)}})+'\n')
            except Exception:
                pass
            # #endregion
            
            if not exists_result:
                raise Exception(f"Dataset was not saved correctly - storage.exists({job_id_str}) returned False")
            
            logger.info(f"Storage verification passed for job {job_id_str}")
            
            # Update job status to completed
            job.status = "completed"
            result_file_list = sample_files if use_streaming else list(files.keys())[:10]
            job.result = {
                "files_generated": total_files,
                "file_list": result_file_list
            }
            session.commit()
            
            logger.info(f"Dataset generation completed successfully for job {job_id_str} - {total_files} files generated")
        except TimeoutError as timeout_error:
            # Handle timeout errors specifically
            import traceback
            error_trace = traceback.format_exc()
            
            logger.error_structured(
                "Dataset generation timed out",
                extra_fields={
                    "job_id": job_id_str,
                    "error_type": "TimeoutError",
                    "error_message": str(timeout_error),
                    "note": "Large datasets may exceed request timeout. Consider using smaller batches or background processing."
                },
                exc_info=True
            )
            
            try:
                session.refresh(job)
                job.status = "failed"
                job.error_message = f"Generation timed out: {str(timeout_error)[:500]}. Large datasets may take longer than request timeout. Try smaller batches or check Job History for progress."
                session.commit()
            except Exception as db_error:
                logger.error_structured(
                    "Failed to update job status to failed",
                    extra_fields={
                        "job_id": job_id_str,
                        "db_error": str(db_error)
                    },
                    exc_info=True
                )
                session.rollback()
        except MemoryError as mem_error:
            # Handle memory errors specifically
            import traceback
            error_trace = traceback.format_exc()
            
            logger.error_structured(
                "Dataset generation failed due to memory error",
                extra_fields={
                    "job_id": job_id_str,
                    "error_type": "MemoryError",
                    "error_message": str(mem_error),
                    "note": "Dataset too large for available memory. Use streaming mode or reduce dataset size."
                },
                exc_info=True
            )
            
            try:
                session.refresh(job)
                job.status = "failed"
                job.error_message = f"Memory error: {str(mem_error)[:500]}. Dataset too large. Try using streaming mode (automatic for >10000 topics) or reduce dataset size."
                session.commit()
            except Exception as db_error:
                logger.error_structured(
                    "Failed to update job status to failed",
                    extra_fields={
                        "job_id": job_id_str,
                        "db_error": str(db_error)
                    },
                    exc_info=True
                )
                session.rollback()
        except Exception as gen_error:
            # If generation fails, mark job as failed but don't fail the request
            import traceback
            from pydantic import ValidationError
            error_trace = traceback.format_exc()
            
            # Check if it's a timeout-related error
            error_str = str(gen_error).lower()
            is_timeout_related = any(keyword in error_str for keyword in ['timeout', 'timed out', 'connection closed', 'request timeout'])
            
            # #region agent log
            debug_log_path = r'c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\.cursor\debug.log'
            try:
                import os
                os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"schedule.py:186","message":"Generation exception caught","data":{"job_id":job_id_str,"error_type":type(gen_error).__name__,"error_message":str(gen_error)[:200]}})+'\n')
            except Exception:
                pass
            # #endregion
            
            logger.error_structured(
                "Dataset generation failed",
                extra_fields={
                    "job_id": job_id_str,
                    "error_type": type(gen_error).__name__,
                    "error_message": str(gen_error),
                    "is_timeout_related": is_timeout_related,
                    "traceback": error_trace
                },
                exc_info=True
            )
            
            try:
                session.refresh(job)
                job.status = "failed"
                # Provide helpful error message
                if is_timeout_related:
                    error_msg = f"Request timed out: {str(gen_error)[:500]}. Large datasets may exceed request timeout. Server timeout increased to 600 seconds. For very large datasets (>50k topics), generation may take 30+ minutes."
                else:
                    error_msg = str(gen_error)[:1000]  # Limit error message length
                job.error_message = error_msg
                session.commit()
            except Exception as db_error:
                logger.error_structured(
                    "Failed to update job status to failed",
                    extra_fields={
                        "job_id": job_id_str,
                        "db_error": str(db_error)
                    },
                    exc_info=True
                )
                session.rollback()
        
        # Ensure job is refreshed before returning
        try:
            session.refresh(job)
        except Exception:
            pass  # Job might have been deleted or doesn't exist
        
        try:
            response_data = {
                "id": str(job.id),
                "name": str(job.name),
                "status": str(job.status),
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            # Use JSONResponse to ensure proper Content-Length handling
            return JSONResponse(content=response_data)
        except Exception as resp_error:
            logger.error_structured(
                "Failed to serialize response",
                extra_fields={
                    "job_id": job_id_str if 'job_id_str' in locals() else "unknown",
                    "error_type": type(resp_error).__name__,
                    "error_message": str(resp_error)
                },
                exc_info=True
            )
            # Return minimal response using JSONResponse
            return JSONResponse(
                content={
                    "id": str(job.id) if job else "unknown",
                    "name": str(job.name) if job else "Unknown",
                    "status": str(job.status) if job else "unknown",
                    "created_at": None,
                }
            )
    except HTTPException as he:
        session.rollback()
        logger.warning_structured(
            "HTTPException in create_job",
            extra_fields={
                "status_code": he.status_code,
                "detail": str(he.detail)
            }
        )
        # Return JSONResponse instead of raising to avoid Content-Length issues
        return JSONResponse(
            status_code=he.status_code,
            content={"detail": str(he.detail)}
        )
    except Exception as e:
        session.rollback()
        error_msg = str(e)
        import traceback
        error_trace = traceback.format_exc()
        logger.error_structured(
            "Failed to create job",
            extra_fields={
                "user_id": user.id if user else "unknown",
                "error_type": type(e).__name__,
                "error_message": error_msg,
                "traceback": error_trace,
                "body_received": str(body)[:500] if isinstance(body, dict) else str(type(body)) if body else "None"
            },
            exc_info=True
        )
        # Log to error.log as well
        logger.error(f"Failed to create job: {error_msg}\n{traceback.format_exc()}")
        # Return JSONResponse instead of raising HTTPException to avoid Content-Length issues
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to create job: {error_msg}"}
        )

@router.post("/schedule")
def schedule_job(
    request: ScheduleJobRequest,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Create a job scheduled for future execution."""
    logger.info_structured(
        "Scheduling job",
        extra_fields={
            "user_id": user.id,
            "scheduled_at": str(request.scheduled_at),
            "timezone": request.timezone
        }
    )
    
    try:
        # Get timezone (already validated by Pydantic)
        tz = ZoneInfo(request.timezone)
        
        # Handle scheduled_at - ensure it's a datetime and handle timezone
        scheduled_at = request.scheduled_at
        if isinstance(scheduled_at, str):
            # Should not happen due to validator, but handle just in case
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            except ValueError:
                logger.warning_structured(
                    "Invalid scheduled_at format",
                    extra_fields={
                        "user_id": user.id,
                        "scheduled_at": scheduled_at,
                        "timezone": request.timezone
                    }
                )
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Invalid scheduled_at format: {scheduled_at}"}
                )
        
        if scheduled_at.tzinfo is None:
            # If naive, assume it's in the specified timezone
            scheduled_dt = scheduled_at.replace(tzinfo=tz)
        else:
            # If timezone-aware, convert to the specified timezone
            scheduled_dt = scheduled_at.astimezone(tz)
        
        now = datetime.now(tz)
        
        if scheduled_dt <= now:
            logger.warning_structured(
                "Scheduled time is not in the future",
                extra_fields={
                    "user_id": user.id,
                    "scheduled_at": scheduled_dt.isoformat(),
                    "current_time": now.isoformat(),
                    "timezone": request.timezone
                }
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Scheduled time must be in the future"}
            )
        
        # Handle config - ensure it's a dict
        if isinstance(request.config, dict):
            config_dict = request.config
        else:
            # Try to convert if it's a Pydantic model or other object
            if hasattr(request.config, 'model_dump'):
                config_dict = request.config.model_dump()
            elif hasattr(request.config, 'dict'):
                config_dict = request.config.dict()
            else:
                config_dict = dict(request.config) if hasattr(request.config, '__dict__') else {}
        
        # Extract name from config
        job_name = config_dict.get("name", "Scheduled Dataset") if isinstance(config_dict, dict) else "Scheduled Dataset"
        
        logger.debug_structured(
            "Schedule job details",
            extra_fields={
                "user_id": user.id,
                "job_name": job_name,
                "scheduled_at": scheduled_dt.isoformat(),
                "timezone": request.timezone,
                "config_keys": list(config_dict.keys()) if isinstance(config_dict, dict) else None
            }
        )
        
        # Store schedule info in config metadata
        if isinstance(config_dict, dict):
            config_dict["_scheduled_at"] = scheduled_dt.isoformat()
            config_dict["_timezone"] = request.timezone
        
        job = crud.create_job(
            session,
            config=config_dict,
            name=job_name,
            user_id=user.id,
        )
        
        session.commit()
        logger.info_structured(
            "Job scheduled successfully",
            extra_fields={
                "job_id": str(job.id),
                "job_name": str(job.name),
                "user_id": user.id,
                "scheduled_at": scheduled_dt.isoformat(),
                "timezone": request.timezone,
                "status": str(job.status)
            }
        )
        
        return {
            "id": str(job.id),
            "name": str(job.name),
            "status": str(job.status),
            "scheduled_at": scheduled_dt.isoformat(),
            "timezone": request.timezone,
        }
    except Exception as e:
        session.rollback()
        logger.error_structured(
            "Failed to schedule job",
            extra_fields={
                "user_id": user.id,
                "scheduled_at": str(request.scheduled_at),
                "timezone": request.timezone,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to schedule job: {str(e)}"}
        )
