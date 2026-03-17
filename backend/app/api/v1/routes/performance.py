from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, db_session
from app.jobs import crud
from app.jobs.models import JobStatus
from typing import Optional

router = APIRouter(prefix="/performance", tags=["performance"])

@router.get("/metrics")
def get_performance_metrics(
    days: int = 7,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get performance metrics for recent jobs."""
    since = datetime.utcnow() - timedelta(days=days)
    
    # Get jobs for user
    jobs = crud.get_user_jobs(session, user.id, since=since)
    
    completed_jobs = [j for j in jobs if j.status == JobStatus.COMPLETED.value or j.status == "completed"]
    failed_jobs = [j for j in jobs if j.status == JobStatus.FAILED.value or j.status == "failed"]
    
    # Calculate metrics
    metrics = {
        "total_jobs": len(jobs),
        "completed_jobs": len(completed_jobs),
        "failed_jobs": len(failed_jobs),
        "success_rate": len(completed_jobs) / len(jobs) * 100 if jobs else 0,
        "average_generation_time": _calculate_avg_time(completed_jobs),
        "total_topics_generated": sum(j.result.get("estimate", {}).get("topics", 0) if j.result and isinstance(j.result, dict) else 0 for j in completed_jobs),
        "total_maps_generated": sum(j.result.get("estimate", {}).get("maps", 0) if j.result and isinstance(j.result, dict) else 0 for j in completed_jobs),
        "total_size": 0,  # Size calculation would need to be added to model
        "jobs_by_status": {
            "succeeded": len(completed_jobs),
            "failed": len(failed_jobs),
            "running": len([j for j in jobs if j.status == JobStatus.RUNNING.value]),
            "pending": len([j for j in jobs if j.status == JobStatus.PENDING.value]),
        },
    }
    
    return metrics

@router.get("/timeline")
def get_performance_timeline(
    days: int = 30,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get performance timeline data for charts."""
    since = datetime.utcnow() - timedelta(days=days)
    
    jobs = crud.get_user_jobs(session, user.id, since=since)
    
    # Group by date
    timeline = {}
    for job in jobs:
        date_key = job.created_at.date().isoformat()
        if date_key not in timeline:
            timeline[date_key] = {
                "date": date_key,
                "jobs": 0,
                "completed": 0,
                "failed": 0,
                "total_time": 0,
                "total_topics": 0,
            }
        
        timeline[date_key]["jobs"] += 1
        if job.status == JobStatus.COMPLETED.value:
            timeline[date_key]["completed"] += 1
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                timeline[date_key]["total_time"] += duration
            if job.result and isinstance(job.result, dict):
                timeline[date_key]["total_topics"] += job.result.get("estimate", {}).get("topics", 0)
        elif job.status == JobStatus.FAILED.value:
            timeline[date_key]["failed"] += 1
    
    return {
        "timeline": list(timeline.values()),
        "days": days,
    }

@router.get("/job/{job_id}/profile")
def get_job_profile(
    job_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get detailed performance profile for a specific job."""
    job = crud.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    profile = {
        "job_id": job_id,
        "job_name": job.name,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "duration_seconds": None,
        "estimate": job.result.get("estimate") if job.result and isinstance(job.result, dict) else None,
    }
    
    if job.started_at and job.completed_at:
        profile["duration_seconds"] = (job.completed_at - job.started_at).total_seconds()
    
    return profile

def _calculate_avg_time(jobs: list) -> Optional[float]:
    """Calculate average generation time."""
    times = []
    for job in jobs:
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            times.append(duration)
    
    return sum(times) / len(times) if times else None
