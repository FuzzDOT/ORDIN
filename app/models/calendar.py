"""
Calendar Models
===============
Pydantic v2 models for calendar integration and availability.

These models support:
- Calendar integration state (OAuth tokens, sync status)
- Privacy-preserving busy blocks (no event titles/descriptions)
- Availability computation (free slots)

STORAGE:
- Integration state: users/{uid}/integrations/calendar/{provider}
- Busy blocks: users/{uid}/calendar_busy_blocks/{block_id}

PRIVACY: By design, only busy/free status is stored. Event details
(titles, descriptions, attendees) are NEVER persisted.
"""

from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CalendarProvider(str, Enum):
    """
    Supported calendar providers.
    
    Designed for extensibility - add new providers here.
    """

    GOOGLE = "google"
    APPLE = "apple"  # Future
    MICROSOFT = "microsoft"  # Future


class IntegrationStatus(str, Enum):
    """
    Calendar integration connection status.
    """

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"  # OAuth in progress


class BusyBlockType(str, Enum):
    """
    Type of busy block for future extensibility.
    
    Currently only 'busy' is used, but this allows for:
    - tentative: Maybe busy (for tentative calendar events)
    - focus: Protected focus time (from user preferences)
    """

    BUSY = "busy"
    TENTATIVE = "tentative"
    FOCUS = "focus"


class CalendarIntegration(BaseModel):
    """
    OAuth integration state for a calendar provider.
    
    Stored in Firestore at: users/{uid}/integrations/calendar/{provider}
    
    SECURITY:
    - Access token is short-lived and used for API calls
    - Refresh token is long-lived and used to get new access tokens
    - Tokens should ideally be encrypted at rest (Phase 2)
    """

    model_config = {"extra": "forbid"}

    provider: CalendarProvider = Field(
        description="Calendar provider identifier"
    )
    status: IntegrationStatus = Field(
        default=IntegrationStatus.PENDING,
        description="Current integration status"
    )
    
    # OAuth tokens
    access_token: Optional[str] = Field(
        default=None,
        description="OAuth access token (short-lived)"
    )
    refresh_token: Optional[str] = Field(
        default=None,
        description="OAuth refresh token (long-lived, for token refresh)"
    )
    token_expiry: Optional[datetime] = Field(
        default=None,
        description="Access token expiration time"
    )
    
    # Scope tracking
    scopes: list[str] = Field(
        default_factory=list,
        description="Granted OAuth scopes"
    )
    
    # Sync state
    last_sync_at: Optional[datetime] = Field(
        default=None,
        description="Last successful sync timestamp"
    )
    last_sync_error: Optional[str] = Field(
        default=None,
        description="Last sync error message (if any)"
    )
    
    # Timestamps
    connected_at: Optional[datetime] = Field(
        default=None,
        description="When the integration was first connected"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )

    @field_validator("token_expiry", "last_sync_at", "connected_at", "updated_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> Optional[datetime]:
        """Parse ISO string to datetime if needed."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("Must be ISO 8601 datetime string")

    def is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire."""
        if self.token_expiry is None:
            return True
        # Consider expired if less than 5 minutes remaining
        from datetime import timedelta
        buffer = timedelta(minutes=5)
        return datetime.utcnow() >= (self.token_expiry - buffer)

    def to_firestore_dict(self) -> dict[str, Any]:
        """Convert to Firestore-compatible dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict[str, Any]) -> "CalendarIntegration":
        """Create from Firestore document data."""
        return cls.model_validate(data)


class BusyBlock(BaseModel):
    """
    A time block when the user is busy.
    
    Stored in Firestore at: users/{uid}/calendar_busy_blocks/{block_id}
    
    PRIVACY GUARANTEES:
    - No event title stored
    - No event description stored
    - No attendee information stored
    - Only start/end times and source metadata
    
    The block_id is a deterministic hash to enable idempotent upserts.
    """

    model_config = {"extra": "forbid"}

    block_id: str = Field(
        description="Deterministic hash ID for idempotent operations"
    )
    user_id: str = Field(
        description="Firebase UID of the user"
    )
    
    # Time range
    start_time: datetime = Field(
        description="Block start time (UTC)"
    )
    end_time: datetime = Field(
        description="Block end time (UTC)"
    )
    
    # Source tracking
    source_provider: CalendarProvider = Field(
        description="Calendar provider this block came from"
    )
    source_calendar_id: Optional[str] = Field(
        default=None,
        description="Original calendar ID (for multi-calendar support)"
    )
    source_event_id: Optional[str] = Field(
        default=None,
        description="Original event ID (for deduplication, not displayed)"
    )
    
    # Block type
    block_type: BusyBlockType = Field(
        default=BusyBlockType.BUSY,
        description="Type of busy block"
    )
    
    # Sync metadata
    synced_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this block was synced"
    )

    @field_validator("start_time", "end_time", "synced_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        """Parse ISO string to datetime if needed."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("Must be ISO 8601 datetime string")

    @model_validator(mode="after")
    def validate_time_range(self) -> "BusyBlock":
        """Ensure end_time is after start_time."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    @classmethod
    def generate_block_id(
        cls,
        user_id: str,
        provider: CalendarProvider,
        source_event_id: str,
        start_time: datetime,
    ) -> str:
        """
        Generate deterministic block ID for idempotent operations.
        
        The ID is a hash of: user_id + provider + event_id + start_time
        This ensures the same event always maps to the same block_id.
        """
        components = f"{user_id}:{provider.value}:{source_event_id}:{start_time.isoformat()}"
        return sha256(components.encode()).hexdigest()[:32]

    @classmethod
    def from_calendar_event(
        cls,
        user_id: str,
        provider: CalendarProvider,
        event_id: str,
        start_time: datetime,
        end_time: datetime,
        calendar_id: Optional[str] = None,
        block_type: BusyBlockType = BusyBlockType.BUSY,
    ) -> "BusyBlock":
        """
        Factory to create BusyBlock from a calendar event.
        
        Strips all identifying information (title, description, etc.)
        and keeps only the time range and source metadata.
        """
        block_id = cls.generate_block_id(user_id, provider, event_id, start_time)
        return cls(
            block_id=block_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            source_provider=provider,
            source_calendar_id=calendar_id,
            source_event_id=event_id,
            block_type=block_type,
        )

    def to_firestore_dict(self) -> dict[str, Any]:
        """Convert to Firestore-compatible dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict[str, Any]) -> "BusyBlock":
        """Create from Firestore document data."""
        return cls.model_validate(data)


