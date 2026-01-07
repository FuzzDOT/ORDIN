"""
Google Calendar Provider
========================
Google Calendar API integration using OAuth 2.0.

SCOPES:
- https://www.googleapis.com/auth/calendar.readonly
  (Read-only access to calendar events)

PRIVACY:
Events are fetched but only minimal data is extracted.
Titles and descriptions are never stored.

RATE LIMITS:
Google Calendar API has quota limits per project.
This implementation handles 403/429 responses with CalendarRateLimitError.
"""

import asyncio
import secrets
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import structlog

from app.integrations.calendar.base import (
    CalendarEvent,
    CalendarAuthError,
    CalendarProviderError,
    CalendarProviderInterface,
    CalendarRateLimitError,
)

logger = structlog.get_logger(__name__)

# Google OAuth and API endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

# Read-only scope for calendar access
GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class GoogleCalendarProvider(CalendarProviderInterface):
    """
    Google Calendar provider implementation.
    
    Uses Google OAuth 2.0 for authentication and the Google Calendar API
    for fetching events.
    
    USAGE:
        provider = GoogleCalendarProvider(
            client_id="your-client-id.apps.googleusercontent.com",
            client_secret="your-client-secret",
        )
        
        # Generate auth URL for user
        auth_url = provider.get_auth_url(
            state=secrets.token_urlsafe(32),
            redirect_uri="https://app.example.com/api/v1/calendar/oauth/callback",
        )
        
        # Exchange code from callback
        tokens = await provider.exchange_code(code, redirect_uri)
        
        # Fetch events
        events = await provider.fetch_events(
            tokens["access_token"],
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(days=14),
        )
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_timeout: float = 30.0,
    ) -> None:
        """
        Initialize Google Calendar provider.
        
        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            http_timeout: HTTP request timeout in seconds
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_timeout = http_timeout
        self._log = logger.bind(provider="google")

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def required_scopes(self) -> list[str]:
        return [GOOGLE_CALENDAR_READONLY_SCOPE]

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """
        Generate Google OAuth authorization URL.
        
        Uses authorization code flow with offline access for refresh tokens.
        prompt=consent ensures refresh token is always returned.
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Must match the redirect_uri used in get_auth_url
        
        Returns:
            Token response containing access_token, refresh_token, expires_in
        """
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    GOOGLE_TOKEN_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code == 200:
                tokens = response.json()
                self._log.info(
                    "code_exchange_success",
                    has_refresh_token="refresh_token" in tokens,
                )
                return {
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens.get("refresh_token"),
                    "expires_in": tokens.get("expires_in", 3600),
                    "scope": tokens.get("scope", ""),
                    "token_type": tokens.get("token_type", "Bearer"),
                }
            else:
                error_data = response.json()
                self._log.warning(
                    "code_exchange_failed",
                    status_code=response.status_code,
                    error=error_data.get("error"),
                )
                raise CalendarAuthError(
                    message="Failed to exchange authorization code",
                    internal_message=f"Google OAuth error: {error_data}",
                    provider="google",
                )

        except httpx.HTTPError as e:
            self._log.error("code_exchange_http_error", error=str(e))
            raise CalendarProviderError(
                message="Failed to connect to Google OAuth",
                internal_message=str(e),
                provider="google",
            )

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token using the refresh token.
        
        Google refresh tokens don't expire unless revoked by user.
        """
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    GOOGLE_TOKEN_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code == 200:
                tokens = response.json()
                self._log.debug("token_refresh_success")
                return {
                    "access_token": tokens["access_token"],
                    "expires_in": tokens.get("expires_in", 3600),
                    "scope": tokens.get("scope", ""),
                    "token_type": tokens.get("token_type", "Bearer"),
                }
            else:
                error_data = response.json()
                self._log.warning(
                    "token_refresh_failed",
                    status_code=response.status_code,
                    error=error_data.get("error"),
                )
                raise CalendarAuthError(
                    message="Failed to refresh access token. Please reconnect your calendar.",
                    internal_message=f"Google OAuth refresh error: {error_data}",
                    provider="google",
                )

        except httpx.HTTPError as e:
            self._log.error("token_refresh_http_error", error=str(e))
            raise CalendarProviderError(
                message="Failed to connect to Google OAuth",
                internal_message=str(e),
                provider="google",
            )

    async def fetch_events(
        self,
        access_token: str,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        """
        Fetch events from Google Calendar within the time range.
        
        Handles pagination automatically to fetch all events.
        
        Args:
            access_token: Valid Google OAuth access token
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            calendar_id: Calendar ID (default: "primary" for user's main calendar)
        
        Returns:
            List of CalendarEvent objects (privacy-preserving)
        """
        events: list[CalendarEvent] = []
        page_token: Optional[str] = None
        
        # Convert to RFC3339 format for Google API
        time_min = start_time.isoformat() + "Z" if start_time.tzinfo is None else start_time.isoformat()
        time_max = end_time.isoformat() + "Z" if end_time.tzinfo is None else end_time.isoformat()

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                while True:
                    params: dict[str, Any] = {
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "singleEvents": "true",  # Expand recurring events
                        "orderBy": "startTime",
                        "maxResults": 250,  # Max allowed by API
                    }
                    if page_token:
                        params["pageToken"] = page_token

                    url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/{calendar_id}/events"
                    response = await client.get(
                        url,
                        params=params,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )

                    if response.status_code == 401:
                        raise CalendarAuthError(
                            message="Calendar access token expired",
                            internal_message="Google API returned 401 Unauthorized",
                            provider="google",
                        )

                    if response.status_code == 403:
                        error_data = response.json()
                        if "rateLimitExceeded" in str(error_data) or "userRateLimitExceeded" in str(error_data):
                            raise CalendarRateLimitError(
                                message="Calendar API rate limit exceeded",
                                retry_after_seconds=60,
                                provider="google",
                            )
                        raise CalendarProviderError(
                            message="Calendar access denied",
                            internal_message=f"Google API 403: {error_data}",
                            provider="google",
                        )

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "60")
                        raise CalendarRateLimitError(
                            message="Calendar API rate limit exceeded",
                            retry_after_seconds=int(retry_after),
                            provider="google",
                        )

                    if response.status_code != 200:
                        raise CalendarProviderError(
                            message="Failed to fetch calendar events",
                            internal_message=f"Google API {response.status_code}: {response.text}",
                            provider="google",
                        )

                    data = response.json()
                    for item in data.get("items", []):
                        event = self._parse_event(item, calendar_id)
                        if event:
                            events.append(event)

                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

            self._log.info(
                "events_fetched",
                count=len(events),
                calendar_id=calendar_id,
                start=start_time.isoformat(),
                end=end_time.isoformat(),
            )
            return events

        except httpx.HTTPError as e:
            self._log.error("fetch_events_http_error", error=str(e))
            raise CalendarProviderError(
                message="Failed to connect to Google Calendar",
                internal_message=str(e),
                provider="google",
            )

    def _parse_event(self, item: dict, calendar_id: str) -> Optional[CalendarEvent]:
        """
        Parse a Google Calendar API event into CalendarEvent.
        
        PRIVACY: Intentionally ignores summary, description, attendees, etc.
        Only extracts timing and status information.
        """
        event_id = item.get("id")
        if not event_id:
            return None
            
        status = item.get("status", "confirmed")
        
        # Skip cancelled events
        if status == "cancelled":
            return None

        start = item.get("start", {})
        end = item.get("end", {})

        # Handle all-day events (date) vs timed events (dateTime)
        is_all_day = "date" in start
        
        try:
            if is_all_day:
                # All-day events use date format: YYYY-MM-DD
                start_str = start.get("date")
                end_str = end.get("date")
                start_time = datetime.fromisoformat(start_str)
                end_time = datetime.fromisoformat(end_str)
            else:
                # Timed events use dateTime format with timezone
                start_str = start.get("dateTime")
                end_str = end.get("dateTime")
                # Handle timezone offset in ISO format
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except (TypeError, ValueError) as e:
            self._log.warning(
                "event_parse_error",
                event_id=event_id,
                error=str(e),
            )
            return None

        # Map Google status to our status
        status_map = {
            "confirmed": "confirmed",
            "tentative": "tentative",
            "cancelled": "cancelled",
        }
        normalized_status = status_map.get(status, "confirmed")

        return CalendarEvent(
            event_id=event_id,
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
            is_all_day=is_all_day,
            status=normalized_status,
        )

    async def list_calendars(self, access_token: str) -> list[dict]:
        """
        List all calendars accessible by the user.
        
        Returns calendars the user owns or has access to.
        """
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                url = f"{GOOGLE_CALENDAR_API_BASE}/users/me/calendarList"
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.status_code == 401:
                    raise CalendarAuthError(
                        message="Calendar access token expired",
                        internal_message="Google API returned 401 Unauthorized",
                        provider="google",
                    )

                if response.status_code != 200:
                    raise CalendarProviderError(
                        message="Failed to list calendars",
                        internal_message=f"Google API {response.status_code}: {response.text}",
                        provider="google",
                    )

                data = response.json()
                calendars = []
                for item in data.get("items", []):
                    calendars.append({
                        "id": item.get("id"),
                        "summary": item.get("summary", ""),
                        "primary": item.get("primary", False),
                        "access_role": item.get("accessRole", "reader"),
                        "background_color": item.get("backgroundColor"),
                    })

                self._log.info("calendars_listed", count=len(calendars))
                return calendars

        except httpx.HTTPError as e:
            self._log.error("list_calendars_http_error", error=str(e))
            raise CalendarProviderError(
                message="Failed to connect to Google Calendar",
                internal_message=str(e),
                provider="google",
            )

    async def revoke_token(self, token: str) -> bool:
        """
        Revoke an OAuth token with Google.
        
        This should be called when user disconnects the integration.
        Can revoke either access or refresh token.
        """
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(
                    GOOGLE_REVOKE_URL,
                    data={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                # Google returns 200 on successful revocation
                if response.status_code == 200:
                    self._log.info("token_revoked")
                    return True
                else:
                    # Token may already be revoked or invalid
                    self._log.warning(
                        "token_revoke_failed",
                        status_code=response.status_code,
                    )
                    return False

        except httpx.HTTPError as e:
            self._log.error("revoke_token_http_error", error=str(e))
            return False


def create_oauth_state() -> str:
    """
    Generate a cryptographically secure state parameter for OAuth.
    
    The state should be stored server-side and validated on callback
    to prevent CSRF attacks.
    """
    return secrets.token_urlsafe(32)
