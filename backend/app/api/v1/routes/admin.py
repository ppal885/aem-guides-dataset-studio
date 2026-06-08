"""Admin and maintenance endpoints."""
import os
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.auth import AdminUser, UserIdentity
from app.services.cleaning_service import clean_old_data
from app.core.structured_logging import get_structured_logger

router = APIRouter(prefix="/admin", tags=["admin"])

logger = get_structured_logger(__name__)


@router.post("/deploy")
def trigger_deploy(user: UserIdentity = AdminUser):
    """Pull latest code from git and restart the backend service (Linux VM only).

    This endpoint is only available when ALLOW_DEV_AUTH_BYPASS=true.
    """
    try:
        repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
        results: dict = {}

        # git pull
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        results["git_pull"] = pull.stdout.strip()[-500:] if pull.stdout else pull.stderr.strip()[-500:]

        # clear pyc
        subprocess.run(
            ["find", f"{repo_dir}/backend/app", "-name", "*.pyc", "-delete"],
            timeout=10,
        )

        # systemctl restart (only works if running as root/with sudo)
        restart = subprocess.run(
            ["systemctl", "restart", "aem-backend"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        results["restart"] = "ok" if restart.returncode == 0 else restart.stderr.strip()

        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CleanupRequest(BaseModel):
    """Request model for manual cleanup."""
    days_old: int = Field(default=7, ge=1, le=365, description="Number of days after which data should be cleaned")


@router.post("/cleanup")
def trigger_cleanup(
    request: CleanupRequest = CleanupRequest(),
    user: UserIdentity = AdminUser,
):
    """Manually trigger data cleanup job.
    
    This endpoint allows administrators to manually trigger the cleanup of old data.
    By default, it cleans data older than 7 days.
    """
    try:
        logger.info_structured(
            "Manual cleanup triggered",
            extra_fields={
                "user_id": user.id,
                "days_old": request.days_old
            }
        )
        
        stats = clean_old_data(days_old=request.days_old)
        
        return {
            "success": True,
            "message": "Cleanup completed successfully",
            "stats": stats
        }
    except Exception as e:
        logger.error_structured(
            "Manual cleanup failed",
            extra_fields={
                "user_id": user.id,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )
