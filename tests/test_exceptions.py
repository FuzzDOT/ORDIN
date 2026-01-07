"""
Exception Handler Tests
=======================
Tests for global exception handling and error responses.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppException,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.handlers import register_exception_handlers
from app.middleware import RequestIdMiddleware


def create_test_app_with_exception(exc: Exception) -> FastAPI:
    """Create a test app that raises the specified exception."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/test")
    async def raise_exception():
        raise exc

    return app


class TestAppExceptionHandler:
    """Tests for AppException handling."""

    def test_validation_error_returns_422(self) -> None:
        """ValidationError should return 422 status."""
        app = create_test_app_with_exception(
            ValidationError("Invalid input", details={"field": "email"})
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        assert response.status_code == 422

    def test_not_found_error_returns_404(self) -> None:
        """NotFoundError should return 404 status."""
        app = create_test_app_with_exception(
            NotFoundError("User", "12345")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        assert response.status_code == 404

    def test_service_unavailable_returns_503(self) -> None:
        """ServiceUnavailableError should return 503 status."""
        app = create_test_app_with_exception(
            ServiceUnavailableError("database")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        assert response.status_code == 503

    def test_error_response_includes_request_id(self) -> None:
        """Error response should include request_id."""
        app = create_test_app_with_exception(
            ValidationError("Invalid input")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        data = response.json()
        assert "error" in data
        assert "request_id" in data["error"]

    def test_error_response_includes_error_code(self) -> None:
        """Error response should include error code."""
        app = create_test_app_with_exception(
            ValidationError("Invalid input")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestUnhandledExceptionHandler:
    """Tests for unexpected exception handling."""

    def test_unhandled_exception_returns_500(self) -> None:
        """Unhandled exceptions should return 500 status."""
        app = create_test_app_with_exception(
            RuntimeError("Something went wrong")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        assert response.status_code == 500

    def test_unhandled_exception_hides_details(self) -> None:
        """Unhandled exceptions should not expose internal details."""
        app = create_test_app_with_exception(
            RuntimeError("Database password exposed!")
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        data = response.json()
        # Should not contain the actual error message
        assert "password" not in data["error"]["message"].lower()
        assert data["error"]["message"] == "An unexpected error occurred"
