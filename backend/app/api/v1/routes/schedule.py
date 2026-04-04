from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError, field_validator

from app.core.auth import CurrentUser, UserIdentity
from app.core.structured_logging import get_structured_logger
from app.db.session import Session, get_db
from app.jobs import crud
from app.services.dataset_job_service import (
    ConcurrentJobLimitError,
    create_dataset_job_record,
    enforce_concurrent_job_limit,
    get_dataset_job_summary,
    run_dataset_job,
    validate_dataset_job_config,
)

logger = get_structured_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


def _pydantic_validation_error_payload(exc: ValidationError) -> dict:
    """Shape aligned with main.py RequestValidationError handler (field, message, type)."""
    return {
        "detail": "Invalid configuration",
        "errors": [
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", ())),
                "message": err.get("msg", "Validation error"),
                "type": err.get("type", "unknown"),
            }
            for err in exc.errors()
        ],
    }


class ScheduleJobRequest(BaseModel):
    """Request model for scheduling a job."""

    config: dict
    scheduled_at: Union[datetime, str]
    timezone: str = "UTC"

    @field_validator("scheduled_at", mode="before")
    @classmethod
    def parse_scheduled_at(cls, value):
        if isinstance(value, str):
            cleaned = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                try:
                    return datetime.fromisoformat(value.replace("Z", ""))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid datetime format: {value}. Expected ISO format (for example 2024-01-01T12:00:00Z)"
                    ) from exc
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            ZoneInfo(value)
            return value
        except Exception as exc:
            raise ValueError(f"Invalid timezone: {value}") from exc


