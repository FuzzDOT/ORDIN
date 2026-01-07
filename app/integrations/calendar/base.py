"""
Calendar Provider Interface
===========================
Abstract base interface for calendar providers.

All calendar integrations (Google, Apple, Microsoft) implement this
interface to enable provider-agnostic calendar sync.

DESIGN PRINCIPLES:
- Provider-specific logic is isolated in implementations
- Service layer works with abstract interface only
- OAuth flow is provider-specific but follows same pattern
- All providers return same CalendarEvent structure
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class CalendarEvent:
    """
    Minimal event representation from calendar providers.
    
    PRIVACY: Only contains data needed for busy block creation.
    Title and description are intentionally excluded.
    
    This is an intermediate representation - events are converted
    to BusyBlocks before storage (further stripping metadata).
    """

    event_id: str
    calendar_id: str
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    status: str = "confirmed"  # confirmed, tentative, cancelled
    
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)


class CalendarProviderError(Exception):
    """Base exception for calendar provider operations."""

    def __init__(
        self,
        message: str,
        internal_message: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.internal_message = internal_message or message
        self.provider = provider


class CalendarAuthError(CalendarProviderError):
    """
    Raised when OAuth authentication fails or tokens are invalid.
    
    This indicates the user needs to re-authenticate.
    """

    pass


class CalendarRateLimitError(CalendarProviderError):
    """
    Raised when the provider's rate limit is exceeded.
    
    The caller should implement exponential backoff.
    """

    def __init__(
        self,
        message: str,
        retry_after_seconds: Optional[int] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class CalendarProviderInterface(ABC):
    """
    Abstract interface for calendar providers.
    
    Implementations must provide:
    - OAuth URL generation
    - Token exchange from auth code
    - Token refresh
    - Event fetching for a time range
    
    USAGE:
        provider = GoogleCalendarProvider(settings)
        auth_url = provider.get_auth_url(state="...")
        tokens = await provider.exchange_code(code="...")
        events = await provider.fetch_events(access_token, start, end)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g., 'google', 'apple')."""
        pass

    @property
    @abstractmethod
    def required_scopes(self) -> list[str]:
        """Return minimum required OAuth scopes for read-only access."""
        pass

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """
        Generate OAuth authorization URL.
        
        Args:
            state: Random state parameter for CSRF protection
            redirect_uri: Callback URL for OAuth redirect
        
        Returns:
            Full authorization URL to redirect user to
        """
        pass

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect_uri used in auth URL
        
        Returns:
            Dictionary containing:
            - access_token: Short-lived access token
            - refresh_token: Long-lived refresh token
            - expires_in: Seconds until access token expires
            - scope: Granted scopes (space-separated)
        
        Raises:
            CalendarAuthError: If code exchange fails
        """
        pass

    @abstractmethod
    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> dict:
        """
        Refresh an expired access token.
        
        Args:
            refresh_token: The refresh token from initial auth
        
        Returns:
            Dictionary containing:
            - access_token: New short-lived access token
            - expires_in: Seconds until access token expires
        
        Raises:
            CalendarAuthError: If refresh fails (token revoked, etc.)
        """
        pass

    @abstractmethod
    async def fetch_events(
        self,
        access_token: str,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        """
        Fetch events from calendar within time range.
        
        Args:
            access_token: Valid OAuth access token
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            calendar_id: Calendar to fetch from (default: primary)
        
        Returns:
            List of CalendarEvent objects
        
        Raises:
            CalendarAuthError: If token is invalid/expired
            CalendarRateLimitError: If rate limited
            CalendarProviderError: For other errors
        """
        pass

    @abstractmethod
    async def list_calendars(
        self,
        access_token: str,
    ) -> list[dict]:
        """
        List available calendars for the user.
        
        Args:
            access_token: Valid OAuth access token
        
        Returns:
            List of calendar metadata dicts with at minimum:
            - id: Calendar ID
            - summary: Calendar name
            - primary: Whether this is the primary calendar
        
        Raises:
            CalendarAuthError: If token is invalid/expired
            CalendarProviderError: For other errors
        """
        pass

    @abstractmethod
    async def revoke_token(self, token: str) -> bool:
        """
        Revoke an OAuth token.
        
        Args:
            token: Access token or refresh token to revoke
        
        Returns:
            True if revocation succeeded
        """
        pass
