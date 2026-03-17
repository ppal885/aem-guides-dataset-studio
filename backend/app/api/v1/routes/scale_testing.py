from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from app.core.auth import UserIdentity, CurrentUser
from app.generator.performance_scale import generate_performance_test_dataset, PerformanceMetrics
from app.jobs.schemas import DatasetConfig

router = APIRouter(prefix="/scale-testing", tags=["scale-testing"])

class LargeScaleTestRequest(BaseModel):
    topic_count: int = 100000
    batch_size: int = 1000

class DeepHierarchyTestRequest(BaseModel):
    depth: int = 10
    children_per_level: int = 5

class WideBranchingTestRequest(BaseModel):
    root_topics: int = 10
    children_per_root: int = 1000

@router.post("/large-scale/preview")
def preview_large_scale(
    request: LargeScaleTestRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview large-scale dataset."""
    return {
        "estimate": {
            "topics": request.topic_count,
            "maps": 0,  # Maps disabled for large scale
            "estimated_size_mb": request.topic_count * 0.5,  # ~0.5KB per topic
            "estimated_time_minutes": request.topic_count / 1000,  # ~1000 topics/sec
        },
        "warnings": [
            f"Large dataset: {request.topic_count:,} topics",
            "Map generation disabled for performance",
            "Consider running during off-peak hours",
        ]
    }

@router.post("/deep-hierarchy/preview")
def preview_deep_hierarchy(
    request: DeepHierarchyTestRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview deep hierarchy dataset."""
    total_topics = sum(request.children_per_level ** level for level in range(request.depth + 1))
    
    return {
        "estimate": {
            "depth": request.depth,
            "children_per_level": request.children_per_level,
            "total_topics": total_topics,
            "maps": request.depth,
        },
        "warnings": [
            f"Deep hierarchy: {request.depth} levels",
            f"Total topics: {total_topics:,}",
        ]
    }

@router.post("/wide-branching/preview")
def preview_wide_branching(
    request: WideBranchingTestRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview wide branching dataset."""
    total_topics = request.root_topics + (request.root_topics * request.children_per_root)
    
    return {
        "estimate": {
            "root_topics": request.root_topics,
            "children_per_root": request.children_per_root,
            "total_topics": total_topics,
            "maps": request.root_topics,
        },
        "warnings": [
            f"Wide branching: {request.children_per_root:,} children per root",
            f"Total topics: {total_topics:,}",
        ]
    }

@router.post("/performance-profile")
def get_performance_profile(
    config: DatasetConfig,
    test_type: str,
    test_params: Dict,
    user: UserIdentity = CurrentUser,
):
    """Get performance profile for a test configuration."""
    try:
        import random
        rand = random.Random(config.seed)
        
        # Generate sample and measure
        base = "/tmp/scale_test"
        files, metrics = generate_performance_test_dataset(
            config,
            base,
            test_type=test_type,
            test_params=test_params,
            rand=rand,
        )
        
        return {
            "test_type": test_type,
            "test_params": test_params,
            "metrics": metrics,
            "sample_size": len(files),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
