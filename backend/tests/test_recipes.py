import pytest
from fastapi.testclient import TestClient

def test_save_recipe(client: TestClient, auth_headers: dict):
    """Test saving a recipe."""
    response = client.post(
        "/api/v1/recipes/save",
        json={
            "name": "Test Recipe",
            "description": "A test recipe",
            "recipe_config": {
                "recipes": [{
                    "type": "incremental_topicref_maps",
                    "pool_size": 100,
                    "map_topicref_counts": [10, 50],
                    "pretty_print": True,
                    "deep_folders": False,
                }]
            },
            "is_public": False,
            "tags": ["test", "performance"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Recipe"

def test_list_recipes(client: TestClient, auth_headers: dict):
    """Test listing recipes."""
    response = client.get("/api/v1/recipes", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "recipes" in data
    assert isinstance(data["recipes"], list)

def test_get_recipe(client: TestClient, auth_headers: dict, saved_recipe_id: str):
    """Test getting a specific recipe."""
    response = client.get(f"/api/v1/recipes/{saved_recipe_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == saved_recipe_id
    assert "recipe_config" in data

def test_update_recipe(client: TestClient, auth_headers: dict, saved_recipe_id: str):
    """Test updating a recipe."""
    response = client.put(
        f"/api/v1/recipes/{saved_recipe_id}",
        json={
            "name": "Updated Recipe Name",
            "description": "Updated description",
            "tags": ["updated"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Recipe Name"

def test_delete_recipe(client: TestClient, auth_headers: dict, saved_recipe_id: str):
    """Test deleting a recipe."""
    response = client.delete(f"/api/v1/recipes/{saved_recipe_id}", headers=auth_headers)
    assert response.status_code == 200
    
    # Verify it's deleted
    response = client.get(f"/api/v1/recipes/{saved_recipe_id}", headers=auth_headers)
    assert response.status_code == 404

def test_use_recipe(client: TestClient, auth_headers: dict, saved_recipe_id: str):
    """Test using a recipe (increments usage count)."""
    # Get initial usage count
    response = client.get(f"/api/v1/recipes/{saved_recipe_id}", headers=auth_headers)
    initial_count = response.json()["usage_count"]
    
    # Use recipe
    response = client.post(f"/api/v1/recipes/{saved_recipe_id}/use", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["usage_count"] == initial_count + 1
    assert "recipe_config" in data

def test_search_recipes(client: TestClient, auth_headers: dict):
    """Test searching recipes."""
    response = client.get(
        "/api/v1/recipes?search=test",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "recipes" in data

def test_filter_recipes_by_tags(client: TestClient, auth_headers: dict):
    """Test filtering recipes by tags."""
    response = client.get(
        "/api/v1/recipes?tags=test,performance",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "recipes" in data

def test_public_recipes(client: TestClient, auth_headers: dict):
    """Test accessing public recipes."""
    # Create a public recipe
    response = client.post(
        "/api/v1/recipes/save",
        json={
            "name": "Public Recipe",
            "recipe_config": {"recipes": []},
            "is_public": True,
            "tags": [],
        },
        headers=auth_headers,
    )
    public_recipe_id = response.json()["id"]
    
    # Access with different user (would need different auth headers)
    # This test would need to be adjusted based on your auth setup
    response = client.get(f"/api/v1/recipes/{public_recipe_id}", headers=auth_headers)
    assert response.status_code == 200
