"""
Dependency Injection
====================
FastAPI dependency providers for shared resources.

This module defines injectable dependencies that can be used across
the application. Dependencies are resolved per-request and can be
easily mocked for testing.

Design principles:
- Dependencies should be stateless or use proper scoping
- Heavy initialization should use lifespan events, not dependencies
- Dependencies can depend on other dependencies (dependency tree)
"""

from typing import Annotated, Optional

from fastapi import Depends, Request

from app.config import Settings, get_settings


def get_request_id(request: Request) -> Optional[str]:
    """
    Extract request ID from the current request state.
    
    This dependency provides access to the request ID set by middleware.
    
    Usage:
        @router.get("/example")
        async def example(request_id: Annotated[str, Depends(get_request_id)]):
            ...
    """
    return getattr(request.state, "request_id", None)


def get_current_settings() -> Settings:
    """
    Provide application settings as a dependency.
    
    This is a thin wrapper around get_settings() for consistency
    with the FastAPI dependency pattern.
    
    Usage:
        @router.get("/example")
        async def example(settings: Annotated[Settings, Depends(get_current_settings)]):
            ...
    """
    return get_settings()


# Type aliases for cleaner dependency injection syntax
SettingsDep = Annotated[Settings, Depends(get_current_settings)]
RequestIdDep = Annotated[Optional[str], Depends(get_request_id)]


# Placeholder for user context (to be implemented with Firebase integration)
class UserContext:
    """
    Placeholder for authenticated user context.
    
    This will be populated by Firebase auth middleware in the future.
    For now, it serves as a contract for downstream code.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        is_authenticated: bool = False,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.is_authenticated = is_authenticated


async def get_user_context(request: Request) -> UserContext:
    """
    Extract user context from request (placeholder for Firebase auth).
    
    Currently returns an unauthenticated context.
    Will be updated when Firebase auth is integrated.
    
    Usage:
        @router.get("/protected")
        async def protected(user: Annotated[UserContext, Depends(get_user_context)]):
            if not user.is_authenticated:
                raise HTTPException(401, "Authentication required")
    """
    # Future implementation will extract Firebase token and validate
    return UserContext(
        user_id=None,
        email=None,
        is_authenticated=False,
    )


UserContextDep = Annotated[UserContext, Depends(get_user_context)]
