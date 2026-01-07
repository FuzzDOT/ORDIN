"""
Calendar Service Tests
======================
Unit tests for A5: Calendar Availability Ingestion Service.

Tests cover:
- OAuth flow (mocked Google API)
- Calendar sync operations
- Busy block storage and retrieval
- Availability computation
- Error handling and edge cases

All tests use mocked external services (Google API, Firestore).
"""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.auth.context import UserContext
from app.integrations.calendar.base import (
    CalendarAuthError,
    CalendarEvent,
    CalendarProviderError,
    CalendarRateLimitError,
)
from app.integrations.calendar.google import GoogleCalendarProvider
from app.models import DayOfWeek, TimeOfDay, UserPreferences
from app.models.calendar import (
    AvailabilityRequest,
    BusyBlock,
    BusyBlockType,
    CalendarIntegration,
    CalendarProvider,
    IntegrationStatus,
)
from app.services.calendar_service import (
    CalendarAuthenticationError,
    CalendarNotConnectedError,
    CalendarRateLimitedException,
    CalendarService,
    CalendarServiceError,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_user() -> UserContext:
    """Create a mock authenticated user."""
    return UserContext(
        uid="test-user-123",
        email="test@example.com",
        email_verified=True,
    )


@pytest.fixture
def mock_settings():
    """Create mock settings with Google OAuth config."""
    settings = MagicMock()
    settings.google_oauth_client_id = "test-client-id.apps.googleusercontent.com"
    settings.google_oauth_client_secret = "test-client-secret"
    settings.google_oauth_redirect_uri = "http://localhost:8000/api/v1/calendar/oauth/google/callback"
    return settings


@pytest.fixture
def mock_calendar_repository():
    """Create a mock calendar repository."""
    repo = MagicMock()
    repo.get_integration = AsyncMock(return_value=None)
    repo.save_integration = AsyncMock()
    repo.update_integration = AsyncMock()
    repo.delete_integration = AsyncMock(return_value=True)
    repo.list_integrations = AsyncMock(return_value=[])
    repo.get_busy_blocks = AsyncMock(return_value=[])
    repo.upsert_busy_blocks = AsyncMock(return_value=0)
    repo.delete_stale_blocks = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_user_repository():
    """Create a mock user repository."""
    repo = MagicMock()
    profile = MagicMock()
    profile.preferences = UserPreferences(
        timezone="America/New_York",
        typical_wake_time=TimeOfDay(hour=8, minute=0),
        typical_sleep_time=TimeOfDay(hour=22, minute=0),
        preferred_working_days=[
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
        ],
    )
    repo.get_or_create = AsyncMock(return_value=profile)
    return repo


@pytest.fixture
def connected_integration() -> CalendarIntegration:
    """Create a mock connected integration."""
    return CalendarIntegration(
        provider=CalendarProvider.GOOGLE,
        status=IntegrationStatus.CONNECTED,
        access_token="valid-access-token",
        refresh_token="valid-refresh-token",
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        connected_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def calendar_service(mock_calendar_repository, mock_user_repository, mock_settings):
    """Create a calendar service with mocked dependencies."""
    with patch("app.services.calendar_service.GoogleCalendarProvider") as mock_provider_class:
        mock_provider = MagicMock()
        mock_provider.provider_name = "google"
        mock_provider.required_scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
        mock_provider.get_auth_url = MagicMock(return_value="https://accounts.google.com/oauth?...")
        mock_provider.exchange_code = AsyncMock(return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
        })
        mock_provider.refresh_access_token = AsyncMock(return_value={
            "access_token": "refreshed-access-token",
            "expires_in": 3600,
        })
        mock_provider.fetch_events = AsyncMock(return_value=[])
        mock_provider.revoke_token = AsyncMock(return_value=True)
        mock_provider_class.return_value = mock_provider

        service = CalendarService(
            repository=mock_calendar_repository,
            user_repository=mock_user_repository,
            settings=mock_settings,
        )
        # Inject the mock provider directly
        service._providers[CalendarProvider.GOOGLE] = mock_provider
        return service


# =============================================================================
# OAUTH FLOW TESTS
# =============================================================================


class TestOAuthFlow:
    """Tests for OAuth initiation and completion."""

    def test_generate_oauth_state(self, calendar_service):
        """OAuth state should be cryptographically random."""
        state1 = calendar_service.generate_oauth_state()
        state2 = calendar_service.generate_oauth_state()
        
        assert len(state1) > 20  # Sufficiently long
        assert state1 != state2  # Each call produces different state

    def test_get_oauth_url(self, calendar_service):
        """OAuth URL should be generated with state parameter."""
        state = "test-state-123"
        url = calendar_service.get_oauth_url(CalendarProvider.GOOGLE, state)
        
        assert url is not None
        assert isinstance(url, str)

    @pytest.mark.asyncio
    async def test_complete_oauth_success(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Successful OAuth should save integration."""
        state = "valid-state"
        code = "authorization-code"
        
        integration = await calendar_service.complete_oauth(
            user=mock_user,
            provider=CalendarProvider.GOOGLE,
            code=code,
            state=state,
            expected_state=state,
        )
        
        assert integration.provider == CalendarProvider.GOOGLE
        assert integration.status == IntegrationStatus.CONNECTED
        assert integration.access_token == "new-access-token"
        mock_calendar_repository.save_integration.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_oauth_state_mismatch(
        self,
        calendar_service,
        mock_user,
    ):
        """OAuth should fail if state doesn't match."""
        with pytest.raises(CalendarAuthenticationError) as exc_info:
            await calendar_service.complete_oauth(
                user=mock_user,
                provider=CalendarProvider.GOOGLE,
                code="any-code",
                state="received-state",
                expected_state="expected-state",
            )
        
        assert "state" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_complete_oauth_code_exchange_failure(
        self,
        calendar_service,
        mock_user,
    ):
        """OAuth should handle code exchange failures."""
        # Make exchange_code raise an error
        provider = calendar_service._providers[CalendarProvider.GOOGLE]
        provider.exchange_code = AsyncMock(
            side_effect=CalendarAuthError("Invalid code", provider="google")
        )
        
        with pytest.raises(CalendarAuthenticationError):
            await calendar_service.complete_oauth(
                user=mock_user,
                provider=CalendarProvider.GOOGLE,
                code="invalid-code",
                state="state",
                expected_state="state",
            )


# =============================================================================
# CALENDAR SYNC TESTS
# =============================================================================


class TestCalendarSync:
    """Tests for calendar sync operations."""

    @pytest.mark.asyncio
    async def test_sync_not_connected(self, calendar_service, mock_user):
        """Sync should fail if calendar not connected."""
        with pytest.raises(CalendarNotConnectedError):
            await calendar_service.sync_calendar(
                user=mock_user,
                provider=CalendarProvider.GOOGLE,
            )

    @pytest.mark.asyncio
    async def test_sync_success(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
        connected_integration,
    ):
        """Successful sync should fetch events and create blocks."""
        mock_calendar_repository.get_integration.return_value = connected_integration
        
        # Mock events
        now = datetime.now(timezone.utc)
        events = [
            CalendarEvent(
                event_id="event-1",
                calendar_id="primary",
                start_time=now + timedelta(hours=2),
                end_time=now + timedelta(hours=3),
                status="confirmed",
            ),
            CalendarEvent(
                event_id="event-2",
                calendar_id="primary",
                start_time=now + timedelta(hours=5),
                end_time=now + timedelta(hours=6),
                status="tentative",
            ),
        ]
        provider = calendar_service._providers[CalendarProvider.GOOGLE]
        provider.fetch_events.return_value = events
        mock_calendar_repository.upsert_busy_blocks.return_value = 2
        
        result = await calendar_service.sync_calendar(
            user=mock_user,
            provider=CalendarProvider.GOOGLE,
        )
        
        assert result.blocks_created == 2
        mock_calendar_repository.upsert_busy_blocks.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_token_expired_refreshes(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Sync should refresh expired tokens automatically."""
        # Create integration with expired token
        expired_integration = CalendarIntegration(
            provider=CalendarProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            access_token="expired-token",
            refresh_token="valid-refresh-token",
            token_expiry=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            connected_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        mock_calendar_repository.get_integration.return_value = expired_integration
        
        # Mock refresh
        provider = calendar_service._providers[CalendarProvider.GOOGLE]
        provider.fetch_events.return_value = []
        
        result = await calendar_service.sync_calendar(
            user=mock_user,
            provider=CalendarProvider.GOOGLE,
        )
        
        # Should have refreshed token
        provider.refresh_access_token.assert_called_once_with("valid-refresh-token")
        assert result.blocks_created == 0

    @pytest.mark.asyncio
    async def test_sync_rate_limited(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
        connected_integration,
    ):
        """Sync should handle rate limiting gracefully."""
        mock_calendar_repository.get_integration.return_value = connected_integration
        
        provider = calendar_service._providers[CalendarProvider.GOOGLE]
        provider.fetch_events = AsyncMock(
            side_effect=CalendarRateLimitError(
                "Rate limited",
                retry_after_seconds=60,
                provider="google",
            )
        )
        
        with pytest.raises(CalendarRateLimitedException) as exc_info:
            await calendar_service.sync_calendar(
                user=mock_user,
                provider=CalendarProvider.GOOGLE,
            )
        
        assert exc_info.value.retry_after_seconds == 60


# =============================================================================
# AVAILABILITY COMPUTATION TESTS
# =============================================================================


class TestAvailabilityComputation:
    """Tests for availability slot computation."""

    @pytest.mark.asyncio
    async def test_availability_no_busy_blocks(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user_repository,
        mock_user,
    ):
        """Availability with no busy blocks should return full waking hours."""
        mock_calendar_repository.get_busy_blocks.return_value = []
        
        # Request availability for a single Monday
        start = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2024, 1, 16, 0, 0, tzinfo=timezone.utc)
        
        request = AvailabilityRequest(
            start_date=start,
            end_date=end,
            minimum_duration_minutes=30,
        )
        
        response = await calendar_service.get_availability(mock_user, request)
        
        # Should have availability during waking hours (8am-10pm = 14 hours)
        assert len(response.slots) > 0
        total_minutes = sum(slot.duration_minutes for slot in response.slots)
        assert total_minutes > 0

    @pytest.mark.asyncio
    async def test_availability_with_busy_blocks(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user_repository,
        mock_user,
    ):
        """Availability should subtract busy blocks from waking hours."""
        # Create a busy block in the middle of the day
        busy_block = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-1",
            start_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),  # 9am ET
            end_time=datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc),    # 11am ET
            calendar_id="primary",
            block_type=BusyBlockType.BUSY,
        )
        mock_calendar_repository.get_busy_blocks.return_value = [busy_block]
        
        start = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2024, 1, 16, 0, 0, tzinfo=timezone.utc)
        
        request = AvailabilityRequest(
            start_date=start,
            end_date=end,
            minimum_duration_minutes=30,
        )
        
        response = await calendar_service.get_availability(mock_user, request)
        
        # Should have gaps around the busy block
        assert len(response.slots) >= 1

    @pytest.mark.asyncio
    async def test_availability_excludes_non_working_days(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Availability should not include weekends (non-working days)."""
        mock_calendar_repository.get_busy_blocks.return_value = []
        
        # Request availability for a Saturday only
        start = datetime(2024, 1, 20, 0, 0, tzinfo=timezone.utc)  # Saturday
        end = datetime(2024, 1, 21, 0, 0, tzinfo=timezone.utc)
        
        request = AvailabilityRequest(
            start_date=start,
            end_date=end,
            minimum_duration_minutes=30,
        )
        
        response = await calendar_service.get_availability(mock_user, request)
        
        # Should have no availability on Saturday (2024-01-20)
        # If any slots are returned, print them for debugging
        slots_on_saturday = [slot for slot in response.slots if slot.start_time.date() == start.date()]
        assert len(slots_on_saturday) == 0, f"Expected no slots on Saturday, got: {response.slots}"

    @pytest.mark.asyncio
    async def test_availability_respects_min_duration(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Small gaps should be filtered by min_duration_minutes."""
        # Create busy blocks leaving only 15-minute gap
        blocks = [
            BusyBlock.from_calendar_event(
                user_id="test-user-123",
                provider=CalendarProvider.GOOGLE,
                event_id="event-1",
                start_time=datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc),
                end_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
                calendar_id="primary",
                block_type=BusyBlockType.BUSY,
            ),
            BusyBlock.from_calendar_event(
                user_id="test-user-123",
                provider=CalendarProvider.GOOGLE,
                event_id="event-2",
                start_time=datetime(2024, 1, 15, 14, 15, tzinfo=timezone.utc),  # 15-min gap
                end_time=datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc),
                calendar_id="primary",
                block_type=BusyBlockType.BUSY,
            ),
        ]
        mock_calendar_repository.get_busy_blocks.return_value = blocks
        
        start = datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc)
        
        request = AvailabilityRequest(
            start_date=start,
            end_date=end,
            minimum_duration_minutes=30,  # Require 30-min minimum
        )
        
        response = await calendar_service.get_availability(mock_user, request)
        
        # 15-minute gap should be excluded
        for slot in response.slots:
            assert slot.duration_minutes >= 30

    @pytest.mark.asyncio
    async def test_availability_tentative_handling(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Tentative events should be configurable as busy or free."""
        tentative_block = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="tentative-event",
            start_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc),
            calendar_id="primary",
            block_type=BusyBlockType.TENTATIVE,
        )
        mock_calendar_repository.get_busy_blocks.return_value = [tentative_block]
        
        start = datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc)
        
        # Request with default settings (tentative as free)
        request = AvailabilityRequest(
            start_date=start,
            end_date=end,
        )
        
        response = await calendar_service.get_availability(mock_user, request)
        
        # Should have some availability
        total = sum(s.duration_minutes for s in response.slots)
        assert total > 0


# =============================================================================
# BUSY BLOCK MODEL TESTS
# =============================================================================


class TestBusyBlockModel:
    """Tests for BusyBlock model functionality."""

    def test_block_id_generation_deterministic(self):
        """Block ID should be deterministic for same inputs."""
        block1 = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-123",
            start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            calendar_id="primary",
        )
        block2 = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-123",
            start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            calendar_id="primary",
        )
        
        assert block1.block_id == block2.block_id

    def test_block_id_different_for_different_events(self):
        """Block ID should be different for different event IDs."""
        block1 = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-123",
            start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            calendar_id="primary",
        )
        block2 = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-456",  # Different event
            start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            calendar_id="primary",
        )
        
        assert block1.block_id != block2.block_id

    def test_duration_calculation(self):
        """Duration should be calculable from start and end times."""
        block = BusyBlock.from_calendar_event(
            user_id="test-user-123",
            provider=CalendarProvider.GOOGLE,
            event_id="event-123",
            start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 15, 11, 30, tzinfo=timezone.utc),
            calendar_id="primary",
        )
        
        # Calculate duration manually
        duration = (block.end_time - block.start_time).total_seconds() / 60
        assert duration == 90


