"""
Repositories
============
Data access layer for Firestore collections.

This package provides repository patterns for accessing Firestore data
with type-safe operations and consistent error handling.
"""

from app.repositories.user_repository import UserRepository
from app.repositories.task_repository import (
    TaskNotFoundError,
    TaskRepository,
    TaskRepositoryError,
)
from app.repositories.calendar_repository import (
    CalendarRepository,
    CalendarRepositoryError,
    IntegrationNotFoundError,
    get_calendar_repository,
)

__all__ = [
    "UserRepository",
    "TaskNotFoundError",
    "TaskRepository",
    "TaskRepositoryError",
    "CalendarRepository",
    "CalendarRepositoryError",
    "IntegrationNotFoundError",
    "get_calendar_repository",
]
