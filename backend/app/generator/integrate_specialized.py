"""
Integration functions for specialized recipe types.

This module provides integration functions that can be called from the main
generation function to handle specialized recipe types.
"""

from typing import Dict
from app.generator.specialized import (
    generate_task_topics_dataset,
    generate_concept_topics_dataset,
    generate_reference_topics_dataset,
    generate_glossary_dataset,
    generate_bookmap_dataset,
)
from app.generator.media import generate_media_rich_dataset
from app.generator.workflows import generate_workflow_enabled_dataset
from app.generator.output_optimization import optimize_dataset_for_output
from app.generator.advanced_relationships import generate_advanced_relationship_dataset
from app.generator.performance_scale import generate_performance_test_dataset, PerformanceMetrics
from app.generator.keyscope_demo import generate_keyscope_demo_dataset
from app.generator.keyword_metadata import generate_keyword_metadata_dataset


def handle_specialized_recipe(recipe, config, base: str, files: Dict[str, bytes], rand) -> Dict[str, bytes]:
    """
    Handle specialized recipe types and add generated files.
    
    Args:
        recipe: Recipe object (one of the specialized recipe types)
        config: DatasetConfig object
        base: Base path for dataset
        files: Existing files dictionary to update
        rand: Random number generator
    
    Returns:
        Updated files dictionary
    """
    if recipe.type == "task_topics":
        task_files = generate_task_topics_dataset(
            config,
            base,
            topic_count=recipe.topic_count,
            steps_per_task=recipe.steps_per_task,
            rand=rand,
        )
        files.update(task_files)
    
    elif recipe.type == "concept_topics":
        concept_files = generate_concept_topics_dataset(
            config,
            base,
            topic_count=recipe.topic_count,
            sections_per_concept=recipe.sections_per_concept,
            rand=rand,
        )
        files.update(concept_files)
    
    elif recipe.type == "reference_topics":
        ref_files = generate_reference_topics_dataset(
            config,
            base,
            topic_count=recipe.topic_count,
            properties_per_ref=recipe.properties_per_ref,
            rand=rand,
        )
        files.update(ref_files)
    
    elif recipe.type == "glossary_pack":
        glossary_files = generate_glossary_dataset(
            config,
            base,
            entry_count=recipe.entry_count,
            rand=rand,
        )
        files.update(glossary_files)
    
    elif recipe.type == "bookmap_structure":
        bookmap_files = generate_bookmap_dataset(
            config,
            base,
            chapter_count=recipe.chapter_count,
            topics_per_chapter=recipe.topics_per_chapter,
            rand=rand,
        )
        files.update(bookmap_files)
    
    elif recipe.type == "media_rich_content":
        media_files = generate_media_rich_dataset(
            config,
            base,
            topic_count=recipe.topic_count,
            images_per_topic=recipe.images_per_topic,
            generate_images=recipe.generate_images,
            rand=rand,
        )
        files.update(media_files)
    
    elif recipe.type == "workflow_enabled_content":
        # Generate base content first (from base_recipe)
        # Then add workflow metadata
        content_paths = [path for path in files.keys() if path.endswith('.dita')]
        workflow_files = generate_workflow_enabled_dataset(
            config,
            base,
            content_paths=content_paths,
            include_review=recipe.include_review,
            include_translation=recipe.include_translation,
            include_approval=recipe.include_approval,
            reviewers=recipe.reviewers,
            target_languages=recipe.target_languages,
            rand=rand,
        )
        files.update(workflow_files)
    
    elif recipe.type == "output_optimized":
        # Optimize existing files
        files = optimize_dataset_for_output(
            config,
            base,
            files,
            output_format=recipe.output_format,
            optimization_options=recipe.optimization_options,
            rand=rand,
        )
    
    elif recipe.type == "advanced_relationships":
        rel_files = generate_advanced_relationship_dataset(
            config,
            base,
            topic_count=recipe.topic_count,
            relationship_patterns=recipe.relationship_patterns,
            rand=rand,
        )
        files.update(rel_files)
    
    elif recipe.type == "large_scale":
        scale_files, perf_metrics = generate_performance_test_dataset(
            config,
            base,
            test_type="large_scale",
            test_params={
                "topic_count": recipe.topic_count,
                "batch_size": recipe.batch_size,
            },
            rand=rand,
        )
        files.update(scale_files)
        # Store metrics in files metadata (can be added to manifest later)
        if not hasattr(config, '_performance_metrics'):
            config._performance_metrics = {}
        config._performance_metrics[recipe.type] = perf_metrics
    
    elif recipe.type == "deep_hierarchy":
        hierarchy_files, perf_metrics = generate_performance_test_dataset(
            config,
            base,
            test_type="deep_hierarchy",
            test_params={
                "depth": recipe.depth,
                "children_per_level": recipe.children_per_level,
            },
            rand=rand,
        )
        files.update(hierarchy_files)
        if not hasattr(config, '_performance_metrics'):
            config._performance_metrics = {}
        config._performance_metrics[recipe.type] = perf_metrics
    
    elif recipe.type == "wide_branching":
        branching_files, perf_metrics = generate_performance_test_dataset(
            config,
            base,
            test_type="wide_branching",
            test_params={
                "root_topics": recipe.root_topics,
                "children_per_root": recipe.children_per_root,
            },
            rand=rand,
        )
        files.update(branching_files)
        if not hasattr(config, '_performance_metrics'):
            config._performance_metrics = {}
        config._performance_metrics[recipe.type] = perf_metrics
    
    elif recipe.type == "keyscope_demo":
        keyscope_files = generate_keyscope_demo_dataset(
            config,
            base,
            id_prefix=recipe.id_prefix,
            include_qualified_keyrefs=recipe.include_qualified_keyrefs,
            pretty_print=recipe.pretty_print,
        )
        files.update(keyscope_files)
    
    elif recipe.type == "keyword_metadata":
        keyword_metadata_files = generate_keyword_metadata_dataset(
            config,
            base,
            id_prefix=recipe.id_prefix,
            num_keywords=recipe.num_keywords,
            num_categories=recipe.num_categories,
            num_topics=recipe.num_topics,
            pretty_print=recipe.pretty_print,
        )
        files.update(keyword_metadata_files)
    
    return files
