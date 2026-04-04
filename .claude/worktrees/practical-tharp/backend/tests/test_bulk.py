import pytest
from fastapi.testclient import TestClient

def test_create_bulk_jobs(client: TestClient, auth_headers: dict):
    """Test creating multiple jobs at once."""
    response = client.post(
        "/api/v1/bulk/jobs",
        json={
            "jobs": [
                {
                    "config": {
                        "name": "Bulk Job 1",
                        "seed": "test-seed-1",
                        "root_folder": "/content/dam/dataset-studio",
                        "recipes": [{
                            "type": "incremental_topicref_maps",
                            "pool_size": 10,
                            "map_topicref_counts": [10],
                            "pretty_print": True,
                            "deep_folders": False,
                        }]
                    }
                },
                {
                    "config": {
                        "name": "Bulk Job 2",
                        "seed": "test-seed-2",
                        "root_folder": "/content/dam/dataset-studio",
                        "recipes": [{
                            "type": "incremental_topicref_maps",
                            "pool_size": 20,
                            "map_topicref_counts": [20],
                            "pretty_print": True,
                            "deep_folders": False,
                        }]
                    }
                },
            ],
            "name_prefix": "Test Batch",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 2
    assert data["failed"] == 0
    assert len(data["job_ids"]) == 2

def test_create_bulk_jobs_max_limit(client: TestClient, auth_headers: dict):
    """Test that bulk creation respects max limit."""
    # Create 101 jobs (over limit)
    jobs = [
        {
            "config": {
                "name": f"Job {i}",
                "seed": "test",
                "root_folder": "/content/dam/dataset-studio",
                "recipes": [],
            }
        }
        for i in range(101)
    ]
    
    response = client.post(
        "/api/v1/bulk/jobs",
        json={"jobs": jobs},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Maximum 100" in response.json()["detail"]

def test_create_bulk_jobs_from_template(client: TestClient, auth_headers: dict):
    """Test creating bulk jobs from a template."""
    response = client.post(
        "/api/v1/bulk/jobs/from-template",
        json={
            "template_id": "performance_test_small",
            "variations": [
                {"recipes": [{"type": "incremental_topicref_maps", "pool_size": 100, "map_topicref_counts": [10]}]},
                {"recipes": [{"type": "incremental_topicref_maps", "pool_size": 200, "map_topicref_counts": [20]}]},
            ],
            "name_prefix": "Template Batch",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] >= 0
    assert "job_ids" in data

def test_create_bulk_jobs_from_csv(client: TestClient, auth_headers: dict):
    """Test creating bulk jobs from CSV."""
    csv_data = """name,seed,recipe_type,recipe_params
Job 1,seed1,incremental_topicref_maps,"{""pool_size"":100,""map_topicref_counts"":[10]}"
Job 2,seed2,incremental_topicref_maps,"{""pool_size"":200,""map_topicref_counts"":[20]}"
"""
    
    response = client.post(
        "/api/v1/bulk/jobs/from-csv",
        json={
            "csv_data": csv_data,
            "name_prefix": "CSV Batch",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] >= 0
    assert "job_ids" in data

def test_bulk_jobs_error_handling(client: TestClient, auth_headers: dict):
    """Test that bulk creation handles errors gracefully."""
    response = client.post(
        "/api/v1/bulk/jobs",
        json={
            "jobs": [
                {
                    "config": {
                        "name": "Valid Job",
                        "seed": "test",
                        "root_folder": "/content/dam/dataset-studio",
                        "recipes": [{
                            "type": "incremental_topicref_maps",
                            "pool_size": 10,
                            "map_topicref_counts": [10],
                            "pretty_print": True,
                            "deep_folders": False,
                        }]
                    }
                },
                {
                    "config": {
                        "name": "Invalid Job",
                        "seed": "test",
                        "root_folder": "/content/dam/dataset-studio",
                        "recipes": []  # Invalid - no recipes
                    }
                },
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Should create valid job, fail invalid one
    assert data["created"] >= 0
    assert data["failed"] >= 0
    assert len(data["errors"]) >= 0
