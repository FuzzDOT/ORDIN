"""
Request Logging Middleware
==========================
Structured logging for all HTTP requests with latency tracking.

Produces JSON log entries containing:
- request_id: Correlation ID for distributed tracing
- method: HTTP method (GET, POST, etc.)
- path: Request path
- status_code: HTTP response status
- latency_ms: Request duration in milliseconds
- client_ip: Client IP address (respects X-Forwarded-For)
"""

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import get_request_id
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs structured request/response data.
    
    Logs are emitted after request completion with timing information.
    The log level is determined by the response status code:
    - 2xx/3xx: INFO
    - 4xx: WARNING
    - 5xx: ERROR
    
    This middleware should be placed after RequestIdMiddleware to ensure
    the request_id is available for logging.
    """

    # Paths to exclude from logging (health checks are high-frequency)
    EXCLUDED_PATHS: set[str] = {"/health", "/ready", "/metrics"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """Log request details with timing information."""
        # Skip logging for health check endpoints to reduce noise
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Capture request start time
        start_time = time.perf_counter()

        # Extract client IP (handle proxies)
        client_ip = self._get_client_ip(request)

        # Process the request
        response = await call_next(request)

        # Calculate latency
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Build structured log entry
        log_data = {
            "request_id": get_request_id(),
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) if request.query_params else None,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "client_ip": client_ip,
            "user_agent": request.headers.get("User-Agent"),
        }

        # Log at appropriate level based on status code
        self._log_request(response.status_code, log_data)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address, respecting X-Forwarded-For header.
        
        In production behind a load balancer, the real client IP is in
        X-Forwarded-For. The leftmost IP is the original client.
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()
        
        # Fall back to direct connection IP
        if request.client:
            return request.client.host
        return "unknown"

    def _log_request(self, status_code: int, log_data: dict) -> None:
        """Log the request at the appropriate level based on status code."""
        if status_code >= 500:
            logger.error("Request completed with server error", **log_data)
        elif status_code >= 400:
            logger.warning("Request completed with client error", **log_data)
        else:
            logger.info("Request completed", **log_data)
