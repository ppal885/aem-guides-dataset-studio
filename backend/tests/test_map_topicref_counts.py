"""
Test map topicref counts to ensure maps contain all expected topic references.

This test suite validates that:
1. Maps contain exactly the expected number of topicrefs
2. All topicrefs point to valid topic files
3. The fix for map truncation works correctly
4. Tests work for both small and large datasets
"""

import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.generate_dataset import run_generate_dataset
from app.jobs.schemas import DatasetConfig


def count_topicrefs_in_map(map_xml: bytes) -> int:
    """Parse map XML and count topicref elements."""
    try:
        content_str = map_xml.decode('utf-8') if isinstance(map_xml, bytes) else map_xml
        root = ET.fromstring(content_str)
        
        # Count all topicref elements
        topicref_count = 0
        for elem in root.iter():
            # Check if element is a topicref (handle namespaces)
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'topicref':
                topicref_count += 1
        
        return topicref_count
    except ET.ParseError as e:
        print(f"Error parsing map XML: {e}")
        return -1


def validate_map_references(map_xml: bytes, topic_files: List[str]) -> Tuple[bool, List[str]]:
    """Verify all hrefs in map point to existing topic files."""
    try:
        content_str = map_xml.decode('utf-8') if isinstance(map_xml, bytes) else map_xml
        root = ET.fromstring(content_str)
        
        errors = []
        topic_file_set = set(topic_files)
        
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'topicref' and 'href' in elem.attrib:
                href = elem.attrib['href']
                # Extract filename from href (handle relative paths)
                href_filename = href.split('/')[-1]
                
                # Check if any topic file matches this href
                found = False
                for topic_file in topic_files:
                    if topic_file.endswith(href_filename) or href_filename in topic_file:
                        found = True
                        break
                
                if not found and not href.startswith('external://'):
                    errors.append(f"Topicref href '{href}' does not match any generated topic file")
        
        return len(errors) == 0, errors
    except ET.ParseError as e:
        return False, [f"XML parse error: {e}"]


def test_map_topicref_count(recipe_type: str, recipe_config: dict, expected_topic_count: int, expected_map_count: int = 1) -> Tuple[bool, str, dict]:
    """
    Test that maps contain all expected topicrefs.
    
    Args:
        recipe_type: Type of recipe to test
        recipe_config: Recipe configuration dict
        expected_topic_count: Expected number of topics
        expected_map_count: Expected number of maps
    
    Returns:
        (success: bool, message: str, stats: dict)
    """
    print(f"\n{'='*60}")
    print(f"Testing: {recipe_type}")
    print(f"Expected: {expected_topic_count} topics, {expected_map_count} map(s)")
    print(f"{'='*60}")
    
    try:
        config_dict = {
            "name": f"Test {recipe_type}",
            "seed": "test-seed-map-validation",
            "root_folder": "/content/dam/test",
            "windows_safe_filenames": True,
            "recipes": [{"type": recipe_type, **recipe_config}]
        }
        
        # Validate config
        dataset_config = DatasetConfig.model_validate(config_dict)
        print(f"[OK] Recipe validation passed")
        
        # Generate dataset
        job_id = f"test-map-validation-{recipe_type}"
        files = run_generate_dataset(config_dict, job_id)
        
        # Analyze results
        dita_files = [f for f in files.keys() if f.endswith('.dita')]
        map_files = [f for f in files.keys() if f.endswith('.ditamap')]
        
        stats = {
            "total_files": len(files),
            "dita_files": len(dita_files),
            "map_files": len(map_files),
            "topicref_counts": {}
        }
        
        # Validate map files
        issues = []
        
        if len(map_files) != expected_map_count:
            issues.append(f"Expected {expected_map_count} map(s), but found {len(map_files)}")
        
        # Check each map file
        for map_file in map_files:
            map_content = files[map_file]
            topicref_count = count_topicrefs_in_map(map_content)
            
            if topicref_count < 0:
                issues.append(f"Failed to parse map file: {map_file}")
                continue
            
            stats["topicref_counts"][map_file] = topicref_count
            
            # For recipes with single map, verify topicref count matches topic count
            if expected_map_count == 1:
                if topicref_count != expected_topic_count:
                    issues.append(
                        f"Map {map_file}: Expected {expected_topic_count} topicrefs, "
                        f"but found {topicref_count}"
                    )
            
            # Validate references point to existing topics
            is_valid, ref_errors = validate_map_references(map_content, dita_files)
            if not is_valid:
                issues.extend(ref_errors[:5])  # Limit error messages
        
        # For incremental maps recipes, validate each map has correct count
        if recipe_type in ["incremental_topicref_maps", "insurance_incremental"]:
            if recipe_type == "incremental_topicref_maps":
                expected_counts = recipe_config.get("map_topicref_counts", [])
            elif recipe_type == "insurance_incremental":
                expected_counts = recipe_config.get("map_sizes", [])
            else:
                expected_counts = []
            
            if expected_counts:
                if len(map_files) != len(expected_counts):
                    issues.append(
                        f"Expected {len(expected_counts)} maps, but found {len(map_files)}"
                    )
                else:
                    # Sort maps and expected counts to match
                    sorted_maps = sorted(map_files)
                    sorted_counts = sorted(expected_counts)
                    
                    for map_file, expected_count in zip(sorted_maps, sorted_counts):
                        actual_count = stats["topicref_counts"].get(map_file, 0)
                        if actual_count != expected_count:
                            issues.append(
                                f"Map {map_file}: Expected {expected_count} topicrefs, "
                                f"but found {actual_count}"
                            )
        
        if issues:
            error_msg = f"Issues found: {'; '.join(issues)}"
            print(f"[FAIL] {error_msg}")
            return False, error_msg, stats
        
        print(f"[OK] All maps validated successfully")
        print(f"     - {stats['dita_files']} topics generated")
        print(f"     - {stats['map_files']} maps generated")
        for map_file, count in stats["topicref_counts"].items():
            print(f"     - {map_file}: {count} topicrefs")
        
        return True, "Success", stats
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}"
        print(f"[FAIL] {error_msg}")
        print(traceback.format_exc())
        return False, error_msg, {}


