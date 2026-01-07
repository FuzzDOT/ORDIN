"""
User Models
===========
Pydantic v2 models for user profiles and preferences.

These models represent the data stored in Firestore for each user.
They provide strong typing, validation, and explicit defaults for
all user-related data structures.

STORAGE: All user data is stored in the 'users' Firestore collection,
with the Firebase UID as the document ID.
"""

from datetime import datetime, time
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, field_validator


class DayOfWeek(str, Enum):
    """Days of the week for scheduling preferences."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class FocusBlockLength(int, Enum):
    """
    Supported focus block lengths in minutes.
    
    These represent the standard Pomodoro-style focus intervals
    that users can configure for their scheduling preferences.
    """

    SHORT = 25  # Traditional Pomodoro
    MEDIUM = 45  # Extended focus
    LONG = 60  # Deep work
    EXTENDED = 90  # Ultra-deep work


class TimeOfDay(BaseModel):
    """
    Time of day representation for wake/sleep times.
    
    Uses 24-hour format with hour and minute components.
    This is stored as a simple object in Firestore for query flexibility.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    hour: Annotated[int, Field(ge=0, le=23)] = Field(
        description="Hour in 24-hour format (0-23)"
    )
    minute: Annotated[int, Field(ge=0, le=59)] = Field(
        default=0,
        description="Minute (0-59)",
    )

    def to_time(self) -> time:
        """Convert to Python time object."""
        return time(hour=self.hour, minute=self.minute)

    @classmethod
    def from_time(cls, t: time) -> "TimeOfDay":
        """Create from Python time object."""
        return cls(hour=t.hour, minute=t.minute)

    def __str__(self) -> str:
        """Format as HH:MM string."""
        return f"{self.hour:02d}:{self.minute:02d}"


class UserPreferences(BaseModel):
    """
    User scheduling and personalization preferences.
    
    These preferences inform the scheduling algorithms but contain
    NO business logic themselves. They are pure data storage.
    
    All fields have sensible defaults to support auto-initialization
    on first user access.
    """

    model_config = {"extra": "forbid"}

    # Timezone for scheduling (IANA timezone identifier)
    timezone: str = Field(
        default="UTC",
        description="User's timezone in IANA format (e.g., 'America/New_York')",
        min_length=1,
        max_length=64,
    )

    # Daily schedule boundaries
    typical_wake_time: TimeOfDay = Field(
        default_factory=lambda: TimeOfDay(hour=7, minute=0),
        description="Typical wake time for scheduling availability",
    )
    typical_sleep_time: TimeOfDay = Field(
        default_factory=lambda: TimeOfDay(hour=23, minute=0),
        description="Typical sleep time for scheduling cutoff",
    )

    # Focus block preferences
    preferred_focus_block_lengths: list[FocusBlockLength] = Field(
        default_factory=lambda: [FocusBlockLength.MEDIUM],
        description="Preferred focus block durations in minutes",
        min_length=1,
        max_length=4,
    )

    # Working days (for scheduling)
    preferred_working_days: list[DayOfWeek] = Field(
        default_factory=lambda: [
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
        ],
        description="Days when user is typically available for work",
        min_length=1,
        max_length=7,
    )

    # Notification preferences (for future use)
    notifications_enabled: bool = Field(
        default=True,
        description="Whether to receive scheduling notifications",
    )
    
    # Quiet hours (no notifications)
    quiet_hours_start: Optional[TimeOfDay] = Field(
        default=None,
        description="Start of quiet hours (no notifications)",
    )
    quiet_hours_end: Optional[TimeOfDay] = Field(
        default=None,
        description="End of quiet hours",
    )

    @field_validator("preferred_working_days", mode="after")
    @classmethod
    def deduplicate_working_days(cls, v: list[DayOfWeek]) -> list[DayOfWeek]:
        """Remove duplicate days while preserving order."""
        seen = set()
        result = []
        for day in v:
            if day not in seen:
                seen.add(day)
                result.append(day)
        return result

    @field_validator("preferred_focus_block_lengths", mode="after")
    @classmethod
    def deduplicate_focus_lengths(
        cls, v: list[FocusBlockLength]
    ) -> list[FocusBlockLength]:
        """Remove duplicate lengths while preserving order."""
        seen = set()
        result = []
        for length in v:
            if length not in seen:
                seen.add(length)
                result.append(length)
        return result


