import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

def test_schedule_job_future(client: TestClient):
    """Test scheduling a job for the future."""
    future_time = datetime.now() + timedelta(hours=1)
    
    response = client.post(
        "/api/v1/jobs/schedule",
        json={
            "config": {
                "name": "Scheduled Test",
                "seed": "test-seed",
                "root_folder": "/content/dam/dataset-studio",
                "windows_safe_filenames": True,
                "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
                "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
                "recipes": [{
                    "type": "incremental_topicref_maps",
                    "pool_size": 10,
                    "map_topicref_counts": [10],
                    "pretty_print": True,
                    "deep_folders": False,
                }]
            },
            "scheduled_at": future_time.isoformat(),
            "timezone": "UTC"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data or "scheduled_at" in data

def test_schedule_job_past(client: TestClient):
    """Test scheduling a job in the past should fail."""
    past_time = datetime.now() - timedelta(hours=1)
    
    response = client.post(
        "/api/v1/jobs/schedule",
        json={
            "config": {
                "name": "Scheduled Test",
                "seed": "test-seed",
                "root_folder": "/content/dam/dataset-studio",
                "recipes": []
            },
            "scheduled_at": past_time.isoformat(),
            "timezone": "UTC"
        }
    )
    assert response.status_code == 400
