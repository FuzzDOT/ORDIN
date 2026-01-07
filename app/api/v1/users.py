"""
User Profile API Endpoints
==========================
REST API for user profile and preferences management.

All endpoints require Firebase authentication (A2).
Users can only access their own profile data.

ENDPOINTS:
    GET  /api/v1/users/me/profile         - Get current user's profile
    PATCH /api/v1/users/me/profile        - Update profile fields
    PATCH /api/v1/users/me/preferences    - Update preference fields
    POST /api/v1/users/me/onboarding      - Mark onboarding complete
    DELETE /api/v1/users/me/profile       - Delete user profile

SECURITY:
- All endpoints require valid Firebase ID token
- Users can only access their own data (enforced by /me pattern)
- No cross-user access is possible through this API
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.core.logging import get_logger
from app.models import (
    DayOfWeek,
    FocusBlockLength,
    TimeOfDay,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfile,
    UserProfileUpdate,
)
from app.services import UserService
from app.services.user_service import UserServiceError

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# -----------------------------------------------------------------------------
# Response Models (versioned, stable API contracts)
# -----------------------------------------------------------------------------


class TimeOfDayResponse(BaseModel):
    """Time of day in API responses."""

    hour: int = Field(ge=0, le=23, description="Hour (0-23)")
    minute: int = Field(ge=0, le=59, description="Minute (0-59)")


class UserPreferencesResponse(BaseModel):
    """User preferences in API responses."""

    timezone: str = Field(description="IANA timezone identifier")
    typical_wake_time: TimeOfDayResponse = Field(description="Typical wake time")
    typical_sleep_time: TimeOfDayResponse = Field(description="Typical sleep time")
    preferred_focus_block_lengths: list[int] = Field(
        description="Preferred focus block durations in minutes"
    )
    preferred_working_days: list[str] = Field(
        description="Preferred working days"
    )
    notifications_enabled: bool = Field(description="Notifications enabled")
    quiet_hours_start: TimeOfDayResponse | None = Field(
        default=None, description="Quiet hours start"
    )
    quiet_hours_end: TimeOfDayResponse | None = Field(
        default=None, description="Quiet hours end"
    )

    @classmethod
    def from_model(cls, prefs: UserPreferences) -> "UserPreferencesResponse":
        """Create response from internal model."""
        return cls(
            timezone=prefs.timezone,
            typical_wake_time=TimeOfDayResponse(
                hour=prefs.typical_wake_time.hour,
                minute=prefs.typical_wake_time.minute,
            ),
            typical_sleep_time=TimeOfDayResponse(
                hour=prefs.typical_sleep_time.hour,
                minute=prefs.typical_sleep_time.minute,
            ),
            preferred_focus_block_lengths=[
                length.value for length in prefs.preferred_focus_block_lengths
            ],
            preferred_working_days=[
                day.value for day in prefs.preferred_working_days
            ],
            notifications_enabled=prefs.notifications_enabled,
            quiet_hours_start=(
                TimeOfDayResponse(
                    hour=prefs.quiet_hours_start.hour,
                    minute=prefs.quiet_hours_start.minute,
                )
                if prefs.quiet_hours_start
                else None
            ),
            quiet_hours_end=(
                TimeOfDayResponse(
                    hour=prefs.quiet_hours_end.hour,
                    minute=prefs.quiet_hours_end.minute,
                )
                if prefs.quiet_hours_end
                else None
            ),
        )


class UserProfileResponse(BaseModel):
    """
    User profile API response.
    
    This is the stable, versioned response format for frontend consumption.
    Internal model changes should not break this contract.
    """

    uid: str = Field(description="Firebase user ID")
    email: str | None = Field(default=None, description="User email")
    display_name: str | None = Field(default=None, description="Display name")
    preferences: UserPreferencesResponse = Field(description="User preferences")
    onboarding_completed: bool = Field(description="Onboarding status")
    created_at: str = Field(description="Profile creation timestamp (ISO 8601)")
    updated_at: str = Field(description="Last update timestamp (ISO 8601)")
    schema_version: int = Field(description="Profile schema version")

    @classmethod
    def from_model(cls, profile: UserProfile) -> "UserProfileResponse":
        """Create response from internal model."""
        return cls(
            uid=profile.uid,
            email=profile.email,
            display_name=profile.display_name,
            preferences=UserPreferencesResponse.from_model(profile.preferences),
            onboarding_completed=profile.onboarding_completed,
            created_at=profile.created_at.isoformat() + "Z",
            updated_at=profile.updated_at.isoformat() + "Z",
            schema_version=profile.schema_version,
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "uid": "firebase-uid-123456",
                    "email": "user@example.com",
                    "display_name": "John Doe",
                    "preferences": {
                        "timezone": "America/New_York",
                        "typical_wake_time": {"hour": 7, "minute": 0},
                        "typical_sleep_time": {"hour": 23, "minute": 0},
                        "preferred_focus_block_lengths": [45, 60],
                        "preferred_working_days": [
                            "monday",
                            "tuesday",
                            "wednesday",
                            "thursday",
                            "friday",
                        ],
                        "notifications_enabled": True,
                        "quiet_hours_start": None,
                        "quiet_hours_end": None,
                    },
                    "onboarding_completed": True,
                    "created_at": "2026-01-06T12:00:00Z",
                    "updated_at": "2026-01-06T14:30:00Z",
                    "schema_version": 1,
                }
            ]
        }
    }


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------


class TimeOfDayRequest(BaseModel):
    """Time of day in API requests."""

    hour: Annotated[int, Field(ge=0, le=23, description="Hour (0-23)")]
    minute: Annotated[int, Field(ge=0, le=59, default=0, description="Minute (0-59)")]

    def to_model(self) -> TimeOfDay:
        """Convert to internal model."""
        return TimeOfDay(hour=self.hour, minute=self.minute)


class UpdateProfileRequest(BaseModel):
    """Request body for profile updates (PATCH)."""

    display_name: str | None = Field(
        default=None,
        max_length=100,
        description="User's display name",
    )

    model_config = {"extra": "forbid"}


class UpdatePreferencesRequest(BaseModel):
    """Request body for preferences updates (PATCH)."""

    timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="IANA timezone identifier (e.g., 'America/New_York')",
    )
    typical_wake_time: TimeOfDayRequest | None = Field(
        default=None,
        description="Typical wake time",
    )
    typical_sleep_time: TimeOfDayRequest | None = Field(
        default=None,
        description="Typical sleep time",
    )
    preferred_focus_block_lengths: list[int] | None = Field(
        default=None,
        min_length=1,
        max_length=4,
        description="Focus block durations in minutes (25, 45, 60, 90)",
    )
    preferred_working_days: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=7,
        description="Working days (monday, tuesday, etc.)",
    )
    notifications_enabled: bool | None = Field(
        default=None,
        description="Enable notifications",
    )
    quiet_hours_start: TimeOfDayRequest | None = Field(
        default=None,
        description="Quiet hours start time",
    )
    quiet_hours_end: TimeOfDayRequest | None = Field(
        default=None,
        description="Quiet hours end time",
    )

    model_config = {"extra": "forbid"}

    def to_update_model(self) -> UserPreferencesUpdate:
        """Convert to internal update model."""
        # Convert focus block lengths to enum
        focus_lengths = None
        if self.preferred_focus_block_lengths is not None:
            focus_lengths = []
            for length in self.preferred_focus_block_lengths:
                try:
                    focus_lengths.append(FocusBlockLength(length))
                except ValueError:
                    # Invalid length - will be caught by validation
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid focus block length: {length}. Must be one of: 25, 45, 60, 90",
                    )

        # Convert working days to enum
        working_days = None
        if self.preferred_working_days is not None:
            working_days = []
            for day in self.preferred_working_days:
                try:
                    working_days.append(DayOfWeek(day.lower()))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid day: {day}. Must be one of: monday, tuesday, wednesday, thursday, friday, saturday, sunday",
                    )

        return UserPreferencesUpdate(
            timezone=self.timezone,
            typical_wake_time=(
                self.typical_wake_time.to_model()
                if self.typical_wake_time
                else None
            ),
            typical_sleep_time=(
                self.typical_sleep_time.to_model()
                if self.typical_sleep_time
                else None
            ),
            preferred_focus_block_lengths=focus_lengths,
            preferred_working_days=working_days,
            notifications_enabled=self.notifications_enabled,
            quiet_hours_start=(
                self.quiet_hours_start.to_model()
                if self.quiet_hours_start
                else None
            ),
            quiet_hours_end=(
                self.quiet_hours_end.to_model()
                if self.quiet_hours_end
                else None
            ),
        )


class SuccessResponse(BaseModel):
    """Simple success response."""

    success: bool = Field(default=True)
    message: str = Field(description="Success message")


# -----------------------------------------------------------------------------
# Dependency: User Service
# -----------------------------------------------------------------------------


def get_user_service() -> UserService:
    """Dependency provider for UserService."""
    return UserService()


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Get current user's profile",
    description="Retrieve the authenticated user's profile. Creates profile with defaults on first access.",
)
async def get_profile(
    user: CurrentUserDep,
    service: UserServiceDep,
) -> UserProfileResponse:
    """
    Get the current user's profile.
    
    Auto-creates profile with default preferences on first access.
    """
    try:
        profile = await service.get_profile(user=user)
        return UserProfileResponse.from_model(profile)
    except UserServiceError as e:
        logger.error("Failed to get profile", uid=user.uid, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile",
        )


@router.patch(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Update current user's profile",
    description="Partially update the authenticated user's profile. Only provided fields are updated.",
)
async def update_profile(
    user: CurrentUserDep,
    service: UserServiceDep,
    request: UpdateProfileRequest,
) -> UserProfileResponse:
    """
    Update the current user's profile.
    
    Partial update - only provided fields are modified.
    """
    try:
        update = UserProfileUpdate(display_name=request.display_name)
        profile = await service.update_profile(user=user, update=update)
        return UserProfileResponse.from_model(profile)
    except UserServiceError as e:
        logger.error("Failed to update profile", uid=user.uid, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile",
        )


@router.patch(
    "/me/preferences",
    response_model=UserProfileResponse,
    summary="Update current user's preferences",
    description="Partially update scheduling preferences. Only provided fields are updated.",
)
async def update_preferences(
    user: CurrentUserDep,
    service: UserServiceDep,
    request: UpdatePreferencesRequest,
) -> UserProfileResponse:
    """
    Update the current user's preferences.
    
    Partial update - only provided preference fields are modified.
    """
    try:
        update = request.to_update_model()
        profile = await service.update_preferences(user=user, update=update)
        return UserProfileResponse.from_model(profile)
    except UserServiceError as e:
        logger.error("Failed to update preferences", uid=user.uid, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        )


@router.post(
    "/me/onboarding/complete",
    response_model=UserProfileResponse,
    summary="Mark onboarding as complete",
    description="Mark the user's onboarding flow as completed.",
)
async def complete_onboarding(
    user: CurrentUserDep,
    service: UserServiceDep,
) -> UserProfileResponse:
    """Mark onboarding as complete."""
    try:
        profile = await service.complete_onboarding(user=user)
        return UserProfileResponse.from_model(profile)
    except UserServiceError as e:
        logger.error("Failed to complete onboarding", uid=user.uid, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete onboarding",
        )


@router.delete(
    "/me/profile",
    response_model=SuccessResponse,
    summary="Delete current user's profile",
    description="Permanently delete the authenticated user's profile and all associated data.",
)
async def delete_profile(
    user: CurrentUserDep,
    service: UserServiceDep,
) -> SuccessResponse:
    """
    Delete the current user's profile.
    
    WARNING: This is permanent and cannot be undone.
    """
    try:
        deleted = await service.delete_profile(user=user)
        if deleted:
            return SuccessResponse(message="Profile deleted successfully")
        return SuccessResponse(message="No profile to delete")
    except UserServiceError as e:
        logger.error("Failed to delete profile", uid=user.uid, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile",
        )
