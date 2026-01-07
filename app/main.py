"""
FastAPI Application Factory
===========================
Main application entry point with production-ready configuration.

This module creates and configures the FastAPI application with:
- Middleware stack (request ID, logging, authentication)
- Exception handlers
- API routers
- CORS configuration
- Lifespan management (startup/shutdown)
- Firebase Admin SDK initialization
- Firestore client initialization

The application follows the factory pattern to support testing
and multiple configuration scenarios.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health_router
from app.api.v1 import router as api_v1_router
from app.auth.firebase import FirebaseInitializationError, initialize_firebase
from app.auth.middleware import FirebaseAuthMiddleware
from app.config import get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db import FirestoreError, initialize_firestore
from app.middleware import RequestIdMiddleware, RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown events.
    
    Startup:
    - Initialize logging
    - Validate configuration (fail-fast)
    - Initialize Firebase Admin SDK
    
    Shutdown:
    - Close database connections (future)
    - Flush logs
    - Clean up resources
    """
    # --- STARTUP ---
    settings = get_settings()
    
    # Initialize structured logging first (so we can log startup events)
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
        firebase_auth_enabled=settings.firebase_auth_enabled,
    )
    
    # Initialize Firebase Admin SDK if authentication is enabled
    if settings.firebase_auth_enabled:
        try:
            initialize_firebase(
                project_id=settings.firebase_project_id,
                credentials_path=settings.firebase_credentials_path,
                emulator_host=settings.firebase_auth_emulator_host,
            )
            logger.info("Firebase Admin SDK initialized successfully")
            
            # Initialize Firestore client (reuses Firebase Admin credentials)
            try:
                initialize_firestore(
                    project_id=settings.firebase_project_id,
                    emulator_host=settings.firestore_emulator_host,
                )
                logger.info("Firestore client initialized successfully")
            except FirestoreError as e:
                if settings.is_production:
                    logger.critical(
                        "Firestore initialization failed in production",
                        error=str(e),
                    )
                    raise
                else:
                    logger.warning(
                        "Firestore initialization failed - data storage will not work",
                        error=str(e),
                    )
                    
        except FirebaseInitializationError as e:
            # In production, Firebase initialization failure is fatal
            if settings.is_production:
                logger.critical(
                    "Firebase initialization failed in production",
                    error=str(e),
                )
                raise
            else:
                # In dev/staging, log warning and continue (auth will fail gracefully)
                logger.warning(
                    "Firebase initialization failed - auth will not work",
                    error=str(e),
                )
    else:
        logger.info("Firebase authentication is disabled")
    
    # Validate configuration (fail-fast on misconfiguration)
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

    # Firebase authentication middleware (verifies tokens, sets user context)
    # Protected paths can be configured here, or use route-level dependencies
    app.add_middleware(
        FirebaseAuthMiddleware,
        protected_paths={"/api/v1"},  # Add path prefixes that require auth
        auth_enabled=settings.firebase_auth_enabled,
    )

    # Request ID middleware (must be before auth to ensure ID is available for logging)
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

    # API v1 routes (authenticated endpoints)
    app.include_router(api_v1_router)

    return app


# Create the application instance
app = create_application()
