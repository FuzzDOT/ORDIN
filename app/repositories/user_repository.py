"""
User Repository
===============
Firestore repository for user profile documents.

This repository provides type-safe CRUD operations for user profiles
stored in the 'users' Firestore collection. It handles:
- Auto-creation of profiles with defaults on first access
- Partial updates (PATCH semantics) without overwriting unspecified fields
- Idempotent operations for reliability
- Consistent error handling and logging

COLLECTION STRUCTURE:
    Collection: users
    Document ID: {firebase_uid}
    Fields: See UserProfile model

ASYNC SAFETY:
Firestore SDK operations are synchronous. This repository uses
asyncio.to_thread() to run them in a thread pool, ensuring
non-blocking behavior in the async FastAPI context.
"""

import asyncio
from datetime import datetime
from typing import Optional

from google.cloud import firestore

from app.core.logging import get_logger
from app.db import FirestoreError, get_firestore_client
from app.models import UserPreferencesUpdate, UserProfile, UserProfileUpdate

logger = get_logger(__name__)

# Firestore collection name
USERS_COLLECTION = "users"


class UserRepositoryError(FirestoreError):
    """Base exception for user repository operations."""

    pass


class UserNotFoundError(UserRepositoryError):
    """Raised when a user profile is not found (should not happen with auto-create)."""

    pass


