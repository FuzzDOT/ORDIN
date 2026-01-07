"""
FastAPI Application Factory
===========================
Main application entry point with production-ready configuration.

This module creates and configures the FastAPI application with:
- Middleware stack (request ID, logging)
- Exception handlers
- API routers
- CORS configuration
- Lifespan management (startup/shutdown)

The application follows the factory pattern to support testing
and multiple configuration scenarios.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health_router
from app.config import get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.middleware import RequestIdMiddleware, RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown events.
    
    Startup:
    - Initialize logging
    - Validate configuration (fail-fast)
    - Connect to external services (future)
    
    Shutdown:
    - Close database connections (future)
    - Flush logs
    - Clean up resources
    """
    # --- STARTUP ---
    settings = get_settings()
    
    # Initialize structured logging
    setup_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )
    
    logger = get_logger(__name__)
    
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.env.value,
        host=settings.host,
        port=settings.port,
    )
    
    # Validate configuration (fail-fast on misconfiguration)
    # Any validation errors will raise before the yield, preventing startup
    if settings.is_production:
        logger.info("Running in production mode with strict settings")
    
    yield  # Application runs here
    
    # --- SHUTDOWN ---
    logger.info("Application shutting down gracefully")
    # Add cleanup logic here (close DB connections, flush queues, etc.)


def create_application() -> FastAPI:
    """
    Application factory function.
    
    Creates and configures the FastAPI application with all middleware,
    exception handlers, and routers.
    
    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    # Create FastAPI instance with OpenAPI configuration
    app = FastAPI(
        title="ORDIN API",
        description="AI-driven task and scheduling system backend",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,  # Disable Swagger in production
        redoc_url="/redoc" if settings.debug else None,  # Disable ReDoc in production
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # Middleware Stack (order matters: first added = outermost)
    # -------------------------------------------------------------------------
    
    # CORS middleware (must be before other middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Request logging middleware (logs after request completes)
    app.add_middleware(RequestLoggingMiddleware)

    # Request ID middleware (must be before logging to ensure ID is available)
    app.add_middleware(RequestIdMiddleware)

    # -------------------------------------------------------------------------
    # Exception Handlers
    # -------------------------------------------------------------------------
    register_exception_handlers(app)

    # -------------------------------------------------------------------------
    # API Routers
    # -------------------------------------------------------------------------
    
    # Health check endpoints (no prefix, root-level)
    app.include_router(health_router)

    # API v1 routes (placeholder for future business logic)
    # app.include_router(api_v1_router, prefix="/api/v1")

    return app


# Create the application instance
app = create_application()
