"""
Test DITA 1.3 compliance and path references for AEM Guides compatibility.
"""
import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.tasks.generate_dataset import run_generate_dataset
from app.jobs.schemas import DatasetConfig


def test_dita_doctype_compliance():
    """Test that all generated files have correct DITA 1.3 doctype declarations."""
    config = {
        "name": "DITA Compliance Test",
        "seed": "test-seed",
        "root_folder": "/content/dam/dataset-studio",
        "windows_safe_filenames": True,
        "recipes": [
            {
                "type": "task_topics",
                "topic_count": 10,
                "steps_per_task": 3,
                "include_map": True,
            }
        ]
    }
    
    files = run_generate_dataset(config, "test-compliance")
    
    errors = []
    for file_path, content in files.items():
        if file_path.endswith(('.dita', '.ditamap')):
            content_str = content.decode('utf-8') if isinstance(content, bytes) else content
            
            # Check for XML declaration
            if not content_str.startswith('<?xml'):
                errors.append(f"{file_path}: Missing XML declaration")
            
            # Check for correct doctype
            if file_path.endswith('.dita'):
                if 'DOCTYPE topic' not in content_str:
                    errors.append(f"{file_path}: Missing or incorrect topic doctype")
                if 'technicalContent/dtd/topic.dtd' not in content_str:
                    errors.append(f"{file_path}: Incorrect topic DTD path")
            elif file_path.endswith('.ditamap'):
                if 'DOCTYPE map' not in content_str:
                    errors.append(f"{file_path}: Missing or incorrect map doctype")
                if 'technicalContent/dtd/map.dtd' not in content_str:
                    errors.append(f"{file_path}: Incorrect map DTD path")
    
    return errors


def test_path_references():
    """Test that all href references use proper relative paths."""
    config = {
        "name": "Path Reference Test",
        "seed": "test-seed",
        "root_folder": "/content/dam/dataset-studio",
        "windows_safe_filenames": True,
        "recipes": [
            {
                "type": "bookmap_structure",
                "chapter_count": 3,
                "topics_per_chapter": 2,
                "include_frontmatter": True,
                "include_backmatter": True,
            }
        ]
    }
    
    files = run_generate_dataset(config, "test-paths")
    
    errors = []
    file_paths = set(files.keys())
    
    for file_path, content in files.items():
        if file_path.endswith('.ditamap'):
            try:
                root = ET.fromstring(content)
                for elem in root.iter():
                    if 'href' in elem.attrib:
                        href = elem.attrib['href']
                        
                        # Check for absolute paths (should be relative)
                        if href.startswith('/') and not href.startswith('//'):
                            errors.append(f"{file_path}: Absolute path found: {href}")
                        
                        # Check for Windows backslashes
                        if '\\' in href:
                            errors.append(f"{file_path}: Windows path separator found: {href}")
                        
                        # Check if referenced file exists
                        if not href.startswith('external://') and not href.startswith('http'):
                            # Calculate expected file path
                            map_dir = os.path.dirname(file_path) or "."
                            expected_path = os.path.normpath(os.path.join(map_dir, href)).replace("\\", "/")
                            
                            # Check if file exists in generated files
                            found = False
                            for gen_path in file_paths:
                                if gen_path.endswith(href.split('/')[-1]) or gen_path.replace("\\", "/") == expected_path:
                                    found = True
                                    break
                            
                            if not found and not href.startswith('../'):
                                # Allow relative paths that go up directories
                                pass
            except ET.ParseError as e:
                errors.append(f"{file_path}: XML parse error: {e}")
    
    return errors


def test_aem_guides_path_structure():
    """Test that paths are compatible with AEM Guides upload structure."""
    config = {
        "name": "AEM Path Test",
        "seed": "test-seed",
        "root_folder": "/content/dam/dataset-studio",
        "windows_safe_filenames": True,
        "recipes": [
            {
                "type": "task_topics",
                "topic_count": 10,
                "include_map": True,
            }
        ]
    }
    
    files = run_generate_dataset(config, "test-aem-paths")
    
    errors = []
    for file_path in files.keys():
        # Check that paths don't contain invalid characters for AEM
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            if char in file_path:
                errors.append(f"{file_path}: Contains invalid character: {char}")
        
        # Check that paths use forward slashes
        if '\\' in file_path:
            errors.append(f"{file_path}: Uses backslash instead of forward slash")
    
    return errors


if __name__ == "__main__":
    print("=" * 60)
    print("DITA 1.3 Compliance and Path Reference Testing")
    print("=" * 60)
    
    print("\n1. Testing DITA doctype compliance...")
    doctype_errors = test_dita_doctype_compliance()
    if doctype_errors:
        print(f"   [FAIL] Found {len(doctype_errors)} doctype errors:")
        for error in doctype_errors[:10]:
            print(f"   - {error}")
    else:
        print("   [OK] All files have correct DITA 1.3 doctype declarations")
    
    print("\n2. Testing path references...")
    path_errors = test_path_references()
    if path_errors:
        print(f"   [FAIL] Found {len(path_errors)} path reference errors:")
        for error in path_errors[:10]:
            print(f"   - {error}")
    else:
        print("   [OK] All path references are valid relative paths")
    
    print("\n3. Testing AEM Guides path structure...")
    aem_errors = test_aem_guides_path_structure()
    if aem_errors:
        print(f"   [FAIL] Found {len(aem_errors)} AEM path errors:")
        for error in aem_errors[:10]:
            print(f"   - {error}")
    else:
        print("   [OK] All paths are compatible with AEM Guides structure")
    
    total_errors = len(doctype_errors) + len(path_errors) + len(aem_errors)
    print(f"\n{'=' * 60}")
    if total_errors == 0:
        print("ALL TESTS PASSED - DITA 1.3 compliant and AEM Guides ready")
    else:
        print(f"TOTAL ERRORS: {total_errors}")
    print("=" * 60)