class UserRepository:
    """
    Repository for user profile Firestore operations.
    
    All methods are async-safe and handle Firestore operations
    in a thread pool to avoid blocking the event loop.
    
    Usage:
        repo = UserRepository()
        profile = await repo.get_or_create(uid="firebase-uid-123", email="user@example.com")
        updated = await repo.update(uid="firebase-uid-123", update=UserProfileUpdate(...))
    """

    def __init__(self) -> None:
        """Initialize the repository with Firestore client."""
        self._db = get_firestore_client()

    def _get_user_ref(self, uid: str):
        """Get a document reference for a user."""
        return self._db.collection(USERS_COLLECTION).document(uid)

    async def get(self, uid: str) -> Optional[UserProfile]:
        """
        Get a user profile by UID.
        
        Args:
            uid: Firebase user ID
        
        Returns:
            UserProfile if found, None otherwise
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                logger.debug("User profile not found", uid=uid)
                return None

            data = doc.to_dict()
            if data is None:
                logger.warning("Document exists but has no data", uid=uid)
                return None
            
            profile = UserProfile.from_firestore_dict(data)
            
            logger.debug("User profile retrieved", uid=uid)
            return profile

        except Exception as e:
            logger.error(
                "Failed to get user profile",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to retrieve user profile",
                f"Firestore get failed for uid={uid}: {e}",
            ) from e

    async def get_or_create(
        self,
        uid: str,
        email: Optional[str] = None,
    ) -> UserProfile:
        """
        Get existing profile or create with defaults.
        
        This is the primary method for accessing user profiles.
        It implements auto-initialization on first access.
        
        Args:
            uid: Firebase user ID
            email: User's email (used for new profile creation)
        
        Returns:
            UserProfile (existing or newly created)
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if doc.exists:
                data = doc.to_dict()
                if data is not None:
                    profile = UserProfile.from_firestore_dict(data)
                    logger.debug("Existing user profile retrieved", uid=uid)
                    return profile

            # Create new profile with defaults
            profile = UserProfile.create_default(uid=uid, email=email)
            await asyncio.to_thread(doc_ref.set, profile.to_firestore_dict())

            logger.info(
                "Created new user profile with defaults",
                uid=uid,
                email=email,
            )
            return profile

        except Exception as e:
            logger.error(
                "Failed to get or create user profile",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to access user profile",
                f"Firestore get_or_create failed for uid={uid}: {e}",
            ) from e

    async def create(
        self,
        uid: str,
        email: Optional[str] = None,
        profile: Optional[UserProfile] = None,
    ) -> UserProfile:
        """
        Create a new user profile.
        
        This is idempotent - if profile already exists, it's returned unchanged.
        Use update() to modify existing profiles.
        
        Args:
            uid: Firebase user ID
            email: User's email
            profile: Optional pre-configured profile (uses defaults if None)
        
        Returns:
            Created or existing UserProfile
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if doc.exists:
                # Profile exists - return it unchanged (idempotent)
                data = doc.to_dict()
                if data is not None:
                    existing = UserProfile.from_firestore_dict(data)
                    logger.debug("Profile already exists, returning existing", uid=uid)
                    return existing

            # Create new profile
            if profile is None:
                profile = UserProfile.create_default(uid=uid, email=email)
            
            await asyncio.to_thread(doc_ref.set, profile.to_firestore_dict())
            
            logger.info("Created new user profile", uid=uid)
            return profile

        except Exception as e:
            logger.error(
                "Failed to create user profile",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to create user profile",
                f"Firestore create failed for uid={uid}: {e}",
            ) from e

    async def update(
        self,
        uid: str,
        update: UserProfileUpdate,
    ) -> UserProfile:
        """
        Partially update a user profile.
        
        Only fields present in the update are modified.
        Unspecified fields remain unchanged (PATCH semantics).
        
        Args:
            uid: Firebase user ID
            update: Partial update data
        
        Returns:
            Updated UserProfile
        
        Raises:
            UserNotFoundError: If profile doesn't exist
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                raise UserNotFoundError(
                    "User profile not found",
                    f"No profile exists for uid={uid}",
                )

            # Build update dict with only provided fields
            update_data = update.model_dump(exclude_none=True)
            
            if not update_data:
                # No fields to update - return existing profile
                data = doc.to_dict()
                if data is None:
                    raise UserNotFoundError(
                        "User profile not found",
                        f"Document has no data for uid={uid}",
                    )
                return UserProfile.from_firestore_dict(data)

            # Add updated_at timestamp
            update_data["updated_at"] = datetime.utcnow().isoformat()

            # Handle nested preferences update
            if "preferences" in update_data and update.preferences is not None:
                # Convert preferences to dict for Firestore
                update_data["preferences"] = update.preferences.model_dump(mode="json")

            # Perform partial update
            await asyncio.to_thread(doc_ref.update, update_data)

            # Fetch and return updated document
            updated_doc = await asyncio.to_thread(doc_ref.get)
            updated_data = updated_doc.to_dict()
            if updated_data is None:
                raise UserRepositoryError(
                    "Failed to retrieve updated profile",
                    f"Updated document has no data for uid={uid}",
                )
            updated_profile = UserProfile.from_firestore_dict(updated_data)

            logger.info(
                "Updated user profile",
                uid=uid,
                updated_fields=list(update_data.keys()),
            )
            return updated_profile

        except UserNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to update user profile",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to update user profile",
                f"Firestore update failed for uid={uid}: {e}",
            ) from e

    async def update_preferences(
        self,
        uid: str,
        update: UserPreferencesUpdate,
    ) -> UserProfile:
        """
        Partially update user preferences.
        
        Only preference fields present in the update are modified.
        This allows updating individual preference fields without
        affecting the entire preferences object.
        
        Args:
            uid: Firebase user ID
            update: Partial preferences update
        
        Returns:
            Updated UserProfile
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                raise UserNotFoundError(
                    "User profile not found",
                    f"No profile exists for uid={uid}",
                )

            # Get current profile
            current_data = doc.to_dict()
            if current_data is None:
                raise UserNotFoundError(
                    "User profile not found",
                    f"Document has no data for uid={uid}",
                )
            current_preferences = current_data.get("preferences", {})

            # Build preferences update dict with only provided fields
            pref_update = update.model_dump(exclude_none=True, mode="json")
            
            if not pref_update:
                # No fields to update - return existing profile
                return UserProfile.from_firestore_dict(current_data)

            # Merge updates into current preferences
            merged_preferences = {**current_preferences, **pref_update}

            # Update document
            update_data = {
                "preferences": merged_preferences,
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            await asyncio.to_thread(doc_ref.update, update_data)

            # Fetch and return updated document
            updated_doc = await asyncio.to_thread(doc_ref.get)
            updated_data = updated_doc.to_dict()
            if updated_data is None:
                raise UserRepositoryError(
                    "Failed to retrieve updated profile",
                    f"Updated document has no data for uid={uid}",
                )
            updated_profile = UserProfile.from_firestore_dict(updated_data)

            logger.info(
                "Updated user preferences",
                uid=uid,
                updated_fields=list(pref_update.keys()),
            )
            return updated_profile

        except UserNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to update user preferences",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to update user preferences",
                f"Firestore preferences update failed for uid={uid}: {e}",
            ) from e

    async def delete(self, uid: str) -> bool:
        """
        Delete a user profile.
        
        This is a soft-delete consideration for production.
        Currently implements hard delete.
        
        Args:
            uid: Firebase user ID
        
        Returns:
            True if deleted, False if didn't exist
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                logger.debug("Profile doesn't exist for deletion", uid=uid)
                return False

            await asyncio.to_thread(doc_ref.delete)
            
            logger.info("Deleted user profile", uid=uid)
            return True

        except Exception as e:
            logger.error(
                "Failed to delete user profile",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to delete user profile",
                f"Firestore delete failed for uid={uid}: {e}",
            ) from e

    async def exists(self, uid: str) -> bool:
        """
        Check if a user profile exists.
        
        Args:
            uid: Firebase user ID
        
        Returns:
            True if profile exists
        """
        try:
            doc_ref = self._get_user_ref(uid)
            doc = await asyncio.to_thread(doc_ref.get)
            return doc.exists

        except Exception as e:
            logger.error(
                "Failed to check user profile existence",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise UserRepositoryError(
                "Failed to check user profile",
                f"Firestore exists check failed for uid={uid}: {e}",
            ) from e
