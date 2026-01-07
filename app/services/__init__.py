"""
Services
========
Business service layer for the application.

Services orchestrate between API handlers and repositories,
providing a clean abstraction layer. For A3 (User Profile) and
A4 (Tasks), no business logic is implemented - services are
pure data access wrappers.

A5 (Calendar) introduces availability computation logic.
"""

from app.services.user_service import UserService
from app.services.task_service import (
    TaskNotFoundServiceError,
    TaskService,
    TaskServiceError,
)
from app.services.calendar_service import (
    CalendarAuthenticationError,
    CalendarNotConnectedError,
    CalendarRateLimitedException,
    CalendarService,
    CalendarServiceError,
    get_calendar_service,
)

__all__ = [
    "UserService",
    "TaskNotFoundServiceError",
    "TaskService",
    "TaskServiceError",
    "CalendarAuthenticationError",
    "CalendarNotConnectedError",
    "CalendarRateLimitedException",
    "CalendarService",
    "CalendarServiceError",
    "get_calendar_service",
]
