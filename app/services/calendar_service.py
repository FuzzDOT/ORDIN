"""
Calendar Service
================
Business logic for calendar integrations and availability computation.

RESPONSIBILITIES:
- OAuth flow coordination
- Calendar sync orchestration
- Availability computation using user preferences
- Token refresh handling
- Rate limit protection

DESIGN NOTES:
- Provider-agnostic: Works with any CalendarProviderInterface implementation
- Privacy-first: Never stores event titles/descriptions
- Idempotent: Sync operations can be safely retried
- User-preference aware: Uses wake/sleep times from A3

AVAILABILITY COMPUTATION:
Availability = Waking Hours - Busy Blocks - Existing Events
The service respects user's working days and wake/sleep preferences.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.auth.context import UserContext
from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.calendar import (
    CalendarAuthError,
    CalendarEvent,
    CalendarProviderError,
    CalendarProviderInterface,
    CalendarRateLimitError,
    GoogleCalendarProvider,
)
from app.models import UserPreferences
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
from app.repositories.calendar_repository import (
    CalendarRepository,
    CalendarRepositoryError,
    get_calendar_repository,
)
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)

# Default sync window configuration
DEFAULT_SYNC_DAYS_AHEAD = 14
MAX_SYNC_DAYS_AHEAD = 90


class CalendarServiceError(Exception):
    """Base exception for calendar service operations."""

    def __init__(
        self,
        message: str,
        internal_message: Optional[str] = None,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.internal_message = internal_message or message
        self.status_code = status_code


class CalendarAuthenticationError(CalendarServiceError):
    """OAuth or token errors requiring re-authentication."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(message, status_code=401, **kwargs)