class AvailabilitySlot(BaseModel):
    """
    A time slot when the user is available (free).
    
    This is computed by subtracting busy blocks from waking hours.
    Not stored in Firestore - computed on demand.
    """

    model_config = {"extra": "forbid", "frozen": True}

    start_time: datetime = Field(
        description="Slot start time (UTC)"
    )
    end_time: datetime = Field(
        description="Slot end time (UTC)"
    )
    duration_minutes: int = Field(
        description="Slot duration in minutes"
    )

    @classmethod
    def from_time_range(cls, start: datetime, end: datetime) -> "AvailabilitySlot":
        """Create slot from time range, calculating duration."""
        duration = int((end - start).total_seconds() / 60)
        return cls(start_time=start, end_time=end, duration_minutes=duration)


class SyncWindow(BaseModel):
    """
    Configuration for calendar sync time window.
    """

    model_config = {"extra": "forbid", "frozen": True}

    start: datetime = Field(description="Sync window start (inclusive)")
    end: datetime = Field(description="Sync window end (exclusive)")
    
    @classmethod
    def default_window(cls, days_ahead: int = 14) -> "SyncWindow":
        """Create default sync window (now to N days ahead)."""
        from datetime import timedelta
        now = datetime.utcnow()
        # Start from beginning of current day
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days_ahead)
        return cls(start=start, end=end)


class CalendarSyncResult(BaseModel):
    """
    Result of a calendar sync operation.
    """

    model_config = {"extra": "forbid"}

    provider: CalendarProvider = Field(description="Provider that was synced")
    success: bool = Field(description="Whether sync completed successfully")
    blocks_created: int = Field(default=0, description="New blocks created")
    blocks_updated: int = Field(default=0, description="Existing blocks updated")
    blocks_deleted: int = Field(default=0, description="Stale blocks deleted")
    sync_window_start: datetime = Field(description="Sync window start")
    sync_window_end: datetime = Field(description="Sync window end")
    error_message: Optional[str] = Field(default=None, description="Error if failed")
    synced_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Sync completion timestamp"
    )


class AvailabilityRequest(BaseModel):
    """
    Request parameters for availability computation.
    """

    model_config = {"extra": "forbid"}

    start_date: datetime = Field(
        description="Start of availability window (inclusive)"
    )
    end_date: datetime = Field(
        description="End of availability window (exclusive)"
    )
    minimum_duration_minutes: Annotated[int, Field(ge=5, le=480)] = Field(
        default=15,
        description="Minimum slot duration to return (5-480 minutes)"
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Timezone for results (uses user preference if not specified)"
    )

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        """Parse ISO string to datetime if needed."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("Must be ISO 8601 datetime string")

    @model_validator(mode="after")
    def validate_date_range(self) -> "AvailabilityRequest":
        """Ensure end_date is after start_date and range is reasonable."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        # Limit to 30 days max
        from datetime import timedelta
        if (self.end_date - self.start_date) > timedelta(days=30):
            raise ValueError("Availability window cannot exceed 30 days")
        return self


class AvailabilityResponse(BaseModel):
    """
    Response containing computed availability slots.
    """

    model_config = {"extra": "forbid"}

    slots: list[AvailabilitySlot] = Field(
        description="List of available time slots"
    )
    start_date: datetime = Field(description="Requested window start")
    end_date: datetime = Field(description="Requested window end")
    timezone: str = Field(description="Timezone used for computation")
    total_available_minutes: int = Field(
        description="Total available time in minutes"
    )
    computed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When availability was computed"
    )
