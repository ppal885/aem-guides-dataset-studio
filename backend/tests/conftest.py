"""Pytest fixtures for testing."""
import pytest
from fastapi.testclient import TestClient

from app.core.auth import UserIdentity
from app.db.base import Base
from app.db.migrations import run_migrations
from app.db.session import engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _initialize_test_database():
    """Keep the test database schema aligned with model and migration changes."""
    Base.metadata.create_all(bind=engine)
    run_migrations()
    yield


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create mock auth headers."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def mock_user():
    """Create a mock user identity."""
    return UserIdentity(id="test-user-id", name="Test User", email="test@example.com")


@pytest.fixture
def saved_recipe_id(client: TestClient, auth_headers: dict) -> str:
    """Create a saved recipe and return its ID for tests that need an existing recipe."""
    response = client.post(
        "/api/v1/recipes/save",
        json={
            "name": "Fixture Recipe",
            "description": "Created by test fixture",
            "recipe_config": {
                "recipes": [{
                    "type": "incremental_topicref_maps",
                    "pool_size": 10,
                    "map_topicref_counts": [5],
                    "pretty_print": True,
                    "deep_folders": False,
                }]
            },
            "is_public": False,
            "tags": ["fixture"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, f"Failed to create fixture recipe: {response.text}"
    return response.json()["id"]
