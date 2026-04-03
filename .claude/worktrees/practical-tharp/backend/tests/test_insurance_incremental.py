"""
Test insurance_incremental recipe to ensure it works correctly.

Tests:
1. Recipe generates correct number of topics and maps
2. Maps contain correct topicref counts
3. Topics contain insurance domain content
4. DTD stubs are generated when enabled
5. IDs are DTD-safe (start with letters)
"""

import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.generate_dataset import run_generate_dataset
from app.jobs.schemas import DatasetConfig


def count_topicrefs_in_map(map_xml: bytes) -> int:
    """Count topicref elements in map XML."""
    try:
        content_str = map_xml.decode('utf-8') if isinstance(map_xml, bytes) else map_xml
        root = ET.fromstring(content_str)
        
        topicref_count = 0
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'topicref':
                topicref_count += 1
        
        return topicref_count
    except ET.ParseError:
        return -1


def validate_insurance_content(topic_xml: bytes) -> bool:
    """Validate that topic contains insurance domain content."""
    try:
        content_str = topic_xml.decode('utf-8') if isinstance(topic_xml, bytes) else topic_xml
        
        # Check for insurance domain keywords
        insurance_keywords = [
            "insurance", "policy", "claim", "premium", "coverage",
            "underwriting", "endorsement", "rider", "FNOL", "KYC",
            "IRDAI", "GDPR", "compliance", "surveyor"
        ]
        
        content_lower = content_str.lower()
        keyword_found = any(keyword in content_lower for keyword in insurance_keywords)
        
        # Check for insurance-specific elements
        has_simpletable = "<simpletable" in content_str
        has_codeblock = '<codeblock' in content_str or '<codeblock' in content_str
        
        return keyword_found and (has_simpletable or has_codeblock)
    except Exception:
        return False


def validate_dtd_safe_id(id_str: str) -> bool:
    """Validate that ID starts with a letter (DTD-safe)."""
    if not id_str:
        return False
    return id_str[0].isalpha() or id_str[0] == '_'


def test_insurance_incremental_basic():
    """Test insurance_incremental with small dataset for quick validation."""
    print("\n" + "="*60)
    print("Testing: insurance_incremental (basic)")
    print("="*60)
    
    try:
        config_dict = {
            "name": "Test Insurance Incremental Basic",
            "seed": "test-insurance-seed",
            "root_folder": "/content/dam/test",
            "windows_safe_filenames": True,
            "recipes": [{
                "type": "insurance_incremental",
                "max_topics": 100,
                "map_sizes": [10, 50, 100],
                "include_local_dtd_stubs": True,
                "output_root_folder_name": "test_insurance"
            }]
        }
        
        dataset_config = DatasetConfig.model_validate(config_dict)
        print("[OK] Recipe validation passed")
        
        job_id = "test-insurance-basic"
        files = run_generate_dataset(config_dict, job_id)
        
        # Analyze results
        dita_files = [f for f in files.keys() if f.endswith('.dita')]
        map_files = [f for f in files.keys() if f.endswith('.ditamap')]
        dtd_files = [f for f in files.keys() if 'dtd' in f and f.endswith('.dtd')]
        
        issues = []
        
        # Check topic count
        if len(dita_files) != 100:
            issues.append(f"Expected 100 topics, but found {len(dita_files)}")
        
        # Check map count
        if len(map_files) != 3:
            issues.append(f"Expected 3 maps, but found {len(map_files)}")
        
        # Check DTD stubs
        if len(dtd_files) != 2:
            issues.append(f"Expected 2 DTD stub files, but found {len(dtd_files)}")
        
        # Validate map topicref counts
        expected_map_counts = [10, 50, 100]
        sorted_maps = sorted(map_files)
        
        for map_file, expected_count in zip(sorted_maps, expected_map_counts):
            map_content = files[map_file]
            actual_count = count_topicrefs_in_map(map_content)
            
            if actual_count != expected_count:
                issues.append(
                    f"Map {map_file}: Expected {expected_count} topicrefs, "
                    f"but found {actual_count}"
                )
        
        # Validate topic IDs are DTD-safe
        sample_topics = dita_files[:10]
        for topic_file in sample_topics:
            topic_content = files[topic_file]
            try:
                content_str = topic_content.decode('utf-8')
                root = ET.fromstring(content_str)
                topic_id = root.get('id', '')
                
                if not validate_dtd_safe_id(topic_id):
                    issues.append(f"Topic {topic_file} has invalid ID: {topic_id}")
            except Exception as e:
                issues.append(f"Failed to parse topic {topic_file}: {e}")
        
        # Validate map IDs are DTD-safe
        for map_file in map_files:
            map_content = files[map_file]
            try:
                content_str = map_content.decode('utf-8')
                root = ET.fromstring(content_str)
                map_id = root.get('id', '')
                
                if not validate_dtd_safe_id(map_id):
                    issues.append(f"Map {map_file} has invalid ID: {map_id}")
            except Exception as e:
                issues.append(f"Failed to parse map {map_file}: {e}")
        
        # Validate insurance content in sample topics
        insurance_content_valid = 0
        sample_topics_for_content = dita_files[:5]
        for topic_file in sample_topics_for_content:
            if validate_insurance_content(files[topic_file]):
                insurance_content_valid += 1
        
        if insurance_content_valid < 3:
            issues.append(
                f"Only {insurance_content_valid}/5 sample topics contain insurance domain content"
            )
        
        if issues:
            error_msg = f"Issues found: {'; '.join(issues)}"
            print(f"[FAIL] {error_msg}")
            return False, error_msg
        
        print(f"[OK] All validations passed")
        print(f"     - {len(dita_files)} topics generated")
        print(f"     - {len(map_files)} maps generated")
        print(f"     - {len(dtd_files)} DTD stub files")
        print(f"     - {insurance_content_valid}/5 sample topics have insurance content")
        
        return True, "Success"
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}"
        print(f"[FAIL] {error_msg}")
        print(traceback.format_exc())
        return False, error_msg


