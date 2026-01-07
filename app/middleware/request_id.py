"""
Request ID Middleware
=====================
Generates and propagates a unique request ID for every HTTP request.

The request ID enables end-to-end request tracing across services and logs.
It follows the X-Request-ID header convention, generating a new UUID if
no ID is provided by the client or upstream proxy.
"""

import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import set_request_id

# Standard header name for request ID propagation
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every request has a unique identifier.
    
    Behavior:
    1. Check for incoming X-Request-ID header (from client or upstream proxy)
    2. Generate a new UUID v4 if no ID is present
    3. Store the ID in async-safe context for logging
    4. Attach the ID to the response headers
    
    This enables distributed tracing when combined with upstream load
    balancers or API gateways that propagate request IDs.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """Process the request with ID injection."""
        # Extract existing request ID or generate a new one
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in context for access throughout the request lifecycle
        set_request_id(request_id)

        # Attach to request state for direct access in route handlers
        request.state.request_id = request_id

        # Process the request
        response = await call_next(request)

        # Include request ID in response for client-side correlation
        response.headers[REQUEST_ID_HEADER] = request_id

        return response
