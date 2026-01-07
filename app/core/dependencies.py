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

For authentication dependencies, see app.auth.dependencies.
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
