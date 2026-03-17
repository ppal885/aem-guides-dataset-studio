"""Storage monitoring endpoints."""
from fastapi import APIRouter, HTTPException
from app.core.auth import UserIdentity, CurrentUser
from app.utils.disk_monitor import get_disk_usage, get_storage_size, check_disk_space, estimate_dataset_size
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/disk-usage")
def get_disk_usage_endpoint(
    user: UserIdentity = CurrentUser,
):
    """Get disk usage information."""
    try:
        disk_info = get_disk_usage()
        return disk_info
    except Exception as e:
        logger.error_structured(
            "Failed to get disk usage",
            extra_fields={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to get disk usage: {str(e)}")


@router.get("/storage-stats")
def get_storage_stats(
    user: UserIdentity = CurrentUser,
):
    """Get storage statistics (total size, file count, etc.)."""
    try:
        stats = get_storage_size()
        return stats
    except Exception as e:
        logger.error_structured(
            "Failed to get storage stats",
            extra_fields={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to get storage stats: {str(e)}")


@router.post("/check-space")
def check_space_endpoint(
    required_gb: float,
    user: UserIdentity = CurrentUser,
):
    """Check if enough disk space is available.
    
    Args:
        required_gb: Required disk space in GB
    """
    try:
        has_space, disk_info = check_disk_space(required_gb)
        
        return {
            "has_space": has_space,
            "required_gb": required_gb,
            "available_gb": disk_info.get("free_gb", 0),
            "disk_info": disk_info
        }
    except Exception as e:
        logger.error_structured(
            "Failed to check disk space",
            extra_fields={"required_gb": required_gb, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to check disk space: {str(e)}")


@router.post("/estimate-size")
def estimate_size_endpoint(
    config: dict,
    user: UserIdentity = CurrentUser,
):
    """Estimate dataset size based on configuration.
    
    Args:
        config: Dataset configuration dictionary
    """
    try:
        estimated_size = estimate_dataset_size(config)
        return {
            "estimated_size_gb": estimated_size,
            "config": config
        }
    except Exception as e:
        logger.error_structured(
            "Failed to estimate dataset size",
            extra_fields={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to estimate size: {str(e)}")
