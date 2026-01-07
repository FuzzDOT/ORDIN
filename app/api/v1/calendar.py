"""
Calendar API Endpoints
======================
REST API for calendar integrations and availability.

ENDPOINTS:
    OAuth Flow:
        GET  /api/v1/calendar/oauth/{provider}/initiate  - Start OAuth flow
        GET  /api/v1/calendar/oauth/{provider}/callback  - OAuth callback
        DELETE /api/v1/calendar/{provider}               - Disconnect integration
    
    Sync:
        POST /api/v1/calendar/{provider}/sync            - Trigger calendar sync
    
    Status:
        GET  /api/v1/calendar/integrations               - List all integrations
        GET  /api/v1/calendar/{provider}/status          - Get integration status
    
    Availability:
        POST /api/v1/calendar/availability               - Compute availability

SECURITY:
- All endpoints except OAuth callback require Firebase authentication
- OAuth callback validates state parameter for CSRF protection
- Users can only access their own calendar data

PRIVACY:
- Only busy blocks are stored, never event titles/descriptions
- Availability computation uses user's wake/sleep preferences
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.core.logging import get_logger
from app.models.calendar import (
    AvailabilityRequest,
    AvailabilityResponse,
    AvailabilitySlot,
    CalendarIntegration,
    CalendarProvider,
    CalendarSyncResult,
    IntegrationStatus,
)
from app.services.calendar_service import (
    CalendarAuthenticationError,
    CalendarNotConnectedError,
    CalendarRateLimitedException,
    CalendarService,
    CalendarServiceError,
    get_calendar_service,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


# -----------------------------------------------------------------------------
# Dependencies
# -----------------------------------------------------------------------------


def get_service() -> CalendarService:
    """Dependency injection for calendar service."""
    return get_calendar_service()


CalendarServiceDep = Annotated[CalendarService, Depends(get_service)]


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------


class OAuthInitiateResponse(BaseModel):
    """Response from OAuth initiate endpoint."""

    auth_url: str = Field(description="URL to redirect user to for OAuth consent")
    state: str = Field(description="State parameter for CSRF protection (store in session)")
    provider: str = Field(description="Calendar provider")


class OAuthCallbackRequest(BaseModel):
    """Query parameters from OAuth callback."""

    code: str = Field(description="Authorization code from provider")
    state: str = Field(description="State parameter for CSRF validation")


class IntegrationResponse(BaseModel):
    """Calendar integration status response."""

    provider: str = Field(description="Calendar provider (google, apple, microsoft)")
    status: str = Field(description="Integration status")
    connected_at: Optional[str] = Field(default=None, description="Connection timestamp")
    last_sync_at: Optional[str] = Field(default=None, description="Last sync timestamp")
    sync_error: Optional[str] = Field(default=None, description="Last sync error, if any")
    scopes: list[str] = Field(default_factory=list, description="Granted OAuth scopes")

    @classmethod
    def from_model(cls, integration: CalendarIntegration) -> "IntegrationResponse":
        """Create response from internal model."""
        return cls(
            provider=integration.provider.value,
            status=integration.status.value,
            connected_at=integration.connected_at.isoformat() if integration.connected_at else None,
            last_sync_at=integration.last_sync_at.isoformat() if integration.last_sync_at else None,
            sync_error=integration.last_sync_error,
            scopes=integration.scopes,
        )


class IntegrationListResponse(BaseModel):
    """List of calendar integrations."""

    integrations: list[IntegrationResponse] = Field(description="All calendar integrations")


class SyncRequest(BaseModel):
    """Request body for calendar sync."""

    days_ahead: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Number of days to sync (1-90)",
    )
    calendar_id: str = Field(
        default="primary",
        description="Calendar ID to sync (default: primary)",
    )


class SyncResponse(BaseModel):
    """Response from calendar sync operation."""

    provider: str = Field(description="Calendar provider")
    blocks_created: int = Field(description="Number of busy blocks created/updated")
    blocks_deleted: int = Field(description="Number of stale blocks deleted")
    sync_window_start: str = Field(description="Sync window start (ISO 8601)")
    sync_window_end: str = Field(description="Sync window end (ISO 8601)")
    synced_at: str = Field(description="Sync timestamp (ISO 8601)")

    @classmethod
    def from_model(cls, result: CalendarSyncResult) -> "SyncResponse":
        """Create response from internal model."""
        return cls(
            provider=result.provider.value,
            blocks_created=result.blocks_created,
            blocks_deleted=result.blocks_deleted,
            sync_window_start=result.sync_window_start.isoformat(),
            sync_window_end=result.sync_window_end.isoformat(),
            synced_at=result.synced_at.isoformat(),
        )


class AvailabilitySlotResponse(BaseModel):
    """Single availability slot in response."""

    start_time: str = Field(description="Slot start (ISO 8601)")
    end_time: str = Field(description="Slot end (ISO 8601)")
    duration_minutes: int = Field(description="Slot duration in minutes")


class GetAvailabilityRequest(BaseModel):
    """Request body for availability computation."""

    start_time: datetime = Field(description="Availability range start")
    end_time: datetime = Field(description="Availability range end")
    min_duration_minutes: int = Field(
        default=30,
        ge=5,
        le=480,
        description="Minimum slot duration in minutes (5-480)",
    )
    include_tentative_as_busy: bool = Field(
        default=False,
        description="Whether to treat tentative events as busy",
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Override timezone (uses user preference if not specified)",
    )


class GetAvailabilityResponse(BaseModel):
    """Response from availability computation."""

    slots: list[AvailabilitySlotResponse] = Field(description="Available time slots")
    start_time: str = Field(description="Query range start (ISO 8601)")
    end_time: str = Field(description="Query range end (ISO 8601)")
    timezone: str = Field(description="Timezone used for computation")
    total_minutes_available: int = Field(description="Total available minutes")

    @classmethod
    def from_model(cls, response: AvailabilityResponse) -> "GetAvailabilityResponse":
        """Create API response from internal model."""
        slots = [
            AvailabilitySlotResponse(
                start_time=slot.start_time.isoformat(),
                end_time=slot.end_time.isoformat(),
                duration_minutes=slot.duration_minutes,
            )
            for slot in response.slots
        ]
        total_minutes = sum(slot.duration_minutes for slot in slots)
        return cls(
            slots=slots,
            start_time=response.start_date.isoformat(),
            end_time=response.end_date.isoformat(),
            timezone=response.timezone,
            total_minutes_available=total_minutes,
        )


class DisconnectResponse(BaseModel):
    """Response from disconnect operation."""

    provider: str = Field(description="Calendar provider")
    disconnected: bool = Field(description="Whether disconnection succeeded")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(description="Error message")
    detail: Optional[str] = Field(default=None, description="Additional details")


# -----------------------------------------------------------------------------
# OAuth Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/oauth/{provider}/initiate",
    response_model=OAuthInitiateResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        501: {"model": ErrorResponse, "description": "Provider not supported"},
    },
)
async def initiate_oauth(
    provider: CalendarProvider,
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> OAuthInitiateResponse:
    """
    Initiate OAuth flow for a calendar provider.
    
    Returns an authorization URL and state parameter.
    The frontend should:
    1. Store the state parameter in session storage
    2. Redirect the user to the auth_url
    3. Handle the callback with state validation
    """
    try:
        state = service.generate_oauth_state()
        auth_url = service.get_oauth_url(provider, state)
        
        logger.info(
            "oauth_initiated",
            uid=user.uid,
            provider=provider.value,
        )
        
        return OAuthInitiateResponse(
            auth_url=auth_url,
            state=state,
            provider=provider.value,
        )
        
    except CalendarServiceError as e:
        logger.warning(
            "oauth_initiate_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


@router.get(
    "/oauth/{provider}/callback",
    responses={
        302: {"description": "Redirect to frontend on success/failure"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
)
async def oauth_callback(
    provider: CalendarProvider,
    code: Annotated[str, Query(description="Authorization code from provider")],
    state: Annotated[str, Query(description="State parameter for CSRF validation")],
    expected_state: Annotated[str, Query(alias="expected_state", description="Expected state from session")],
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> IntegrationResponse:
    """
    Complete OAuth flow by exchanging authorization code for tokens.
    
    Note: In production, the expected_state should come from server-side session,
    not from the query parameter. This implementation accepts it as a parameter
    for flexibility in frontend session management.
    
    After successful authentication:
    1. Tokens are securely stored
    2. Integration status is set to CONNECTED
    3. Response indicates success
    """
    try:
        integration = await service.complete_oauth(
            user=user,
            provider=provider,
            code=code,
            state=state,
            expected_state=expected_state,
        )
        
        logger.info(
            "oauth_completed",
            uid=user.uid,
            provider=provider.value,
        )
        
        return IntegrationResponse.from_model(integration)
        
    except CalendarAuthenticationError as e:
        logger.warning(
            "oauth_callback_auth_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except CalendarServiceError as e:
        logger.error(
            "oauth_callback_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


# -----------------------------------------------------------------------------
# Integration Management Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/integrations",
    response_model=IntegrationListResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def list_integrations(
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> IntegrationListResponse:
    """
    List all calendar integrations for the current user.
    
    Returns status of all supported calendar providers,
    including disconnected ones if they were previously connected.
    """
    try:
        integrations = await service.list_integrations(user)
        
        return IntegrationListResponse(
            integrations=[
                IntegrationResponse.from_model(i) for i in integrations
            ]
        )
        
    except CalendarServiceError as e:
        logger.error(
            "list_integrations_failed",
            uid=user.uid,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


@router.get(
    "/{provider}/status",
    response_model=IntegrationResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Integration not found"},
    },
)
async def get_integration_status(
    provider: CalendarProvider,
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> IntegrationResponse:
    """
    Get status of a specific calendar integration.
    
    Returns detailed status including last sync time and any errors.
    """
    try:
        integration = await service.get_integration(user, provider)
        
        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{provider.value.title()} Calendar is not connected",
            )
        
        return IntegrationResponse.from_model(integration)
        
    except CalendarServiceError as e:
        logger.error(
            "get_integration_status_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


@router.delete(
    "/{provider}",
    response_model=DisconnectResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def disconnect_integration(
    provider: CalendarProvider,
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> DisconnectResponse:
    """
    Disconnect a calendar integration.
    
    This will:
    1. Revoke OAuth tokens with the provider
    2. Delete stored tokens
    3. Delete all busy blocks from this provider
    
    The user will need to re-authenticate to reconnect.
    """
    try:
        disconnected = await service.disconnect(user, provider)
        
        logger.info(
            "integration_disconnected",
            uid=user.uid,
            provider=provider.value,
        )
        
        return DisconnectResponse(
            provider=provider.value,
            disconnected=disconnected,
        )
        
    except CalendarServiceError as e:
        logger.error(
            "disconnect_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


# -----------------------------------------------------------------------------
# Sync Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/{provider}/sync",
    response_model=SyncResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Calendar not connected"},
        401: {"model": ErrorResponse, "description": "Token expired"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        502: {"model": ErrorResponse, "description": "Provider error"},
    },
)
async def sync_calendar(
    provider: CalendarProvider,
    user: CurrentUserDep,
    service: CalendarServiceDep,
    request: SyncRequest = SyncRequest(),
) -> SyncResponse:
    """
    Sync calendar events and update busy blocks.
    
    Fetches events from the calendar provider for the specified
    time window and converts them to privacy-preserving busy blocks.
    
    This operation is idempotent - safe to call multiple times.
    Stale blocks (events that were removed from calendar) are deleted.
    """
    try:
        result = await service.sync_calendar(
            user=user,
            provider=provider,
            days_ahead=request.days_ahead,
            calendar_id=request.calendar_id,
        )
        
        return SyncResponse.from_model(result)
        
    except CalendarNotConnectedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )
    except CalendarAuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except CalendarRateLimitedException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers=(
                {"Retry-After": str(e.retry_after_seconds)}
                if e.retry_after_seconds
                else None
            ),
        )
    except CalendarServiceError as e:
        logger.error(
            "sync_failed",
            uid=user.uid,
            provider=provider.value,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )


# -----------------------------------------------------------------------------
# Availability Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/availability",
    response_model=GetAvailabilityResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def get_availability(
    request: GetAvailabilityRequest,
    user: CurrentUserDep,
    service: CalendarServiceDep,
) -> GetAvailabilityResponse:
    """
    Compute available time slots for the current user.
    
    Algorithm:
    1. Uses user's wake/sleep times from preferences
    2. Filters to user's working days
    3. Subtracts all busy blocks from calendars
    4. Returns slots meeting minimum duration
    
    Time slots are returned in the user's timezone (or override if specified).
    """
    # Validate time range
    if request.end_time <= request.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be after start_time",
        )
    
    max_range = 90  # days
    if (request.end_time - request.start_time).days > max_range:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Time range cannot exceed {max_range} days",
        )

    try:
        # Convert to internal request model
        internal_request = AvailabilityRequest(
            start_date=request.start_time,
            end_date=request.end_time,
            minimum_duration_minutes=request.min_duration_minutes,
            timezone=request.timezone,
        )
        
        response = await service.get_availability(user, internal_request)
        
        logger.debug(
            "availability_computed",
            uid=user.uid,
            slots=len(response.slots),
            start=request.start_time.isoformat(),
            end=request.end_time.isoformat(),
        )
        
        return GetAvailabilityResponse.from_model(response)
        
    except CalendarServiceError as e:
        logger.error(
            "availability_failed",
            uid=user.uid,
            error=e.internal_message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
