"""
System information and environment status endpoint.
"""

from fastapi import APIRouter
from backend.schemas.common import SystemInfoResponse
from backend.services.system_service import get_system_info

router = APIRouter(tags=["System"])


@router.get("/system/info", response_model=SystemInfoResponse, summary="Host and platform metrics")
async def system_info():
    """
    Returns platform diagnostics, CPU, RAM, disk usage, offline mode status,
    and detected VAULT ecosystem tools (CuratorKIT, SafeTune, AuditKIT).
    """
    return get_system_info()
