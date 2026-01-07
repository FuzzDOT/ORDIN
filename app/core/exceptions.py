"""
Typed Exception Hierarchy
=========================
Centralized exception definitions for consistent error handling.

Design principles:
- All application exceptions inherit from AppException
- Each exception type has a unique error_code for client handling
- HTTP status codes are defined at the exception level
- Exceptions carry structured context for debugging
"""

from typing import Any, Optional


class AppException(Exception):
    """
    Base exception for all application-specific errors.
    
    All custom exceptions should inherit from this class to ensure
    consistent error handling and response formatting.
    
    Attributes:
        message: Human-readable error description
        error_code: Machine-readable error identifier (e.g., "VALIDATION_ERROR")
        status_code: HTTP status code for this error type
        details: Additional structured context for debugging
    """

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(AppException):
    """
    Raised when application configuration is invalid or missing.
    
    This exception typically causes the application to fail at startup,
    following the fail-fast principle for misconfiguration.
    """

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )


class ValidationError(AppException):
    """
    Raised when request validation fails.
    
    Use for business logic validation beyond Pydantic schema validation.
    Pydantic validation errors are handled separately by FastAPI.
    """

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class NotFoundError(AppException):
    """
    Raised when a requested resource does not exist.
    """

    def __init__(
        self,
        resource: str,
        identifier: Any,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            error_code="NOT_FOUND",
            status_code=404,
            details=details or {"resource": resource, "identifier": str(identifier)},
        )


class ConflictError(AppException):
    """
    Raised when an operation conflicts with existing state.
    
    Common uses: duplicate creation, concurrent modification conflicts.
    """

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=409,
            details=details,
        )


class ServiceUnavailableError(AppException):
    """
    Raised when an external dependency is unavailable.
    
    Use for database connection failures, third-party API outages, etc.
    This signals to load balancers that the instance may need to be
    removed from rotation.
    """

    def __init__(
        self,
        service: str,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message or f"Service '{service}' is currently unavailable",
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details or {"service": service},
        )


class RateLimitError(AppException):
    """
    Raised when rate limits are exceeded.
    
    The retry_after field indicates when the client can retry.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: int = 60,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details or {"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class AuthorizationError(AppException):
    """
    Raised when a user lacks permission for an operation.
    
    Note: Authentication is handled by Firebase externally.
    This exception is for authorization (permission) failures.
    """

    def __init__(
        self,
        message: str = "Insufficient permissions for this operation",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="FORBIDDEN",
            status_code=403,
            details=details,
        )
