"""
API Response Schemas
====================
Pydantic v2 models for standardized API responses.

These models ensure consistent response structure across all endpoints
and provide automatic OpenAPI documentation generation.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """
    Structured error detail for validation and field-level errors.
    """

    field: str = Field(description="Field path that caused the error")
    message: str = Field(description="Human-readable error message")
    type: str = Field(description="Error type identifier")


class ErrorResponse(BaseModel):
    """
    Standardized error response format.
    
    All API errors follow this structure for consistent client handling.
    """

    code: str = Field(
        description="Machine-readable error code (e.g., 'VALIDATION_ERROR')"
    )
    message: str = Field(description="Human-readable error description")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context about the error",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request correlation ID for debugging",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": [{"field": "email", "message": "Invalid email format"}]},
                    "request_id": "550e8400-e29b-41d4-a716-446655440000",
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """
    Response model for the /health (liveness) endpoint.
    
    Kubernetes uses this to determine if the container is alive.
    A failing health check triggers container restart.
    """

    status: str = Field(
        default="healthy",
        description="Health status indicator",
    )
    version: str = Field(description="Application version")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Current server timestamp (UTC)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "version": "0.1.0",
                    "timestamp": "2026-01-06T12:00:00Z",
                }
            ]
        }
    }


class ReadinessResponse(BaseModel):
    """
    Response model for the /ready (readiness) endpoint.
    
    Kubernetes uses this to determine if the pod can receive traffic.
    A failing readiness check removes the pod from load balancer rotation.
    """

    status: str = Field(description="Readiness status: 'ready' or 'not_ready'")
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description="Individual dependency check results",
    )
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Current server timestamp (UTC)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "ready",
                    "checks": {"config": True},
                    "version": "0.1.0",
                    "environment": "prod",
                    "timestamp": "2026-01-06T12:00:00Z",
                }
            ]
        }
    }


class BaseResponse(BaseModel):
    """
    Base response wrapper for successful API responses.
    
    Provides consistent structure for all successful responses
    with optional metadata support.
    """

    success: bool = Field(default=True, description="Operation success indicator")
    data: Optional[Any] = Field(default=None, description="Response payload")
    meta: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional response metadata (pagination, etc.)",
    )
