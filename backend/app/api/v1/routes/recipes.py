from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, db_session
from app.jobs import crud
from app.jobs.crud_recipes import (
    create_saved_recipe,
    get_saved_recipe,
    get_saved_recipes,
    update_saved_recipe,
    delete_saved_recipe,
    increment_recipe_usage,
)
from app.services.recipe_catalog_service import get_recipe_catalog
from app.services.recipe_sample_preview_service import get_recipe_sample_preview

router = APIRouter(prefix="/recipes", tags=["recipes"])

class SavedRecipeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    recipe_config: dict
    is_public: bool = False
    tags: List[str] = []

class SavedRecipeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


@router.get("/catalog")
def recipe_catalog(
    search: Optional[str] = Query(None, description="Search recipe id, title, description, or tags"),
    category: Optional[str] = Query(None, description="Filter by category id"),
    featured_track: Optional[str] = Query(None, description="Filter by featured track id"),
    user: UserIdentity = CurrentUser,
):
    del user
    payload = get_recipe_catalog()
    entries = list(payload.get("entries") or [])

    search_text = (search or "").strip().lower()
    if search_text:
        entries = [
            entry
            for entry in entries
            if search_text in " ".join(
                [
                    str(entry.get("id") or ""),
                    str(entry.get("title") or ""),
                    str(entry.get("description") or ""),
                    " ".join(str(tag) for tag in entry.get("tags") or []),
                ]
            ).lower()
        ]

    if category:
        entries = [entry for entry in entries if entry.get("category") == category]

    if featured_track:
        entries = [
            entry
            for entry in entries
            if featured_track in (entry.get("featured_tracks") or [])
        ]

    payload["entries"] = entries
    payload["total_count"] = len(entries)
    return payload


@router.get("/catalog/samples/{recipe_id}")
def recipe_catalog_sample(recipe_id: str, user: UserIdentity = CurrentUser):
    del user
    sample = get_recipe_sample_preview(recipe_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"No sample preview available for recipe '{recipe_id}'")
    xml, summary = sample
    return {"recipe_id": recipe_id, "full_example_xml": xml, "expected_result": summary}


@router.post("/save")
def save_recipe(
    recipe: SavedRecipeCreate,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Save a recipe configuration for reuse."""
    try:
        saved_recipe = create_saved_recipe(
            session,
            name=recipe.name,
            description=recipe.description,
            recipe_config=recipe.recipe_config,
            user_id=user.id,
            is_public=recipe.is_public,
            tags=recipe.tags,
        )
        session.commit()
        return {
            "id": saved_recipe.id,
            "name": saved_recipe.name,
            "message": "Recipe saved successfully",
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save recipe: {str(e)}")

@router.get("")
def list_recipes(
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
    include_public: bool = True,
    tags: Optional[str] = None,
    search: Optional[str] = None,
):
    """List saved recipes (user's recipes + public recipes)."""
    tag_list = tags.split(",") if tags else None
    
    recipes = get_saved_recipes(
        session,
        user_id=user.id,
        include_public=include_public,
        tags=tag_list,
        search=search,
    )
    
    return {
        "recipes": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_public": r.is_public,
                "tags": r.tags,
                "usage_count": r.usage_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": r.user_id,
                "is_owner": r.user_id == user.id,
            }
            for r in recipes
        ]
    }

@router.get("/{recipe_id}")
def get_recipe(
    recipe_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Get a specific saved recipe."""
    recipe = get_saved_recipe(session, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Check access
    if not recipe.is_public and recipe.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "recipe_config": recipe.recipe_config,
        "is_public": recipe.is_public,
        "tags": recipe.tags,
        "usage_count": recipe.usage_count,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
        "user_id": recipe.user_id,
        "is_owner": recipe.user_id == user.id,
    }

@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: str,
    updates: SavedRecipeUpdate,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Update a saved recipe."""
    recipe = get_saved_recipe(session, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    if recipe.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        updated = update_saved_recipe(
            session,
            recipe_id,
            name=updates.name,
            description=updates.description,
            is_public=updates.is_public,
            tags=updates.tags,
        )
        session.commit()
        return {
            "id": updated.id,
            "name": updated.name,
            "message": "Recipe updated successfully",
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to update recipe: {str(e)}")

@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Delete a saved recipe."""
    recipe = get_saved_recipe(session, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    if recipe.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        delete_saved_recipe(session, recipe_id)
        session.commit()
        return {"message": "Recipe deleted successfully"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to delete recipe: {str(e)}")

@router.post("/{recipe_id}/use")
def use_recipe(
    recipe_id: str,
    user: UserIdentity = CurrentUser,
    session: Session = Depends(db_session),
):
    """Use a saved recipe (increments usage count)."""
    recipe = get_saved_recipe(session, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Check access
    if not recipe.is_public and recipe.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Increment usage count
    increment_recipe_usage(session, recipe_id)
    session.commit()
    session.refresh(recipe)

    return {
        "id": recipe.id,
        "recipe_config": recipe.recipe_config,
        "usage_count": recipe.usage_count,
    }
