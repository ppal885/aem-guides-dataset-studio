"""
XML validation tests to ensure generated DITA XML contains no invalid entities.

These tests verify that all generated XML files are valid and can be parsed
without errors, preventing FM post-processing errors.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.generate_dataset import run_generate_dataset
from app.jobs.schemas import DatasetConfig


def find_invalid_ampersands(xml_content: str) -> list:
    """
    Find invalid ampersand patterns in XML content.
    
    Returns list of (line_number, match) tuples for invalid & patterns.
    """
    invalid_pattern = re.compile(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)')
    issues = []
    
    lines = xml_content.split('\n')
    for line_num, line in enumerate(lines, 1):
        matches = invalid_pattern.finditer(line)
        for match in matches:
            issues.append((line_num, match.group(), line.strip()[:100]))
    
    return issues


def validate_xml_content(xml_content: bytes) -> tuple[bool, list]:
    """
    Validate XML content for invalid entities.
    
    Returns:
        (is_valid: bool, issues: list of error messages)
    """
    issues = []
    
    try:
        # Decode to string
        xml_str = xml_content.decode('utf-8', errors='ignore')
        
        # Try to parse XML
        try:
            ET.fromstring(xml_str)
        except ET.ParseError as e:
            issues.append(f"XML Parse Error: {e}")
            return False, issues
        
        # Check for invalid ampersands
        invalid_amps = find_invalid_ampersands(xml_str)
        if invalid_amps:
            for line_num, match, context in invalid_amps:
                issues.append(
                    f"Line {line_num}: Invalid ampersand '{match}' "
                    f"(context: ...{context}...)"
                )
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Validation error: {e}")
        return False, issues


def test_task_topics_xml_validation():
    """Test that task topics generate valid XML."""
    print("\nTesting task_topics XML validation...")
    
    config_dict = {
        "name": "Test Task Topics XML",
        "seed": "test-xml-validation",
        "root_folder": "/content/dam/test",
        "windows_safe_filenames": True,
        "recipes": [{
            "type": "task_topics",
            "topic_count": 10,
            "steps_per_task": 3,
            "include_map": True,
        }]
    }
    
    try:
        dataset_config = DatasetConfig.model_validate(config_dict)
        job_id = "test-xml-validation-task"
        files = run_generate_dataset(config_dict, job_id)
        
        issues_found = []
        
        # Validate all DITA files
        for file_path, content in files.items():
            if file_path.endswith(('.dita', '.ditamap')):
                is_valid, issues = validate_xml_content(content)
                if not is_valid:
                    issues_found.extend([f"{file_path}: {issue}" for issue in issues])
        
        if issues_found:
            print(f"Found {len(issues_found)} XML validation issues:")
            for issue in issues_found[:10]:  # Show first 10
                print(f"  - {issue}")
            return False, issues_found
        
        print("✓ All task_topics XML files are valid")
        return True, []
        
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(traceback.format_exc())
        return False, [str(e)]


def test_insurance_incremental_xml_validation():
    """Test that insurance_incremental generates valid XML."""
    print("\nTesting insurance_incremental XML validation...")
    
    config_dict = {
        "name": "Test Insurance XML",
        "seed": "test-xml-validation-insurance",
        "root_folder": "/content/dam/test",
        "windows_safe_filenames": True,
        "recipes": [{
            "type": "insurance_incremental",
            "max_topics": 50,
            "map_sizes": [10, 50],
            "include_local_dtd_stubs": False,
        }]
    }
    
    try:
        dataset_config = DatasetConfig.model_validate(config_dict)
        job_id = "test-xml-validation-insurance"
        files = run_generate_dataset(config_dict, job_id)
        
        issues_found = []
        
        # Validate all DITA files
        for file_path, content in files.items():
            if file_path.endswith(('.dita', '.ditamap')):
                is_valid, issues = validate_xml_content(content)
                if not is_valid:
                    issues_found.extend([f"{file_path}: {issue}" for issue in issues])
        
        if issues_found:
            print(f"Found {len(issues_found)} XML validation issues:")
            for issue in issues_found[:10]:  # Show first 10
                print(f"  - {issue}")
            return False, issues_found
        
        print("✓ All insurance_incremental XML files are valid")
        return True, []
        
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(traceback.format_exc())
        return False, [str(e)]


def test_xml_with_special_characters():
    """Test XML generation with special characters that commonly cause issues."""
    print("\nTesting XML with special characters...")
    
    # Test with content that contains &, <, >
    test_cases = [
        "Company A & Company B",
        "Price < 100",
        "Value > 50",
        "A & B < C > D",
        "Version 1.0 & 2.0",
    ]
    
    from app.utils.xml_escape import xml_escape_text, xml_escape_attr
    
    for test_text in test_cases:
        escaped_text = xml_escape_text(test_text)
        escaped_attr = xml_escape_attr(test_text)
        
        # Verify no invalid ampersands
        invalid_pattern = re.compile(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)')
        
        if invalid_pattern.search(escaped_text):
            print(f"  ✗ Invalid ampersand in escaped text: {test_text} -> {escaped_text}")
            return False
        
        if invalid_pattern.search(escaped_attr):
            print(f"  ✗ Invalid ampersand in escaped attr: {test_text} -> {escaped_attr}")
            return False
        
        # Verify XML can be parsed
        try:
            test_elem = ET.Element("test")
            test_elem.text = escaped_text
            test_elem.set("attr", escaped_attr)
            ET.tostring(test_elem, encoding='utf-8')
        except Exception as e:
            print(f"  ✗ Failed to create valid XML: {test_text} -> {e}")
            return False
    
    print("✓ All special character tests passed")
    return True


def main():
    """Run all XML validation tests."""
    print("="*60)
    print("XML VALIDATION TESTS")
    print("="*60)
    
    results = {}
    
    # Test escaping functions
    results["special_chars"] = test_xml_with_special_characters()
    
    # Test generated XML
    results["task_topics"] = test_task_topics_xml_validation()[0]
    results["insurance_incremental"] = test_insurance_incremental_xml_validation()[0]
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All XML validation tests passed - No invalid entities found")
        return 0
    else:
        print("\n✗ Some XML validation tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
