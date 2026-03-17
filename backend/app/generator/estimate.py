"""Estimate counts for dataset generation."""
from typing import NamedTuple
from app.jobs.schemas import DatasetConfig


class EstimateCounts(NamedTuple):
    """Estimated counts for dataset generation."""
    topics: int
    maps: int
    xrefs: int
    topicrefs: int
    keydefs: int


def estimate_counts(config: DatasetConfig) -> EstimateCounts:
    """
    Estimate the counts of various elements in the dataset.
    
    This is a simplified estimation. In production, this would
    calculate based on the actual recipe configurations.
    """
    topics = 0
    maps = 0
    xrefs = 0
    topicrefs = 0
    keydefs = 0
    
    for recipe in config.recipes:
        recipe_type = recipe.type
        
        if recipe_type == "incremental_topicref_maps":
            # Estimate based on map_topicref_counts
            if hasattr(recipe, 'map_topicref_counts'):
                maps += len(recipe.map_topicref_counts)
                topicrefs += sum(recipe.map_topicref_counts)
            if hasattr(recipe, 'pool_size'):
                topics += recipe.pool_size
        
        elif recipe_type == "heavy_topics_tables_codeblocks":
            if hasattr(recipe, 'topic_count'):
                topics += recipe.topic_count
            if hasattr(recipe, 'include_map') and recipe.include_map:
                maps += 1
                if hasattr(recipe, 'map_topicref_count'):
                    topicrefs += recipe.map_topicref_count
        
        elif recipe_type == "customer_reuse_pack":
            if hasattr(recipe, 'remove_map_count'):
                maps += recipe.remove_map_count
            if hasattr(recipe, 'topic_references_per_map'):
                topicrefs += recipe.topic_references_per_map * (recipe.remove_map_count if hasattr(recipe, 'remove_map_count') else 1)
            if hasattr(recipe, 'shared_topics'):
                topics += recipe.shared_topics
            if hasattr(recipe, 'key_definitions'):
                keydefs += recipe.key_definitions
        
        # Add more recipe type estimations as needed
    
    # Estimate xrefs as a percentage of topics
    xrefs = int(topics * 0.3)  # Rough estimate: 30% of topics have xrefs
    
    return EstimateCounts(
        topics=topics,
        maps=maps,
        xrefs=xrefs,
        topicrefs=topicrefs,
        keydefs=keydefs,
    )
