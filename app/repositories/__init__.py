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

__all__ = [
    "UserRepository",
    "TaskNotFoundError",
    "TaskRepository",
    "TaskRepositoryError",
]
