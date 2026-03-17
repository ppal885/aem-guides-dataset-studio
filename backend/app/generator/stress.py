"""
Stress recipe family - large content, many topicrefs, deep hierarchy, large keyscope.

Thin wrappers over existing stress generators.
"""
from typing import Dict

from app.generator.heavy_content import generate_heavy_topics_dataset
from app.generator.map_stress import generate_map_parse_stress_dataset
from app.generator.keyscope_demo import generate_keyscope_demo_dataset
from app.jobs.schemas import DatasetConfig


def generate_stress_topic_large_content(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Stress: topic with large content (tables, codeblocks)."""
    return generate_heavy_topics_dataset(
        config, base_path,
        topic_count=5,
        tables_per_topic=10,
        codeblocks_per_topic=5,
        **kwargs
    )


def generate_stress_map_100_topicrefs(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Stress: map with 100 topicrefs."""
    return generate_map_parse_stress_dataset(
        config, base_path,
        map_count=1,
        topicrefs_per_map=100,
        **kwargs
    )


def generate_stress_deep_map_hierarchy(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Stress: deep nested map hierarchy."""
    return generate_map_parse_stress_dataset(
        config, base_path,
        map_count=5,
        topicrefs_per_map=20,
        **kwargs
    )


def generate_stress_large_keyscope_map(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Stress: large keyscope map. Uses keyscope_demo (minimal stress)."""
    return generate_keyscope_demo_dataset(config, base_path, id_prefix, include_qualified_keyrefs=True, **kwargs)


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["map", "topicref", "topic", "keyscope", "keydef"],
        "scenario_types": ["STRESS", "SCALE"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": "positive",
        "complexity": "stress",
        "output_scale": "stress",
        "module": "app.generator.stress",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("stress.topic_large_content", "Topic Large Content", "Stress: topic with large content.", "generate_stress_topic_large_content",
          ["STRESS", "HEAVY", "CONTENT"], ["stress test", "large topic", "performance"], ["minimal repro"]),
    _spec("stress.map_100_topicrefs", "Map 100 Topicrefs", "Stress: map with 100 topicrefs.", "generate_stress_map_100_topicrefs",
          ["STRESS", "MAP", "TOPICREF"], ["stress test", "many topicrefs", "map scale"], ["minimal repro"]),
    _spec("stress.deep_map_hierarchy", "Deep Map Hierarchy", "Stress: deep nested map hierarchy.", "generate_stress_deep_map_hierarchy",
          ["STRESS", "MAP", "HIERARCHY"], ["stress test", "deep hierarchy"], ["minimal repro"]),
    _spec("stress.large_keyscope_map", "Large Keyscope Map", "Stress: large keyscope map.", "generate_stress_large_keyscope_map",
          ["STRESS", "KEYSCOPE", "KEYDEF"], ["stress test", "keyscope", "key resolution"], ["minimal repro"]),
]
