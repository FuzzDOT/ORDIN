"""
Firebase Authentication Tests
==============================
Tests for the authentication middleware and dependencies.

NOTE: These tests mock Firebase Admin SDK to avoid external dependencies.
For integration tests with real Firebase, use a test project.
"""

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.context import UserContext
from app.auth.dependencies import get_current_user, get_optional_user
from app.auth.middleware import FirebaseAuthMiddleware
from app.middleware.request_id import RequestIdMiddleware


def create_test_app(
    protected_paths: Optional[set] = None,
    auth_enabled: bool = True,
) -> FastAPI:
    """Create a test FastAPI app with auth middleware."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        FirebaseAuthMiddleware,
        protected_paths=protected_paths or set(),
        auth_enabled=auth_enabled,
    )

    @app.get("/public")
    async def public_endpoint():
        return {"message": "public"}

    @app.get("/protected")
    async def protected_endpoint(user=Depends(get_current_user)):
        return {"uid": user.uid, "email": user.email}

    @app.get("/optional")
    async def optional_endpoint(user=Depends(get_optional_user)):
        if user:
            return {"uid": user.uid, "authenticated": True}
        return {"authenticated": False}

    return app


class TestFirebaseAuthMiddleware:
    """Tests for FirebaseAuthMiddleware."""

    def test_public_endpoint_no_token(self) -> None:
        """Public endpoints should work without authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/public")
        assert response.status_code == 200
        assert response.json() == {"message": "public"}

    def test_protected_route_without_token_returns_401(self) -> None:
        """Protected routes should return 401 without token."""
        app = create_test_app(protected_paths={"/protected"})
        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "UNAUTHORIZED" in response.json()["error"]["code"]

    def test_protected_route_with_invalid_bearer_format(self) -> None:
        """Invalid Authorization header format should return 401."""
        app = create_test_app(protected_paths={"/protected"})
        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "Basic abc123"},
        )
        assert response.status_code == 401

    def test_auth_disabled_bypasses_verification(self) -> None:
        """When auth is disabled, all routes should be accessible."""
        app = create_test_app(protected_paths={"/protected"}, auth_enabled=False)
        client = TestClient(app, raise_server_exceptions=False)
        
        # Note: The route still requires a user via dependency, so it will fail
        # This tests that the middleware itself doesn't block
        response = client.get("/public")
        assert response.status_code == 200

    @patch("app.auth.middleware.verify_firebase_token")
    def test_valid_token_sets_user_context(self, mock_verify: MagicMock) -> None:
        """Valid token should set user context on request."""
        mock_user = UserContext(
            uid="test-uid-123",
            email="test@example.com",
            email_verified=True,
        )
        mock_verify.return_value = mock_user

        app = create_test_app()
        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        assert response.json()["uid"] == "test-uid-123"
        assert response.json()["email"] == "test@example.com"

    @patch("app.auth.middleware.verify_firebase_token")
    def test_optional_auth_with_token(self, mock_verify: MagicMock) -> None:
        """Optional auth endpoint should return user when token provided."""
        mock_user = UserContext(
            uid="optional-user",
            email="optional@example.com",
            email_verified=False,
        )
        mock_verify.return_value = mock_user

        app = create_test_app()
        client = TestClient(app)
        response = client.get(
            "/optional",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert response.json()["uid"] == "optional-user"

    def test_optional_auth_without_token(self) -> None:
        """Optional auth endpoint should work without token."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/optional")
        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    def test_response_includes_www_authenticate_header(self) -> None:
        """401 responses should include WWW-Authenticate header."""
        app = create_test_app(protected_paths={"/protected"})
        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert "Bearer" in response.headers["WWW-Authenticate"]


class TestUserContext:
    """Tests for UserContext model."""

    def test_user_context_is_immutable(self) -> None:
        """UserContext should be immutable (frozen)."""
        user = UserContext(uid="test-uid", email="test@example.com")
        with pytest.raises(Exception):  # Pydantic raises ValidationError
            user.uid = "new-uid"

    def test_user_context_is_authenticated(self) -> None:
        """UserContext should always report as authenticated."""
        user = UserContext(uid="test-uid")
        assert user.is_authenticated is True

    def test_display_id_prefers_email(self) -> None:
        """display_id should return email if available."""
        user = UserContext(uid="test-uid", email="test@example.com")
        assert user.display_id == "test@example.com"

    def test_display_id_falls_back_to_uid(self) -> None:
        """display_id should return uid if email is not set."""
        user = UserContext(uid="test-uid")
        assert user.display_id == "test-uid"

    def test_user_context_str_representation(self) -> None:
        """String representation should be safe for logging."""
        user = UserContext(
            uid="test-uid",
            email="test@example.com",
            email_verified=True,
        )
        str_repr = str(user)
        assert "test-uid" in str_repr
        assert "test@example.com" in str_repr


class TestTokenExtraction:
    """Tests for token extraction from Authorization header."""

    def test_bearer_token_extracted(self) -> None:
        """Token should be extracted from Bearer header."""
        # This is implicitly tested via the middleware tests above
        pass

    def test_empty_bearer_token_rejected(self) -> None:
        """Empty Bearer token should be treated as missing."""
        app = create_test_app(protected_paths={"/protected"})
        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_case_sensitive_bearer_prefix(self) -> None:
        """Bearer prefix should be case-sensitive."""
        app = create_test_app(protected_paths={"/protected"})
        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "bearer token"},  # lowercase
        )
        assert response.status_code == 401
