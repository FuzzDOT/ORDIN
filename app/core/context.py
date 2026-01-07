"""
Request Context Management
==========================
Thread-safe and async-safe context variables for request-scoped data.
Uses Python's contextvars for proper async context propagation.

The request_id context variable is set by middleware and accessible
throughout the request lifecycle without explicit parameter passing.
"""

from contextvars import ContextVar
from typing import Optional

# Request ID context variable - propagated across async boundaries
# This enables correlation of all log entries within a single request
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """
    Retrieve the current request ID from context.
    
    Returns:
        The request ID if set, None otherwise.
    """
    return request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """
    Set the request ID in the current context.
    
    Args:
        request_id: Unique identifier for the current request.
    """
    request_id_ctx.set(request_id)
