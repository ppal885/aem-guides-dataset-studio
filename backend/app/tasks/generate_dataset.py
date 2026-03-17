"""Dataset generation task."""
from typing import Dict, Optional, Callable
from app.jobs.schemas import DatasetConfig, Recipe
from pydantic import ValidationError
import random


def run_generate_dataset(
    config: Dict, 
    job_id: str, 
    stream_callback: Optional[Callable[[Dict[str, bytes]], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[str, bytes]:
    """
    Generate dataset based on configuration.
    
    Args:
        config: Dataset configuration dictionary
        job_id: Job ID for tracking
        stream_callback: Optional callback for streaming batches to storage
        progress_callback: Optional callback(progress_percent, files_generated, current_stage) for progress updates
        
    Returns:
        Dictionary mapping file paths to file contents
    """
    import json
    from datetime import datetime
    
    # Parse config dict into DatasetConfig object
    dataset_config = DatasetConfig.model_validate(config)
    
    # Initialize random generator with seed
    seed_value = dataset_config.seed if isinstance(dataset_config.seed, (int, str)) else hash(str(dataset_config.seed))
    rand = random.Random(seed_value)
    
    # Base path for files
    base = dataset_config.root_folder.strip('/') if dataset_config.root_folder else "dataset"
    
    # Estimate total files for progress tracking
    total_files_estimated = 0
    for recipe in dataset_config.recipes:
        recipe_type = recipe.type
        if hasattr(recipe, 'topic_count'):
            total_files_estimated += recipe.topic_count
        elif recipe_type == "glossary_pack" and hasattr(recipe, 'entry_count'):
            total_files_estimated += recipe.entry_count
        elif recipe_type == "bookmap_structure":
            if hasattr(recipe, 'chapter_count') and hasattr(recipe, 'topics_per_chapter'):
                total_files_estimated += recipe.chapter_count * recipe.topics_per_chapter
        elif recipe_type == "deep_hierarchy":
            # Calculate: sum(children_per_level^level for level 0 to depth) + maps if included
            depth = recipe.depth if hasattr(recipe, 'depth') else 10
            children_per_level = recipe.children_per_level if hasattr(recipe, 'children_per_level') else 5
            include_maps = recipe.include_maps if hasattr(recipe, 'include_maps') else True
            topic_count = sum(children_per_level ** level for level in range(depth + 1))
            total_files_estimated += topic_count
            if include_maps:
                total_files_estimated += depth  # One map per level
        elif recipe_type == "wide_branching":
            # Calculate: root_topics + (root_topics * children_per_root) + root_topics maps
            root_topics = recipe.root_topics if hasattr(recipe, 'root_topics') else 10
            children_per_root = recipe.children_per_root if hasattr(recipe, 'children_per_root') else 1000
            total_files_estimated += root_topics  # Root topics
            total_files_estimated += root_topics * children_per_root  # Child topics
            total_files_estimated += root_topics  # Maps (one per root)
        elif recipe_type == "map_parse_stress":
            # Calculate: (map_count * topicrefs_per_map) topics + map_count maps
            map_count = recipe.map_count if hasattr(recipe, 'map_count') else 10
            topicrefs_per_map = recipe.topicrefs_per_map if hasattr(recipe, 'topicrefs_per_map') else 1000
            total_files_estimated += map_count * topicrefs_per_map  # Topics
            total_files_estimated += map_count  # Maps
        elif recipe_type == "conrefend_cyclic_duplicate_id":
            total_files_estimated += 4  # 2 topics, 1 map, 1 readme
        elif recipe_type == "dita_conref_title_dataset_recipe":
            topic_count = recipe.topic_count if hasattr(recipe, 'topic_count') else 10
            total_files_estimated += topic_count + 2  # topics + variables.dita + manifest
        elif recipe_type == "dita_conref_keyref_dataset_recipe":
            topic_count = recipe.topic_count if hasattr(recipe, 'topic_count') else 15
            total_files_estimated += topic_count + 3  # topics + keydef-map + variables.dita + manifest
        elif recipe_type == "dita_subject_scheme_dataset_recipe":
            valid_count = recipe.valid_count if hasattr(recipe, 'valid_count') else 10
            invalid_count = recipe.invalid_count if hasattr(recipe, 'invalid_count') else 10
            total_files_estimated += valid_count + invalid_count + 3  # topics + 2 maps + manifest
        elif recipe_type == "dita_glossary_abbrev_dataset_recipe":
            entry_count = recipe.entry_count if hasattr(recipe, 'entry_count') else 15
            usage_count = recipe.usage_topic_count if hasattr(recipe, 'usage_topic_count') else 10
            total_files_estimated += entry_count + usage_count + 2  # entries + topics + map + manifest
        elif recipe_type == "map_cyclic":
            total_files_estimated += 5  # 2 topics, 2 maps, 1 readme
        elif recipe_type == "heavy_conditional_topic_6000_lines":
            total_files_estimated += 3  # 1 topic, 1 ditaval, 1 manifest
        elif recipe_type == "keyref_nested_keydef_chain_map_to_map_to_topic":
            total_files_estimated += 6  # 2 maps, 2 topics, README, manifest
        else:
            total_files_estimated += 10  # Default estimate
    
    # Notify progress callback of start
    if progress_callback:
        progress_callback(0, 0, "Starting generation")
    
    # Accumulate all generated files
    files = {}
    files_generated = 0
    
    # Helper function to update progress
    def update_progress(stage: str):
        if progress_callback and total_files_estimated > 0:
            progress_percent = min(95, int((files_generated / total_files_estimated) * 95))
            progress_callback(progress_percent, files_generated, stage)
        elif progress_callback:
            recipe_progress = int(((recipe_idx + 1) / len(dataset_config.recipes)) * 90)
            progress_callback(recipe_progress, files_generated, stage)
    
    # Process each recipe
    for recipe_idx, recipe in enumerate(dataset_config.recipes):
        recipe_type = recipe.type
        stage_name = recipe_type.replace('_', ' ').title()
        
        # Update progress: starting recipe
        if progress_callback:
            update_progress(f"Generating {stage_name}")
        
        try:
            if recipe_type == "task_topics":
                from app.generator.specialized import generate_task_topics_dataset
                recipe_files = generate_task_topics_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    steps_per_task=recipe.steps_per_task if hasattr(recipe, 'steps_per_task') else 3,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "concept_topics":
                from app.generator.specialized import generate_concept_topics_dataset
                recipe_files = generate_concept_topics_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    sections_per_concept=recipe.sections_per_concept if hasattr(recipe, 'sections_per_concept') else 3,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "reference_topics":
                from app.generator.specialized import generate_reference_topics_dataset
                recipe_files = generate_reference_topics_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    properties_per_ref=recipe.properties_per_ref if hasattr(recipe, 'properties_per_ref') else 5,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "glossary_pack":
                from app.generator.specialized import generate_glossary_dataset
                recipe_files = generate_glossary_dataset(
                    dataset_config, base,
                    entry_count=recipe.entry_count if hasattr(recipe, 'entry_count') else 50,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "bookmap_structure":
                from app.generator.specialized import generate_bookmap_dataset
                recipe_files = generate_bookmap_dataset(
                    dataset_config, base,
                    chapter_count=recipe.chapter_count if hasattr(recipe, 'chapter_count') else 5,
                    topics_per_chapter=recipe.topics_per_chapter if hasattr(recipe, 'topics_per_chapter') else 10,
                    include_frontmatter=recipe.include_frontmatter if hasattr(recipe, 'include_frontmatter') else True,
                    include_backmatter=recipe.include_backmatter if hasattr(recipe, 'include_backmatter') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "relationship_table":
                from app.generator.relationship_tables import generate_relationship_table_dataset
                recipe_files = generate_relationship_table_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    relationship_types=recipe.relationship_types if hasattr(recipe, 'relationship_types') else ["next", "prev", "related"],
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "conref_pack":
                from app.generator.conrefs import generate_conref_pack
                recipe_files = generate_conref_pack(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    conref_density=recipe.conref_density if hasattr(recipe, 'conref_density') else 0.3,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "conrefend_cyclic_duplicate_id":
                from app.generator.conrefend_cyclic import generate_conrefend_cyclic_duplicate_id
                recipe_files = generate_conrefend_cyclic_duplicate_id(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "dita_conref_title_dataset_recipe":
                from app.generator.conref_title import generate_dita_conref_title_dataset
                recipe_files = generate_dita_conref_title_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 10,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "dita_conref_keyref_dataset_recipe":
                from app.generator.conref_keyref import generate_dita_conref_keyref_dataset
                recipe_files = generate_dita_conref_keyref_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 15,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "dita_subject_scheme_dataset_recipe":
                from app.generator.subject_scheme import generate_dita_subject_scheme_dataset
                recipe_files = generate_dita_subject_scheme_dataset(
                    dataset_config, base,
                    valid_count=recipe.valid_count if hasattr(recipe, 'valid_count') else 10,
                    invalid_count=recipe.invalid_count if hasattr(recipe, 'invalid_count') else 10,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "dita_glossary_abbrev_dataset_recipe":
                from app.generator.glossary_abbrev import generate_dita_glossary_abbrev_dataset
                recipe_files = generate_dita_glossary_abbrev_dataset(
                    dataset_config, base,
                    entry_count=recipe.entry_count if hasattr(recipe, 'entry_count') else 15,
                    usage_topic_count=recipe.usage_topic_count if hasattr(recipe, 'usage_topic_count') else 10,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "map_cyclic":
                from app.generator.map_cyclic import generate_map_cyclic
                recipe_files = generate_map_cyclic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "keyref_nested_keydef_chain_map_to_map_to_topic":
                from app.generator.nested_keydef_chain import generate_keyref_nested_keydef_chain_map_to_map_to_topic
                recipe_files = generate_keyref_nested_keydef_chain_map_to_map_to_topic(
                    dataset_config, base,
                    root_map_name=recipe.root_map_name if hasattr(recipe, 'root_map_name') else "map_a.ditamap",
                    intermediate_map_name=recipe.intermediate_map_name if hasattr(recipe, 'intermediate_map_name') else "map_b.ditamap",
                    keyword_topic_name=recipe.keyword_topic_name if hasattr(recipe, 'keyword_topic_name') else "topic_c_keywords.dita",
                    consumer_topic_name=recipe.consumer_topic_name if hasattr(recipe, 'consumer_topic_name') else "topic_d_consumer.dita",
                    root_map_title=recipe.root_map_title if hasattr(recipe, 'root_map_title') else "Outer Context Map",
                    intermediate_map_title=recipe.intermediate_map_title if hasattr(recipe, 'intermediate_map_title') else "Static Key Map",
                    keyword_topic_title=recipe.keyword_topic_title if hasattr(recipe, 'keyword_topic_title') else "Keyword Source Topic",
                    consumer_topic_title=recipe.consumer_topic_title if hasattr(recipe, 'consumer_topic_title') else "Consumer Topic",
                    root_to_intermediate_key=recipe.root_to_intermediate_key if hasattr(recipe, 'root_to_intermediate_key') else "staticKeyMap",
                    direct_intermediate_key_name=recipe.direct_intermediate_key_name if hasattr(recipe, 'direct_intermediate_key_name') else "productName",
                    nested_keyword_file_key_name=recipe.nested_keyword_file_key_name if hasattr(recipe, 'nested_keyword_file_key_name') else "keywordFile",
                    nested_keyword_id=recipe.nested_keyword_id if hasattr(recipe, 'nested_keyword_id') else "versionString",
                    consumer_keyrefs=recipe.consumer_keyrefs if hasattr(recipe, 'consumer_keyrefs') else None,
                    include_direct_key_in_root_map=recipe.include_direct_key_in_root_map if hasattr(recipe, 'include_direct_key_in_root_map') else True,
                    include_direct_key_in_intermediate_map=recipe.include_direct_key_in_intermediate_map if hasattr(recipe, 'include_direct_key_in_intermediate_map') else True,
                    include_nested_keyword_topic=recipe.include_nested_keyword_topic if hasattr(recipe, 'include_nested_keyword_topic') else True,
                    include_workaround_notes=recipe.include_workaround_notes if hasattr(recipe, 'include_workaround_notes') else True,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "heavy_conditional_topic_6000_lines":
                from app.generator.heavy_conditional_topic import generate_heavy_conditional_topic_6000_lines
                recipe_files = generate_heavy_conditional_topic_6000_lines(
                    dataset_config, base,
                    topic_id=recipe.topic_id if hasattr(recipe, 'topic_id') else "heavy_conditional_topic_001",
                    title=recipe.title if hasattr(recipe, 'title') else "Enterprise Conditional Processing Heavy Topic",
                    target_lines=recipe.target_lines if hasattr(recipe, 'target_lines') else 6000,
                    section_count=recipe.section_count if hasattr(recipe, 'section_count') else 120,
                    subsections_per_section=recipe.subsections_per_section if hasattr(recipe, 'subsections_per_section') else 4,
                    paragraphs_per_subsection=recipe.paragraphs_per_subsection if hasattr(recipe, 'paragraphs_per_subsection') else 6,
                    include_tables=recipe.include_tables if hasattr(recipe, 'include_tables') else True,
                    include_codeblocks=recipe.include_codeblocks if hasattr(recipe, 'include_codeblocks') else True,
                    include_notes=recipe.include_notes if hasattr(recipe, 'include_notes') else True,
                    include_examples=recipe.include_examples if hasattr(recipe, 'include_examples') else True,
                    include_xrefs=recipe.include_xrefs if hasattr(recipe, 'include_xrefs') else False,
                    include_images=recipe.include_images if hasattr(recipe, 'include_images') else False,
                    include_ditaval=recipe.include_ditaval if hasattr(recipe, 'include_ditaval') else True,
                    condition_density=recipe.condition_density if hasattr(recipe, 'condition_density') else "high",
                    audience_values=recipe.audience_values if hasattr(recipe, 'audience_values') else None,
                    platform_values=recipe.platform_values if hasattr(recipe, 'platform_values') else None,
                    otherprops_values=recipe.otherprops_values if hasattr(recipe, 'otherprops_values') else None,
                    tables_per_n_sections=recipe.tables_per_n_sections if hasattr(recipe, 'tables_per_n_sections') else 2,
                    codeblocks_per_n_sections=recipe.codeblocks_per_n_sections if hasattr(recipe, 'codeblocks_per_n_sections') else 2,
                    notes_per_n_sections=recipe.notes_per_n_sections if hasattr(recipe, 'notes_per_n_sections') else 3,
                    examples_per_n_sections=recipe.examples_per_n_sections if hasattr(recipe, 'examples_per_n_sections') else 3,
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "conditional_content":
                from app.generator.conditionals import generate_conditional_dataset
                recipe_files = generate_conditional_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    audiences=recipe.audiences if hasattr(recipe, 'audiences') else ["internal", "external"],
                    platforms=recipe.platforms if hasattr(recipe, 'platforms') else ["windows", "linux", "mac"],
                    products=recipe.products if hasattr(recipe, 'products') else ["basic", "pro", "enterprise"],
                    generate_ditaval=recipe.generate_ditaval if hasattr(recipe, 'generate_ditaval') else True,
                    ditaval_profiles=recipe.ditaval_profiles if hasattr(recipe, 'ditaval_profiles') else None,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "media_rich_content":
                from app.generator.media import generate_media_rich_dataset
                recipe_files = generate_media_rich_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    images_per_topic=recipe.images_per_topic if hasattr(recipe, 'images_per_topic') else 3,
                    generate_images=recipe.generate_images if hasattr(recipe, 'generate_images') else True,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "workflow_enabled_content":
                from app.generator.workflows import generate_workflow_enabled_dataset
                # First, generate base content from base_recipe if provided
                base_content_paths = []
                if hasattr(recipe, 'base_recipe') and recipe.base_recipe:
                    # Create a temporary config with just the base recipe
                    base_config = config.copy()
                    base_config['recipes'] = [recipe.base_recipe]
                    # Generate base content
                    base_files = run_generate_dataset(base_config, f"{job_id}-base")
                    files.update(base_files)
                    # Collect content paths for workflow metadata
                    base_content_paths = [path for path in base_files.keys() if path.endswith('.dita')]
                else:
                    # Use existing files if base_recipe not provided
                    base_content_paths = [path for path in files.keys() if path.endswith('.dita')]
                
                # Generate workflow metadata
                workflow_files = generate_workflow_enabled_dataset(
                    dataset_config, base,
                    content_paths=base_content_paths,
                    include_review=recipe.include_review if hasattr(recipe, 'include_review') else True,
                    include_translation=recipe.include_translation if hasattr(recipe, 'include_translation') else True,
                    include_approval=recipe.include_approval if hasattr(recipe, 'include_approval') else True,
                    reviewers=recipe.reviewers if hasattr(recipe, 'reviewers') else None,
                    target_languages=recipe.target_languages if hasattr(recipe, 'target_languages') else None,
                    rand=rand
                )
                files.update(workflow_files)
                files_generated += len(workflow_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "advanced_relationships":
                from app.generator.advanced_relationships import generate_advanced_relationship_dataset
                recipe_files = generate_advanced_relationship_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    relationship_patterns=recipe.relationship_patterns if hasattr(recipe, 'relationship_patterns') else ["hierarchical", "cross_map"],
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "keyscope_demo":
                from app.generator.keyscope_demo import generate_keyscope_demo_dataset
                recipe_files = generate_keyscope_demo_dataset(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "keyscope",
                    include_qualified_keyrefs=recipe.include_qualified_keyrefs if hasattr(recipe, 'include_qualified_keyrefs') else True,
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "keyword_metadata":
                from app.generator.keyword_metadata import generate_keyword_metadata_dataset
                recipe_files = generate_keyword_metadata_dataset(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "keyword",
                    num_keywords=recipe.num_keywords if hasattr(recipe, 'num_keywords') else 50,
                    num_categories=recipe.num_categories if hasattr(recipe, 'num_categories') else 5,
                    num_topics=recipe.num_topics if hasattr(recipe, 'num_topics') else 10,
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "large_scale":
                from app.generator.performance_scale import generate_performance_test_dataset
                # For large_scale, progress is tracked in stream_callback
                # Estimate files for progress tracking
                estimated_files = recipe.topic_count if hasattr(recipe, 'topic_count') else 1000
                recipe_files, _ = generate_performance_test_dataset(
                    dataset_config, base,
                    test_type="large_scale",
                    test_params={
                        "topic_count": recipe.topic_count if hasattr(recipe, 'topic_count') else 1000,
                        "batch_size": recipe.batch_size if hasattr(recipe, 'batch_size') else 100,
                    },
                    rand=rand,
                    stream_callback=stream_callback
                )
                if recipe_files:
                    files.update(recipe_files)
                    files_generated += len(recipe_files)
                else:
                    # If streaming, files_generated is tracked in stream_callback
                    # Estimate based on topic_count
                    files_generated += estimated_files
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "deep_hierarchy":
                from app.generator.performance_scale import generate_performance_test_dataset
                recipe_files, _ = generate_performance_test_dataset(
                    dataset_config, base,
                    test_type="deep_hierarchy",
                    test_params={
                        "depth": recipe.depth if hasattr(recipe, 'depth') else 10,
                        "children_per_level": recipe.children_per_level if hasattr(recipe, 'children_per_level') else 5,
                        "include_maps": recipe.include_maps if hasattr(recipe, 'include_maps') else True,
                    },
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "wide_branching":
                from app.generator.performance_scale import generate_performance_test_dataset
                recipe_files, _ = generate_performance_test_dataset(
                    dataset_config, base,
                    test_type="wide_branching",
                    test_params={
                        "root_topics": recipe.root_topics if hasattr(recipe, 'root_topics') else 10,
                        "children_per_root": recipe.children_per_root if hasattr(recipe, 'children_per_root') else 1000,
                    },
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "incremental_topicref_maps":
                from app.generator.performance_scale import generate_performance_test_dataset
                recipe_files, _ = generate_performance_test_dataset(
                    dataset_config, base,
                    test_type="incremental_topicref_maps",
                    test_params={
                        "pool_size": recipe.pool_size if hasattr(recipe, 'pool_size') else 10000,
                        "map_topicref_counts": recipe.map_topicref_counts if hasattr(recipe, 'map_topicref_counts') else [100, 500, 1000, 2000, 5000],
                        "deep_folders": recipe.deep_folders if hasattr(recipe, 'deep_folders') else True,
                    },
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "heavy_topics_tables_codeblocks":
                from app.generator.heavy_content import generate_heavy_topics_dataset
                recipe_files = generate_heavy_topics_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 100,
                    tables_per_topic=recipe.tables_per_topic if hasattr(recipe, 'tables_per_topic') else 5,
                    codeblocks_per_topic=recipe.codeblocks_per_topic if hasattr(recipe, 'codeblocks_per_topic') else 3,
                    table_cols=recipe.table_cols if hasattr(recipe, 'table_cols') else 10,
                    table_rows=recipe.table_rows if hasattr(recipe, 'table_rows') else 50,
                    code_lines_per_codeblock=recipe.code_lines_per_codeblock if hasattr(recipe, 'code_lines_per_codeblock') else 100,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    map_topicref_count=recipe.map_topicref_count if hasattr(recipe, 'map_topicref_count') else 100,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "customer_reuse_pack":
                from app.generator.customer_reuse import generate_customer_reuse_pack_dataset
                recipe_files = generate_customer_reuse_pack_dataset(
                    dataset_config, base,
                    remove_map_count=recipe.remove_map_count if hasattr(recipe, 'remove_map_count') else 5,
                    shared_topics=recipe.shared_topics if hasattr(recipe, 'shared_topics') else 20,
                    topic_references_per_map=recipe.topic_references_per_map if hasattr(recipe, 'topic_references_per_map') else 10,
                    key_definitions=recipe.key_definitions if hasattr(recipe, 'key_definitions') else 50,
                    key_groups=recipe.key_groups if hasattr(recipe, 'key_groups') else 5,
                    external_references=recipe.external_references if hasattr(recipe, 'external_references') else 10,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "map_parse_stress":
                from app.generator.map_stress import generate_map_parse_stress_dataset
                recipe_files = generate_map_parse_stress_dataset(
                    dataset_config, base,
                    map_count=recipe.map_count if hasattr(recipe, 'map_count') else 10,
                    topicrefs_per_map=recipe.topicrefs_per_map if hasattr(recipe, 'topicrefs_per_map') else 1000,
                    pretty_print=recipe.pretty_print if hasattr(recipe, 'pretty_print') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "localized_content":
                from app.generator.localization import generate_localized_dataset
                # First generate base content from base_recipe
                if hasattr(recipe, 'base_recipe') and recipe.base_recipe:
                    base_config = config.copy()
                    base_config['recipes'] = [recipe.base_recipe]
                    base_content = run_generate_dataset(base_config, f"{job_id}-base")
                    files.update(base_content)
                else:
                    base_content = files
                
                # Generate localized variants
                localized_files = generate_localized_dataset(
                    dataset_config, base,
                    base_content=base_content,
                    source_language=recipe.source_language if hasattr(recipe, 'source_language') else "en",
                    target_languages=recipe.target_languages if hasattr(recipe, 'target_languages') else ["de", "fr", "ja"],
                )
                files.update(localized_files)
                files_generated += len(localized_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "output_optimized":
                from app.generator.output_optimization import optimize_dataset_for_output
                # First generate base content from base_recipe
                if hasattr(recipe, 'base_recipe') and recipe.base_recipe:
                    base_config = config.copy()
                    base_config['recipes'] = [recipe.base_recipe]
                    base_content = run_generate_dataset(base_config, f"{job_id}-base")
                    files.update(base_content)
                else:
                    base_content = files
                
                # Optimize existing files
                optimized_files = optimize_dataset_for_output(
                    dataset_config, base,
                    files=base_content,
                    output_format=recipe.output_format if hasattr(recipe, 'output_format') else "html5",
                    optimization_options=recipe.optimization_options if hasattr(recipe, 'optimization_options') else None,
                    rand=rand
                )
                files.update(optimized_files)
                files_generated += len(optimized_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "hub_spoke_inbound":
                from app.generator.legacy_patterns import generate_hub_spoke_inbound_dataset
                recipe_files = generate_hub_spoke_inbound_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            elif recipe_type == "keydef_heavy":
                from app.generator.legacy_patterns import generate_keydef_heavy_dataset
                recipe_files = generate_keydef_heavy_dataset(
                    dataset_config, base,
                    topic_count=recipe.topic_count if hasattr(recipe, 'topic_count') else 20,
                    keydef_count=recipe.keydef_count if hasattr(recipe, 'keydef_count') else 100,
                    include_map=recipe.include_map if hasattr(recipe, 'include_map') else True,
                    rand=rand
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_topicgroup_basic":
                from app.generator.maps import generate_maps_topicgroup_basic
                recipe_files = generate_maps_topicgroup_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_topicgroup_nested":
                from app.generator.maps import generate_maps_topicgroup_nested
                recipe_files = generate_maps_topicgroup_nested(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_topicref_basic":
                from app.generator.maps import generate_maps_topicref_basic
                recipe_files = generate_maps_topicref_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_nested_topicrefs":
                from app.generator.maps import generate_maps_nested_topicrefs
                recipe_files = generate_maps_nested_topicrefs(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_mapref_basic":
                from app.generator.maps import generate_maps_mapref_basic
                recipe_files = generate_maps_mapref_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_topichead_basic":
                from app.generator.maps import generate_maps_topichead_basic
                recipe_files = generate_maps_topichead_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_reltable_basic":
                from app.generator.maps import generate_maps_reltable_basic
                recipe_files = generate_maps_reltable_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_topicset_basic":
                from app.generator.maps import generate_maps_topicset_basic
                recipe_files = generate_maps_topicset_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")

            elif recipe_type == "maps_navref_basic":
                from app.generator.maps import generate_maps_navref_basic
                recipe_files = generate_maps_navref_basic(
                    dataset_config, base,
                    id_prefix=recipe.id_prefix if hasattr(recipe, 'id_prefix') else "t",
                )
                files.update(recipe_files)
                files_generated += len(recipe_files)
                update_progress(f"Completed {stage_name}")
            
            else:
                # For unsupported recipe types, generate basic topics as fallback
                from app.generator.specialized import generate_task_topics_dataset
                recipe_files = generate_task_topics_dataset(
                    dataset_config, base,
                    topic_count=10,
                    steps_per_task=3,
                    rand=rand
                )
                files.update(recipe_files)
        
        except Exception as e:
            import traceback
            # Log error but continue with other recipes
            print(f"Error processing recipe {recipe_type}: {e}")
            print(traceback.format_exc())
            continue
    
    # If no recipes or no files generated, create at least some basic content
    if not files:
        from app.generator.specialized import generate_task_topics_dataset
        basic_files = generate_task_topics_dataset(
            dataset_config, base,
            topic_count=5,
            steps_per_task=3,
            rand=rand
        )
        files.update(basic_files)
        files_generated += len(basic_files)
    
    # Update progress: finalizing
    if progress_callback:
        progress_callback(95, files_generated, "Finalizing dataset")
    
    # Add README with job info
    readme_content = f"""Dataset Generation Job
====================

Job ID: {job_id}
Generated: {datetime.now().isoformat()}
Dataset Name: {dataset_config.name}
Seed: {dataset_config.seed}

Recipes Processed: {len(dataset_config.recipes)}
Files Generated: {len(files)}

This dataset was generated using the AEM Guides Dataset Studio.
"""
    files["README.txt"] = readme_content.encode('utf-8')
    files_generated += 1
    
    # Add manifest file
    manifest = {
        "job_id": job_id,
        "generated_at": datetime.now().isoformat(),
        "dataset_name": dataset_config.name,
        "seed": str(dataset_config.seed),
        "total_files": len(files),
        "dita_files": len([f for f in files.keys() if f.endswith(('.dita', '.ditamap'))]),
        "recipe_count": len(dataset_config.recipes),
        "status": "completed"
    }
    files["manifest.json"] = json.dumps(manifest, indent=2).encode('utf-8')
    files_generated += 1
    
    # Update progress: completed
    if progress_callback:
        progress_callback(100, files_generated, "Generation complete")
    
    return files