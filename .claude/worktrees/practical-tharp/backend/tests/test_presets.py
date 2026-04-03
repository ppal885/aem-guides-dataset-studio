import pytest
from fastapi.testclient import TestClient

def test_list_presets(client: TestClient):
    """Test listing all presets."""
    response = client.get("/api/v1/presets")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    assert isinstance(data["presets"], list)
    assert len(data["presets"]) > 0

def test_get_preset(client: TestClient):
    """Test getting a specific preset."""
    response = client.get("/api/v1/presets/performance_test_small")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "description" in data
    assert "config" in data

def test_get_nonexistent_preset(client: TestClient):
    """Test getting a non-existent preset returns 404."""
    response = client.get("/api/v1/presets/nonexistent")
    assert response.status_code == 404

def test_apply_preset(client: TestClient):
    """Test applying a preset."""
    response = client.post(
        "/api/v1/presets/performance_test_small/apply",
        json={"base_config": {"name": "Test Dataset"}}
    )
    assert response.status_code == 200
    data = response.json()
    assert "config" in data
    assert "recipes" in data["config"]

def test_apply_preset_without_base_config(client: TestClient):
    """Test applying a preset without base config."""
    response = client.post("/api/v1/presets/performance_test_small/apply")
    assert response.status_code == 200
    data = response.json()
    assert "config" in data
