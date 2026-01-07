"""
Test Configuration and Fixtures
================================
Shared pytest fixtures for all test modules.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_application


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Provide test-specific settings."""
    return Settings(
        app_name="ordin-backend-test",
        env="dev",
        debug=True,
        log_level="DEBUG",
        log_format="text",
    )


@pytest.fixture(scope="function")
def client() -> TestClient:
    """
    Provide a test client for API testing.
    
    Creates a fresh application instance for each test function
    to ensure test isolation.
    """
    app = create_application()
    with TestClient(app) as test_client:
        yield test_client
