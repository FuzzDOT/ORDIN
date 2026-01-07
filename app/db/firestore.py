"""
Firestore Client
================
Async-safe Firestore client initialization and access.

ARCHITECTURE:
- Reuses the existing Firebase Admin SDK initialization from A2
- Provides a singleton Firestore client for the application
- Thread-safe initialization with double-checked locking
- Supports Firestore emulator for local development

USAGE:
    from app.db import get_firestore_client
    
    db = get_firestore_client()
    doc_ref = db.collection("users").document(uid)
    doc = await asyncio.to_thread(doc_ref.get)
"""

import os
import threading
from typing import Optional

from google.cloud.firestore_v1 import Client as FirestoreNativeClient

from app.core.logging import get_logger

logger = get_logger(__name__)

# Thread-safe initialization
_firestore_client: Optional[FirestoreNativeClient] = None
_firestore_lock = threading.Lock()


class FirestoreError(Exception):
    """
    Base exception for Firestore operations.
    
    SECURITY: Error messages are sanitized before being returned to clients.
    Detailed error information is logged server-side only.
    """

    def __init__(self, message: str, internal_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.internal_message = internal_message or message


class FirestoreInitializationError(FirestoreError):
    """Raised when Firestore client fails to initialize."""

    pass


class FirestoreOperationError(FirestoreError):
    """Raised when a Firestore operation fails."""

    pass


class FirestoreClient:
    """
    Wrapper around Firestore native client for type safety and logging.
    
    This class provides a clean interface for Firestore operations
    with consistent error handling and logging.
    """

    def __init__(self, client: FirestoreNativeClient) -> None:
        self._client = client

    @property
    def native(self) -> FirestoreNativeClient:
        """Access the underlying Firestore native client."""
        return self._client

    def collection(self, collection_path: str):
        """Get a reference to a collection."""
        return self._client.collection(collection_path)

    def document(self, document_path: str):
        """Get a reference to a document."""
        return self._client.document(document_path)

    def batch(self):
        """Create a write batch for atomic operations."""
        return self._client.batch()


def initialize_firestore(
    project_id: Optional[str] = None,
    emulator_host: Optional[str] = None,
) -> FirestoreClient:
    """
    Initialize Firestore client (idempotent).
    
    This function is safe to call multiple times. It uses double-checked locking
    to ensure thread-safe initialization. The client reuses the Firebase Admin
    SDK credentials initialized by the auth module.
    
    Args:
        project_id: Google Cloud project ID (required for emulator)
        emulator_host: Firestore emulator host (e.g., "localhost:8080")
    
    Returns:
        FirestoreClient: Initialized Firestore client wrapper
    
    Raises:
        FirestoreInitializationError: If initialization fails
    
    SECURITY: No credentials are logged. Only initialization status is recorded.
    """
    global _firestore_client

    # Fast path: already initialized
    if _firestore_client is not None:
        return FirestoreClient(_firestore_client)

    with _firestore_lock:
        # Double-check after acquiring lock
        if _firestore_client is not None:
            return FirestoreClient(_firestore_client)

        try:
            # Configure emulator if specified
            if emulator_host:
                os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
                logger.info(
                    "Configuring Firestore to use emulator",
                    emulator_host=emulator_host,
                )

            # Import firebase_admin here to ensure it's initialized first
            import firebase_admin
            from firebase_admin import firestore

            # Get the default Firebase app (initialized by A2)
            try:
                app = firebase_admin.get_app()
            except ValueError:
                # Firebase not initialized yet - this shouldn't happen in normal flow
                # but we handle it gracefully for testing scenarios
                raise FirestoreInitializationError(
                    "Firebase Admin SDK not initialized",
                    "Call initialize_firebase() before initialize_firestore()",
                )

            # Create Firestore client using the Firebase Admin app
            _firestore_client = firestore.client(app)
            
            logger.info(
                "Firestore client initialized successfully",
                project_id=project_id or "default",
                emulator_mode=bool(emulator_host),
            )

            return FirestoreClient(_firestore_client)

        except FirestoreInitializationError:
            raise
        except Exception as e:
            logger.error(
                "Failed to initialize Firestore client",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise FirestoreInitializationError(
                "Failed to initialize Firestore",
                f"Firestore initialization failed: {e}",
            ) from e


def get_firestore_client() -> FirestoreClient:
    """
    Get the initialized Firestore client.
    
    This function returns the singleton Firestore client. It must be called
    after initialize_firestore() has been called during application startup.
    
    Returns:
        FirestoreClient: The initialized Firestore client
    
    Raises:
        FirestoreInitializationError: If Firestore has not been initialized
    """
    global _firestore_client

    if _firestore_client is None:
        raise FirestoreInitializationError(
            "Firestore not initialized",
            "Call initialize_firestore() during application startup",
        )

    return FirestoreClient(_firestore_client)


def reset_firestore_client() -> None:
    """
    Reset the Firestore client (for testing only).
    
    WARNING: This function is intended for test cleanup only.
    Do not use in production code.
    """
    global _firestore_client
    with _firestore_lock:
        _firestore_client = None
