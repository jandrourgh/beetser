"""API router registry."""

from fastapi import APIRouter

from . import activity, auth, jobs, library, origins, settings, system

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(origins.router)
api_router.include_router(jobs.router)
api_router.include_router(library.router)
api_router.include_router(settings.router)
api_router.include_router(activity.router)
api_router.include_router(system.router)

__all__ = ["api_router"]