class UserProfile(BaseModel):
    """
    Complete user profile stored in Firestore.
    
    This is the top-level document model for the 'users' collection.
    Each document is keyed by the Firebase UID.
    
    STORAGE STRUCTURE:
        Collection: users
        Document ID: {firebase_uid}
        Fields: All fields from this model
    
    VERSION HISTORY:
        v1: Initial profile with preferences (current)
    """

    model_config = {"extra": "forbid"}

    # Schema version for forward compatibility
    schema_version: int = Field(
        default=1,
        description="Schema version for migrations",
        ge=1,
    )

    # Firebase UID (stored for convenience, matches document ID)
    uid: str = Field(
        description="Firebase user ID (document ID)",
        min_length=1,
        max_length=128,
    )

    # Basic profile information
    email: Optional[str] = Field(
        default=None,
        description="User's email (from Firebase, cached)",
        max_length=320,
    )
    display_name: Optional[str] = Field(
        default=None,
        description="User's display name",
        max_length=100,
    )

    # User preferences (nested object)
    preferences: UserPreferences = Field(
        default_factory=UserPreferences,
        description="User scheduling and notification preferences",
    )

    # Metadata (managed automatically)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Profile creation timestamp (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp (UTC)",
    )

    # Onboarding status
    onboarding_completed: bool = Field(
        default=False,
        description="Whether user has completed onboarding flow",
    )

    def to_firestore_dict(self) -> dict:
        """
        Convert to Firestore-compatible dictionary.
        
        Handles enum serialization and datetime formatting.
        """
        data = self.model_dump(mode="json")
        return data

    @classmethod
    def from_firestore_dict(cls, data: dict) -> "UserProfile":
        """
        Create from Firestore document data.
        
        Handles deserialization of enums and datetime fields.
        """
        return cls.model_validate(data)

    @classmethod
    def create_default(cls, uid: str, email: Optional[str] = None) -> "UserProfile":
        """
        Create a new profile with default values.
        
        Used for auto-initialization on first user access.
        
        Args:
            uid: Firebase user ID
            email: User's email (optional, from Firebase token)
        
        Returns:
            UserProfile with all default preferences
        """
        now = datetime.utcnow()
        return cls(
            uid=uid,
            email=email,
            created_at=now,
            updated_at=now,
        )


class UserProfileUpdate(BaseModel):
    """
    Partial update model for user profiles.
    
    All fields are optional to support PATCH semantics.
    Only provided fields will be updated; others remain unchanged.
    """

    model_config = {"extra": "forbid"}

    display_name: Optional[str] = Field(
        default=None,
        description="User's display name",
        max_length=100,
    )
    preferences: Optional[UserPreferences] = Field(
        default=None,
        description="Updated preferences (replaces entire preferences object)",
    )
    onboarding_completed: Optional[bool] = Field(
        default=None,
        description="Onboarding completion status",
    )


class UserPreferencesUpdate(BaseModel):
    """
    Partial update model for user preferences only.
    
    Allows updating individual preference fields without affecting others.
    """

    model_config = {"extra": "forbid"}

    timezone: Optional[str] = Field(
        default=None,
        description="User's timezone in IANA format",
        min_length=1,
        max_length=64,
    )
    typical_wake_time: Optional[TimeOfDay] = Field(
        default=None,
        description="Typical wake time",
    )
    typical_sleep_time: Optional[TimeOfDay] = Field(
        default=None,
        description="Typical sleep time",
    )
    preferred_focus_block_lengths: Optional[list[FocusBlockLength]] = Field(
        default=None,
        description="Preferred focus block durations",
        min_length=1,
        max_length=4,
    )
    preferred_working_days: Optional[list[DayOfWeek]] = Field(
        default=None,
        description="Preferred working days",
        min_length=1,
        max_length=7,
    )
    notifications_enabled: Optional[bool] = Field(
        default=None,
        description="Notification preference",
    )
    quiet_hours_start: Optional[TimeOfDay] = Field(
        default=None,
        description="Quiet hours start",
    )
    quiet_hours_end: Optional[TimeOfDay] = Field(
        default=None,
        description="Quiet hours end",
    )


# Re-export task models for convenient imports
from app.models.task import (
    Task,
    TaskConstraints,
    TaskCreate,
    TaskDomain,
    TaskListFilters,
    TaskStatus,
    TaskUpdate,
)

# Re-export calendar models for convenient imports (A5)
from app.models.calendar import (
    AvailabilityRequest,
    AvailabilityResponse,
    AvailabilitySlot,
    BusyBlock,
    BusyBlockType,
    CalendarIntegration,
    CalendarProvider,
    CalendarSyncResult,
    IntegrationStatus,
    SyncWindow,
)

__all__ = [
    # User models
    "DayOfWeek",
    "FocusBlockLength",
    "TimeOfDay",
    "UserPreferences",
    "UserPreferencesUpdate",
    "UserProfile",
    "UserProfileUpdate",
    # Task models
    "Task",
    "TaskConstraints",
    "TaskCreate",
    "TaskDomain",
    "TaskListFilters",
    "TaskStatus",
    "TaskUpdate",
    # Calendar models (A5)
    "AvailabilityRequest",
    "AvailabilityResponse",
    "AvailabilitySlot",
    "BusyBlock",
    "BusyBlockType",
    "CalendarIntegration",
    "CalendarProvider",
    "CalendarSyncResult",
    "IntegrationStatus",
    "SyncWindow",
]
