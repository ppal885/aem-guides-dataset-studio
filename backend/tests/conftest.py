"""Pytest fixtures for testing."""
import pytest
from fastapi.testclient import TestClient

from app.core.auth import UserIdentity
from app.main import app


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