@router.get("")
def list_jobs(
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by job status"),
    limit: Optional[int] = Query(None, description="Maximum number of jobs to return (no limit if not specified)"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip for pagination"),
):
    """List all jobs for the current user."""
    logger.info_structured(
        "Listing jobs",
        extra_fields={
            "user_id": user.id,
            "status_filter": status,
            "limit": limit,
            "offset": offset,
        },
    )

    try:
        jobs, total_count = crud.get_user_jobs(
            session,
            user_id=user.id,
            status=status,
            limit=limit,
            offset=offset,
        )
        jobs_list = []
        for job in jobs:
            recipe_type = "unknown"
            if job.config and isinstance(job.config, dict):
                recipes = job.config.get("recipes", [])
                if recipes and isinstance(recipes, list) and isinstance(recipes[0], dict):
                    recipe_type = recipes[0].get("type", "unknown")
            jobs_list.append(
                {
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
                }
            )
        return {
            "jobs": jobs_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.error_structured(
            "Failed to list jobs",
            extra_fields={
                "user_id": user.id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": f"Failed to list jobs: {str(exc)}"})


@router.post("/validate-config")
async def validate_job_config(
    request: Request,
    user: UserIdentity = CurrentUser,
):
    """
    Validate dataset `config` without creating a job.
    Request body: same as POST /jobs — `{ "config": { ... } }`.
    Returns 200 with `valid: true` and normalized `config`, or 422 with structured `errors`.
    """
    _ = user
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Invalid JSON in request body: {str(exc)}"},
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request body must be a JSON object",
                "errors": [],
            },
        )
    config_dict = body.get("config")
    if config_dict is None:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Missing 'config' field in request body",
                "errors": [],
            },
        )
    if not isinstance(config_dict, dict):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "'config' must be a dictionary",
                "errors": [],
            },
        )
    try:
        parsed = validate_dataset_job_config(config_dict)
        return JSONResponse(
            content={
                "valid": True,
                "config": parsed.model_dump(mode="json"),
            }
        )
    except ValidationError as exc:
        logger.info_structured(
            "Job config validation failed (validate-config)",
            extra_fields={"errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=_pydantic_validation_error_payload(exc))


@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(get_db),
):
    """Get a single job with progress information."""
    logger.info_structured(
        "Getting job details",
        extra_fields={"user_id": user.id, "job_id": job_id},
    )

    try:
        job = crud.get_job(session, job_id)
        if not job:
            return JSONResponse(status_code=404, content={"detail": "Job not found"})
        if job.user_id != user.id:
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        recipe_type = "unknown"
        if job.config and isinstance(job.config, dict):
            recipes = job.config.get("recipes", [])
            if recipes and isinstance(recipes, list) and isinstance(recipes[0], dict):
                recipe_type = recipes[0].get("type", "unknown")

        estimated_time_remaining = None
        if job.status == "running" and job.started_at and job.progress_percent and job.progress_percent > 0:
            elapsed_seconds = (datetime.now(timezone.utc) - job.started_at.replace(tzinfo=timezone.utc)).total_seconds()
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
    except Exception as exc:
        logger.error_structured(
            "Failed to get job",
            extra_fields={
                "user_id": user.id,
                "job_id": job_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": f"Failed to get job: {str(exc)}"})


@router.post("")
async def create_job(
    request: Request,
    user: UserIdentity = CurrentUser,
):
    """Create an immediate job and execute it synchronously."""
    body = None
    try:
        try:
            body = await request.json()
        except Exception as exc:
            logger.error_structured(
                "Failed to parse request body as JSON",
                extra_fields={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return JSONResponse(status_code=400, content={"detail": f"Invalid JSON in request body: {str(exc)}"})

        if not isinstance(body, dict):
            return JSONResponse(status_code=422, content={"detail": "Request body must be a JSON object"})

        config_dict = body.get("config")
        if config_dict is None:
            return JSONResponse(status_code=422, content={"detail": "Missing 'config' field in request body"})
        if not isinstance(config_dict, dict):
            return JSONResponse(status_code=422, content={"detail": "'config' must be a dictionary"})

        recipes = config_dict.get("recipes", [])
        if recipes and not isinstance(recipes, list):
            return JSONResponse(status_code=400, content={"detail": "Recipes must be a list"})

        job_name = str(config_dict.get("name") or "Dataset Generation").strip() or "Dataset Generation"
        logger.info_structured(
            "Creating immediate dataset job",
            extra_fields={
                "user_id": user.id,
                "job_name": job_name,
                "recipe_count": len(recipes) if isinstance(recipes, list) else 0,
            },
        )

        enforce_concurrent_job_limit(user.id)
        job_record = create_dataset_job_record(config_dict, user_id=user.id, name=job_name)
        run_dataset_job(str(job_record["id"]), job_record["config"])
        response_data = get_dataset_job_summary(str(job_record["id"])) or {
            "id": str(job_record["id"]),
            "name": str(job_record["name"]),
            "status": str(job_record["status"]),
            "created_at": job_record.get("created_at"),
        }
        return JSONResponse(content=response_data)
    except ConcurrentJobLimitError as exc:
        logger.warning_structured(
            "Concurrent job limit reached",
            extra_fields={"user_id": user.id, "error": str(exc)},
        )
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    except ValidationError as exc:
        logger.warning_structured(
            "Invalid job configuration",
            extra_fields={"user_id": user.id, "errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=_pydantic_validation_error_payload(exc))
    except Exception as exc:
        logger.error_structured(
            "Failed to create job",
            extra_fields={
                "user_id": user.id if user else "unknown",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "body_received": str(body)[:500] if isinstance(body, dict) else str(type(body)) if body else "None",
            },
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": f"Failed to create job: {str(exc)}"})


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
            "timezone": request.timezone,
        },
    )

    try:
        tz = ZoneInfo(request.timezone)
        scheduled_at = request.scheduled_at
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))

        scheduled_dt = scheduled_at.replace(tzinfo=tz) if scheduled_at.tzinfo is None else scheduled_at.astimezone(tz)
        now = datetime.now(tz)
        if scheduled_dt <= now:
            return JSONResponse(status_code=400, content={"detail": "Scheduled time must be in the future"})

        config_dict = request.config if isinstance(request.config, dict) else {}
        job_name = config_dict.get("name", "Scheduled Dataset") if isinstance(config_dict, dict) else "Scheduled Dataset"
        config_dict["_scheduled_at"] = scheduled_dt.isoformat()
        config_dict["_timezone"] = request.timezone

        job = crud.create_job(
            session,
            config=config_dict,
            name=job_name,
            user_id=user.id,
        )
        session.commit()

        return {
            "id": str(job.id),
            "name": str(job.name),
            "status": str(job.status),
            "scheduled_at": scheduled_dt.isoformat(),
            "timezone": request.timezone,
        }
    except Exception as exc:
        session.rollback()
        logger.error_structured(
            "Failed to schedule job",
            extra_fields={
                "user_id": user.id,
                "scheduled_at": str(request.scheduled_at),
                "timezone": request.timezone,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": f"Failed to schedule job: {str(exc)}"})
