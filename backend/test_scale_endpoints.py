"""
Test script for scale testing endpoints.

Run this to test the performance endpoints:
    python test_scale_endpoints.py
"""

import requests
import json
from typing import Dict

BASE_URL = "http://localhost:8001/api/v1"

def test_large_scale_preview():
    """Test large-scale preview endpoint."""
    print("\n=== Testing Large Scale Preview ===")
    
    url = f"{BASE_URL}/scale-testing/large-scale/preview"
    payload = {
        "topic_count": 10000,
        "batch_size": 1000
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Success!")
        print(f"Estimated topics: {data['estimate']['topics']:,}")
        print(f"Estimated size: {data['estimate']['estimated_size_mb']:.2f} MB")
        print(f"Estimated time: {data['estimate']['estimated_time_minutes']:.2f} minutes")
        print(f"Warnings: {len(data['warnings'])}")
        for warning in data['warnings']:
            print(f"  - {warning}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def test_deep_hierarchy_preview():
    """Test deep hierarchy preview endpoint."""
    print("\n=== Testing Deep Hierarchy Preview ===")
    
    url = f"{BASE_URL}/scale-testing/deep-hierarchy/preview"
    payload = {
        "depth": 10,
        "children_per_level": 5
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Success!")
        print(f"Depth: {data['estimate']['depth']}")
        print(f"Children per level: {data['estimate']['children_per_level']}")
        print(f"Total topics: {data['estimate']['total_topics']:,}")
        print(f"Maps: {data['estimate']['maps']}")
        print(f"Warnings: {len(data['warnings'])}")
        for warning in data['warnings']:
            print(f"  - {warning}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def test_wide_branching_preview():
    """Test wide branching preview endpoint."""
    print("\n=== Testing Wide Branching Preview ===")
    
    url = f"{BASE_URL}/scale-testing/wide-branching/preview"
    payload = {
        "root_topics": 10,
        "children_per_root": 1000
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Success!")
        print(f"Root topics: {data['estimate']['root_topics']}")
        print(f"Children per root: {data['estimate']['children_per_root']:,}")
        print(f"Total topics: {data['estimate']['total_topics']:,}")
        print(f"Maps: {data['estimate']['maps']}")
        print(f"Warnings: {len(data['warnings'])}")
        for warning in data['warnings']:
            print(f"  - {warning}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def test_performance_profile():
    """Test performance profile endpoint."""
    print("\n=== Testing Performance Profile ===")
    
    url = f"{BASE_URL}/scale-testing/performance-profile"
    payload = {
        "config": {
            "name": "Test Dataset",
            "seed": "test",
            "root_folder": "/content/dam/dataset-studio",
            "windows_safe_filenames": True,
            "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
            "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
            "recipes": []
        },
        "test_type": "large_scale",
        "test_params": {
            "topic_count": 1000,
            "batch_size": 100
        }
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Success!")
        print(f"Test type: {data['test_type']}")
        print(f"Sample size: {data['sample_size']}")
        if 'metrics' in data:
            metrics = data['metrics']
            print(f"Duration: {metrics.get('duration_seconds', 'N/A')}s")
            print(f"Topics generated: {metrics.get('topics_generated', 'N/A')}")
            print(f"Memory delta: {metrics.get('memory_delta_mb', 'N/A')} MB")
            if metrics.get('topics_per_second'):
                print(f"Throughput: {metrics['topics_per_second']:.2f} topics/sec")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Scale Testing Endpoints Test Suite")
    print("=" * 60)
    
    results = []
    
    results.append(("Large Scale Preview", test_large_scale_preview()))
    results.append(("Deep Hierarchy Preview", test_deep_hierarchy_preview()))
    results.append(("Wide Branching Preview", test_wide_branching_preview()))
    results.append(("Performance Profile", test_performance_profile()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    total = len(results)
    passed = sum(1 for _, result in results if result)
    
    print(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