def test_task_topics_large():
    """Test task_topics with 100 topics."""
    return test_map_topicref_count(
        "task_topics",
        {"topic_count": 100, "steps_per_task": 5, "include_map": True},
        expected_topic_count=100,
        expected_map_count=1
    )


def test_concept_topics_medium():
    """Test concept_topics with 50 topics."""
    return test_map_topicref_count(
        "concept_topics",
        {"topic_count": 50, "sections_per_concept": 3, "include_map": True},
        expected_topic_count=50,
        expected_map_count=1
    )


def test_reference_topics_large():
    """Test reference_topics with 200 topics."""
    return test_map_topicref_count(
        "reference_topics",
        {"topic_count": 200, "properties_per_ref": 5, "include_map": True},
        expected_topic_count=200,
        expected_map_count=1
    )


def test_incremental_topicref_maps():
    """Test incremental_topicref_maps with multiple maps."""
    return test_map_topicref_count(
        "incremental_topicref_maps",
        {"pool_size": 500, "map_topicref_counts": [10, 50, 100, 500], "deep_folders": False},
        expected_topic_count=500,  # Total topics in pool
        expected_map_count=4  # 4 maps
    )


def test_insurance_incremental():
    """Test insurance_incremental recipe."""
    return test_map_topicref_count(
        "insurance_incremental",
        {"max_topics": 1000, "map_sizes": [10, 100, 1000], "include_local_dtd_stubs": False},
        expected_topic_count=1000,
        expected_map_count=3  # 3 maps
    )


def test_task_topics_small():
    """Test task_topics with 10 topics (quick smoke test)."""
    return test_map_topicref_count(
        "task_topics",
        {"topic_count": 10, "steps_per_task": 3, "include_map": True},
        expected_topic_count=10,
        expected_map_count=1
    )


def main():
    """Run all map topicref validation tests."""
    print("\n" + "="*60)
    print("MAP TOPICREF COUNT VALIDATION TESTS")
    print("="*60)
    
    test_cases = [
        ("task_topics_small", test_task_topics_small),
        ("task_topics_large", test_task_topics_large),
        ("concept_topics_medium", test_concept_topics_medium),
        ("reference_topics_large", test_reference_topics_large),
        ("incremental_topicref_maps", test_incremental_topicref_maps),
        ("insurance_incremental", test_insurance_incremental),
    ]
    
    results = {}
    for test_name, test_func in test_cases:
        success, message, stats = test_func()
        results[test_name] = {
            "success": success,
            "message": message,
            "stats": stats
        }
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    successful = sum(1 for r in results.values() if r["success"])
    total = len(results)
    
    print(f"Successful: {successful}/{total}")
    print()
    
    for test_name, result in results.items():
        status = "[OK]" if result["success"] else "[FAIL]"
        print(f"{status} {test_name}: {result['message']}")
        if result["success"] and result["stats"]:
            stats = result["stats"]
            print(f"    Generated {stats.get('dita_files', 0)} topics, "
                  f"{stats.get('map_files', 0)} maps")
            for map_file, count in stats.get("topicref_counts", {}).items():
                print(f"    {map_file}: {count} topicrefs")
    
    print(f"\n{'='*60}")
    if successful == total:
        print("ALL TESTS PASSED - Maps contain all expected topicrefs")
    else:
        print(f"{total - successful} TEST(S) FAILED")
    print("="*60)
    
    return successful == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
