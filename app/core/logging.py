"""
Structured Logging Infrastructure
=================================
Production-grade JSON logging with automatic context enrichment.

Features:
- Structured JSON output for log aggregation (ELK, Datadog, etc.)
- Automatic request_id injection from context
- Automatic user_id injection for authenticated requests
- Configurable log levels per environment
- Human-readable format option for local development
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from structlog.types import Processor

from app.core.context import get_request_id, get_user_id


def add_request_id(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Structlog processor to inject request_id from context.
    
    This processor runs for every log call, automatically adding
    the request_id if one is set in the current context.
    """
    request_id = get_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def add_user_id(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Structlog processor to inject user_id from context.
    
    This processor runs for every log call, automatically adding
    the user_id if one is set (i.e., for authenticated requests).
    """
    user_id = get_user_id()
    if user_id:
        event_dict["user_id"] = user_id
    return event_dict


def add_timestamp(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Add ISO 8601 timestamp in UTC to all log entries.
    
    Using UTC ensures consistency across distributed systems
    and simplifies log correlation.
    """
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_service_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Add service metadata to all log entries.
    
    This helps identify log sources in multi-service environments.
    """
    # Import here to avoid circular dependency
    from app.config import get_settings

    settings = get_settings()
    event_dict["service"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.env.value
    return event_dict


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format - 'json' for production, 'text' for development
    
    This function should be called once at application startup.
    It configures both structlog and the standard library logging.
    """
    # Common processors for all log entries
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_request_id,
        add_user_id,
        add_service_context,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        # Production: JSON output for log aggregation systems
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Development: Human-readable colored output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Add exception formatting before rendering
    shared_processors.append(structlog.processors.format_exc_info)
    shared_processors.append(renderer)

    # Configure structlog
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Suppress noisy third-party loggers in production
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name, typically __name__ of the calling module.
    
    Returns:
        A bound structlog logger with automatic context enrichment.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", user_id=123)
    """
    return structlog.get_logger(name)
