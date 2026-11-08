"""
Health check endpoint.
"""

from fastapi import APIRouter
from backend.schemas.common import HealthResponse
from backend.services.system_service import get_health_status

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Backend health status")
async def health_check():
    """
    Returns application health, version, environment, and database connectivity.
    """
    return get_health_status()