def test_insurance_incremental_no_dtd():
    """Test insurance_incremental without DTD stubs."""
    print("\n" + "="*60)
    print("Testing: insurance_incremental (no DTD stubs)")
    print("="*60)
    
    try:
        config_dict = {
            "name": "Test Insurance Incremental No DTD",
            "seed": "test-insurance-seed-2",
            "root_folder": "/content/dam/test",
            "windows_safe_filenames": True,
            "recipes": [{
                "type": "insurance_incremental",
                "max_topics": 50,
                "map_sizes": [10, 50],
                "include_local_dtd_stubs": False,
                "output_root_folder_name": "test_insurance_no_dtd"
            }]
        }
        
        dataset_config = DatasetConfig.model_validate(config_dict)
        print("[OK] Recipe validation passed")
        
        job_id = "test-insurance-no-dtd"
        files = run_generate_dataset(config_dict, job_id)
        
        dtd_files = [f for f in files.keys() if 'dtd' in f and f.endswith('.dtd')]
        
        if len(dtd_files) > 0:
            error_msg = f"Expected no DTD files, but found {len(dtd_files)}"
            print(f"[FAIL] {error_msg}")
            return False, error_msg
        
        print("[OK] No DTD stubs generated as expected")
        return True, "Success"
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}"
        print(f"[FAIL] {error_msg}")
        print(traceback.format_exc())
        return False, error_msg


def main():
    """Run all insurance_incremental tests."""
    print("\n" + "="*60)
    print("INSURANCE INCREMENTAL RECIPE TESTS")
    print("="*60)
    
    test_cases = [
        ("insurance_incremental_basic", test_insurance_incremental_basic),
        ("insurance_incremental_no_dtd", test_insurance_incremental_no_dtd),
    ]
    
    results = {}
    for test_name, test_func in test_cases:
        success, message = test_func()
        results[test_name] = {
            "success": success,
            "message": message
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
    
    print(f"\n{'='*60}")
    if successful == total:
        print("ALL TESTS PASSED - Insurance incremental recipe works correctly")
    else:
        print(f"{total - successful} TEST(S) FAILED")
    print("="*60)
    
    return successful == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
