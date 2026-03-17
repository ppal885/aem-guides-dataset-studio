"""CRUD operations for jobs."""
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app.jobs.models import Job, SavedRecipe
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def create_job(
    session: Session,
    config: dict,
    name: str,
    user_id: str,
    status: str = "pending",
) -> Job:
    """Create a new job."""
    logger.debug(f"Creating job: name={name}, user_id={user_id}, status={status}")
    try:
        job = Job(
            name=name,
            config=config,
            user_id=user_id,
            status=status,
        )
        session.add(job)
        logger.debug(f"Job object created: {job.id}")
        return job
    except Exception as e:
        logger.error(f"Failed to create job: {e}", exc_info=True)
        raise


def get_job(session: Session, job_id: str) -> Optional[Job]:
    """Get a job by ID."""
    return session.query(Job).filter(Job.id == job_id).first()


def get_user_jobs(
    session: Session,
    user_id: str,
    since: Optional[datetime] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> tuple[List[Job], int]:
    """Get jobs for a user. Returns (jobs_list, total_count).
    
    If limit is None, returns all jobs without limit.
    """
    query = session.query(Job).filter(Job.user_id == user_id)
    
    if since:
        query = query.filter(Job.created_at >= since)
    
    if status:
        query = query.filter(Job.status == status)
    
    # Get total count before applying limit/offset
    total_count = query.count()
    
    # Apply ordering
    query = query.order_by(Job.created_at.desc())
    
    # Apply offset
    if offset > 0:
        query = query.offset(offset)
    
    # Apply limit if provided, otherwise return all
    if limit is not None:
        query = query.limit(limit)
    
    jobs = query.all()
    return (jobs, total_count)


def update_job_status(
    session: Session,
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    result: Optional[dict] = None,
) -> Optional[Job]:
    """Update job status."""
    job = get_job(session, job_id)
    if not job:
        return None
    
    job.status = status
    if error_message:
        job.error_message = error_message
    if result:
        job.result = result
    
    if status == "running":
        job.started_at = datetime.utcnow()
    elif status in ("completed", "failed"):
        job.completed_at = datetime.utcnow()
    
    return job


def update_job_progress(
    session: Session,
    job_id: str,
    progress_percent: Optional[int] = None,
    files_generated: Optional[int] = None,
    total_files_estimated: Optional[int] = None,
    current_stage: Optional[str] = None,
) -> Optional[Job]:
    """Update job progress information."""
    job = get_job(session, job_id)
    if not job:
        return None
    
    if progress_percent is not None:
        job.progress_percent = max(0, min(100, progress_percent))
    if files_generated is not None:
        job.files_generated = files_generated
    if total_files_estimated is not None:
        job.total_files_estimated = total_files_estimated
    if current_stage is not None:
        job.current_stage = current_stage
    
    return job


def delete_job(session: Session, job_id: str) -> bool:
    """Delete a job by ID."""
    job = get_job(session, job_id)
    if not job:
        return False
    
    session.delete(job)
    return True


def get_old_jobs(session: Session, older_than: datetime) -> List[Job]:
    """Get jobs older than the specified datetime.
    
    Only returns jobs that are completed or failed - never returns running or pending jobs.
    This prevents regressions where active jobs are accidentally deleted.
    """
    return session.query(Job).filter(
        Job.created_at < older_than,
        Job.status.in_(["completed", "failed"])
    ).all()


def delete_old_jobs(session: Session, older_than: datetime) -> int:
    """Delete jobs older than the specified datetime. Returns count of deleted jobs.
    
    Only deletes completed or failed jobs - never deletes running or pending jobs.
    This prevents regressions where active jobs are accidentally deleted.
    """
    old_jobs = get_old_jobs(session, older_than)
    
    # Final safety check - never delete running or pending jobs
    safe_to_delete = [j for j in old_jobs if j.status in ["completed", "failed"]]
    if len(safe_to_delete) != len(old_jobs):
        logger.warning(
            f"Filtered out {len(old_jobs) - len(safe_to_delete)} jobs with invalid status for deletion"
        )
    
    count = 0
    for job in safe_to_delete:
        session.delete(job)
        count += 1
    
    return count


def get_old_saved_recipes(session: Session, older_than: datetime) -> List[SavedRecipe]:
    """Get saved recipes older than the specified datetime."""
    return session.query(SavedRecipe).filter(SavedRecipe.created_at < older_than).all()


def delete_old_saved_recipes(session: Session, older_than: datetime) -> int:
    """Delete saved recipes older than the specified datetime. Returns count of deleted recipes."""
    old_recipes = get_old_saved_recipes(session, older_than)
    count = len(old_recipes)
    
    for recipe in old_recipes:
        session.delete(recipe)
    
    return count
