"""
Health Check API Endpoints
==========================
Kubernetes-compatible health and readiness probes.

These endpoints are critical for container orchestration:
- /health (liveness): Is the process alive? If not, restart it.
- /ready (readiness): Can the process handle traffic? If not, stop sending traffic.

Both endpoints are excluded from request logging to reduce noise.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.responses import HealthResponse, ReadinessResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Kubernetes liveness check. Returns 200 if the application is running.",
)
async def health_check() -> HealthResponse:
    """
    Liveness probe endpoint.
    
    This endpoint should:
    - Return quickly (no external dependency checks)
    - Return 200 if the process is alive
    - Return 5xx only if the process is in a broken state
    
    Kubernetes will restart the container if this fails.
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Kubernetes readiness check. Returns 200 if the application can handle traffic.",
    responses={
        503: {
            "description": "Service not ready",
            "content": {
                "application/json": {
                    "example": {
                        "status": "not_ready",
                        "checks": {"config": False},
                        "version": "0.1.0",
                        "environment": "prod",
                    }
                }
            },
        }
    },
)
async def readiness_check(response: Response) -> ReadinessResponse:
    """
    Readiness probe endpoint.
    
    This endpoint checks if the application is ready to handle traffic:
    - Configuration is valid
    - (Future: Database connection is available)
    - (Future: External services are reachable)
    
    If not ready, Kubernetes removes the pod from service endpoints.
    """
    settings = get_settings()
    
    # Run dependency checks
    checks: dict[str, bool] = {}
    
    # Check 1: Configuration is loaded and valid
    try:
        checks["config"] = settings is not None and settings.app_name is not None
    except Exception:
        checks["config"] = False

    # Add more checks here as dependencies are added:
    # checks["database"] = await check_database_connection()
    # checks["redis"] = await check_redis_connection()
    # checks["external_api"] = await check_external_api()

    # Determine overall readiness
    is_ready = all(checks.values())
    
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("Readiness check failed", checks=checks)

    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
        version=settings.app_version,
        environment=settings.env.value,
        timestamp=datetime.now(timezone.utc),
    )
