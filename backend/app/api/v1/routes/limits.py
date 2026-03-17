"""Limits endpoint for dataset generation constraints."""
from fastapi import APIRouter, HTTPException
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/limits", tags=["limits"])


@router.get("")
def get_limits():
    """Get dataset generation limits and constraints."""
    try:
        logger.debug("Limits endpoint accessed")
        limits = {
            "topicrefs_per_map_max": 5000,
            "total_topicrefs_max": 100000,
            "topics_max": 10000,
            "maps_max": 100,
            "xrefs_max": 50000,
            "keydefs_max": 1000,
            "file_size_max_mb": 100,
            "concurrent_jobs_max": 20,  # Increased from 5 to 20 for better scalability
        }
        return limits
    except Exception as e:
        logger.error(f"Error in get_limits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get limits: {str(e)}")