# =============================================================================
# GOOGLE PROVIDER TESTS
# =============================================================================


class TestGoogleCalendarProvider:
    """Tests for Google Calendar provider implementation."""

    def test_auth_url_generation(self):
        """Auth URL should include required parameters."""
        provider = GoogleCalendarProvider(
            client_id="test-client-id",
            client_secret="test-secret",
        )
        
        url = provider.get_auth_url(
            state="test-state",
            redirect_uri="http://localhost/callback",
        )
        
        assert "test-client-id" in url
        assert "test-state" in url
        assert "calendar.readonly" in url
        assert "access_type=offline" in url

    def test_required_scopes(self):
        """Required scopes should be read-only."""
        provider = GoogleCalendarProvider(
            client_id="test-client-id",
            client_secret="test-secret",
        )
        
        scopes = provider.required_scopes
        assert len(scopes) == 1
        assert "readonly" in scopes[0]


# =============================================================================
# DISCONNECT TESTS
# =============================================================================


class TestDisconnect:
    """Tests for calendar disconnection."""

    @pytest.mark.asyncio
    async def test_disconnect_success(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
        connected_integration,
    ):
        """Disconnect should revoke tokens and delete data."""
        mock_calendar_repository.get_integration.return_value = connected_integration
        
        result = await calendar_service.disconnect(
            user=mock_user,
            provider=CalendarProvider.GOOGLE,
        )
        
        assert result is True
        mock_calendar_repository.delete_integration.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(
        self,
        calendar_service,
        mock_calendar_repository,
        mock_user,
    ):
        """Disconnect when not connected should succeed."""
        mock_calendar_repository.get_integration.return_value = None
        
        result = await calendar_service.disconnect(
            user=mock_user,
            provider=CalendarProvider.GOOGLE,
        )
        
        assert result is True  # Already disconnected
