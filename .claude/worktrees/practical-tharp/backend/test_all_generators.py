"""Test all generator functions to verify they work correctly."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.tasks.generate_dataset import run_generate_dataset
from app.jobs.schemas import DatasetConfig
import json

def test_recipe_type(recipe_type: str, recipe_config: dict, description: str):
    """Test a single recipe type and return results."""
    print(f"\n{'='*60}")
    print(f"Testing: {recipe_type}")
    print(f"Description: {description}")
    print(f"{'='*60}")
    
    config = {
        "name": f"Test {recipe_type}",
        "seed": "test-seed-123",
        "root_folder": "/content/dam/dataset-studio",
        "windows_safe_filenames": True,
        "recipes": [{"type": recipe_type, **recipe_config}]
    }
    
    try:
        files = run_generate_dataset(config, f"test-{recipe_type}")
        
        # Analyze results
        dita_files = [f for f in files.keys() if f.endswith('.dita')]
        map_files = [f for f in files.keys() if f.endswith('.ditamap')]
        other_files = [f for f in files.keys() if not f.endswith(('.dita', '.ditamap'))]
        
        print(f"[OK] Generated {len(files)} total files")
        print(f"  - {len(dita_files)} DITA topic files (.dita)")
        print(f"  - {len(map_files)} DITA map files (.ditamap)")
        print(f"  - {len(other_files)} other files (README, manifest, etc.)")
        
        if dita_files:
            print(f"\n  Sample topic files:")
            for f in sorted(dita_files)[:5]:
                print(f"    - {f}")
        
        if map_files:
            print(f"\n  Map files:")
            for f in sorted(map_files):
                print(f"    - {f}")
        
        return {
            "success": True,
            "total_files": len(files),
            "dita_files": len(dita_files),
            "map_files": len(map_files),
            "description": description
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "description": description
        }

# Test all recipe types
test_results = {}

# Task Topics
test_results["task_topics"] = test_recipe_type(
    "task_topics",
    {"topic_count": 10, "steps_per_task": 5, "include_map": True},
    "Generates DITA task topics with step-by-step procedures, prerequisites, and results"
)

# Concept Topics
test_results["concept_topics"] = test_recipe_type(
    "concept_topics",
    {"topic_count": 10, "sections_per_concept": 3, "include_map": True},
    "Generates DITA concept topics with explanatory content organized into sections"
)

# Reference Topics
test_results["reference_topics"] = test_recipe_type(
    "reference_topics",
    {"topic_count": 10, "properties_per_ref": 5, "include_map": True},
    "Generates DITA reference topics with property tables and technical specifications"
)

# Glossary Pack
test_results["glossary_pack"] = test_recipe_type(
    "glossary_pack",
    {"entry_count": 20, "include_acronyms": True, "include_map": True},
    "Generates DITA glossary entries with definitions and optional acronyms"
)

# Bookmap Structure
test_results["bookmap_structure"] = test_recipe_type(
    "bookmap_structure",
    {"chapter_count": 5, "topics_per_chapter": 3, "include_frontmatter": True, "include_backmatter": True},
    "Generates DITA bookmap with chapters, frontmatter, and backmatter sections"
)

# Incremental Topicref Maps
test_results["incremental_topicref_maps"] = test_recipe_type(
    "incremental_topicref_maps",
    {"pool_size": 100, "map_topicref_counts": [10, 50, 100], "deep_folders": False},
    "Generates a pool of topics and multiple maps with incremental topicref counts for performance testing"
)

# Relationship Table
test_results["relationship_table"] = test_recipe_type(
    "relationship_table",
    {"topic_count": 20, "relationship_types": ["next", "previous", "related"], "include_map": True},
    "Generates DITA topics with relationship tables linking topics together"
)

# Conref Pack
test_results["conref_pack"] = test_recipe_type(
    "conref_pack",
    {"topic_count": 15, "conref_density": 0.3, "include_map": True},
    "Generates DITA topics with conref (content reference) elements for content reuse"
)

# Conditional Content
test_results["conditional_content"] = test_recipe_type(
    "conditional_content",
    {"topic_count": 15, "audiences": ["admin", "user"], "platforms": ["windows", "linux"], "products": ["product-a"]},
    "Generates DITA topics with conditional processing attributes and DITAVAL files"
)

# Media Rich Content
test_results["media_rich_content"] = test_recipe_type(
    "media_rich_content",
    {"topic_count": 10, "images_per_topic": 2, "generate_images": False, "include_map": True},
    "Generates DITA topics with image references and media-rich content"
)

# Advanced Relationships
test_results["advanced_relationships"] = test_recipe_type(
    "advanced_relationships",
    {"topic_count": 20, "relationship_patterns": ["hierarchical", "cross-map"], "include_map": True},
    "Generates DITA topics with advanced relationship patterns and cross-references"
)

# Keyscope Demo
test_results["keyscope_demo"] = test_recipe_type(
    "keyscope_demo",
    {"id_prefix": "t", "include_qualified_keyrefs": True},
    "Generates DITA content demonstrating keyscope functionality with scoped key definitions"
)

# Keyword Metadata
test_results["keyword_metadata"] = test_recipe_type(
    "keyword_metadata",
    {"id_prefix": "t", "num_keywords": 5, "num_categories": 3, "num_topics": 5},
    "Generates DITA key map with keyword metadata and consumer topics"
)

# Summary
print(f"\n{'='*60}")
print("TEST SUMMARY")
print(f"{'='*60}")
successful = sum(1 for r in test_results.values() if r.get("success"))
total = len(test_results)
print(f"Successful: {successful}/{total}")

for recipe_type, result in test_results.items():
    status = "[OK]" if result.get("success") else "[FAIL]"
    print(f"{status} {recipe_type}: {result.get('description', 'N/A')}")
    if result.get("success"):
        print(f"    Generated {result.get('total_files', 0)} files ({result.get('dita_files', 0)} topics, {result.get('map_files', 0)} maps)")
