"""Disk space monitoring utilities."""
import os
import shutil
from pathlib import Path
from typing import Dict, Optional
from app.storage import get_storage
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def get_disk_usage(path: Optional[Path] = None) -> Dict[str, float]:
    """Get disk usage information for a path.
    
    Args:
        path: Path to check. If None, uses storage base path.
    
    Returns:
        Dictionary with disk usage information:
        - total_gb: Total disk space in GB
        - used_gb: Used disk space in GB
        - free_gb: Free disk space in GB
        - percent_used: Percentage of disk used
    """
    if path is None:
        storage = get_storage()
        path = storage.base_path
    
    try:
        total, used, free = shutil.disk_usage(path)
        
        return {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "percent_used": round((used / total) * 100, 2),
            "path": str(path)
        }
    except Exception as e:
        logger.error_structured(
            "Failed to get disk usage",
            extra_fields={"path": str(path), "error": str(e)},
            exc_info=True
        )
        return {
            "total_gb": 0,
            "used_gb": 0,
            "free_gb": 0,
            "percent_used": 0,
            "path": str(path),
            "error": str(e)
        }


def check_disk_space(required_gb: float, path: Optional[Path] = None) -> tuple[bool, Dict[str, float]]:
    """Check if enough disk space is available.
    
    Args:
        required_gb: Required disk space in GB
        path: Path to check. If None, uses storage base path.
    
    Returns:
        Tuple of (has_space, disk_info)
    """
    disk_info = get_disk_usage(path)
    
    if "error" in disk_info:
        return False, disk_info
    
    free_gb = disk_info["free_gb"]
    has_space = free_gb >= required_gb * 1.5  # 50% buffer
    
    return has_space, disk_info


def estimate_dataset_size(config: dict) -> float:
    """Estimate dataset size in GB based on configuration.
    
    Args:
        config: Dataset configuration dictionary
    
    Returns:
        Estimated size in GB
    """
    topic_count = config.get('topic_count', 100)
    files_per_topic = config.get('files_per_topic', 5)
    avg_file_size_mb = config.get('avg_file_size_mb', 0.5)
    
    total_files = topic_count * files_per_topic
    estimated_size_gb = (total_files * avg_file_size_mb) / 1024
    
    return round(estimated_size_gb, 2)


def get_storage_size(job_id: Optional[str] = None) -> Dict[str, float]:
    """Get storage size for a specific job or all storage.
    
    Args:
        job_id: Job ID to check. If None, checks entire storage.
    
    Returns:
        Dictionary with storage size information
    """
    storage = get_storage()
    
    if job_id:
        job_path = storage.get_job_path(job_id)
        if not job_path.exists():
            return {"size_gb": 0, "file_count": 0}
        
        total_size = sum(f.stat().st_size for f in job_path.rglob('*') if f.is_file())
        file_count = len(list(job_path.rglob('*'))) - len(list(job_path.rglob('*/')))
        
        return {
            "size_gb": round(total_size / (1024**3), 2),
            "file_count": file_count,
            "job_id": job_id
        }
    else:
        total_size = 0
        file_count = 0
        
        if storage.base_path.exists():
            for item in storage.base_path.iterdir():
                if item.is_dir():
                    for file in item.rglob('*'):
                        if file.is_file():
                            total_size += file.stat().st_size
                            file_count += 1
        
        return {
            "size_gb": round(total_size / (1024**3), 2),
            "file_count": file_count,
            "total_jobs": len(list(storage.base_path.iterdir())) if storage.base_path.exists() else 0
        }