class CalendarRateLimitedException(CalendarServiceError):
    """Rate limit exceeded, caller should retry later."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: Optional[int] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, status_code=429, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class CalendarNotConnectedError(CalendarServiceError):
    """Calendar provider not connected for user."""

    def __init__(self, provider: CalendarProvider) -> None:
        super().__init__(
            f"{provider.value.title()} Calendar is not connected",
            status_code=400,
        )


class CalendarService:
    """
    Service for calendar integration operations.
    
    Handles OAuth flows, calendar sync, and availability computation.
    Uses provider-agnostic interface for calendar operations.
    
    Usage:
        service = CalendarService()
        
        # Start OAuth
        auth_url = service.get_oauth_url(provider="google", state="...")
        
        # Complete OAuth
        integration = await service.complete_oauth(user, provider, code, state)
        
        # Sync calendar
        result = await service.sync_calendar(user, provider)
        
        # Get availability
        slots = await service.get_availability(user, start, end)
    """

    def __init__(
        self,
        repository: Optional[CalendarRepository] = None,
        user_repository: Optional[UserRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize service with dependencies."""
        self._repository = repository or get_calendar_repository()
        self._user_repository = user_repository or UserRepository()
        self._settings = settings or get_settings()
        self._providers: dict[CalendarProvider, CalendarProviderInterface] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize calendar provider instances."""
        # Initialize Google provider if configured
        if self._settings.google_oauth_client_id and self._settings.google_oauth_client_secret:
            self._providers[CalendarProvider.GOOGLE] = GoogleCalendarProvider(
                client_id=self._settings.google_oauth_client_id,
                client_secret=self._settings.google_oauth_client_secret,
            )

    def _get_provider(self, provider: CalendarProvider) -> CalendarProviderInterface:
        """Get provider instance, raising if not configured."""
        if provider not in self._providers:
            raise CalendarServiceError(
                f"{provider.value.title()} Calendar is not configured",
                status_code=501,
            )
        return self._providers[provider]

    # =========================================================================
    # OAUTH FLOW
    # =========================================================================

    def generate_oauth_state(self) -> str:
        """Generate a cryptographically secure OAuth state parameter."""
        return secrets.token_urlsafe(32)

    def get_oauth_url(
        self,
        provider: CalendarProvider,
        state: str,
    ) -> str:
        """
        Generate OAuth authorization URL for a calendar provider.
        
        Args:
            provider: Calendar provider to authorize
            state: CSRF protection state (should be stored server-side)
        
        Returns:
            Full OAuth authorization URL to redirect user to
        """
        provider_impl = self._get_provider(provider)
        redirect_uri = self._settings.google_oauth_redirect_uri
        return provider_impl.get_auth_url(state=state, redirect_uri=redirect_uri)

    async def complete_oauth(
        self,
        user: UserContext,
        provider: CalendarProvider,
        code: str,
        state: str,
        expected_state: str,
    ) -> CalendarIntegration:
        """
        Complete OAuth flow by exchanging code for tokens.
        
        Args:
            user: Authenticated user context
            provider: Calendar provider
            code: Authorization code from OAuth callback
            state: State from callback (must match expected)
            expected_state: State we generated initially
        
        Returns:
            CalendarIntegration with connected status
        
        Raises:
            CalendarAuthenticationError: If state mismatch or code exchange fails
        """
        # Validate state for CSRF protection
        if state != expected_state:
            logger.warning(
                "oauth_state_mismatch",
                uid=user.uid,
                provider=provider.value,
            )
            raise CalendarAuthenticationError(
                "Invalid OAuth state. Please try connecting again.",
                internal_message="OAuth state mismatch - possible CSRF attempt",
            )

        provider_impl = self._get_provider(provider)
        redirect_uri = self._settings.google_oauth_redirect_uri

        try:
            tokens = await provider_impl.exchange_code(code, redirect_uri)
        except CalendarAuthError as e:
            raise CalendarAuthenticationError(
                "Failed to connect calendar. Please try again.",
                internal_message=e.internal_message,
            )
        except CalendarProviderError as e:
            raise CalendarServiceError(
                "Failed to connect to calendar provider",
                internal_message=e.internal_message,
                status_code=502,
            )

        # Calculate token expiration
        expires_in = tokens.get("expires_in", 3600)
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Create integration record
        integration = CalendarIntegration(
            provider=provider,
            status=IntegrationStatus.CONNECTED,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            token_expiry=token_expiry,
            scopes=tokens.get("scope", "").split(),
            connected_at=datetime.now(timezone.utc),
        )

        # Save to Firestore
        await self._repository.save_integration(user.uid, integration)

        logger.info(
            "calendar_connected",
            uid=user.uid,
            provider=provider.value,
        )
        return integration

    async def disconnect(
        self,
        user: UserContext,
        provider: CalendarProvider,
    ) -> bool:
        """
        Disconnect a calendar integration.
        
        Revokes OAuth token and deletes integration + busy blocks.
        
        Args:
            user: Authenticated user context
            provider: Calendar provider to disconnect
        
        Returns:
            True if disconnected successfully
        """
        # Get existing integration
        integration = await self._repository.get_integration(user.uid, provider)
        if not integration:
            return True  # Already disconnected

        # Try to revoke token with provider
        try:
            provider_impl = self._get_provider(provider)
            token = integration.refresh_token or integration.access_token
            if token:
                await provider_impl.revoke_token(token)
        except Exception as e:
            # Log but continue - we'll delete locally anyway
            logger.warning(
                "token_revocation_failed",
                uid=user.uid,
                provider=provider.value,
                error=str(e),
            )

        # Delete integration and busy blocks
        await self._repository.delete_integration(user.uid, provider)

        logger.info(
            "calendar_disconnected",
            uid=user.uid,
            provider=provider.value,
        )
        return True

    # =========================================================================
    # TOKEN MANAGEMENT
    # =========================================================================

    async def _ensure_valid_token(
        self,
        user: UserContext,
        integration: CalendarIntegration,
    ) -> CalendarIntegration:
        """
        Ensure the access token is valid, refreshing if needed.
        
        Returns updated integration if token was refreshed.
        """
        # Check if token needs refresh (with 5-minute buffer)
        now = datetime.now(timezone.utc)
        if integration.token_expiry:
            # Handle both aware and naive datetimes
            expires_at = integration.token_expiry
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if now + timedelta(minutes=5) < expires_at:
                return integration  # Token still valid

        # Need to refresh
        if not integration.refresh_token:
            raise CalendarAuthenticationError(
                "Calendar session expired. Please reconnect.",
                internal_message="No refresh token available",
            )

        provider_impl = self._get_provider(integration.provider)
        
        try:
            tokens = await provider_impl.refresh_access_token(integration.refresh_token)
        except CalendarAuthError as e:
            # Mark integration as error state
            await self._repository.update_integration(
                user.uid,
                integration.provider,
                {
                    "status": IntegrationStatus.ERROR.value,
                    "last_sync_error": "Token refresh failed",
                },
            )
            raise CalendarAuthenticationError(
                "Calendar access expired. Please reconnect.",
                internal_message=e.internal_message,
            )

        # Calculate new expiration
        expires_in = tokens.get("expires_in", 3600)
        token_expiry = now + timedelta(seconds=expires_in)

        # Update integration with new token
        updated = await self._repository.update_integration(
            user.uid,
            integration.provider,
            {
                "access_token": tokens["access_token"],
                "token_expiry": token_expiry,
            },
        )

        logger.debug(
            "token_refreshed",
            uid=user.uid,
            provider=integration.provider.value,
        )
        return updated or integration

    # =========================================================================
    # CALENDAR SYNC
    # =========================================================================

    async def sync_calendar(
        self,
        user: UserContext,
        provider: CalendarProvider,
        days_ahead: int = DEFAULT_SYNC_DAYS_AHEAD,
        calendar_id: str = "primary",
    ) -> CalendarSyncResult:
        """
        Sync calendar events and update busy blocks.
        
        Fetches events from provider, converts to busy blocks,
        and performs idempotent upsert with stale block cleanup.
        
        Args:
            user: Authenticated user context
            provider: Calendar provider to sync
            days_ahead: How many days ahead to sync
            calendar_id: Which calendar to sync (default: primary)
        
        Returns:
            CalendarSyncResult with sync statistics
        """
        # Validate days_ahead
        if days_ahead < 1:
            days_ahead = 1
        elif days_ahead > MAX_SYNC_DAYS_AHEAD:
            days_ahead = MAX_SYNC_DAYS_AHEAD

        # Get integration
        integration = await self._repository.get_integration(user.uid, provider)
        if not integration or integration.status != IntegrationStatus.CONNECTED:
            raise CalendarNotConnectedError(provider)

        # Ensure valid token
        integration = await self._ensure_valid_token(user, integration)

        # Define sync window
        now = datetime.now(timezone.utc)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=days_ahead)

        provider_impl = self._get_provider(provider)

        # Ensure we have a valid access token
        if not integration.access_token:
            raise CalendarAuthenticationError(
                "No access token available. Please reconnect.",
                internal_message="Missing access token",
            )

        try:
            # Fetch events from provider
            events = await provider_impl.fetch_events(
                access_token=integration.access_token,
                start_time=start_time,
                end_time=end_time,
                calendar_id=calendar_id,
            )
        except CalendarAuthError as e:
            # Mark integration as error
            await self._repository.update_integration(
                user.uid,
                provider,
                {
                    "status": IntegrationStatus.ERROR.value,
                    "last_sync_error": "Authentication failed",
                },
            )
            raise CalendarAuthenticationError(
                "Calendar access expired. Please reconnect.",
                internal_message=e.internal_message,
            )
        except CalendarRateLimitError as e:
            raise CalendarRateLimitedException(
                "Calendar sync rate limited. Please try again later.",
                retry_after_seconds=e.retry_after_seconds,
                internal_message=e.internal_message,
            )
        except CalendarProviderError as e:
            raise CalendarServiceError(
                "Failed to sync calendar",
                internal_message=e.internal_message,
                status_code=502,
            )

        # Convert events to busy blocks
        blocks = self._events_to_blocks(events, provider, now)
        valid_block_ids = {b.block_id for b in blocks}

        # Upsert blocks
        upserted = await self._repository.upsert_busy_blocks(user.uid, blocks)

        # Delete stale blocks
        deleted = await self._repository.delete_stale_blocks(
            user.uid,
            provider,
            calendar_id,
            valid_block_ids,
            start_time,
            end_time,
        )

        # Update sync metadata
        await self._repository.update_integration(
            user.uid,
            provider,
            {
                "last_sync_at": now,
                "last_sync_error": None,
                "status": IntegrationStatus.CONNECTED.value,
            },
        )

        result = CalendarSyncResult(
            provider=provider,
            success=True,
            blocks_created=upserted,
            blocks_updated=0,  # Upsert doesn't distinguish
            blocks_deleted=deleted,
            sync_window_start=start_time,
            sync_window_end=end_time,
            synced_at=now,
        )

        logger.info(
            "calendar_synced",
            uid=user.uid,
            provider=provider.value,
            events=len(events),
            blocks=upserted,
            deleted=deleted,
        )
        return result

    def _events_to_blocks(
        self,
        events: list[CalendarEvent],
        provider: CalendarProvider,
        synced_at: datetime,
    ) -> list[BusyBlock]:
        """
        Convert calendar events to privacy-preserving busy blocks.
        
        All event metadata (titles, descriptions) is stripped.
        """
        blocks = []
        for event in events:
            # Skip cancelled events
            if event.status == "cancelled":
                continue

            # Map event status to block type
            block_type = BusyBlockType.BUSY
            if event.status == "tentative":
                block_type = BusyBlockType.TENTATIVE

            # Use factory method which handles block_id generation
            block = BusyBlock.from_calendar_event(
                user_id="",  # Will be set by repository
                provider=provider,
                event_id=event.event_id,
                start_time=event.start_time,
                end_time=event.end_time,
                calendar_id=event.calendar_id,
                block_type=block_type,
            )
            blocks.append(block)

        return blocks

    # =========================================================================
    # AVAILABILITY COMPUTATION
    # =========================================================================

    async def get_availability(
        self,
        user: UserContext,
        request: AvailabilityRequest,
    ) -> AvailabilityResponse:
        """
        Compute available time slots for a user.
        
        Algorithm:
        1. Generate potential slots from user's waking hours
        2. Filter to working days only
        3. Subtract busy blocks from calendar
        4. Apply minimum slot duration
        
        Args:
            user: Authenticated user context
            request: Availability request parameters
        
        Returns:
            AvailabilityResponse with list of free slots
        """
        # Get user preferences
        profile = await self._user_repository.get_or_create(user.uid, user.email)
        preferences = profile.preferences

        # Get busy blocks for the time range
        busy_blocks = await self._repository.get_busy_blocks(
            user.uid,
            request.start_date,
            request.end_date,
        )

        # Generate available slots
        slots = self._compute_availability(
            preferences=preferences,
            busy_blocks=busy_blocks,
            start_time=request.start_date,
            end_time=request.end_date,
            min_duration_minutes=request.minimum_duration_minutes,
            include_tentative_as_busy=False,  # Not in model, default to False
            timezone_str=request.timezone,
        )

        total_minutes = sum(slot.duration_minutes for slot in slots)

        return AvailabilityResponse(
            slots=slots,
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=request.timezone or preferences.timezone,
            total_available_minutes=total_minutes,
        )

    def _compute_availability(
        self,
        preferences: UserPreferences,
        busy_blocks: list[BusyBlock],
        start_time: datetime,
        end_time: datetime,
        min_duration_minutes: int = 30,
        include_tentative_as_busy: bool = False,
        timezone_str: Optional[str] = None,
    ) -> list[AvailabilitySlot]:
        """
        Core availability computation algorithm.
        
        Generates free slots by:
        1. Iterating through each day in the range
        2. Creating potential slot from wake to sleep time
        3. Subtracting busy blocks
        4. Filtering slots by minimum duration
        """
        import pytz

        # Use user's timezone or UTC
        tz = pytz.timezone(timezone_str or preferences.timezone)

        # Convert times to user's timezone
        start_local = start_time.astimezone(tz) if start_time.tzinfo else tz.localize(start_time)
        end_local = end_time.astimezone(tz) if end_time.tzinfo else tz.localize(end_time)

        # Get working days as set
        working_days = {d.value for d in preferences.preferred_working_days}

        # Convert busy blocks to (start, end) tuples
        busy_intervals = []
        for block in busy_blocks:
            if include_tentative_as_busy or block.block_type != BusyBlockType.TENTATIVE:
                block_start = block.start_time
                block_end = block.end_time
                if block_start.tzinfo is None:
                    block_start = block_start.replace(tzinfo=timezone.utc)
                if block_end.tzinfo is None:
                    block_end = block_end.replace(tzinfo=timezone.utc)
                busy_intervals.append((block_start, block_end))

        # Sort busy intervals by start time
        busy_intervals.sort(key=lambda x: x[0])

        available_slots = []

        # Iterate through each day
        current_date = start_local.date()
        end_date = end_local.date()

        while current_date <= end_date:
            # Check if this is a working day
            day_name = current_date.strftime("%A").lower()
            if day_name not in working_days:
                current_date += timedelta(days=1)
                continue

            # Get waking hours for this day
            wake_time = tz.localize(
                datetime.combine(
                    current_date,
                    preferences.typical_wake_time.to_time(),
                )
            )
            sleep_time = tz.localize(
                datetime.combine(
                    current_date,
                    preferences.typical_sleep_time.to_time(),
                )
            )

            # Handle sleep time after midnight (rare case)
            if sleep_time <= wake_time:
                sleep_time += timedelta(days=1)

            # Clamp to request range
            day_start = max(wake_time, start_local)
            day_end = min(sleep_time, end_local)

            if day_start >= day_end:
                current_date += timedelta(days=1)
                continue

            # Find free slots by subtracting busy intervals
            free_intervals = self._subtract_intervals(
                (day_start, day_end),
                busy_intervals,
            )

            # Convert to AvailabilitySlot objects
            for free_start, free_end in free_intervals:
                duration = int((free_end - free_start).total_seconds() / 60)
                if duration >= min_duration_minutes:
                    available_slots.append(
                        AvailabilitySlot(
                            start_time=free_start,
                            end_time=free_end,
                            duration_minutes=duration,
                        )
                    )

            current_date += timedelta(days=1)

        return available_slots

    def _subtract_intervals(
        self,
        available: tuple[datetime, datetime],
        busy: list[tuple[datetime, datetime]],
    ) -> list[tuple[datetime, datetime]]:
        """
        Subtract busy intervals from an available interval.
        
        Returns list of remaining free intervals.
        """
        free = [available]

        for busy_start, busy_end in busy:
            new_free = []
            for free_start, free_end in free:
                # No overlap
                if busy_end <= free_start or busy_start >= free_end:
                    new_free.append((free_start, free_end))
                # Busy completely covers free
                elif busy_start <= free_start and busy_end >= free_end:
                    continue
                # Busy starts before free, ends during
                elif busy_start <= free_start < busy_end < free_end:
                    new_free.append((busy_end, free_end))
                # Busy starts during free, ends after
                elif free_start < busy_start < free_end <= busy_end:
                    new_free.append((free_start, busy_start))
                # Busy is in the middle of free
                elif free_start < busy_start and busy_end < free_end:
                    new_free.append((free_start, busy_start))
                    new_free.append((busy_end, free_end))
            free = new_free

        return free

    # =========================================================================
    # INTEGRATION STATUS
    # =========================================================================

    async def get_integration(
        self,
        user: UserContext,
        provider: CalendarProvider,
    ) -> Optional[CalendarIntegration]:
        """Get integration status for a provider."""
        return await self._repository.get_integration(user.uid, provider)

    async def list_integrations(
        self,
        user: UserContext,
    ) -> list[CalendarIntegration]:
        """List all calendar integrations for user."""
        return await self._repository.list_integrations(user.uid)


# Global service instance
_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get the global CalendarService instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service
