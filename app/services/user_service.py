"""
User Service
============
Service layer for user profile operations.

This service provides a clean interface between API handlers and
the user repository. It handles:
- User context validation (ensuring users can only access their own data)
- Profile auto-initialization
- Consistent error handling

NOTE: No business logic, decision logic, or personalization algorithms
are implemented here. This is pure data access and validation.
"""

from typing import Optional

from app.auth.context import UserContext
from app.core.logging import get_logger
from app.models import UserPreferencesUpdate, UserProfile, UserProfileUpdate
from app.repositories import UserRepository
from app.repositories.user_repository import UserNotFoundError, UserRepositoryError

logger = get_logger(__name__)


class UserServiceError(Exception):
    """Base exception for user service operations."""

    def __init__(self, message: str, internal_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.internal_message = internal_message or message


class UserAccessDeniedError(UserServiceError):
    """Raised when a user attempts to access another user's data."""

    pass


class UserService:
    """
    Service for user profile operations.
    
    All operations require a UserContext from authentication.
    Users can only access their own profiles (enforced by this service).
    
    Usage:
        service = UserService()
        profile = await service.get_profile(user=current_user)
        updated = await service.update_profile(user=current_user, update=data)
    """

    def __init__(self) -> None:
        """Initialize service with repository."""
        self._repository = UserRepository()

    async def get_profile(self, user: UserContext) -> UserProfile:
        """
        Get the current user's profile.
        
        Auto-creates profile with defaults if it doesn't exist.
        
        Args:
            user: Authenticated user context (from A2)
        
        Returns:
            UserProfile for the authenticated user
        """
        try:
            profile = await self._repository.get_or_create(
                uid=user.uid,
                email=user.email,
            )
            
            logger.debug(
                "Retrieved user profile",
                uid=user.uid,
                schema_version=profile.schema_version,
            )
            return profile

        except UserRepositoryError as e:
            logger.error(
                "Failed to get user profile",
                uid=user.uid,
                error=e.internal_message,
            )
            raise UserServiceError(
                "Failed to retrieve profile",
                e.internal_message,
            ) from e

    async def update_profile(
        self,
        user: UserContext,
        update: UserProfileUpdate,
    ) -> UserProfile:
        """
        Update the current user's profile.
        
        Partial update - only provided fields are modified.
        
        Args:
            user: Authenticated user context
            update: Partial profile update data
        
        Returns:
            Updated UserProfile
        """
        try:
            # Ensure profile exists (auto-create if needed)
            await self._repository.get_or_create(uid=user.uid, email=user.email)
            
            # Perform update
            updated_profile = await self._repository.update(
                uid=user.uid,
                update=update,
            )
            
            logger.info(
                "Updated user profile",
                uid=user.uid,
            )
            return updated_profile

        except UserNotFoundError:
            # This shouldn't happen due to get_or_create, but handle gracefully
            logger.error("Profile not found after get_or_create", uid=user.uid)
            raise UserServiceError(
                "Profile not found",
                f"Profile disappeared for uid={user.uid}",
            )
        except UserRepositoryError as e:
            logger.error(
                "Failed to update user profile",
                uid=user.uid,
                error=e.internal_message,
            )
            raise UserServiceError(
                "Failed to update profile",
                e.internal_message,
            ) from e

    async def update_preferences(
        self,
        user: UserContext,
        update: UserPreferencesUpdate,
    ) -> UserProfile:
        """
        Update the current user's preferences.
        
        Partial update - only provided preference fields are modified.
        
        Args:
            user: Authenticated user context
            update: Partial preferences update data
        
        Returns:
            Updated UserProfile
        """
        try:
            # Ensure profile exists (auto-create if needed)
            await self._repository.get_or_create(uid=user.uid, email=user.email)
            
            # Perform preferences update
            updated_profile = await self._repository.update_preferences(
                uid=user.uid,
                update=update,
            )
            
            logger.info(
                "Updated user preferences",
                uid=user.uid,
            )
            return updated_profile

        except UserNotFoundError:
            logger.error("Profile not found after get_or_create", uid=user.uid)
            raise UserServiceError(
                "Profile not found",
                f"Profile disappeared for uid={user.uid}",
            )
        except UserRepositoryError as e:
            logger.error(
                "Failed to update user preferences",
                uid=user.uid,
                error=e.internal_message,
            )
            raise UserServiceError(
                "Failed to update preferences",
                e.internal_message,
            ) from e

    async def complete_onboarding(self, user: UserContext) -> UserProfile:
        """
        Mark user onboarding as completed.
        
        Args:
            user: Authenticated user context
        
        Returns:
            Updated UserProfile with onboarding_completed=True
        """
        update = UserProfileUpdate(onboarding_completed=True)
        return await self.update_profile(user=user, update=update)

    async def delete_profile(self, user: UserContext) -> bool:
        """
        Delete the current user's profile.
        
        WARNING: This is destructive and should be used carefully.
        Consider implementing soft delete in production.
        
        Args:
            user: Authenticated user context
        
        Returns:
            True if profile was deleted
        """
        try:
            deleted = await self._repository.delete(uid=user.uid)
            
            if deleted:
                logger.info("Deleted user profile", uid=user.uid)
            else:
                logger.debug("No profile to delete", uid=user.uid)
            
            return deleted

        except UserRepositoryError as e:
            logger.error(
                "Failed to delete user profile",
                uid=user.uid,
                error=e.internal_message,
            )
            raise UserServiceError(
                "Failed to delete profile",
                e.internal_message,
            ) from e
