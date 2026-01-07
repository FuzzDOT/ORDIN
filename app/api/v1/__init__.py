"""
API v1 Package
==============
Versioned API endpoints for the ORDIN backend.

All endpoints in this package require authentication via Firebase
and use the /api/v1 prefix.
"""

from fastapi import APIRouter

from app.api.v1.users import router as users_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.calendar import router as calendar_router

# Main v1 router that aggregates all sub-routers
router = APIRouter(prefix="/api/v1")

# Include sub-routers
router.include_router(users_router)
router.include_router(tasks_router)
router.include_router(calendar_router)

__all__ = ["router"]
