"""
Calendar Integrations Package
=============================
Calendar provider integrations for syncing busy blocks.

Supports:
- Google Calendar (implemented)
- Apple Calendar (future)
- Microsoft Outlook (future)

ARCHITECTURE:
All providers implement the CalendarProviderInterface, enabling
provider-agnostic calendar sync in the service layer.
"""

from app.integrations.calendar.base import (
    CalendarProviderInterface,
    CalendarProviderError,
    CalendarAuthError,
    CalendarRateLimitError,
    CalendarEvent,
)
from app.integrations.calendar.google import GoogleCalendarProvider

__all__ = [
    "CalendarProviderInterface",
    "CalendarProviderError",
    "CalendarAuthError", 
    "CalendarRateLimitError",
    "CalendarEvent",
    "GoogleCalendarProvider",
]
