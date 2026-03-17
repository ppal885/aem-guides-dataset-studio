from fastapi import APIRouter, HTTPException
from app.templates.recipe_presets import list_presets, get_preset, apply_preset

router = APIRouter(prefix="/presets", tags=["presets"])

@router.get("")
def list_recipe_presets():
    """List all available recipe presets."""
    return {"presets": list_presets()}

@router.get("/{preset_id}")
def get_recipe_preset(preset_id: str):
    """Get a specific recipe preset."""
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    return preset

@router.post("/{preset_id}/apply")
def apply_recipe_preset(preset_id: str, base_config: dict = None):
    """Apply a preset to a base configuration."""
    try:
        config = apply_preset(preset_id, base_config)
        return {"config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
