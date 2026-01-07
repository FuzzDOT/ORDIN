"""
Repositories
============
Data access layer for Firestore collections.

This package provides repository patterns for accessing Firestore data
with type-safe operations and consistent error handling.
"""

from app.repositories.user_repository import UserRepository

__all__ = ["UserRepository"]
