from typing import Literal
from app.jobs.schemas import (
    DatasetConfig,
    IncrementalTopicrefMapsRecipe,
    HeavyTopicsTablesCodeblocksRecipe,
    CustomerReusePackRecipe,
    MapParseStressRecipe,
    Recipe,
)

RECIPE_PRESETS = {
    "performance_test_small": {
        "name": "Performance Test (Small)",
        "description": "Small dataset for quick performance testing - 5 maps with 10-1000 topicrefs",
        "config": {
            "recipes": [
                {
                    "type": "incremental_topicref_maps",
                    "pool_size": 1000,
                    "map_topicref_counts": [10, 50, 100, 500, 1000],
                    "pretty_print": True,
                    "deep_folders": False,
                }
            ]
        }
    },
    "performance_test_large": {
        "name": "Performance Test (Large)",
        "description": "Large dataset for stress testing - 5 maps with 1k-5k topicrefs",
        "config": {
            "recipes": [
                {
                    "type": "incremental_topicref_maps",
                    "pool_size": 5000,
                    "map_topicref_counts": [1000, 2000, 3000, 4000, 5000],
                    "pretty_print": True,
                    "deep_folders": False,
                }
            ]
        }
    },
    "heavy_content_test": {
        "name": "Heavy Content Test",
        "description": "Topics with tables and codeblocks for content processing tests",
        "config": {
            "recipes": [
                {
                    "type": "heavy_topics_tables_codeblocks",
                    "topic_count": 100,
                    "tables_per_topic": 5,
                    "codeblocks_per_topic": 5,
                    "table_cols": 4,
                    "table_rows": 10,
                    "code_lines_per_codeblock": 20,
                    "include_map": True,
                    "map_topicref_count": 100,
                    "pretty_print": True,
                    "windows_safe_paths": True,
                }
            ]
        }
    },
    "customer_reuse_basic": {
        "name": "Customer Reuse (Basic)",
        "description": "Basic customer reuse pattern with shared topics",
        "config": {
            "recipes": [
                {
                    "type": "customer_reuse_pack",
                    "remove_map_count": 5,
                    "shared_topics": 50,
                    "topic_references_per_map": 20,
                    "key_definitions": 30,
                    "key_groups": 3,
                    "external_references": 10,
                }
            ]
        }
    },
    "quick_smoke_test": {
        "name": "Quick Smoke Test",
        "description": "Minimal dataset for quick validation - 1 map, 10 topics",
        "config": {
            "recipes": [
                {
                    "type": "incremental_topicref_maps",
                    "pool_size": 10,
                    "map_topicref_counts": [10],
                    "pretty_print": True,
                    "deep_folders": False,
                }
            ]
        }
    },
}

def get_preset(preset_id: str) -> dict | None:
    """Get a recipe preset by ID."""
    return RECIPE_PRESETS.get(preset_id)

def list_presets() -> list[dict]:
    """List all available recipe presets."""
    return [
        {"id": preset_id, "name": preset["name"], "description": preset["description"]}
        for preset_id, preset in RECIPE_PRESETS.items()
    ]

def apply_preset(preset_id: str, base_config: dict | None = None) -> dict:
    """Apply a preset to a base configuration."""
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError(f"Preset '{preset_id}' not found")
    
    config = base_config.copy() if base_config else {}
    preset_config = preset["config"].copy()
    
    if "recipes" in config:
        config["recipes"].extend(preset_config.get("recipes", []))
    else:
        config["recipes"] = preset_config.get("recipes", [])
    
    for key, value in preset_config.items():
        if key != "recipes":
            config[key] = value
    
    return config
