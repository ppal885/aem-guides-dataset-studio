"""
Comprehensive test script for all recipe types in the dataset generation system.

This script tests each recipe type to ensure:
1. The recipe can be validated
2. The generator function exists and can be called
3. Files are generated successfully
4. Generated files contain expected content
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.jobs.schemas import DatasetConfig, Recipe
from app.tasks.generate_dataset import run_generate_dataset
from typing import Dict, List, Tuple


# Recipe test configurations
RECIPE_TESTS = {
    "task_topics": {
        "recipe": {
            "type": "task_topics",
            "topic_count": 10,
            "steps_per_task": 3,
            "include_prereq": True,
            "include_result": True,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Task Topics - Generates DITA task topics with procedural steps, prerequisites, and results"
    },
    "concept_topics": {
        "recipe": {
            "type": "concept_topics",
            "topic_count": 10,
            "sections_per_concept": 2,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Concept Topics - Generates DITA concept topics explaining ideas and concepts"
    },
    "reference_topics": {
        "recipe": {
            "type": "reference_topics",
            "topic_count": 10,
            "properties_per_ref": 3,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Reference Topics - Generates DITA reference topics with property tables and structured data"
    },
    "glossary_pack": {
        "recipe": {
            "type": "glossary_pack",
            "entry_count": 10,
            "include_acronyms": True,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Glossary Pack - Generates glossary entries with definitions and optional acronyms"
    },
    "bookmap_structure": {
        "recipe": {
            "type": "bookmap_structure",
            "chapter_count": 3,
            "topics_per_chapter": 2,
            "include_frontmatter": True,
            "include_backmatter": True,
            "pretty_print": True
        },
        "expected_files": ["ditamap"],
        "description": "Bookmap Structure - Generates bookmap with chapters, frontmatter, and backmatter"
    },
    "relationship_table": {
        "recipe": {
            "type": "relationship_table",
            "topic_count": 10,
            "relationship_types": ["next", "previous", "related"],
            "relationship_density": 0.3,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Relationship Table - Generates topics with relationship tables linking related content"
    },
    "conref_pack": {
        "recipe": {
            "type": "conref_pack",
            "topic_count": 10,
            "conref_density": 0.3,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Conref Pack - Generates topics with content references (conrefs) for content reuse"
    },
    "conditional_content": {
        "recipe": {
            "type": "conditional_content",
            "topic_count": 10,
            "audiences": ["admin", "user"],
            "platforms": ["windows", "linux"],
            "products": ["product-a"],
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap", "ditaval"],
        "description": "Conditional Content - Generates topics with conditional processing attributes and DITAVAL files"
    },
    "media_rich_content": {
        "recipe": {
            "type": "media_rich_content",
            "topic_count": 10,
            "images_per_topic": 2,
            "generate_images": False,  # Set to False for faster testing
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Media Rich Content - Generates topics with embedded images and media references"
    },
    "advanced_relationships": {
        "recipe": {
            "type": "advanced_relationships",
            "topic_count": 50,
            "relationship_patterns": ["hierarchical", "cross-map"],
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Advanced Relationships - Generates complex relationship patterns between topics and maps"
    },
    "keyscope_demo": {
        "recipe": {
            "type": "keyscope_demo",
            "id_prefix": "t",
            "include_qualified_keyrefs": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Keyscope Demo - Generates maps and topics demonstrating scoped key resolution"
    },
    "keyword_metadata": {
        "recipe": {
            "type": "keyword_metadata",
            "id_prefix": "t",
            "num_keywords": 5,
            "num_categories": 3,
            "num_topics": 5,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Keyword Metadata - Generates topics with keyword metadata keys and category assignments"
    },
    "incremental_topicref_maps": {
        "recipe": {
            "type": "incremental_topicref_maps",
            "pool_size": 50,
            "map_topicref_counts": [5, 10, 20],
            "pretty_print": True,
            "deep_folders": False
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Incremental Topicref Maps - Generates a pool of topics and multiple maps with varying topicref counts"
    },
    "large_scale": {
        "recipe": {
            "type": "large_scale",
            "topic_count": 1000,  # Minimum for testing
            "batch_size": 100,
            "include_map": False,
            "pretty_print": False
        },
        "expected_files": ["dita"],
        "description": "Large Scale - Generates a large number of topics for performance testing (100k+ topics)"
    },
    "deep_hierarchy": {
        "recipe": {
            "type": "deep_hierarchy",
            "depth": 3,  # Reduced for testing
            "children_per_level": 2,
            "include_maps": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Deep Hierarchy - Generates deeply nested topic hierarchies (10+ levels)"
    },
    "wide_branching": {
        "recipe": {
            "type": "wide_branching",
            "root_topics": 2,
            "children_per_root": 10,  # Minimum for testing
            "include_maps": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Wide Branching - Generates topics with many children per parent (1000+ children)"
    },
    "workflow_enabled_content": {
        "recipe": {
            "type": "workflow_enabled_content",
            "base_recipe": {
                "type": "task_topics",
                "topic_count": 10,
                "steps_per_task": 3,
                "include_prereq": True,
                "include_result": True,
                "include_map": True,
                "pretty_print": True
            },
            "include_review": True,
            "include_translation": True,
            "include_approval": True,
            "reviewers": ["reviewer1", "reviewer2"],
            "target_languages": ["es", "fr"]
        },
        "expected_files": ["dita", "ditamap", "json"],
        "description": "Workflow Enabled Content - Generates content with review, translation, and approval workflow metadata"
    },
    "heavy_topics_tables_codeblocks": {
        "recipe": {
            "type": "heavy_topics_tables_codeblocks",
            "topic_count": 10,
            "tables_per_topic": 2,
            "codeblocks_per_topic": 2,
            "table_cols": 3,
            "table_rows": 5,
            "code_lines_per_codeblock": 10,
            "include_map": True,
            "map_topicref_count": 10,
            "pretty_print": True,
            "windows_safe_paths": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Heavy Topics Tables & Codeblocks - Generates topics with multiple tables and codeblocks for content processing tests"
    },
    "customer_reuse_pack": {
        "recipe": {
            "type": "customer_reuse_pack",
            "remove_map_count": 3,
            "shared_topics": 20,
            "topic_references_per_map": 10,
            "key_definitions": 15,
            "key_groups": 2,
            "external_references": 2
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Customer Reuse Pack - Generates shared topics referenced by multiple maps with key definitions"
    },
    "map_parse_stress": {
        "recipe": {
            "type": "map_parse_stress",
            "map_count": 2,
            "topicrefs_per_map": 20,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Map Parse Stress - Generates maps with many topicrefs to stress test map parsing"
    },
    "hub_spoke_inbound": {
        "recipe": {
            "type": "hub_spoke_inbound",
            "topic_count": 10,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Hub-Spoke Inbound - Generates hub topic with multiple spoke topics referencing it"
    },
    "keydef_heavy": {
        "recipe": {
            "type": "keydef_heavy",
            "topic_count": 10,
            "keydef_count": 5,
            "include_map": True,
            "pretty_print": True
        },
        "expected_files": ["dita", "ditamap"],
        "description": "Keydef Heavy - Generates maps with many key definitions for key resolution testing"
    },
    "localized_content": {
        "recipe": {
            "type": "localized_content",
            "base_recipe": {
                "type": "task_topics",
                "topic_count": 10,
                "steps_per_task": 3,
                "include_prereq": True,
                "include_result": True,
                "include_map": True,
                "pretty_print": True
            },
            "source_language": "en",
            "target_languages": ["es", "fr"],
            "include_translation_metadata": True
        },
        "expected_files": ["dita", "ditamap", "json"],
        "description": "Localized Content - Generates language variants of base content with translation metadata"
    },
    "output_optimized": {
        "recipe": {
            "type": "output_optimized",
            "base_recipe": {
                "type": "task_topics",
                "topic_count": 10,
                "steps_per_task": 3,
                "include_prereq": True,
                "include_result": True,
                "include_map": True,
                "pretty_print": True
            },
            "output_format": "aemsite",
            "optimization_options": {}
        },
        "expected_files": ["dita", "ditamap", "json"],
        "description": "Output Optimized - Optimizes base content for specific output formats (AEM Site, PDF, HTML5, Mobile)"
    }
}


def test_recipe_type(recipe_type: str, test_config: Dict) -> Tuple[bool, str, Dict]:
    """
    Test a single recipe type.
    
    Returns:
        (success: bool, message: str, stats: dict)
    """
    print(f"\n{'='*60}")
    print(f"Testing: {recipe_type}")
    print(f"Description: {test_config['description']}")
    print(f"{'='*60}")
    
    try:
        # Create dataset config (this will validate the recipe)
        config_dict = {
            "name": f"Test {recipe_type}",
            "seed": "test-seed",
            "root_folder": "/content/dam/test",
            "windows_safe_filenames": True,
            "recipes": [test_config["recipe"]]
        }
        
        # Validate config (this validates recipes too)
        dataset_config = DatasetConfig.model_validate(config_dict)
        print(f"[OK] Recipe validation passed")
        
        # Generate dataset
        job_id = f"test-{recipe_type}"
        files = run_generate_dataset(config_dict, job_id)
        
        # Analyze results
        dita_files = [f for f in files.keys() if f.endswith('.dita')]
        map_files = [f for f in files.keys() if f.endswith('.ditamap')]
        ditaval_files = [f for f in files.keys() if f.endswith('.ditaval')]
        json_files = [f for f in files.keys() if f.endswith('.json') and not f.endswith('manifest.json')]
        other_files = [f for f in files.keys() if f not in dita_files + map_files + ditaval_files + json_files and not f.endswith(('.txt', '.json'))]
        
        stats = {
            "total_files": len(files),
            "dita_files": len(dita_files),
            "map_files": len(map_files),
            "ditaval_files": len(ditaval_files),
            "json_files": len(json_files),
            "other_files": len(other_files),
            "file_list": list(files.keys())[:10]  # First 10 files
        }
        
        # Check expected files
        issues = []
        if "dita" in test_config["expected_files"] and len(dita_files) == 0:
            issues.append("No DITA topic files generated")
        if "ditamap" in test_config["expected_files"] and len(map_files) == 0:
            issues.append("No DITA map files generated")
        if "ditaval" in test_config["expected_files"] and len(ditaval_files) == 0:
            issues.append("No DITAVAL files generated")
        if "json" in test_config["expected_files"] and len(json_files) == 0:
            issues.append("No JSON metadata files generated")
        
        # Check file content
        sample_file = None
        sample_content = None
        if dita_files:
            sample_file = dita_files[0]
            sample_content = files[sample_file].decode('utf-8', errors='ignore')
            if len(sample_content) < 100:
                issues.append(f"Sample file {sample_file} seems too small ({len(sample_content)} bytes)")
            if '<?xml' not in sample_content:
                issues.append(f"Sample file {sample_file} doesn't appear to be valid XML")
        
        if issues:
            return False, f"Issues found: {', '.join(issues)}", stats
        
        print(f"[OK] Generated {stats['total_files']} files")
        print(f"     - {stats['dita_files']} DITA topics")
        print(f"     - {stats['map_files']} DITA maps")
        if stats['ditaval_files'] > 0:
            print(f"     - {stats['ditaval_files']} DITAVAL files")
        if stats['json_files'] > 0:
            print(f"     - {stats['json_files']} JSON metadata files")
        if stats['other_files'] > 0:
            print(f"     - {stats['other_files']} other files")
        
        return True, "Success", stats
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}"
        print(f"[FAIL] {error_msg}")
        print(traceback.format_exc())
        return False, error_msg, {}


def main():
    """Run tests for all recipe types."""
    print("\n" + "="*60)
    print("COMPREHENSIVE RECIPE TYPE TESTING")
    print("="*60)
    
    results = {}
    passed = 0
    failed = 0
    
    for recipe_type, test_config in RECIPE_TESTS.items():
        success, message, stats = test_recipe_type(recipe_type, test_config)
        results[recipe_type] = {
            "success": success,
            "message": message,
            "stats": stats,
            "description": test_config["description"]
        }
        
        if success:
            passed += 1
        else:
            failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total recipes tested: {len(RECIPE_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("\nDetailed Results:")
    
    for recipe_type, result in results.items():
        status = "[PASS]" if result["success"] else "[FAIL]"
        print(f"{status} {recipe_type}: {result['message']}")
        if result["stats"]:
            stats = result["stats"]
            print(f"      Files: {stats.get('total_files', 0)} total, "
                  f"{stats.get('dita_files', 0)} topics, "
                  f"{stats.get('map_files', 0)} maps")
    
    # Save results to file
    output_file = Path(__file__).parent / "test_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_file}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
