"""
Application Configuration
=========================
Centralized configuration using Pydantic v2 BaseSettings.
Supports environment-specific overrides (dev, staging, prod) with fail-fast validation.

Environment variables are loaded from:
1. System environment variables (highest priority)
2. .env file (for local development)

The application will fail to start if required configuration is missing or invalid.
"""

from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment enumeration for type-safe environment handling."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    """
    Application settings with environment-based configuration.
    
    All settings can be overridden via environment variables.
    Prefix: ORDIN_ (e.g., ORDIN_ENV=prod, ORDIN_DEBUG=false)
    
    Fail-fast behavior: Invalid configuration raises ValidationError at startup,
    preventing deployment of misconfigured instances.
    """

    model_config = SettingsConfigDict(
        env_prefix="ORDIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars for forward compatibility
    )

    # -------------------------------------------------------------------------
    # Core Application Settings
    # -------------------------------------------------------------------------
    app_name: str = Field(
        default="ordin-backend",
        description="Application name used in logs and metrics",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Semantic version for API versioning and health checks",
    )
    env: Environment = Field(
        default=Environment.DEV,
        description="Deployment environment (dev, staging, prod)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode. Must be False in production.",
    )

    # -------------------------------------------------------------------------
    # Server Configuration
    # -------------------------------------------------------------------------
    host: str = Field(
        default="0.0.0.0",
        description="Server bind address",
    )
    port: Annotated[int, Field(ge=1, le=65535)] = Field(
        default=8000,
        description="Server port",
    )
    workers: Annotated[int, Field(ge=1, le=32)] = Field(
        default=1,
        description="Number of Uvicorn workers. Use 1 for K8s (scale via replicas).",
    )

    # -------------------------------------------------------------------------
    # Logging Configuration
    # -------------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_format: str = Field(
        default="json",
        description="Log format: 'json' for production, 'text' for local dev",
    )

    # -------------------------------------------------------------------------
    # Request Processing
    # -------------------------------------------------------------------------
    request_timeout_seconds: Annotated[int, Field(ge=1, le=300)] = Field(
        default=30,
        description="Default request timeout in seconds",
    )
    max_request_size_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        description="Maximum request body size in bytes",
    )

    # -------------------------------------------------------------------------
    # Health Check Configuration
    # -------------------------------------------------------------------------
    health_check_path: str = Field(
        default="/health",
        description="Liveness probe endpoint path",
    )
    ready_check_path: str = Field(
        default="/ready",
        description="Readiness probe endpoint path",
    )

    # -------------------------------------------------------------------------
    # CORS Configuration (prepared for frontend integration)
    # -------------------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug_in_prod(cls, v: bool, info) -> bool:
        """Enforce debug=False in production environment."""
        # Access other fields via info.data
        env = info.data.get("env")
        if env == Environment.PROD and v is True:
            raise ValueError("Debug mode must be disabled in production")
        return v

    @field_validator("log_level", mode="after")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = v.upper()
        if normalized not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return normalized

    @field_validator("log_format", mode="after")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Ensure log format is valid."""
        valid_formats = {"json", "text"}
        normalized = v.lower()
        if normalized not in valid_formats:
            raise ValueError(f"Invalid log format: {v}. Must be one of {valid_formats}")
        return normalized

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env == Environment.PROD

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.env == Environment.DEV


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton factory for application settings.
    
    Uses LRU cache to ensure settings are loaded once and reused.
    This is the primary entry point for accessing configuration.
    
    Raises:
        ValidationError: If required settings are missing or invalid.
    """
    return Settings()
