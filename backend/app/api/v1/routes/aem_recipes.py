from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.core.auth import UserIdentity, CurrentUser
from app.db.session import Session, db_session

router = APIRouter(prefix="/aem-recipes", tags=["aem-recipes"])

class RelationshipTableRecipeRequest(BaseModel):
    topic_count: int = 100
    relationship_types: List[str] = ["next", "previous", "related"]
    relationship_density: float = 0.3
    include_map: bool = True
    pretty_print: bool = True

class LocalizedContentRecipeRequest(BaseModel):
    base_recipe: dict
    source_language: str = "en"
    target_languages: List[str] = ["es", "fr", "de"]
    include_translation_metadata: bool = True

class ConrefPackRecipeRequest(BaseModel):
    topic_count: int = 50
    reusable_elements_per_topic: int = 3
    conref_density: float = 0.3
    include_map: bool = True
    pretty_print: bool = True

class ConditionalContentRecipeRequest(BaseModel):
    topic_count: int = 50
    audiences: List[str] = ["admin", "user", "developer"]
    platforms: List[str] = ["windows", "mac", "linux"]
    products: List[str] = ["product-a", "product-b"]
    generate_ditaval: bool = True
    ditaval_profiles: List[str] = ["admin-windows", "user-all"]
    include_map: bool = True
    pretty_print: bool = True

@router.post("/relationship-table/preview")
def preview_relationship_table(
    recipe: RelationshipTableRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview relationship table dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "relationships": int(recipe.topic_count * recipe.topic_count * recipe.relationship_density),
        },
        "structure": {
            "topics": {"count": recipe.topic_count},
            "maps": [{"name": "relationship_table.ditamap", "has_reltable": True}],
        }
    }

@router.post("/conref/preview")
def preview_conref_pack(
    recipe: ConrefPackRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview conref pack dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "conrefs": int(recipe.topic_count * recipe.conref_density * recipe.reusable_elements_per_topic),
        },
        "structure": {
            "topics": {"count": recipe.topic_count, "reusable_elements": recipe.reusable_elements_per_topic},
            "maps": [{"name": "conref_map.ditamap"}],
        }
    }

@router.post("/conditional/preview")
def preview_conditional_content(
    recipe: ConditionalContentRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview conditional content dataset."""
    return {
        "estimate": {
            "topics": recipe.topic_count,
            "maps": 1 if recipe.include_map else 0,
            "ditaval_files": len(recipe.ditaval_profiles) if recipe.generate_ditaval else 0,
        },
        "structure": {
            "topics": {"count": recipe.topic_count, "conditional": True},
            "profiles": recipe.ditaval_profiles,
        }
    }

@router.post("/localized/preview")
def preview_localized_content(
    recipe: LocalizedContentRecipeRequest,
    user: UserIdentity = CurrentUser,
):
    """Preview localized content dataset."""
    return {
        "estimate": {
            "languages": len(recipe.target_languages) + 1,  # +1 for source
            "language_copies": len(recipe.target_languages),
        },
        "structure": {
            "source_language": recipe.source_language,
            "target_languages": recipe.target_languages,
            "translation_metadata": recipe.include_translation_metadata,
        }
    }
