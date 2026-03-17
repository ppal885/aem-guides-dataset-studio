from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.core.auth import UserIdentity, CurrentUser

router = APIRouter(prefix="/specialized", tags=["specialized"])

class TaskTopicsRecipeRequest(BaseModel):
    topic_count: int = 50
    steps_per_task: int = 5
    include_prereq: bool = True
    include_result: bool = True
    include_map: bool = True

class ConceptTopicsRecipeRequest(BaseModel):
    topic_count: int = 50
    sections_per_concept: int = 3
    include_map: bool = True

class ReferenceTopicsRecipeRequest(BaseModel):
    topic_count: int = 50
    properties_per_ref: int = 5
    include_map: bool = True

class GlossaryPackRecipeRequest(BaseModel):
    entry_count: int = 100
    include_acronyms: bool = True
    include_map: bool = True

class BookmapStructureRecipeRequest(BaseModel):
    chapter_count: int = 10
    topics_per_chapter: int = 5
    include_frontmatter: bool = True
    include_backmatter: bool = True

class MediaRichContentRecipeRequest(BaseModel):
    topic_count: int = 50
    images_per_topic: int = 3
    generate_images: bool = True
    image_width: int = 800
    image_height: int = 600
    include_map: bool = True

class WorkflowEnabledContentRecipeRequest(BaseModel):
    base_recipe: dict
    include_review: bool = True
    include_translation: bool = True
    include_approval: bool = True
    reviewers: List[str] = ["reviewer1", "reviewer2"]
    target_languages: List[str] = ["es", "fr"]

class OutputOptimizedRecipeRequest(BaseModel):
    base_recipe: dict
    output_format: str = "aemsite"
    optimization_options: dict = {}

@router.post("/task-topics/preview")
def preview_task_topics(
    recipe: TaskTopicsRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview task topics dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "total_steps": recipe.topic_count * recipe.steps_per_task,
        },
        "structure": {
            "topics": {"type": "task", "count": recipe.topic_count},
            "maps": [{"name": "tasks.ditamap"}] if recipe.include_map else [],
        }
    }

@router.post("/concept-topics/preview")
def preview_concept_topics(
    recipe: ConceptTopicsRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview concept topics dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "total_sections": recipe.topic_count * recipe.sections_per_concept,
        },
        "structure": {
            "topics": {"type": "concept", "count": recipe.topic_count},
        }
    }

@router.post("/reference-topics/preview")
def preview_reference_topics(
    recipe: ReferenceTopicsRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview reference topics dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "total_properties": recipe.topic_count * recipe.properties_per_ref,
        },
        "structure": {
            "topics": {"type": "reference", "count": recipe.topic_count},
        }
    }

@router.post("/glossary/preview")
def preview_glossary(
    recipe: GlossaryPackRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview glossary dataset."""
    return {
        "estimate": {
            "glossary_entries": recipe.entry_count,
            "maps": 1 if recipe.include_map else 0,
        },
        "structure": {
            "glossary": {"entries": recipe.entry_count},
        }
    }

@router.post("/bookmap/preview")
def preview_bookmap(
    recipe: BookmapStructureRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview bookmap dataset."""
    return {
        "estimate": {
            "chapters": recipe.chapter_count,
            "topics": recipe.chapter_count * recipe.topics_per_chapter,
            "maps": 1,
        },
        "structure": {
            "bookmap": {
                "chapters": recipe.chapter_count,
                "frontmatter": recipe.include_frontmatter,
                "backmatter": recipe.include_backmatter,
            }
        }
    }

@router.post("/media-rich/preview")
def preview_media_rich(
    recipe: MediaRichContentRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview media-rich content dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "images": recipe.topic_count * recipe.images_per_topic if recipe.generate_images else 0,
            "maps": 1 if recipe.include_map else 0,
        },
        "structure": {
            "topics": {"count": recipe.topic_count, "media_rich": True},
            "assets": {"images": recipe.topic_count * recipe.images_per_topic} if recipe.generate_images else {},
        }
    }

@router.post("/workflow-enabled/preview")
def preview_workflow_enabled(
    recipe: WorkflowEnabledContentRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview workflow-enabled content dataset."""
    return {
        "estimate": {
            "workflows": {
                "review": recipe.include_review,
                "translation": recipe.include_translation,
                "approval": recipe.include_approval,
            }
        },
        "structure": {
            "workflows": {
                "reviewers": len(recipe.reviewers),
                "target_languages": len(recipe.target_languages),
            }
        }
    }

@router.post("/output-optimized/preview")
def preview_output_optimized(
    recipe: OutputOptimizedRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview output-optimized content dataset."""
    return {
        "estimate": {
            "output_format": recipe.output_format,
        },
        "structure": {
            "optimization": {
                "format": recipe.output_format,
                "options": recipe.optimization_options,
            }
        }
    }
