"""
Database Layer
==============
Firestore database client and repository implementations.

This package provides:
- Firestore client initialization and connection management
- Base repository patterns for Firestore collections
- Type-safe document operations with Pydantic models
"""

from app.db.firestore import (
    FirestoreClient,
    FirestoreError,
    get_firestore_client,
    initialize_firestore,
)

__all__ = [
    "FirestoreClient",
    "FirestoreError",
    "get_firestore_client",
    "initialize_firestore",
]
