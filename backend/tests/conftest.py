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
