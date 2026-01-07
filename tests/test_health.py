"""
Health Endpoint Tests
=====================
Tests for /health and /ready endpoints.
"""

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for the /health liveness probe."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Health endpoint should return 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_healthy_status(self, client: TestClient) -> None:
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_includes_version(self, client: TestClient) -> None:
        """Health endpoint should include application version."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_health_includes_timestamp(self, client: TestClient) -> None:
        """Health endpoint should include timestamp."""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data


class TestReadinessEndpoint:
    """Tests for the /ready readiness probe."""

    def test_ready_returns_200_when_healthy(self, client: TestClient) -> None:
        """Ready endpoint should return 200 when all checks pass."""
        response = client.get("/ready")
        assert response.status_code == 200

    def test_ready_returns_ready_status(self, client: TestClient) -> None:
        """Ready endpoint should return ready status."""
        response = client.get("/ready")
        data = response.json()
        assert data["status"] == "ready"

    def test_ready_includes_checks(self, client: TestClient) -> None:
        """Ready endpoint should include individual checks."""
        response = client.get("/ready")
        data = response.json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_ready_includes_environment(self, client: TestClient) -> None:
        """Ready endpoint should include environment."""
        response = client.get("/ready")
        data = response.json()
        assert "environment" in data


class TestRequestIdPropagation:
    """Tests for X-Request-ID header handling."""

    def test_response_includes_request_id(self, client: TestClient) -> None:
        """Response should include X-Request-ID header."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_request_id_is_uuid_format(self, client: TestClient) -> None:
        """Generated request ID should be in UUID format."""
        import uuid

        response = client.get("/health")
        request_id = response.headers["X-Request-ID"]
        # Should not raise ValueError if valid UUID
        uuid.UUID(request_id)

    def test_provided_request_id_is_propagated(self, client: TestClient) -> None:
        """Provided X-Request-ID should be returned in response."""
        custom_id = "custom-request-id-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id
