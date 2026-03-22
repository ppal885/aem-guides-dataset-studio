from sqlalchemy.orm import Session
from typing import Optional, List
from app.jobs.models import SavedRecipe
from datetime import datetime

def create_saved_recipe(
    session: Session,
    name: str,
    recipe_config: dict,
    user_id: str,
    description: Optional[str] = None,
    is_public: bool = False,
    tags: Optional[List[str]] = None,
) -> SavedRecipe:
    """Create a new saved recipe."""
    recipe = SavedRecipe(
        name=name,
        description=description,
        recipe_config=recipe_config,
        user_id=user_id,
        is_public=is_public,
        tags=tags or [],
    )
    session.add(recipe)
    return recipe

def get_saved_recipe(session: Session, recipe_id: str) -> Optional[SavedRecipe]:
    """Get a saved recipe by ID."""
    return session.query(SavedRecipe).filter(SavedRecipe.id == recipe_id).first()

def get_saved_recipes(
    session: Session,
    user_id: str,
    include_public: bool = True,
    tags: Optional[List[str]] = None,
    search: Optional[str] = None,
) -> List[SavedRecipe]:
    """Get saved recipes for a user."""
    query = session.query(SavedRecipe)
    
    # Filter by user or public
    if include_public:
        query = query.filter(
            (SavedRecipe.user_id == user_id) | (SavedRecipe.is_public == True)
        )
    else:
        query = query.filter(SavedRecipe.user_id == user_id)
    
    # Search by name/description
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (SavedRecipe.name.ilike(search_term)) |
            (SavedRecipe.description.ilike(search_term))
        )
    
    # Filter by tags
    if tags:
        for tag in tags:
            query = query.filter(SavedRecipe.tags.contains([tag]))
    
    return query.order_by(SavedRecipe.created_at.desc()).all()

def update_saved_recipe(
    session: Session,
    recipe_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_public: Optional[bool] = None,
    tags: Optional[List[str]] = None,
) -> SavedRecipe:
    """Update a saved recipe."""
    recipe = get_saved_recipe(session, recipe_id)
    if not recipe:
        raise ValueError("Recipe not found")
    
    if name is not None:
        recipe.name = name
    if description is not None:
        recipe.description = description
    if is_public is not None:
        recipe.is_public = is_public
    if tags is not None:
        recipe.tags = tags
    
    recipe.updated_at = datetime.utcnow()
    return recipe

def delete_saved_recipe(session: Session, recipe_id: str) -> None:
    """Delete a saved recipe."""
    recipe = get_saved_recipe(session, recipe_id)
    if recipe:
        session.delete(recipe)

def increment_recipe_usage(session: Session, recipe_id: str) -> SavedRecipe:
    """Increment usage count for a recipe using atomic update to prevent race conditions."""
    from sqlalchemy import update
    
    result = session.execute(
        update(SavedRecipe)
        .where(SavedRecipe.id == recipe_id)
        .values(usage_count=SavedRecipe.usage_count + 1)
    )
    
    if result.rowcount == 0:
        raise ValueError("Recipe not found")
    
    session.flush()
    recipe = get_saved_recipe(session, recipe_id)
    return recipe
