from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Union
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, db_session
from app.jobs import crud
from app.jobs.schemas import DatasetConfig
from app.tasks.generate_dataset import run_generate_dataset
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
router = APIRouter(prefix="/bulk", tags=["bulk"])

class FlexibleJobRequest(BaseModel):
    """Flexible job request that accepts dict config."""
    config: dict
    
    class Config:
        """Pydantic config to allow arbitrary types."""
        arbitrary_types_allowed = True

class BulkJobRequest(BaseModel):
    jobs: List[FlexibleJobRequest]
    name_prefix: Optional[str] = None

class BulkJobResponse(BaseModel):
    created: int
    failed: int
    job_ids: List[str]
    errors: List[dict]

@router.post("/jobs")
def create_bulk_jobs(
    bulk_request: BulkJobRequest,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Create multiple jobs at once."""
    logger.info_structured(
        "Creating bulk jobs",
        extra_fields={
            "user_id": user.id,
            "job_count": len(bulk_request.jobs),
            "name_prefix": bulk_request.name_prefix
        }
    )
    
    if len(bulk_request.jobs) > 100:
        logger.warning_structured(
            "Bulk job request exceeds limit",
            extra_fields={
                "user_id": user.id,
                "job_count": len(bulk_request.jobs),
                "max_allowed": 100
            }
        )
        raise HTTPException(status_code=400, detail="Maximum 100 jobs per bulk request")
    
    created = 0
    failed = 0
    job_ids = []
    errors = []
    
    for idx, job_request in enumerate(bulk_request.jobs):
        try:
            # Handle config - convert DatasetConfig to dict if needed
            if hasattr(job_request.config, 'model_dump'):
                config_dict = job_request.config.model_dump()
            elif hasattr(job_request.config, 'dict'):
                config_dict = job_request.config.dict()
            elif isinstance(job_request.config, dict):
                config_dict = job_request.config
            else:
                config_dict = dict(job_request.config) if hasattr(job_request.config, '__dict__') else {}
            
            # Generate job name if prefix provided
            job_name = config_dict.get("name", f"Bulk Job {idx + 1}") if isinstance(config_dict, dict) else f"Bulk Job {idx + 1}"
            if bulk_request.name_prefix:
                job_name = f"{bulk_request.name_prefix} - {job_name}"
            
            logger.debug_structured(
                "Creating bulk job",
                extra_fields={
                    "job_index": idx + 1,
                    "total_jobs": len(bulk_request.jobs),
                    "job_name": job_name,
                    "user_id": user.id
                }
            )
            
            # Create job
            job = crud.create_job(
                session,
                config=config_dict,
                name=job_name,
                user_id=user.id,
            )
            
            # Commit each job individually to prevent all-or-nothing failures
            try:
                session.commit()
                logger.debug_structured(
                    "Bulk job committed successfully",
                    extra_fields={
                        "job_id": str(job.id),
                        "job_index": idx + 1,
                        "job_name": job_name
                    }
                )
                
                # Start generation task only after successful commit
                run_generate_dataset.delay(job.id)
                
                job_ids.append(str(job.id))
                created += 1
            except Exception as commit_error:
                session.rollback()
                logger.error_structured(
                    "Failed to commit bulk job",
                    extra_fields={
                        "job_index": idx + 1,
                        "job_name": job_name,
                        "error_type": type(commit_error).__name__,
                        "error_message": str(commit_error)
                    },
                    exc_info=True
                )
                raise
            
        except HTTPException:
            raise
        except Exception as e:
            failed += 1
            # Rollback any uncommitted changes for this job
            try:
                session.rollback()
            except Exception:
                pass
            
            # Safely get config name for error reporting
            try:
                if isinstance(job_request.config, dict):
                    config_name = job_request.config.get("name", "Unknown")
                elif hasattr(job_request.config, 'name'):
                    config_name = getattr(job_request.config, 'name', 'Unknown')
                else:
                    config_name = "Unknown"
            except Exception:
                config_name = "Unknown"
            
            error_msg = str(e)
            logger.error_structured(
                "Failed to create bulk job",
                extra_fields={
                    "job_index": idx + 1,
                    "total_jobs": len(bulk_request.jobs),
                    "config_name": config_name,
                    "error_type": type(e).__name__,
                    "error_message": error_msg
                },
                exc_info=True
            )
            errors.append({
                "index": idx,
                "error": error_msg,
                "config": config_name,
            })
    
    logger.info_structured(
        "Bulk job creation completed",
        extra_fields={
            "user_id": user.id,
            "created": created,
            "failed": failed,
            "total": len(bulk_request.jobs)
        }
    )
    
    return BulkJobResponse(
        created=created,
        failed=failed,
        job_ids=job_ids,
        errors=errors,
    )

@router.post("/jobs/from-template")
def create_bulk_jobs_from_template(
    template_id: str,
    variations: List[dict],
    name_prefix: Optional[str] = None,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Create multiple jobs from a template with variations."""
    logger.info_structured(
        "Creating bulk jobs from template",
        extra_fields={
            "template_id": template_id,
            "user_id": user.id,
            "variation_count": len(variations),
            "name_prefix": name_prefix
        }
    )
    
    # Get template (could be a saved recipe or preset)
    # For now, we'll use presets
    from app.templates.recipe_presets import get_preset
    
    preset = get_preset(template_id)
    if not preset:
        logger.warning_structured(
            "Template not found",
            extra_fields={
                "template_id": template_id,
                "user_id": user.id
            }
        )
        raise HTTPException(status_code=404, detail="Template not found")
    
    created = 0
    failed = 0
    job_ids = []
    errors = []
    
    for idx, variation in enumerate(variations):
        try:
            # Merge template config with variation
            config = preset["config"].copy()
            if "recipes" in variation:
                config["recipes"] = variation["recipes"]
            if "name" in variation:
                config["name"] = variation["name"]
            elif name_prefix:
                config["name"] = f"{name_prefix} - Variation {idx + 1}"
            
            job_name = config.get("name", f"Template Job {idx + 1}")
            logger.debug_structured(
                "Creating template job",
                extra_fields={
                    "job_index": idx + 1,
                    "total_variations": len(variations),
                    "job_name": job_name,
                    "template_id": template_id,
                    "user_id": user.id
                }
            )
            
            # Create job
            job = crud.create_job(
                session,
                config=config,
                name=job_name,
                user_id=user.id,
            )
            
            # Commit each job individually to prevent all-or-nothing failures
            try:
                session.commit()
                logger.debug_structured(
                    "Template job committed successfully",
                    extra_fields={
                        "job_id": str(job.id),
                        "job_index": idx + 1,
                        "job_name": job_name,
                        "template_id": template_id
                    }
                )
                
                # Start generation task only after successful commit
                run_generate_dataset.delay(job.id)
                
                job_ids.append(str(job.id))
                created += 1
            except Exception as commit_error:
                session.rollback()
                logger.error_structured(
                    "Failed to commit template job",
                    extra_fields={
                        "job_index": idx + 1,
                        "job_name": job_name,
                        "template_id": template_id,
                        "error_type": type(commit_error).__name__,
                        "error_message": str(commit_error)
                    },
                    exc_info=True
                )
                raise
            
        except HTTPException:
            raise
        except Exception as e:
            failed += 1
            # Rollback any uncommitted changes for this job
            try:
                session.rollback()
            except Exception:
                pass
            
            error_msg = str(e)
            logger.error_structured(
                "Failed to create template job",
                extra_fields={
                    "job_index": idx + 1,
                    "total_variations": len(variations),
                    "template_id": template_id,
                    "variation_name": variation.get("name", f"Variation {idx + 1}"),
                    "error_type": type(e).__name__,
                    "error_message": error_msg
                },
                exc_info=True
            )
            errors.append({
                "index": idx,
                "error": error_msg,
                "variation": variation.get("name", f"Variation {idx + 1}"),
            })
    
    logger.info_structured(
        "Template bulk job creation completed",
        extra_fields={
            "template_id": template_id,
            "user_id": user.id,
            "created": created,
            "failed": failed,
            "total": len(variations)
        }
    )
    
    return BulkJobResponse(
        created=created,
        failed=failed,
        job_ids=job_ids,
        errors=errors,
    )

@router.post("/jobs/from-csv")
def create_bulk_jobs_from_csv(
    csv_data: str,
    name_prefix: Optional[str] = None,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Create multiple jobs from CSV data."""
    import csv
    from io import StringIO
    
    logger.info_structured(
        "Creating bulk jobs from CSV",
        extra_fields={
            "user_id": user.id,
            "name_prefix": name_prefix
        }
    )
    
    try:
        reader = csv.DictReader(StringIO(csv_data))
        jobs = []
        
        for row_idx, row in enumerate(reader):
            try:
                # Parse CSV row into job config
                # Expected columns: name, seed, recipe_type, recipe_params (JSON)
                job_config = {
                    "name": row.get("name", f"CSV Job {row_idx + 1}"),
                    "seed": row.get("seed", "csv-seed"),
                    "root_folder": row.get("root_folder", "/content/dam/dataset-studio"),
                    "windows_safe_filenames": row.get("windows_safe", "true").lower() == "true",
                    "recipes": [],
                }
                
                # Parse recipe params
                recipe_type = row.get("recipe_type")
                if recipe_type:
                    import json
                    try:
                        recipe_params = json.loads(row.get("recipe_params", "{}"))
                        recipe_params["type"] = recipe_type
                        job_config["recipes"].append(recipe_params)
                    except json.JSONDecodeError as e:
                        logger.warning_structured(
                            "Invalid JSON in recipe_params",
                            extra_fields={
                                "row_index": row_idx + 1,
                                "recipe_type": recipe_type,
                                "error_message": str(e)
                            }
                        )
                        # Continue without recipe params
                
                jobs.append(FlexibleJobRequest(config=job_config))
            except Exception as e:
                logger.error_structured(
                    "Failed to parse CSV row",
                    extra_fields={
                        "row_index": row_idx + 1,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    },
                    exc_info=True
                )
                # Continue with next row
        
        if not jobs:
            logger.warning_structured(
                "No valid jobs found in CSV",
                extra_fields={"user_id": user.id}
            )
            raise HTTPException(status_code=400, detail="No valid jobs found in CSV data")
        
        logger.info_structured(
            "Parsed jobs from CSV",
            extra_fields={
                "user_id": user.id,
                "job_count": len(jobs)
            }
        )
        
        # Use bulk create
        bulk_request = BulkJobRequest(jobs=jobs, name_prefix=name_prefix)
        return create_bulk_jobs(bulk_request, user, session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error_structured(
            "Failed to process CSV data",
            extra_fields={
                "user_id": user.id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        raise HTTPException(status_code=400, detail=f"Invalid CSV data: {str(e)}")
