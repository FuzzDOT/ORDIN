"""
Services
========
Business service layer for the application.

Services orchestrate between API handlers and repositories,
providing a clean abstraction layer. However, for A3 (User Profile),
no business logic is implemented - services are pure data access wrappers.
"""

from app.services.user_service import UserService

__all__ = ["UserService"]
