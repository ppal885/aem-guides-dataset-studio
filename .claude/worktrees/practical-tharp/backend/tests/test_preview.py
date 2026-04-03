import pytest
from fastapi.testclient import TestClient

def test_preview_incremental_maps(client: TestClient):
    """Test preview for incremental topicref maps."""
    response = client.post("/api/v1/jobs/preview", json={
        "config": {
            "name": "Test Preview",
            "seed": "test-seed",
            "root_folder": "/content/dam/dataset-studio",
            "windows_safe_filenames": True,
            "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
            "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
            "recipes": [{
                "type": "incremental_topicref_maps",
                "pool_size": 100,
                "map_topicref_counts": [10, 50],
                "pretty_print": True,
                "deep_folders": False,
            }]
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert "estimate" in data
    assert "structure" in data
    assert "topics" in data["estimate"]
    assert "maps" in data["estimate"]
    assert "recipes" in data["structure"]

def test_preview_heavy_topics(client: TestClient):
    """Test preview for heavy topics recipe."""
    response = client.post("/api/v1/jobs/preview", json={
        "config": {
            "name": "Test Preview",
            "seed": "test-seed",
            "root_folder": "/content/dam/dataset-studio",
            "windows_safe_filenames": True,
            "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
            "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
            "recipes": [{
                "type": "heavy_topics_tables_codeblocks",
                "topic_count": 50,
                "tables_per_topic": 5,
                "codeblocks_per_topic": 5,
                "table_cols": 4,
                "table_rows": 10,
                "code_lines_per_codeblock": 20,
                "include_map": True,
                "map_topicref_count": 50,
                "pretty_print": True,
                "windows_safe_paths": True,
            }]
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert "estimate" in data
    assert "structure" in data

def test_preview_invalid_config(client: TestClient):
    """Test preview with invalid configuration."""
    response = client.post("/api/v1/jobs/preview", json={
        "config": {
            "name": "Invalid",
            "recipes": []
        }
    })
    assert response.status_code == 400
