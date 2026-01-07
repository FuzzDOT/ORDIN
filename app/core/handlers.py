"""
Global Exception Handlers
=========================
Centralized exception handling for consistent API error responses.

These handlers intercept exceptions and convert them to structured
JSON responses. All errors include the request_id for correlation.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI application.
    
    This function should be called during application startup.
    Handler order matters: more specific handlers should be registered first.
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        """
        Handle application-specific exceptions.
        
        These are expected errors with well-defined error codes and messages.
        """
        request_id = get_request_id()

        # Log at appropriate level based on status code
        log_data = {
            "request_id": request_id,
            "error_code": exc.error_code,
            "path": request.url.path,
            "details": exc.details,
        }

        if exc.status_code >= 500:
            logger.error(exc.message, **log_data, exc_info=True)
        else:
            logger.warning(exc.message, **log_data)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """
        Handle Pydantic/FastAPI request validation errors.
        
        These occur when request data doesn't match the expected schema.
        The response includes detailed field-level error information.
        """
        request_id = get_request_id()

        # Transform Pydantic errors into a cleaner format
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        logger.warning(
            "Request validation failed",
            request_id=request_id,
            path=request.url.path,
            error_count=len(errors),
        )

        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": errors},
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(
        request: Request,
        exc: PydanticValidationError,
    ) -> JSONResponse:
        """
        Handle Pydantic v2 validation errors from response models.
        
        This catches validation errors that occur during response serialization.
        """
        request_id = get_request_id()

        logger.error(
            "Response validation failed",
            request_id=request_id,
            path=request.url.path,
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                    "details": {},
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """
        Handle Starlette HTTP exceptions.
        
        These include 404 Not Found, 405 Method Not Allowed, etc.
        """
        request_id = get_request_id()

        logger.warning(
            f"HTTP {exc.status_code}: {exc.detail}",
            request_id=request_id,
            path=request.url.path,
            status_code=exc.status_code,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                    "details": {},
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Catch-all handler for unexpected exceptions.
        
        SECURITY: Never expose internal error details in production.
        The full exception is logged but only a generic message is returned.
        """
        request_id = get_request_id()

        # Always log the full exception for debugging
        logger.exception(
            "Unhandled exception",
            request_id=request_id,
            path=request.url.path,
            exception_type=type(exc).__name__,
        )

        # Return generic error message (no internal details exposed)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {},
                    "request_id": request_id,
                }
            },
        )
