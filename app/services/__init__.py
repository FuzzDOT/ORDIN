"""
Services
========
Business service layer for the application.

Services orchestrate between API handlers and repositories,
providing a clean abstraction layer. For A3 (User Profile) and
A4 (Tasks), no business logic is implemented - services are
pure data access wrappers.
"""

from app.services.user_service import UserService
from app.services.task_service import (
    TaskNotFoundServiceError,
    TaskService,
    TaskServiceError,
)

__all__ = [
    "UserService",
    "TaskNotFoundServiceError",
    "TaskService",
    "TaskServiceError",
]
