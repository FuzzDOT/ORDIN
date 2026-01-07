# API package
# Contains all API route definitions organized by domain.

from app.api.health import router as health_router

__all__ = ["health_router"]
