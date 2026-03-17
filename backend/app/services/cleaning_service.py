"""Service for cleaning old data."""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.jobs import crud
from app.services.chat_service import get_old_chat_sessions, delete_old_chat_sessions
from app.storage import get_storage
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def clean_old_data(days_old: int = 7) -> dict:
    """Clean data older than specified days.
    
    Args:
        days_old: Number of days after which data should be cleaned (default: 7)
    
    Returns:
        Dictionary with cleaning statistics
    """
    # Use timezone-aware datetime to avoid comparison issues with PostgreSQL
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
    stats = {
        "jobs_deleted": 0,
        "jobs_storage_deleted": 0,
        "saved_recipes_deleted": 0,
        "chat_sessions_deleted": 0,
        "errors": []
    }
    
    db: Session = SessionLocal()
    try:
        # Only get completed or failed jobs - never delete running/pending jobs
        old_jobs = crud.get_old_jobs(db, cutoff_date)
        
        # Count jobs by status for logging
        status_counts = {}
        for job in old_jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
        
        logger.info_structured(
            "Found old jobs to clean",
            extra_fields={
                "count": len(old_jobs),
                "cutoff_date": cutoff_date.isoformat(),
                "days_old": days_old,
                "status_breakdown": status_counts
            }
        )
        
        # Double-check: Verify no running or pending jobs are being deleted
        running_or_pending = [j for j in old_jobs if j.status in ["running", "pending"]]
        if running_or_pending:
            logger.error_structured(
                "CRITICAL: Attempted to delete active jobs - aborting cleanup",
                extra_fields={
                    "active_jobs_count": len(running_or_pending),
                    "job_ids": [j.id for j in running_or_pending]
                }
            )
            stats["errors"].append(f"Prevented deletion of {len(running_or_pending)} active jobs")
            return stats
        
        storage = get_storage()
        
        for job in old_jobs:
            try:
                # Final safety check before deletion
                if job.status not in ["completed", "failed"]:
                    logger.warning_structured(
                        "Skipping job deletion - invalid status",
                        extra_fields={"job_id": job.id, "status": job.status}
                    )
                    continue
                    
                if storage.delete_job_data(job.id):
                    stats["jobs_storage_deleted"] += 1
                    logger.debug_structured(
                        "Deleted job storage",
                        extra_fields={"job_id": job.id, "job_name": job.name, "status": job.status}
                    )
                else:
                    logger.warning_structured(
                        "Job storage not found or already deleted",
                        extra_fields={"job_id": job.id, "job_name": job.name}
                    )
            except Exception as e:
                error_msg = f"Failed to delete storage for job {job.id}: {str(e)}"
                stats["errors"].append(error_msg)
                logger.error_structured(
                    "Failed to delete job storage",
                    extra_fields={"job_id": job.id, "error": str(e)},
                    exc_info=True
                )
        
        # Delete from database - this will only delete completed/failed jobs due to get_old_jobs filter
        stats["jobs_deleted"] = crud.delete_old_jobs(db, cutoff_date)
        logger.info_structured(
            "Deleted old jobs from database",
            extra_fields={"count": stats["jobs_deleted"]}
        )
        
        old_recipes = crud.get_old_saved_recipes(db, cutoff_date)
        logger.info_structured(
            "Found old saved recipes to clean",
            extra_fields={
                "count": len(old_recipes),
                "cutoff_date": cutoff_date.isoformat()
            }
        )
        
        stats["saved_recipes_deleted"] = crud.delete_old_saved_recipes(db, cutoff_date)
        logger.info_structured(
            "Deleted old saved recipes from database",
            extra_fields={"count": stats["saved_recipes_deleted"]}
        )

        # Chat retention: delete sessions (and messages via CASCADE) older than cutoff
        old_chat_sessions = get_old_chat_sessions(cutoff_date)
        logger.info_structured(
            "Found old chat sessions to clean",
            extra_fields={
                "count": len(old_chat_sessions),
                "cutoff_date": cutoff_date.isoformat(),
            }
        )
        stats["chat_sessions_deleted"] = delete_old_chat_sessions(cutoff_date)
        logger.info_structured(
            "Deleted old chat sessions from database",
            extra_fields={"count": stats["chat_sessions_deleted"]}
        )
        
        db.commit()
        
        logger.info_structured(
            "Data cleaning completed",
            extra_fields={
                "jobs_deleted": stats["jobs_deleted"],
                "jobs_storage_deleted": stats["jobs_storage_deleted"],
                "saved_recipes_deleted": stats["saved_recipes_deleted"],
                "chat_sessions_deleted": stats["chat_sessions_deleted"],
                "errors_count": len(stats["errors"])
            }
        )
        
    except Exception as e:
        db.rollback()
        error_msg = f"Data cleaning failed: {str(e)}"
        stats["errors"].append(error_msg)
        logger.error_structured(
            "Data cleaning failed",
            extra_fields={"error": str(e)},
            exc_info=True
        )
    finally:
        db.close()
    
    return stats
